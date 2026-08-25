from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import crud, distance, schemas
from ..deps import get_db
from ..scraping.service import scrape_activity

router = APIRouter(prefix="/api/activities", tags=["activities"])

# Google's own per-request cap is 25 origins x 25 destinations (625
# elements) on a standard key - this app's activity counts are nowhere
# near that, so a much smaller cap here is just a sanity guard against a
# fat-fingered "select everything twice" request, not a real constraint.
MAX_DISTANCE_MATRIX_ELEMENTS = 100


@router.get("", response_model=List[schemas.Activity])
def list_activities(
    trip_id: Optional[int] = None,
    unassociated: bool = False,
    db: Session = Depends(get_db),
):
    return crud.get_activities(db, trip_id=trip_id, unassociated=unassociated)


@router.post("", response_model=schemas.Activity)
def create_activity(activity: schemas.ActivityCreate, db: Session = Depends(get_db)):
    if activity.trip_id is not None and crud.get_trip(db, activity.trip_id) is None:
        raise HTTPException(status_code=400, detail="trip_id does not refer to an existing trip")
    return crud.create_activity(db, activity)


@router.get("/cities", response_model=List[str])
def list_cities(db: Session = Depends(get_db)):
    # Must stay registered before /{activity_id} below - Starlette matches
    # routes by path structure only (no type-checking at match time, unlike
    # FastAPI's later parameter validation), so "cities" would otherwise
    # match {activity_id} first and 422 trying to parse it as an int.
    return crud.get_all_cities(db)


