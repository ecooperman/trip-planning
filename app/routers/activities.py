from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import crud, schemas
from ..deps import get_db
from ..scraping.service import scrape_activity

router = APIRouter(prefix="/api/activities", tags=["activities"])


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


@router.get("/{activity_id}/distances", response_model=List[schemas.ActivityDistanceEntry])
def get_activity_distances(activity_id: int, db: Session = Depends(get_db)):
    """Every distance already calculated involving this activity - against
    another activity, or a stay (see Compare distances, which lets you
    pick either as an origin/destination) - reads straight from the cache
    (LocationDistance), never calls Google itself. Shown on the activity's
    own card so a comparison you've already run stays visible without
    having to re-run it or remember which page you calculated it from."""
    if crud.get_activity(db, activity_id) is None:
        raise HTTPException(status_code=404, detail="Activity not found")

    outbound, inbound = crud.get_location_distance_rows(db, "activity", activity_id)
    entries: Dict[tuple, schemas.ActivityDistanceEntry] = {}

    def add_row(row, direction: str, other_kind: str, other_id: int):
        key = (other_kind, other_id, direction)
        entry = entries.get(key)
        if entry is None:
            other = crud.get_activity(db, other_id) if other_kind == "activity" else crud.get_stay(db, other_id)
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
