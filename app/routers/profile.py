"""The signed-in person's view of their API keys. The keys themselves are saved, replaced and removed once on the dashboard (Your profile ->
Your API keys, dashboard/app/keys.py) and used by every app; this app only says which services the caller can use here (their own key, or an
administrator's house key). Nothing here can see or change a key."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import apikeys, models, schemas
from ..auth import current_user
from ..deps import get_db

router = APIRouter(prefix="/api/profile", tags=["profile"])


@router.get("/api-keys", response_model=schemas.ApiKeyList)
def list_api_keys(user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    return schemas.ApiKeyList(keys=[schemas.ApiKeyStatus(**row) for row in apikeys.status(db, user)])
