"""Checks both the invite routes and the share routes make about an email address."""
import re

from fastapi import HTTPException
from shared_python import cloudflare
from sqlalchemy.orm import Session

from . import config, crud

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def valid_email(raw: str) -> str:
    email = crud.normalize_email(raw)
    if not _EMAIL.match(email) or email == crud.LEGACY_OWNER_EMAIL:
        raise HTTPException(status_code=400, detail="That doesn't look like an email address")
    return email


def can_sign_in(db: Session, email: str) -> bool:
    """Whether this person can get in right now. Cloudflare decides who passes
    the login gate, so it's asked rather than inferring it from an account
    existing - someone removed from the allowed group keeps their account but
    can't sign in. With Cloudflare unconfigured (local development) all there
    is to go on is whether they've signed in."""
    try:
        let_in = cloudflare.is_let_in(email, config.ADMIN_EMAILS)
    except cloudflare.CloudflareError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    if let_in is None:
        return crud.get_account(db, email) is not None
    return let_in
