from typing import List

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from .. import crud, schemas
from ..deps import get_db
from ..scraping.service import scrape_place

router = APIRouter(prefix="/api/places", tags=["places"])

# Same reasoning as dog_care.py's MAX_ATTACHMENT_BYTES - a sanity guard,
# not a real constraint. Photos run larger than the invoice/instructions
# PDFs that guard was sized for (a modern phone photo can be several MB),
# hence the bigger cap here.
MAX_PHOTO_BYTES = 20 * 1024 * 1024


@router.get("", response_model=List[schemas.Place])
def list_places(db: Session = Depends(get_db)):
    return crud.get_places(db)


@router.post("", response_model=schemas.Place)
def create_place(place: schemas.PlaceCreate, db: Session = Depends(get_db)):
    return crud.create_place(db, place)


@router.get("/{place_id}", response_model=schemas.Place)
def get_place(place_id: int, db: Session = Depends(get_db)):
    place = crud.get_place(db, place_id)
    if place is None:
        raise HTTPException(status_code=404, detail="Place not found")
    return place


@router.patch("/{place_id}", response_model=schemas.Place)
def update_place(place_id: int, updates: schemas.PlaceUpdate, db: Session = Depends(get_db)):
    place = crud.update_place(db, place_id, updates)
    if place is None:
        raise HTTPException(status_code=404, detail="Place not found")
    return place


@router.delete("/{place_id}")
def delete_place(place_id: int, db: Session = Depends(get_db)):
    result = crud.delete_place(db, place_id)
    if result == "not_found":
        raise HTTPException(status_code=404, detail="Place not found")
    if result == "in_use":
        raise HTTPException(status_code=409, detail="This place is still linked to one or more activities - unlink or delete those first")
    return {"ok": True}


@router.post("/{place_id}/scrape", response_model=schemas.Place)
def trigger_scrape(place_id: int, db: Session = Depends(get_db)):
    place = crud.get_place(db, place_id)
    if place is None:
        raise HTTPException(status_code=404, detail="Place not found")
    if not place.url:
        raise HTTPException(status_code=400, detail="Place has no URL to scrape")
    return scrape_place(db, place_id, place.url)


# --- photos (plain binary storage, no processing of contents at all) -------


@router.get("/{place_id}/photos", response_model=List[schemas.PlaceImage])
def list_place_photos(place_id: int, db: Session = Depends(get_db)):
    if crud.get_place(db, place_id) is None:
        raise HTTPException(status_code=404, detail="Place not found")
    return crud.get_place_images(db, place_id)


@router.post("/{place_id}/photos", response_model=schemas.PlaceImage)
async def upload_place_photo(place_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    data = await file.read()
    if len(data) > MAX_PHOTO_BYTES:
        raise HTTPException(status_code=400, detail=f"Photo too large - max {MAX_PHOTO_BYTES // (1024 * 1024)}MB")
    image = crud.add_place_image(db, place_id, file.filename or "photo", file.content_type or "application/octet-stream", data)
    if image is None:
        raise HTTPException(status_code=404, detail="Place not found")
    return image


@router.get("/{place_id}/photos/{photo_id}")
def download_place_photo(place_id: int, photo_id: int, db: Session = Depends(get_db)):
    # No Cache-Control override here - main.py's no_cache middleware forces
    # no-store on every response app-wide regardless, so a photo re-fetches
    # on every page load same as everything else in this app.
    image = crud.get_place_image(db, photo_id)
    if image is None or image.place_id != place_id:
        raise HTTPException(status_code=404, detail="Photo not found")
    return Response(content=image.data, media_type=image.content_type)


@router.delete("/{place_id}/photos/{photo_id}")
def delete_place_photo(place_id: int, photo_id: int, db: Session = Depends(get_db)):
    ok = crud.delete_place_image(db, place_id, photo_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Photo not found")
    return {"ok": True}
