"""Candidate-stay bulk import (URLs -> AI-seeded Stay rows) and the
per-trip comparison grid on compare.html - criteria (the columns), their
per-stay verdicts (the cells), and a one-shot read of everything the grid
needs. Kept in its own router, self-contained, the same way distance.py
and dog_care.py are - trips.py / stays.py stay untouched.
"""

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from .. import crud, models, schemas, stay_extraction
from ..deps import get_db
from ..scraping.page_text import fetch_page_text
from ..scraping.service import _resolve as resolve_scrape

router = APIRouter(prefix="/api", tags=["stay-compare"])

# Screenshots of a listing - always small in practice; a sanity guard only,
# same reasoning as dog_care's attachment cap.
MAX_SCREENSHOT_BYTES = 10 * 1024 * 1024
_ANTHROPIC_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}


def _domain(url: str) -> str:
    from urllib.parse import urlparse

    return (urlparse(url).netloc or url).replace("www.", "")


def _stay_dates_for(trip: models.Trip):
    """A candidate stay needs non-null dates. Use the trip's if it has
    them; otherwise a placeholder 1-week window from today for the user to
    fix - never block the import on it."""
    start = trip.start_date or datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    end = trip.end_date or (start + timedelta(days=7))
    return start, end


@router.post("/trips/{trip_id}/stays/import", response_model=schemas.StayImportResult)
def import_stays_from_urls(
    trip_id: int, request: schemas.StayImportRequest, db: Session = Depends(get_db)
):
    """For each URL: fetch a link preview + the page's body text, have
    Claude pull out price/room/amenity facts, and create one candidate
    (un-booked, needs_review) Stay. A URL that can't be read still gets a
    stub stay with the link, so nothing pasted is silently lost.

    A URL that already has a candidate stay on this trip (see
    crud.find_stay_by_url) is refreshed in place instead - re-pasting the
    same batch (to pick up the fetcher's improvements, or just to recheck
    prices) updates existing rows rather than piling up duplicates.
    """
    trip = crud.get_trip(db, trip_id)
    if trip is None:
        raise HTTPException(status_code=404, detail="Trip not found")

    urls = []
    seen = set()
    for raw in request.urls:
        u = (raw or "").strip()
        if u and u not in seen:
            seen.add(u)
            urls.append(u)
    if not urls:
        raise HTTPException(status_code=400, detail="No URLs given")

    start_date, end_date = _stay_dates_for(trip)
    items: list[schemas.StayImportItem] = []
    created = 0
    updated = 0

    for url in urls:
        existing = crud.find_stay_by_url(db, trip_id, url)

        # Link-preview (OG) data - reuses the existing scraper registry.
        status, scraped, err = resolve_scrape(url)
        og_title = scraped.title if scraped else None
        og_description = scraped.description if scraped else None
        og_image = scraped.image_url if scraped else None

        page_text = fetch_page_text(url)

        try:
            extracted = stay_extraction.extract_from_text(url, og_title, og_description, page_text)
        except RuntimeError as api_err:
            # No API key - a config problem, not a per-URL one. Stop here
            # rather than stubbing out every remaining URL identically.
            raise HTTPException(status_code=503, detail=str(api_err))
        except Exception as read_err:  # noqa: BLE001 - a bad read of one URL mustn't sink the batch
            if existing:
                db_stay = crud.update_imported_stay(
                    db, existing.id,
                    name=(og_title or None), fields={"description": og_description},
                    scrape_status=status, scraped_title=og_title, scraped_description=og_description,
                    scraped_image_url=og_image, scrape_error=err,
                )
                updated += 1
                action = "updated"
                detail = f"Couldn't re-read this one ({read_err}); left its existing details alone."
            else:
                db_stay = crud.create_imported_stay(
                    db, trip_id,
                    name=(og_title or f"Stay from {_domain(url)}"),
                    url=url, start_date=start_date, end_date=end_date,
                    fields={"description": og_description},
                    scraped_image_url=og_image,
                )
                created += 1
                action = "created"
                detail = f"Couldn't auto-read this one ({read_err}); added a stub to fill in."
            items.append(schemas.StayImportItem(
                url=url, ok=False, stay_id=db_stay.id, name=db_stay.name, action=action, detail=detail,
            ))
            continue

        fields = extracted.worksheet_fields()
        low_confidence = (extracted.confidence == "low") or not page_text
        name = (extracted.name or og_title or f"Stay from {_domain(url)}").strip()

        if existing:
            db_stay = crud.update_imported_stay(
                db, existing.id,
                name=name, fields=fields,
                scrape_status=status, scraped_title=og_title, scraped_description=og_description,
                scraped_image_url=og_image, scrape_error=err,
            )
            updated += 1
            action = "updated"
        else:
            db_stay = crud.create_imported_stay(
                db, trip_id,
                name=name, url=url, start_date=start_date, end_date=end_date,
                fields=fields, scraped_image_url=og_image,
            )
            created += 1
            action = "created"

        detail = None
        if low_confidence:
            detail = "The page was hard to read automatically - double-check the details."
        items.append(schemas.StayImportItem(
            url=url, ok=not low_confidence, stay_id=db_stay.id, name=db_stay.name, action=action, detail=detail,
        ))

    return schemas.StayImportResult(created=created, updated=updated, items=items)