@router.post("/distance-matrix", response_model=schemas.DistanceMatrixResponse)
def distance_matrix(payload: schemas.DistanceMatrixRequest, db: Session = Depends(get_db)):
    """Real walking/driving distance+duration between every origin and
    every destination given - one shared endpoint behind every distance
    surface in the app (a full pairwise matrix among a set of candidates,
    many candidates against one fixed anchor, or one activity against
    everything else - see app/distance.py's module docstring). Self-pairs
    (an activity compared to itself) are silently dropped rather than
    sent to Google - meaningless, and would just burn part of the element
    cap for nothing.
    """
    if len(payload.origin_ids) * len(payload.destination_ids) > MAX_DISTANCE_MATRIX_ELEMENTS:
        raise HTTPException(status_code=400, detail=f"Too many activities selected - max {MAX_DISTANCE_MATRIX_ELEMENTS} origin x destination pairs per request")

    all_ids = set(payload.origin_ids) | set(payload.destination_ids)
    activities_by_id: Dict[int, object] = {}
    for activity_id in all_ids:
        activity = crud.get_activity(db, activity_id)
        if activity is None:
            raise HTTPException(status_code=404, detail=f"Activity {activity_id} not found")
        activities_by_id[activity_id] = activity

    pairs: List[schemas.DistancePair] = []
    origin_valid_ids: List[int] = []
    for origin_id in payload.origin_ids:
        if distance.address_query_for(activities_by_id[origin_id]) is None:
            for destination_id in payload.destination_ids:
                if destination_id == origin_id:
                    continue
                pairs.append(schemas.DistancePair(origin_id=origin_id, destination_id=destination_id, skipped_reason="no address"))
        else:
            origin_valid_ids.append(origin_id)

    destination_valid_ids: List[int] = []
    for destination_id in payload.destination_ids:
        if distance.address_query_for(activities_by_id[destination_id]) is None:
            for origin_id in origin_valid_ids:
                if origin_id == destination_id:
                    continue
                pairs.append(schemas.DistancePair(origin_id=origin_id, destination_id=destination_id, skipped_reason="no address"))
        else:
            destination_valid_ids.append(destination_id)

    # Every (origin, destination) actually worth asking about - both have a
    # usable address, and it's not an activity compared to itself.
    valid_pairs = {(o, d) for o in origin_valid_ids for d in destination_valid_ids if o != d}

    if valid_pairs:
        # Cached first (see app/models.py's ActivityDistance and
        # crud.get_cached_distances/cache_distance) - a repeat comparison
        # of the same activities, or a new comparison that reuses some of
        # the same ones, costs nothing beyond a DB lookup for whatever's
        # already been priced out before. force_refresh (the manual
        # "re-check this" escape hatch) skips straight past it, treating
        # every valid pair as missing so it's re-asked and re-cached.
        cached = {} if payload.force_refresh else crud.get_cached_distances(db, origin_valid_ids, destination_valid_ids, payload.mode)
        missing_pairs = valid_pairs - set(cached.keys())

        for pair in valid_pairs & set(cached.keys()):
            row = cached[pair]
            pairs.append(
                schemas.DistancePair(
                    origin_id=pair[0],
                    destination_id=pair[1],
                    distance_meters=row.distance_meters,
                    distance_text=row.distance_text,
                    duration_seconds=row.duration_seconds,
                    duration_text=row.duration_text,
                )
            )

        if missing_pairs:
            # A rectangular sub-grid across every origin/destination that
            # has at least one missing pair - simpler than fetching the
            # exact sparse set, at the cost of occasionally re-fetching (and
            # re-caching, harmlessly) a cell that was already cached. Given
            # this app's activity counts, that's a fine trade for the
            # simplicity - not worth hand-rolling sparse-grid batching for.
            missing_origin_ids = sorted({p[0] for p in missing_pairs})
            missing_destination_ids = sorted({p[1] for p in missing_pairs})
            origin_queries = [distance.address_query_for(activities_by_id[oid]) for oid in missing_origin_ids]
            destination_queries = [distance.address_query_for(activities_by_id[did]) for did in missing_destination_ids]
            try:
                matrix = distance.get_distance_matrix(origin_queries, destination_queries, mode=payload.mode)
            except RuntimeError as e:
                raise HTTPException(status_code=503, detail=str(e))
            for i, origin_id in enumerate(missing_origin_ids):
                for j, destination_id in enumerate(missing_destination_ids):
                    if origin_id == destination_id:
                        continue
                    result = matrix[i][j]
                    was_requested = (origin_id, destination_id) in missing_pairs
                    if result is None:
                        if was_requested:
                            pairs.append(schemas.DistancePair(origin_id=origin_id, destination_id=destination_id, skipped_reason="no route found"))
                        continue
                    # Cached even if this particular cell wasn't explicitly
                    # requested (a side effect of the rectangular sub-grid
                    # above) - free future cache hits, no reason not to.
                    crud.cache_distance(db, origin_id, destination_id, payload.mode, result)
                    if was_requested:
                        pairs.append(
                            schemas.DistancePair(
                                origin_id=origin_id,
                                destination_id=destination_id,
                                distance_meters=result.distance_meters,
                                distance_text=result.distance_text,
                                duration_seconds=result.duration_seconds,
                                duration_text=result.duration_text,
                            )
                        )

    return schemas.DistanceMatrixResponse(pairs=pairs)


@router.get("/{activity_id}", response_model=schemas.Activity)
def get_activity(activity_id: int, db: Session = Depends(get_db)):
    activity = crud.get_activity(db, activity_id)
    if activity is None:
        raise HTTPException(status_code=404, detail="Activity not found")
    return activity


@router.patch("/{activity_id}", response_model=schemas.Activity)
def update_activity(activity_id: int, updates: schemas.ActivityUpdate, db: Session = Depends(get_db)):
    activity = crud.update_activity(db, activity_id, updates)
    if activity is None:
        raise HTTPException(status_code=404, detail="Activity not found")
    return activity


@router.delete("/{activity_id}")
def delete_activity(activity_id: int, db: Session = Depends(get_db)):
    ok = crud.delete_activity(db, activity_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Activity not found")
    return {"ok": True}


@router.post("/{activity_id}/scrape", response_model=schemas.Activity)
def trigger_scrape(activity_id: int, db: Session = Depends(get_db)):
    activity = crud.get_activity(db, activity_id)
    if activity is None:
        raise HTTPException(status_code=404, detail="Activity not found")
    if not activity.url:
        raise HTTPException(status_code=400, detail="Activity has no URL to scrape")
    return scrape_activity(db, activity_id, activity.url)
