from typing import List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from shared_python import cloudflare

from .. import config, crud, models, notify, schemas
from ..auth import current_user, is_admin, require_admin
from ..deps import get_db
from ..signin import can_sign_in, valid_email

# The administrator's side of inviting people: the requests waiting for a
# decision, and approving or declining them. (Asking is on a trip's own routes,
# /api/trips/{id}/invites.)
router = APIRouter(prefix="/api/admin/invites", tags=["invites"])
# Asking for someone to be let into the app itself (any signed-in person).
app_router = APIRouter(prefix="/api/app-invites", tags=["invites"])


def approve(db: Session, invite: models.Invite, background: BackgroundTasks) -> models.Invite:
    """Let the person through Cloudflare's login gate, then put them on the
    trip, then tell them by email. The Cloudflare step goes first: if it fails
    the request stays waiting, so nobody is recorded as let in who still can't
    sign in."""
    try:
        cloudflare.allow_email(invite.email)
    except cloudflare.NotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except cloudflare.SeatCapReached as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except cloudflare.CloudflareError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    granted = crud.grant_invite(db, invite)
    if granted.for_app:
        # Nothing was shared: they are simply let in, and told how to sign in.
        background.add_task(notify.tell_let_in, granted.email, granted.invited_by.email)
        return granted
    # Plain values, not the ORM objects: this runs after the response, when the
    # request's session is closed.
    background.add_task(
        notify.tell_given_access,
        granted.email,
        granted.invited_by.email,
        granted.trip.location if granted.trip is not None else "a trip",
        granted.trip_id,
        granted.role,
        True,
    )
    return granted


def _waiting_invite(db: Session, invite_id: int) -> models.Invite:
    invite = crud.get_invite(db, invite_id)
    if invite is None:
        raise HTTPException(status_code=404, detail="Invite not found")
    if invite.status != models.INVITE_PENDING:
        raise HTTPException(status_code=409, detail=f"That request was already {invite.status}")
    return invite


@router.get("", response_model=List[schemas.AdminInvite])
def list_waiting(admin: models.User = Depends(require_admin), db: Session = Depends(get_db)):
    return crud.get_pending_invites(db)


@router.get("/declined", response_model=List[schemas.AdminInvite])
def list_declined(admin: models.User = Depends(require_admin), db: Session = Depends(get_db)):
    """Requests that were declined, so the administrator can change their mind."""
    return crud.get_declined_invites(db)


@router.post("/{invite_id}/reinstate")
def reinstate_invite(invite_id: int, admin: models.User = Depends(require_admin), db: Session = Depends(get_db)):
    """Allow a declined person to be asked for again: the declined request is removed,
    so anyone may ask once more (and the asker gets that invite back)."""
    invite = crud.get_invite(db, invite_id)
    if invite is None:
        raise HTTPException(status_code=404, detail="Invite not found")
    if invite.status != models.INVITE_DECLINED:
        raise HTTPException(status_code=409, detail="Only a declined request can be allowed again")
    crud.cancel_invite(db, invite)
    return {"ok": True}


@router.post("/{invite_id}/approve", response_model=schemas.AdminInvite)
def approve_invite(
    invite_id: int,
    background: BackgroundTasks,
    admin: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    invite = approve(db, _waiting_invite(db, invite_id), background)
    invite.invited_by_email = invite.invited_by.email
    invite.trip_name = invite.trip.location if invite.trip is not None else None
    return invite


@router.post("/{invite_id}/decline", response_model=schemas.AdminInvite)
def decline_invite(invite_id: int, admin: models.User = Depends(require_admin), db: Session = Depends(get_db)):
    invite = crud.decline_invite(db, _waiting_invite(db, invite_id))
    invite.invited_by_email = invite.invited_by.email
    invite.trip_name = invite.trip.location if invite.trip is not None else None
    return invite


# --- asking for someone to be let into the app itself --------------------------------------------


@app_router.get("", response_model=List[schemas.AppInvite])
def my_app_invites(user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    """The requests this person made to let people into the app, in any state."""
    return crud.get_my_app_invites(db, user)


@app_router.post("", response_model=schemas.AppInvite)
def ask_app_invite(
    body: schemas.AppInviteCreate,
    background: BackgroundTasks,
    user: models.User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Ask for someone with no account to be let into the app (not onto one trip).
    The administrator is told and decides; an administrator's own request is
    approved straight away. Counts against the same allowance as the invites
    to a trip."""
    email = valid_email(body.email)
    if can_sign_in(db, email):
        raise HTTPException(status_code=409, detail=f"{email} can already sign in, so there's nothing to request.")
    invite, problem = crud.create_invite(db, None, user, email, "view", for_app=True)
    if problem == "duplicate":
        earlier = crud.get_app_invite(db, email)
        if earlier is not None and earlier.status == models.INVITE_DECLINED:
            detail = f"A request for {email} was declined. Only the administrator can let them in now."
        else:
            detail = f"A request for {email} is already waiting for the administrator to approve."
        raise HTTPException(status_code=409, detail=detail)
    if problem == "none_left":
        raise HTTPException(
            status_code=403,
            detail=f"You've used all {config.INVITES_PER_USER} of your invites. Only the administrator can raise the limit.",
        )
    if is_admin(user):
        return approve(db, invite, background)
    background.add_task(notify.invite_requested, user.email, invite.email)
    return invite


@app_router.delete("/{invite_id}")
def withdraw_app_invite(invite_id: int, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    """Withdraw one of your own requests that's still waiting (this gives the invite back)."""
    invite = crud.get_invite(db, invite_id)
    if invite is None or not invite.for_app or invite.invited_by_id != user.id:
        raise HTTPException(status_code=404, detail="Invite not found")
    if invite.status != models.INVITE_PENDING:
        raise HTTPException(status_code=409, detail="Only a request that's still waiting can be withdrawn")
    crud.cancel_invite(db, invite)
    return {"ok": True}
