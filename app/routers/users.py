from typing import List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import crud, models, notify, schemas
from ..auth import is_admin, require_admin
from ..deps import get_db
from ..signin import valid_email
from .invites import let_through_gate

# The administrator's list of everyone with an account in this app: who is
# enabled, who was removed, and adding, removing, restoring and deleting people.
# Access is per app: this decides who may use Trips, whatever Cloudflare's
# shared login gate lets through (and it never touches that gate - another
# app may still want the person).
router = APIRouter(prefix="/api/admin/users", tags=["users"])


def _overview_of(db: Session, user_id: int) -> schemas.AdminUser:
    return next(u for u in crud.get_users_overview(db) if u.id == user_id)


def _person(db: Session, user_id: int) -> models.User:
    user = crud.get_user(db, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="That person wasn't found")
    return user


@router.get("", response_model=List[schemas.AdminUser])
def list_users(admin: models.User = Depends(require_admin), db: Session = Depends(get_db)):
    return crud.get_users_overview(db)


@router.post("", response_model=schemas.AdminUser)
def add_user(
    body: schemas.UserAdd,
    background: BackgroundTasks,
    admin: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Let someone into the app without anyone having asked: they pass
    Cloudflare's login gate, get an active account, and are emailed how to
    sign in. Adding a removed person restores them."""
    email = valid_email(body.email)
    existing = crud.get_account(db, email)
    if existing is not None and existing.status == models.USER_ACTIVE:
        raise HTTPException(status_code=409, detail=f"{email} already has access.")
    let_through_gate(email)
    user = crud.enable_user(db, email)
    background.add_task(notify.tell_let_in, email, admin.email)
    return _overview_of(db, user.id)


@router.post("/{user_id}/revoke", response_model=schemas.AdminUser)
def revoke_user(user_id: int, admin: models.User = Depends(require_admin), db: Session = Depends(get_db)):
    """Take this person's access to the app away. Their trips and everything
    else stay exactly as they are, so restoring them puts it all back."""
    user = _person(db, user_id)
    if is_admin(user):
        raise HTTPException(status_code=400, detail="An administrator's access can't be removed")
    crud.set_user_status(db, user, models.USER_REMOVED)
    return _overview_of(db, user.id)


@router.post("/{user_id}/restore", response_model=schemas.AdminUser)
def restore_user(user_id: int, admin: models.User = Depends(require_admin), db: Session = Depends(get_db)):
    """Give a removed person their access (and everything they had) back."""
    user = _person(db, user_id)
    # Their place at Cloudflare's gate never changed, but make sure it is still there.
    let_through_gate(user.email)
    crud.set_user_status(db, user, models.USER_ACTIVE)
    return _overview_of(db, user.id)


@router.delete("/{user_id}")
def delete_user(user_id: int, admin: models.User = Depends(require_admin), db: Session = Depends(get_db)):
    """Permanently erase what this person owns (see crud.delete_user_data). Only
    for someone already removed, so it is always a second, deliberate step; the
    account itself stays, removed, so they can't walk back in with a new one."""
    user = _person(db, user_id)
    if is_admin(user):
        raise HTTPException(status_code=400, detail="An administrator's account can't be deleted")
    if user.status != models.USER_REMOVED:
        raise HTTPException(status_code=409, detail="Remove their access first - deleting is a separate, final step")
    crud.delete_user_data(db, user)
    return {"ok": True}
