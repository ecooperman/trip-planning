from typing import List

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from .. import crud, export, schemas
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


@router.post("/{trip_id}/fill-missing-cities")
def fill_missing_activity_cities(trip_id: int, db: Session = Depends(get_db)):
    """Sets city on every one of this trip's activities that doesn't have
    one yet, to the trip's own city - never overwrites an activity that
    already has its own city set (e.g. a day trip elsewhere). Re-runnable
    any time - safe to click again after adding more activities, it only
    ever touches whatever's still missing."""
    trip = crud.get_trip(db, trip_id)
    if trip is None:
        raise HTTPException(status_code=404, detail="Trip not found")
    if not trip.city:
        raise HTTPException(status_code=400, detail="This trip has no city set yet")
    updated = crud.fill_missing_activity_cities(db, trip_id, trip.city)
    return {"updated": updated}


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


@router.get("/{trip_id}/export.xlsx")
def export_trip_xlsx(trip_id: int, db: Session = Depends(get_db)):
    """A formatted, offline-friendly itinerary download - see app/export.py
    for the actual layout (matches the hand-maintained spreadsheet format
    Evan used before this app existed)."""
    trip = crud.get_trip(db, trip_id)
    if trip is None:
        raise HTTPException(status_code=404, detail="Trip not found")
    activities = crud.get_activities(db, trip_id=trip_id)
    stays = crud.get_stays(db, trip_id)
    workbook = export.build_trip_workbook(trip, activities, stays)
    buf = export.workbook_bytes(workbook)
    filename = export.safe_filename(trip.location)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
