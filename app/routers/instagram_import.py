from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import ai_extraction, crud, schemas
from ..deps import get_db

router = APIRouter(prefix="/api/instagram-import", tags=["instagram-import"])


@router.post("", response_model=schemas.InstagramImportResult)
def import_from_instagram(request: schemas.InstagramImportRequest, db: Session = Depends(get_db)):
    """Classifies each post's caption with Claude and creates one Activity
    per real place it finds - a seed generator, not a finisher (see
    ai_extraction.py's docstring). Every created activity is unscheduled
    and notes which post it came from, so a bad extraction is easy to find
    and fix or delete on trip.html afterward."""
    if request.trip_id is not None and crud.get_trip(db, request.trip_id) is None:
        raise HTTPException(status_code=404, detail="Trip not found")

    posts_skipped = 0
    created_names = []

    for post in request.posts:
        try:
            extracted = ai_extraction.extract_activities(post.caption)
        except RuntimeError as err:
            # ANTHROPIC_API_KEY unset - fail the whole import loudly rather
            # than silently skipping every post one at a time.
            raise HTTPException(status_code=503, detail=str(err))

        if not extracted:
            posts_skipped += 1
            continue

        for activity in extracted:
            notes = activity.notes.strip()
            source_note = f"Imported from Instagram: {post.permalink}"
            full_notes = f"{notes}\n\n{source_note}" if notes else source_note
            crud.create_activity(
                db,
                schemas.ActivityCreate(
                    name=activity.name,
                    notes=full_notes,
                    trip_id=request.trip_id,
                ),
            )
            created_names.append(activity.name)

    return schemas.InstagramImportResult(
        posts_processed=len(request.posts),
        posts_skipped=posts_skipped,
        activities_created=len(created_names),
        created_names=created_names,
    )
