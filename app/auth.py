"""Who is making this request.

There are no passwords or sign-up forms: every request has already been
through Cloudflare Access, which attaches the signed-in person's email.
shared_python.auth verifies it (and refuses everything in production if that
isn't configured); here it becomes this app's own User row - which exists only if the
administrator enabled that person in this app. Other apps on this machine (finances, social-planning) have no
signed-in person and call in with a shared X-Service-Token instead.
"""
import hmac
import logging

from fastapi import Depends, HTTPException, Request
from shared_python import auth as cloudflare_access
from sqlalchemy.orm import Session

from . import config, crud, models
from .deps import get_db

log = logging.getLogger(__name__)

SERVICE_HEADER = "x-service-token"


def request_email(request: Request) -> str:
    """The verified email of whoever is asking (see shared_python/auth.py)."""
    return cloudflare_access.request_email(request, config.DEV_USER_EMAIL)


NO_ACCESS = {
    "none": "You haven't been given access to Trips. Ask the person who told you about it, or the administrator, to invite you.",
    "removed": "Your access to Trips has been removed. Ask the administrator if you think that's a mistake.",
}


def signed_in_email(request: Request) -> str:
    """The signed-in person's normalized email (401 if there isn't one)."""
    email = crud.normalize_email(request_email(request))
    if "@" not in email:
        raise HTTPException(status_code=401, detail="Not signed in")
    return email


def current_user(request: Request, db: Session = Depends(get_db)) -> models.User:
    """Whoever is asking, who must also have been enabled in this app: getting
    through Cloudflare's login gate (shared with other apps) is not enough."""
    user, problem = crud.user_for_request(db, signed_in_email(request))
    if user is None:
        raise HTTPException(status_code=403, detail=NO_ACCESS[problem])
    return user


def is_admin(user: models.User) -> bool:
    return user.email in config.ADMIN_EMAILS


def require_admin(user: models.User = Depends(current_user)) -> models.User:
    """For the features that are the app owner's alone (dog care, the link to
    social-planning)."""
    if not is_admin(user):
        raise HTTPException(status_code=403, detail="Only the app's administrator can do that")
    return user


def _service_user(db: Session) -> models.User:
    email = config.SERVICE_USER_EMAIL or (sorted(config.ADMIN_EMAILS)[0] if config.ADMIN_EMAILS else None)
    if not email:
        raise HTTPException(status_code=503, detail="No service user is configured (set ADMIN_EMAILS)")
    user = crud.service_user(db, email)
    if user is None:
        raise HTTPException(status_code=403, detail="The service user's access has been removed")
    return user


def user_or_service(request: Request, db: Session = Depends(get_db)) -> models.User:
    """For the few endpoints another app on this machine calls directly: a
    valid X-Service-Token makes the request that of the service user (the
    administrator); otherwise it must be a signed-in person as usual. A wrong
    token is refused outright - never quietly treated as "no token"."""
    supplied = request.headers.get(SERVICE_HEADER)
    if supplied is not None:
        if not config.SERVICE_TOKEN or not hmac.compare_digest(supplied.encode(), config.SERVICE_TOKEN.encode()):
            raise HTTPException(status_code=401, detail="Invalid service token")
        return _service_user(db)
    return current_user(request, db)


def admin_or_service(request: Request, db: Session = Depends(get_db)) -> models.User:
    """user_or_service, then the administrator only - for what talks to the
    social-planning app on the administrator's behalf."""
    user = user_or_service(request, db)
    if not is_admin(user):
        raise HTTPException(status_code=403, detail="Only the app's administrator can do that")
    return user
