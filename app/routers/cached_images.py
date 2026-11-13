from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from .. import models
from ..auth import current_user
from ..deps import get_db

router = APIRouter(prefix="/api/cached-images", tags=["cached-images"])


@router.get("/{image_id}")
def get_cached_image(image_id: int, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    """A picture kept from a scraped page (see app/imagecache.py). Anyone signed
    in to the app can load it, like the rest of /api."""
    image = db.get(models.CachedImage, image_id)
    if image is None:
        raise HTTPException(status_code=404, detail="Image not found")
    return Response(content=image.data, media_type=image.content_type, headers={"X-Content-Type-Options": "nosniff"})
