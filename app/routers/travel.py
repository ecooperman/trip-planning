from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import crud, models, schemas
from ..access import OnTrip, check_role, travel_access
from ..auth import current_user
from ..deps import get_db

# A travel segment's access is whatever the caller has on its trip.
router = APIRouter(prefix="/api/travel", tags=["travel"])


@router.post("", response_model=schemas.TravelSegment)
def create_travel_segment(
    segment: schemas.TravelSegmentCreate, user: models.User = Depends(current_user), db: Session = Depends(get_db)
):
    member = crud.get_membership(db, user.id, segment.trip_id)
    if member is None:
        raise HTTPException(status_code=400, detail="trip_id does not refer to an existing trip")
    check_role(member.role, models.ROLE_EDIT)
    return crud.create_travel_segment(db, segment)


@router.get("/{travel_segment_id}", response_model=schemas.TravelSegment)
def get_travel_segment(access: OnTrip = Depends(travel_access(models.ROLE_VIEW))):
    return access.item


@router.patch("/{travel_segment_id}", response_model=schemas.TravelSegment)
def update_travel_segment(
    travel_segment_id: int,
    updates: schemas.TravelSegmentUpdate,
    access: OnTrip = Depends(travel_access(models.ROLE_EDIT)),
    db: Session = Depends(get_db),
):
    return crud.update_travel_segment(db, travel_segment_id, updates)


@router.delete("/{travel_segment_id}")
def delete_travel_segment(
    travel_segment_id: int, access: OnTrip = Depends(travel_access(models.ROLE_EDIT)), db: Session = Depends(get_db)
):
    crud.delete_travel_segment(db, travel_segment_id)
    return {"ok": True}
