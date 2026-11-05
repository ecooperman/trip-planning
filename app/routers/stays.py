from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import crud, models, schemas
from ..access import OnTrip, check_role, stay_access
from ..auth import current_user
from ..deps import get_db
from ..scraping.service import scrape_stay

# A stay's access is whatever the caller has on its trip.
router = APIRouter(prefix="/api/stays", tags=["stays"])


@router.post("", response_model=schemas.Stay)
def create_stay(stay: schemas.StayCreate, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    member = crud.get_membership(db, user.id, stay.trip_id)
    if member is None:
        raise HTTPException(status_code=400, detail="trip_id does not refer to an existing trip")
    check_role(member.role, models.ROLE_EDIT)
    return crud.create_stay(db, stay)


@router.get("/{stay_id}", response_model=schemas.Stay)
def get_stay(access: OnTrip = Depends(stay_access(models.ROLE_VIEW))):
    return access.item


@router.patch("/{stay_id}", response_model=schemas.Stay)
def update_stay(
    stay_id: int,
    updates: schemas.StayUpdate,
    access: OnTrip = Depends(stay_access(models.ROLE_EDIT)),
    db: Session = Depends(get_db),
):
    return crud.update_stay(db, stay_id, updates)


@router.delete("/{stay_id}")
def delete_stay(stay_id: int, access: OnTrip = Depends(stay_access(models.ROLE_EDIT)), db: Session = Depends(get_db)):
    crud.delete_stay(db, stay_id)
    return {"ok": True}


@router.post("/{stay_id}/scrape", response_model=schemas.Stay)
def trigger_scrape(stay_id: int, access: OnTrip = Depends(stay_access(models.ROLE_EDIT)), db: Session = Depends(get_db)):
    stay = access.item
    if not stay.url:
        raise HTTPException(status_code=400, detail="Stay has no URL to scrape")
    return scrape_stay(db, stay_id, stay.url)
