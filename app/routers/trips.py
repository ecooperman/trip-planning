import re
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from .. import crud, export, models, schemas
from ..access import ActivityAccess, activity_access, check_role, trip_access
from ..auth import current_user, require_admin, user_or_service
from ..deps import get_db

router = APIRouter(prefix="/api/trips", tags=["trips"])

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@router.get("", response_model=List[schemas.Trip])
def list_trips(user: models.User = Depends(user_or_service), db: Session = Depends(get_db)):
    """The trips you can reach (yours, and ones shared with you). Also read by
    the plans app, with its service token."""
    return crud.get_trips(db, user.id)


@router.get("/cost-summary", response_model=List[schemas.TripCostSummary])
def trips_cost_summary(user: models.User = Depends(user_or_service), db: Session = Depends(get_db)):
    """Per non-archived trip you own, the summed cost of its non-archived
    activities and booked stays and travel segments. Read by the finances
    app to forecast trip spend, with its service token."""
    return crud.trip_cost_summary(db, user.id)


@router.post("", response_model=schemas.Trip)
def create_trip(trip: schemas.TripCreate, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    return crud.create_trip(db, user, trip)


@router.get("/{trip_id}", response_model=schemas.Trip)
def get_trip(member: models.TripMember = Depends(trip_access(models.ROLE_VIEW)), db: Session = Depends(get_db)):
    return crud.trip_view(db, member)


@router.patch("/{trip_id}", response_model=schemas.Trip)
def update_trip(
    trip_id: int,
    updates: schemas.TripUpdate,
    member: models.TripMember = Depends(trip_access(models.ROLE_EDIT)),
    db: Session = Depends(get_db),
):
    if "archived" in updates.model_fields_set:
        # Archiving also archives every activity on the trip - the owner's call.
        check_role(member.role, models.ROLE_OWNER)
    crud.update_trip(db, trip_id, updates)
    return crud.trip_view(db, crud.get_membership(db, member.user_id, trip_id))


@router.delete("/{trip_id}")
def delete_trip(
    trip_id: int,
    delete_activities: bool = False,
    member: models.TripMember = Depends(trip_access(models.ROLE_OWNER)),
    db: Session = Depends(get_db),
):
    """delete_activities=false (default) unlinks this trip's activities but
    keeps them around as unassociated; delete_activities=true deletes them
    too. Stays are never given a choice - they have no existence outside
    their trip, so they're always deleted along with it. Deleting a trip
    removes it for everyone it's shared with.
    """
    crud.delete_trip(db, trip_id, delete_activities=delete_activities)
    return {"ok": True}


# --- sharing ---


def _member_out(member: models.TripMember) -> schemas.Member:
    return schemas.Member(user_id=member.user_id, email=member.user.email, role=member.role)


@router.get("/{trip_id}/members", response_model=List[schemas.Member])
def list_members(
    trip_id: int, member: models.TripMember = Depends(trip_access(models.ROLE_OWNER)), db: Session = Depends(get_db)
):
    return [_member_out(m) for m in crud.get_members(db, trip_id)]


@router.post("/{trip_id}/members", response_model=schemas.Member)
def add_member(
    trip_id: int,
    body: schemas.MemberAdd,
    member: models.TripMember = Depends(trip_access(models.ROLE_OWNER)),
    db: Session = Depends(get_db),
):
    email = crud.normalize_email(body.email)
    if not _EMAIL.match(email):
        raise HTTPException(status_code=400, detail="That doesn't look like an email address")
    added = crud.add_member(db, trip_id, email, body.role)
    if added is None:
        raise HTTPException(status_code=409, detail="That person already has access to this trip")
    return _member_out(crud.get_member(db, trip_id, added.user_id))


@router.patch("/{trip_id}/members/{user_id}", response_model=schemas.Member)
def update_member(
    trip_id: int,
    user_id: int,
    body: schemas.MemberUpdate,
    member: models.TripMember = Depends(trip_access(models.ROLE_OWNER)),
    db: Session = Depends(get_db),
):
    target = crud.get_member(db, trip_id, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="That person isn't on this trip")
    if target.role == models.ROLE_OWNER:
        raise HTTPException(status_code=400, detail="The owner's access can't be changed")
    return _member_out(crud.set_member_role(db, target, body.role))


@router.delete("/{trip_id}/members/{user_id}")
def remove_member(
    trip_id: int,
    user_id: int,
    member: models.TripMember = Depends(trip_access(models.ROLE_VIEW)),
    db: Session = Depends(get_db),
):
    """The owner can remove anyone else; anyone else can remove only
    themselves (leave the trip)."""
    if user_id != member.user_id:
        check_role(member.role, models.ROLE_OWNER)
    target = crud.get_member(db, trip_id, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="That person isn't on this trip")
    if target.role == models.ROLE_OWNER:
        raise HTTPException(status_code=400, detail="The owner can't be removed - delete the trip instead")
    crud.remove_member(db, target)
    return {"ok": True}


# --- what's on the trip ---


@router.get("/{trip_id}/activities", response_model=List[schemas.Activity])
def list_trip_activities(
    trip_id: int, member: models.TripMember = Depends(trip_access(models.ROLE_VIEW)), db: Session = Depends(get_db)
):
    return crud.get_activities(db, member.user_id, trip_id=trip_id)


@router.post("/{trip_id}/activities/{activity_id}", response_model=schemas.Activity)
def associate_activity(
    trip_id: int,
    activity_id: int,
    member: models.TripMember = Depends(trip_access(models.ROLE_EDIT)),
    access: ActivityAccess = Depends(activity_access(models.ROLE_EDIT)),
    db: Session = Depends(get_db),
):
    # A trip only ever holds its owner's content, so an activity from anyone
    # else's library can't be put on it (or the reverse).
    if access.activity.owner_id != member.trip.owner_id:
        raise HTTPException(status_code=400, detail="That activity belongs to a different person's library than this trip")
    return crud.associate_activity(db, trip_id, activity_id)


@router.delete("/{trip_id}/activities/{activity_id}")
def unlink_activity(
    trip_id: int,
    activity_id: int,
    member: models.TripMember = Depends(trip_access(models.ROLE_EDIT)),
    db: Session = Depends(get_db),
):
    ok = crud.unlink_activity(db, trip_id, activity_id)
    if not ok:
        raise HTTPException(status_code=404, detail="That activity is not linked to that trip")
    return {"ok": True}


@router.post("/{trip_id}/fill-missing-cities")
def fill_missing_activity_cities(
    trip_id: int, member: models.TripMember = Depends(trip_access(models.ROLE_EDIT)), db: Session = Depends(get_db)
):
    """Sets city on every one of this trip's activities that doesn't have
    one yet, to the trip's own city - never overwrites an activity that
    already has its own city set (e.g. a day trip elsewhere). Re-runnable
    any time - safe to click again after adding more activities, it only
    ever touches whatever's still missing."""
    trip = member.trip
    if not trip.city:
        raise HTTPException(status_code=400, detail="This trip has no city set yet")
    updated = crud.fill_missing_activity_cities(db, trip_id, trip.city)
    return {"updated": updated}


@router.get("/{trip_id}/stays", response_model=List[schemas.Stay])
def list_trip_stays(
    trip_id: int, member: models.TripMember = Depends(trip_access(models.ROLE_VIEW)), db: Session = Depends(get_db)
):
    return crud.get_stays(db, trip_id)


@router.get("/{trip_id}/stay-coverage", response_model=schemas.DateRangeCoverage)
def get_stay_coverage(
    trip_id: int, member: models.TripMember = Depends(trip_access(models.ROLE_VIEW)), db: Session = Depends(get_db)
):
    return crud.get_trip_stay_coverage(db, trip_id)


@router.get("/{trip_id}/travel", response_model=List[schemas.TravelSegment])
def list_trip_travel_segments(
    trip_id: int, member: models.TripMember = Depends(trip_access(models.ROLE_VIEW)), db: Session = Depends(get_db)
):
    return crud.get_travel_segments(db, trip_id)


@router.get("/{trip_id}/dog-care", response_model=List[schemas.DogCareBooking])
def list_trip_dog_care_bookings(
    trip_id: int,
    member: models.TripMember = Depends(trip_access(models.ROLE_OWNER)),
    admin: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return crud.get_dog_care_bookings(db, trip_id)


@router.get("/{trip_id}/dog-care-coverage", response_model=schemas.DateRangeCoverage)
def get_dog_care_coverage(
    trip_id: int,
    member: models.TripMember = Depends(trip_access(models.ROLE_OWNER)),
    admin: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return crud.get_trip_dog_care_coverage(db, trip_id)


@router.get("/{trip_id}/export.xlsx")
def export_trip_xlsx(
    trip_id: int, member: models.TripMember = Depends(trip_access(models.ROLE_VIEW)), db: Session = Depends(get_db)
):
    """A formatted, offline-friendly itinerary download - see app/export.py
    for the actual layout (matches the hand-maintained spreadsheet format
    Evan used before this app existed)."""
    trip = member.trip
    activities = crud.get_activities(db, member.user_id, trip_id=trip_id)
    stays = crud.get_stays(db, trip_id)
    travel_segments = crud.get_travel_segments(db, trip_id)
    workbook = export.build_trip_workbook(trip, activities, stays, travel_segments)
    buf = export.workbook_bytes(workbook)
    filename = export.safe_filename(trip.location)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
