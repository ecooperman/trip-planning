from typing import List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from shared_python import cloudflare

from .. import crud, models, notify, schemas
from ..auth import require_admin
from ..deps import get_db

# The administrator's side of inviting people: the requests waiting for a
# decision, and approving or declining them. (Asking is on a trip's own routes,
# /api/trips/{id}/invites.)
router = APIRouter(prefix="/api/admin/invites", tags=["invites"])


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
