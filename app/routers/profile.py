"""The signed-in person's own settings: the API keys they bring for the paid
services (see app/apikeys.py). Everything here is about the caller alone; there
is no way to see or touch anyone else's, an administrator's included."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import apikeys, models, schemas
from ..auth import current_user
from ..deps import get_db

router = APIRouter(prefix="/api/profile", tags=["profile"])

Provider = Literal["anthropic", "google_maps", "jina"]


def _one(db: Session, user: models.User, provider: str) -> schemas.ApiKeyStatus:
    return next(schemas.ApiKeyStatus(**row) for row in apikeys.status(db, user) if row["provider"] == provider)


@router.get("/api-keys", response_model=schemas.ApiKeyList)
def list_api_keys(user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    return schemas.ApiKeyList(
        can_save=apikeys.storage_available(),
        keys=[schemas.ApiKeyStatus(**row) for row in apikeys.status(db, user)],
    )


@router.put("/api-keys/{provider}", response_model=schemas.ApiKeySaved)
def save_api_key(
    provider: Provider,
    body: schemas.ApiKeyIn,
    user: models.User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Check the key with the service, then store it encrypted. A key the
    service refuses isn't saved; one that couldn't be checked (the service was
    unreachable) is saved and reported as unverified."""
    if not apikeys.storage_available():
        raise HTTPException(status_code=503, detail="Saving keys isn't set up on the server yet - ask the administrator")
    try:
        key = apikeys.clean(body.key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    verified, why = apikeys.verify(provider, key)
    if verified is False:
        raise HTTPException(status_code=400, detail=why)
    apikeys.save(db, user, provider, key)
    note = "" if verified else f"Saved, but not verified: {why}."
    return schemas.ApiKeySaved(key=_one(db, user, provider), verified=verified, note=note)


@router.delete("/api-keys/{provider}", response_model=schemas.ApiKeyStatus)
def remove_api_key(provider: Provider, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    if not apikeys.remove(db, user, provider):
        raise HTTPException(status_code=404, detail="You haven't saved a key for that service")
    return _one(db, user, provider)
