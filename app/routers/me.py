from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import apikeys, crud, models, schemas
from ..auth import current_user, is_admin
from ..deps import get_db

router = APIRouter(prefix="/api/me", tags=["me"])


@router.get("", response_model=schemas.Me)
def get_me(user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    admin = is_admin(user)
    return schemas.Me(
        id=user.id,
        email=user.email,
        is_admin=admin,
        invites_left=crud.invites_left(db, user),
        pending_invites=crud.pending_invite_count(db) if admin else 0,
        can_use=apikeys.available(db, user),
    )


@router.get("/people", response_model=List[str])
def get_people(user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    """Addresses to suggest in the sharing box: only people this person has
    already shared with or asked for (see crud.known_people)."""
    return crud.known_people(db, user)
