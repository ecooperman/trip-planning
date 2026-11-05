from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from .. import crud, models, schemas
from ..access import OnTrip, dog_care_access
from ..auth import current_user, require_admin
from ..deps import get_db

# Dog care is the app owner's own business, not something shared: only an
# administrator who owns the trip ever reaches it (see access.dog_care_access).
router = APIRouter(prefix="/api/dog-care", tags=["dog-care"])

# A sanity guard, not a real constraint - these are invoice/instructions
# PDFs, always small in practice. Stored as a plain SQLite BLOB (see
# models.DogCareBooking) since this app's upload volume is tiny (a couple
# files a year); this just stops an accidental huge upload from bloating
# the DB file unexpectedly.
MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024

AttachmentKind = Literal["invoice", "instructions"]


@router.post("", response_model=schemas.DogCareBooking)
def create_dog_care_booking(
    booking: schemas.DogCareBookingCreate,
    user: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    member = crud.get_membership(db, user.id, booking.trip_id)
    if member is None or member.role != models.ROLE_OWNER:
        raise HTTPException(status_code=400, detail="trip_id does not refer to an existing trip")
    return crud.create_dog_care_booking(db, booking)


@router.get("/{booking_id}", response_model=schemas.DogCareBooking)
def get_dog_care_booking(access: OnTrip = Depends(dog_care_access())):
    return access.item


@router.patch("/{booking_id}", response_model=schemas.DogCareBooking)
def update_dog_care_booking(
    booking_id: int,
    updates: schemas.DogCareBookingUpdate,
    access: OnTrip = Depends(dog_care_access()),
    db: Session = Depends(get_db),
):
    return crud.update_dog_care_booking(db, booking_id, updates)


@router.delete("/{booking_id}")
def delete_dog_care_booking(booking_id: int, access: OnTrip = Depends(dog_care_access()), db: Session = Depends(get_db)):
    crud.delete_dog_care_booking(db, booking_id)
    return {"ok": True}


# --- attachments (invoice / instructions - plain binary storage, no
# parsing or processing of contents at all) --------------------------------


@router.post("/{booking_id}/attachments/{kind}", response_model=schemas.DogCareBooking)
async def upload_dog_care_attachment(
    booking_id: int,
    kind: AttachmentKind,
    file: UploadFile = File(...),
    access: OnTrip = Depends(dog_care_access()),
    db: Session = Depends(get_db),
):
    """Uploads/replaces one attachment - a re-upload overwrites whatever
    was there before, it doesn't keep history."""
    data = await file.read()
    if len(data) > MAX_ATTACHMENT_BYTES:
        raise HTTPException(status_code=400, detail=f"File too large - max {MAX_ATTACHMENT_BYTES // (1024 * 1024)}MB")
    return crud.set_dog_care_attachment(
        db, booking_id, kind, file.filename or kind, file.content_type or "application/octet-stream", data
    )


@router.get("/{booking_id}/attachments/{kind}")
def download_dog_care_attachment(
    booking_id: int, kind: AttachmentKind, access: OnTrip = Depends(dog_care_access())
):
    booking = access.item
    data = getattr(booking, f"{kind}_data")
    if data is None:
        raise HTTPException(status_code=404, detail=f"No {kind} attached")
    filename = getattr(booking, f"{kind}_filename") or kind
    content_type = getattr(booking, f"{kind}_content_type") or "application/octet-stream"
    return Response(
        content=data,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("/{booking_id}/attachments/{kind}", response_model=schemas.DogCareBooking)
def clear_dog_care_attachment(
    booking_id: int, kind: AttachmentKind, access: OnTrip = Depends(dog_care_access()), db: Session = Depends(get_db)
):
    return crud.clear_dog_care_attachment(db, booking_id, kind)
