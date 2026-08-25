from typing import List, Optional

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