@router.post("/stays/{stay_id}/extract-screenshot", response_model=schemas.Stay)
async def extract_stay_from_screenshot(
    stay_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)
):
    """Re-read a stay's details from a screenshot of its listing - the
    reliable fallback when the URL importer hit a bot wall. Patches only
    the fields the model can see; re-flags the stay for review."""
    if crud.get_stay(db, stay_id) is None:
        raise HTTPException(status_code=404, detail="Stay not found")
    data = await file.read()
    if len(data) > MAX_SCREENSHOT_BYTES:
        raise HTTPException(status_code=400, detail=f"Image too large - max {MAX_SCREENSHOT_BYTES // (1024 * 1024)}MB")
    media_type = (file.content_type or "").lower()
    if media_type not in _ANTHROPIC_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="Upload a JPEG, PNG, GIF, or WebP image")
    try:
        extracted = stay_extraction.extract_from_image(data, media_type)
    except RuntimeError as err:
        raise HTTPException(status_code=503, detail=str(err))
    updated = crud.apply_stay_extraction(db, stay_id, extracted.worksheet_fields())
    if updated is None:
        raise HTTPException(status_code=404, detail="Stay not found")
    return updated


# --- comparison criteria (the grid's columns) -----------------------------


@router.get("/trips/{trip_id}/stay-criteria", response_model=list[schemas.StayCriterion])
def list_stay_criteria(trip_id: int, db: Session = Depends(get_db)):
    if crud.get_trip(db, trip_id) is None:
        raise HTTPException(status_code=404, detail="Trip not found")
    return crud.get_stay_criteria(db, trip_id)


@router.post("/trips/{trip_id}/stay-criteria", response_model=schemas.StayCriterion)
def create_stay_criterion(trip_id: int, data: schemas.StayCriterionCreate, db: Session = Depends(get_db)):
    criterion = crud.create_stay_criterion(db, trip_id, data)
    if criterion is None:
        raise HTTPException(status_code=404, detail="Trip not found")
    return criterion


@router.patch("/stay-criteria/{criterion_id}", response_model=schemas.StayCriterion)
def update_stay_criterion(criterion_id: int, updates: schemas.StayCriterionUpdate, db: Session = Depends(get_db)):
    criterion = crud.update_stay_criterion(db, criterion_id, updates)
    if criterion is None:
        raise HTTPException(status_code=404, detail="Criterion not found")
    return criterion


@router.delete("/stay-criteria/{criterion_id}")
def delete_stay_criterion(criterion_id: int, db: Session = Depends(get_db)):
    if not crud.delete_stay_criterion(db, criterion_id):
        raise HTTPException(status_code=404, detail="Criterion not found")
    return {"ok": True}


@router.put("/stays/{stay_id}/verdicts/{criterion_id}", response_model=schemas.StayCriterionVerdict)
def set_verdict(stay_id: int, criterion_id: int, body: schemas.CriterionVerdictSet, db: Session = Depends(get_db)):
    row = crud.set_criterion_verdict(db, stay_id, criterion_id, body.verdict, body.note)
    if row is None:
        raise HTTPException(status_code=404, detail="Stay or criterion not found for this trip")
    return row


@router.get("/trips/{trip_id}/stay-comparison", response_model=schemas.StayComparison)
def get_stay_comparison(trip_id: int, db: Session = Depends(get_db)):
    data = crud.get_stay_comparison(db, trip_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Trip not found")
    return data
