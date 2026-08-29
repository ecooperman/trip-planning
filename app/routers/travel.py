from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import crud, schemas
from ..deps import get_db

router = APIRouter(prefix="/api/travel", tags=["travel"])


@router.post("", response_model=schemas.TravelSegment)
def create_travel_segment(segment: schemas.TravelSegmentCreate, db: Session = Depends(get_db)):
    db_segment = crud.create_travel_segment(db, segment)
    if db_segment is None:
        raise HTTPException(status_code=400, detail="trip_id does not refer to an existing trip")
    return db_segment


@router.get("/{travel_segment_id}", response_model=schemas.TravelSegment)
def get_travel_segment(travel_segment_id: int, db: Session = Depends(get_db)):
    segment = crud.get_travel_segment(db, travel_segment_id)
    if segment is None:
        raise HTTPException(status_code=404, detail="Travel segment not found")
    return segment


@router.patch("/{travel_segment_id}", response_model=schemas.TravelSegment)
def update_travel_segment(travel_segment_id: int, updates: schemas.TravelSegmentUpdate, db: Session = Depends(get_db)):
    segment = crud.update_travel_segment(db, travel_segment_id, updates)
    if segment is None:
        raise HTTPException(status_code=404, detail="Travel segment not found")
    return segment


@router.delete("/{travel_segment_id}")
def delete_travel_segment(travel_segment_id: int, db: Session = Depends(get_db)):
    ok = crud.delete_travel_segment(db, travel_segment_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Travel segment not found")
    return {"ok": True}
