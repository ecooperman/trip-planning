"""Checks both the invite routes and the share routes make about an email address."""
import re

from fastapi import HTTPException
from shared_python import cloudflare
from sqlalchemy.orm import Session

from . import config, crud, models

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def valid_email(raw: str) -> str:
    email = crud.normalize_email(raw)
    if not _EMAIL.match(email) or email == crud.LEGACY_OWNER_EMAIL:
        raise HTTPException(status_code=400, detail="That doesn't look like an email address")
    return email


def refuse_if_removed(db: Session, email: str) -> None:
    """Sharing with, or asking for, someone the administrator removed is refused
    with a reason: only the administrator can restore them (Users page)."""
    account = crud.get_account(db, email)
    if account is not None and account.status == models.USER_REMOVED:
        raise HTTPException(
            status_code=409,
            detail=f"{email}'s access to Trips was removed. Only the administrator can restore it.",
        )


def can_sign_in(db: Session, email: str) -> bool:
    """Whether this person can use the app right now: they have an active
    account here (an administrator let them in) and Cloudflare still lets them
    through the login gate. Having passed the gate for some other app doesn't
    count - the account is per app. With Cloudflare unconfigured (local
    development) the account is all there is to go on."""
    account = crud.get_account(db, email)
    if account is None or account.status != models.USER_ACTIVE:
        return False
    try:
        let_in = cloudflare.is_let_in(email, config.ADMIN_EMAILS)
    except cloudflare.CloudflareError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return True if let_in is None else let_in
