from typing import Dict, List, Tuple

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import crud, distance, schemas
from ..deps import get_db

router = APIRouter(prefix="/api", tags=["distance"])

# Google's own per-request cap is 25 origins x 25 destinations (625
# elements) on a standard key - this app's activity/stay counts are
# nowhere near that, so a much smaller cap here is just a sanity guard
# against a fat-fingered "select everything twice" request, not a real
# constraint.
MAX_DISTANCE_MATRIX_ELEMENTS = 100

LocationRef = Tuple[str, int]  # (kind, id) - see schemas.LocationRef


def _get_location(db: Session, kind: str, location_id: int):
    if kind == "activity":
        return crud.get_activity(db, location_id)
    return crud.get_stay(db, location_id)


def _location_address_query(kind: str, obj):
    if kind == "activity":
        return distance.address_query_for(obj)
    return distance.stay_address_query_for(obj)


def _location_label(kind: str, obj) -> str:
    if kind == "activity":
        return f"{obj.name} — {obj.city}" if obj.city else obj.name
    # A stay has no city of its own worth appending (see
    # distance.stay_address_query_for) - "(Stay)" is what actually
    # distinguishes it from an activity of the same name in a picker or
    # results list.
    return f"{obj.name} (Stay)"


@router.post("/distance-matrix", response_model=schemas.DistanceMatrixResponse)
def distance_matrix(payload: schemas.DistanceMatrixRequest, db: Session = Depends(get_db)):
    """Real walking/driving distance+duration between every origin and
    every destination given - one shared endpoint behind every distance
    surface in the app (a full pairwise matrix among a set of candidates,
    many candidates against one fixed anchor, or one location against
    everything else - see app/distance.py's module docstring). An origin
    or destination can be an activity or a stay (a trip's lodging, usable
    as a fixed "home base" - see LocationRef). Self-pairs (a location
    compared to itself) are silently dropped rather than sent to Google -
    meaningless, and would just burn part of the element cap for nothing.
    """
    if len(payload.origins) * len(payload.destinations) > MAX_DISTANCE_MATRIX_ELEMENTS:
        raise HTTPException(status_code=400, detail=f"Too many locations selected - max {MAX_DISTANCE_MATRIX_ELEMENTS} origin x destination pairs per request")

    origin_refs: List[LocationRef] = [(ref.kind, ref.id) for ref in payload.origins]
    destination_refs: List[LocationRef] = [(ref.kind, ref.id) for ref in payload.destinations]

    locations_by_ref: Dict[LocationRef, object] = {}
    for ref in set(origin_refs) | set(destination_refs):
        obj = _get_location(db, *ref)
        if obj is None:
            raise HTTPException(status_code=404, detail=f"{ref[0].capitalize()} {ref[1]} not found")
        locations_by_ref[ref] = obj

    def new_pair(o_ref: LocationRef, d_ref: LocationRef, **kwargs) -> schemas.DistancePair:
        return schemas.DistancePair(
            origin_kind=o_ref[0],
            origin_id=o_ref[1],
            origin_label=_location_label(o_ref[0], locations_by_ref[o_ref]),
            destination_kind=d_ref[0],
            destination_id=d_ref[1],
            destination_label=_location_label(d_ref[0], locations_by_ref[d_ref]),
            **kwargs,
        )

    pairs: List[schemas.DistancePair] = []
    origin_valid_refs: List[LocationRef] = []
    for o_ref in origin_refs:
        if _location_address_query(o_ref[0], locations_by_ref[o_ref]) is None:
            for d_ref in destination_refs:
                if d_ref == o_ref:
                    continue
                pairs.append(new_pair(o_ref, d_ref, skipped_reason="no address"))
        else:
            origin_valid_refs.append(o_ref)

    destination_valid_refs: List[LocationRef] = []
    for d_ref in destination_refs:
        if _location_address_query(d_ref[0], locations_by_ref[d_ref]) is None:
            for o_ref in origin_valid_refs:
                if o_ref == d_ref:
                    continue
                pairs.append(new_pair(o_ref, d_ref, skipped_reason="no address"))
        else:
            destination_valid_refs.append(d_ref)

    # Every (origin, destination) actually worth asking about - both have a
    # usable address, and it's not a location compared to itself.
    valid_pairs = {(o, d) for o in origin_valid_refs for d in destination_valid_refs if o != d}

    if valid_pairs:
        # Cached first (see app/models.py's LocationDistance and
        # crud.get_cached_distances/cache_distance) - a repeat comparison
        # of the same locations, or a new comparison that reuses some of
        # the same ones, costs nothing beyond a DB lookup for whatever's
        # already been priced out before. force_refresh (the manual
        # "re-check this" escape hatch) skips straight past it, treating
        # every valid pair as missing so it's re-asked and re-cached.
        cached = {} if payload.force_refresh else crud.get_cached_distances(db, origin_valid_refs, destination_valid_refs, payload.mode)
        missing_pairs = valid_pairs - set(cached.keys())

        for pair in valid_pairs & set(cached.keys()):
            o_ref, d_ref = pair
            row = cached[pair]
            pairs.append(
                new_pair(
                    o_ref,
                    d_ref,
                    distance_meters=row.distance_meters,
                    distance_text=row.distance_text,
                    duration_seconds=row.duration_seconds,
                    duration_text=row.duration_text,
                    from_cache=True,
                )
            )

        if missing_pairs:
            # A rectangular sub-grid across every origin/destination that
            # has at least one missing pair - simpler than fetching the
            # exact sparse set, at the cost of occasionally re-fetching (and
            # re-caching, harmlessly) a cell that was already cached. Given
            # this app's location counts, that's a fine trade for the
            # simplicity - not worth hand-rolling sparse-grid batching for.
            missing_origin_refs = sorted({p[0] for p in missing_pairs})
            missing_destination_refs = sorted({p[1] for p in missing_pairs})
            origin_queries = [_location_address_query(ref[0], locations_by_ref[ref]) for ref in missing_origin_refs]
            destination_queries = [_location_address_query(ref[0], locations_by_ref[ref]) for ref in missing_destination_refs]
            try:
                matrix = distance.get_distance_matrix(origin_queries, destination_queries, mode=payload.mode)
            except RuntimeError as e:
                raise HTTPException(status_code=503, detail=str(e))
            for i, o_ref in enumerate(missing_origin_refs):
                for j, d_ref in enumerate(missing_destination_refs):
                    if o_ref == d_ref:
                        continue
                    result = matrix[i][j]
                    was_requested = (o_ref, d_ref) in missing_pairs
                    if result is None:
                        if was_requested:
                            pairs.append(new_pair(o_ref, d_ref, skipped_reason="no route found"))
                        continue
                    # Cached even if this particular cell wasn't explicitly
                    # requested (a side effect of the rectangular sub-grid
                    # above) - free future cache hits, no reason not to.
                    crud.cache_distance(db, o_ref[0], o_ref[1], d_ref[0], d_ref[1], payload.mode, result)
                    if was_requested:
                        pairs.append(
                            new_pair(
                                o_ref,
                                d_ref,
                                distance_meters=result.distance_meters,
                                distance_text=result.distance_text,
                                duration_seconds=result.duration_seconds,
                                duration_text=result.duration_text,
                                from_cache=False,
                            )
                        )

    return schemas.DistanceMatrixResponse(pairs=pairs)
