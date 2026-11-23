"""What the dashboard's stats pages ask this app: for each account, when they were last here and how much they keep in it, as numbers
and dates only (never a trip's name, a place or a cost). Administrators only."""
from fastapi import APIRouter, Depends
from shared_python import usage
from sqlalchemy.orm import Session

from .. import models
from ..auth import require_admin
from ..deps import get_db

router = APIRouter(prefix="/api/admin/stats", tags=["stats"], dependencies=[Depends(require_admin)])


@router.get("")
def stats(db: Session = Depends(get_db)):
    return usage.build(db, models.User, {
        "trips": usage.per_user(db, models.Trip.owner_id, models.Trip.created_at),
        "activities": usage.per_user(db, models.Activity.owner_id, models.Activity.created_at),
        "places": usage.per_user(db, models.Place.owner_id, models.Place.created_at),
        "trips shared with them": usage.per_user(db, models.TripMember.user_id, None, models.TripMember.role != models.ROLE_OWNER),
    })
