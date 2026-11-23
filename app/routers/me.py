from typing import List

from fastapi import APIRouter, Depends, Request
from shared_python import directory, oidc_login
from sqlalchemy.orm import Session

from .. import apikeys, crud, models, schemas
from ..auth import current_user, is_admin
from ..deps import get_db

router = APIRouter(prefix="/api/me", tags=["me"])


@router.get("", response_model=schemas.Me)
def get_me(request: Request, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    admin = is_admin(user)
    return schemas.Me(
        id=user.id,
        email=user.email,
        is_admin=admin,
        invites_left=crud.invites_left(db, user),
        pending_invites=crud.pending_invite_count(db) if admin else 0,
        can_use=apikeys.available(db, user),
        # Where Log out goes: None = Cloudflare Access (the page default); otherwise the shared sign-in's logout.
        logout_url=oidc_login.logout_url(request),
    )


@router.get("/people", response_model=List[dict])
def get_people(user: models.User = Depends(current_user)):
    """People to suggest in the sharing box, as {email, name}: everyone with an account in any of the apps (the name is the one an
    administrator saved, or ""), for an administrator only. An ordinary person gets nothing and types the whole address: suggestions would
    otherwise tell them who else uses the apps (shared_python.directory)."""
    if not is_admin(user):
        return []
    me = user.email.lower()
    return [person for person in directory.known_people() if person["email"] != me]
