from fastapi import APIRouter, Depends

from .. import models, schemas
from ..auth import current_user, is_admin

router = APIRouter(prefix="/api/me", tags=["me"])


@router.get("", response_model=schemas.Me)
def get_me(user: models.User = Depends(current_user)):
    return schemas.Me(id=user.id, email=user.email, is_admin=is_admin(user))
