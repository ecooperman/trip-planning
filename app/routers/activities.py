from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import crud, models, schemas
from ..access import ActivityAccess, activity_access, check_role
from ..auth import current_user
from ..deps import get_db
from ..scraping.service import scrape_activity

router = APIRouter(prefix="/api/activities", tags=["activities"])


def _check_library_refs(db: Session, owner_id: int, place_id: Optional[int], category_ids) -> None:
    """A place or category on an activity must come from the same person's
    library as the activity itself - never someone else's."""
    if place_id is not None and not crud.place_owned(db, owner_id, place_id):
        raise HTTPException(status_code=404, detail="Place not found")
    if not crud.categories_owned(db, owner_id, category_ids):
        raise HTTPException(status_code=404, detail="Category not found")


@router.get("", response_model=List[schemas.Activity])
def list_activities(
    trip_id: Optional[int] = None,
    unassociated: bool = False,
    user: models.User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Your own activities - or, with trip_id, everything on that trip (yours
    or shared with you)."""
    if trip_id is not None and crud.get_membership(db, user.id, trip_id) is None:
        raise HTTPException(status_code=404, detail="Trip not found")
    return crud.get_activities(db, user.id, trip_id=trip_id, unassociated=unassociated)


@router.post("", response_model=schemas.Activity)
def create_activity(activity: schemas.ActivityCreate, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    # An activity added to a trip belongs to the trip's owner, even when an
    # editor adds it (see models.Activity.owner_id).
    owner_id = user.id
    if activity.trip_id is not None:
        member = crud.get_membership(db, user.id, activity.trip_id)
        if member is None:
            raise HTTPException(status_code=400, detail="trip_id does not refer to an existing trip")
        check_role(member.role, models.ROLE_EDIT)
        owner_id = member.trip.owner_id
    _check_library_refs(db, owner_id, activity.place_id, activity.category_ids)
    return crud.create_activity(db, owner_id, activity)


@router.get("/cities", response_model=List[str])
def list_cities(user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    # Must stay registered before /{activity_id} below - Starlette matches
    # routes by path structure only (no type-checking at match time, unlike
    # FastAPI's later parameter validation), so "cities" would otherwise
    # match {activity_id} first and 422 trying to parse it as an int.
    return crud.get_all_cities(db, user.id)


@router.get("/{activity_id}", response_model=schemas.Activity)
def get_activity(access: ActivityAccess = Depends(activity_access(models.ROLE_VIEW))):
    return access.activity


@router.patch("/{activity_id}", response_model=schemas.Activity)
def update_activity(
    activity_id: int,
    updates: schemas.ActivityUpdate,
    access: ActivityAccess = Depends(activity_access(models.ROLE_EDIT)),
    db: Session = Depends(get_db),
):
    _check_library_refs(db, access.activity.owner_id, updates.place_id, updates.category_ids)
    return crud.update_activity(db, activity_id, updates)


@router.get("/{activity_id}/distances", response_model=List[schemas.ActivityDistanceEntry])
def get_activity_distances(
    activity_id: int,
    access: ActivityAccess = Depends(activity_access(models.ROLE_VIEW)),
    user: models.User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Every distance already calculated involving this activity - against
    another activity, or a stay (see Compare distances, which lets you
    pick either as an origin/destination) - reads straight from the cache
    (LocationDistance), never calls Google itself. Shown on the activity's
    own card so a comparison you've already run stays visible without
    having to re-run it or remember which page you calculated it from."""
    outbound, inbound = crud.get_location_distance_rows(db, "activity", activity_id)
    entries: Dict[tuple, schemas.ActivityDistanceEntry] = {}

    def _can_see(kind: str, other) -> bool:
        if kind == "activity":
            return crud.activity_role(db, user.id, other) is not None
        return crud.get_membership(db, user.id, other.trip_id) is not None

    def add_row(row, direction: str, other_kind: str, other_id: int):
        key = (other_kind, other_id, direction)
        entry = entries.get(key)
        if entry is None:
            other = crud.get_activity(db, other_id) if other_kind == "activity" else crud.get_stay(db, other_id)
            if other is not None and not _can_see(other_kind, other):
                return  # a cached pair with something that's no longer yours to see
            entry = schemas.ActivityDistanceEntry(
                other_kind=other_kind,
                other_id=other_id,
                other_name=other.name if other else f"Deleted {other_kind}",
                # A stay has no city of its own (see models.Stay) - nothing
                # meaningful to show here for one.
                other_city=other.city if other and other_kind == "activity" else None,
                direction=direction,
            )
            entries[key] = entry
        mode_info = schemas.DistanceModeInfo(distance_text=row.distance_text, duration_text=row.duration_text)
        setattr(entry, row.mode, mode_info)

    for row in outbound:
        add_row(row, "to", row.destination_kind, row.destination_id)
    for row in inbound:
        add_row(row, "from", row.origin_kind, row.origin_id)

    return list(entries.values())


@router.delete("/{activity_id}")
def delete_activity(
    activity_id: int, access: ActivityAccess = Depends(activity_access(models.ROLE_EDIT)), db: Session = Depends(get_db)
):
    crud.delete_activity(db, activity_id)
    return {"ok": True}


@router.post("/{activity_id}/scrape", response_model=schemas.Activity)
def trigger_scrape(
    activity_id: int, access: ActivityAccess = Depends(activity_access(models.ROLE_EDIT)), db: Session = Depends(get_db)
):
    activity = access.activity
    if not activity.url:
        raise HTTPException(status_code=400, detail="Activity has no URL to scrape")
    return scrape_activity(db, activity_id, activity.url)


@router.post("/{activity_id}/promote-to-place", response_model=schemas.Activity)
def promote_to_place(
    activity_id: int,
    access: ActivityAccess = Depends(activity_access(models.ROLE_OWNER)),
    db: Session = Depends(get_db),
):
    """Turns this activity's own name/address/etc. into a new, reusable
    Place, links the activity to it, and clears those columns here - see
    crud.promote_activity_to_place. 400s if there's nothing to promote
    (already place-linked, or has no name of its own to begin with)."""
    activity = access.activity
    if activity.place_id is not None:
        raise HTTPException(status_code=400, detail="This activity is already linked to a place")
    if not activity.own_name:
        raise HTTPException(status_code=400, detail="This activity has no name of its own to turn into a place")
    return crud.promote_activity_to_place(db, activity_id)
