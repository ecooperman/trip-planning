from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import crud, schemas
from ..deps import get_db

router = APIRouter(prefix="/api/trips", tags=["trips"])


@router.get("", response_model=List[schemas.Trip])
def list_trips(db: Session = Depends(get_db)):
    return crud.get_trips(db)


@router.post("", response_model=schemas.Trip)
def create_trip(trip: schemas.TripCreate, db: Session = Depends(get_db)):
    return crud.create_trip(db, trip)


@router.get("/{trip_id}", response_model=schemas.Trip)
def get_trip(trip_id: int, db: Session = Depends(get_db)):
    trip = crud.get_trip(db, trip_id)
    if trip is None:
        raise HTTPException(status_code=404, detail="Trip not found")
    return trip


@router.patch("/{trip_id}", response_model=schemas.Trip)
def update_trip(trip_id: int, updates: schemas.TripUpdate, db: Session = Depends(get_db)):
    trip = crud.update_trip(db, trip_id, updates)
    if trip is None:
        raise HTTPException(status_code=404, detail="Trip not found")
    return trip


@router.delete("/{trip_id}")
def delete_trip(trip_id: int, delete_activities: bool = False, db: Session = Depends(get_db)):
    """delete_activities=false (default) unlinks this trip's activities but
    keeps them around as unassociated; delete_activities=true deletes them
    too. Stays are never given a choice - they have no existence outside
    their trip, so they're always deleted along with it.
    """
    ok = crud.delete_trip(db, trip_id, delete_activities=delete_activities)
    if not ok:
        raise HTTPException(status_code=404, detail="Trip not found")
    return {"ok": True}


@router.get("/{trip_id}/activities", response_model=List[schemas.Activity])
def list_trip_activities(trip_id: int, db: Session = Depends(get_db)):
    if crud.get_trip(db, trip_id) is None:
        raise HTTPException(status_code=404, detail="Trip not found")
    return crud.get_activities(db, trip_id=trip_id)


@router.post("/{trip_id}/activities/{activity_id}", response_model=schemas.Activity)
def associate_activity(trip_id: int, activity_id: int, db: Session = Depends(get_db)):
    activity = crud.associate_activity(db, trip_id, activity_id)
    if activity is None:
        raise HTTPException(status_code=404, detail="Trip or activity not found")
    return activity


@router.delete("/{trip_id}/activities/{activity_id}")
def unlink_activity(trip_id: int, activity_id: int, db: Session = Depends(get_db)):
    ok = crud.unlink_activity(db, trip_id, activity_id)
    if not ok:
        raise HTTPException(status_code=404, detail="That activity is not linked to that trip")
    return {"ok": True}


@router.get("/{trip_id}/stays", response_model=List[schemas.Stay])
def list_trip_stays(trip_id: int, db: Session = Depends(get_db)):
    if crud.get_trip(db, trip_id) is None:
        raise HTTPException(status_code=404, detail="Trip not found")
    return crud.get_stays(db, trip_id)


@router.get("/{trip_id}/stay-coverage", response_model=schemas.StayCoverage)
def get_stay_coverage(trip_id: int, db: Session = Depends(get_db)):
    coverage = crud.get_trip_stay_coverage(db, trip_id)
    if coverage is None:
        raise HTTPException(status_code=404, detail="Trip not found")
    return coverage
