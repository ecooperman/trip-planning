"""Access checks, as FastAPI dependencies.

Anything the caller can't reach is the same 404 as something that doesn't
exist, so ids can't be probed. Something they can reach but not change is a
403 saying so. Roles: see models.ROLE_*. The rules, in short:

- a trip: the caller's TripMember role
- stays, travel segments, stay criteria, dog care: the role on their trip
- an activity: its owner, or a member of the trip it's on (that role)
- a place: its owner; others can only view one that an activity on a trip
  shared with them uses
"""
from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, HTTPException

from . import crud, models
from .auth import current_user
from .deps import get_db


def check_role(role: Optional[str], minimum: str) -> None:
    if role is not None and models.ROLE_RANK[role] >= models.ROLE_RANK[minimum]:
        return
    if minimum == models.ROLE_OWNER:
        raise HTTPException(status_code=403, detail="Only the owner can do that")
    raise HTTPException(status_code=403, detail="You have view-only access to this")


def _trip_member(db, user: models.User, trip_id: int, minimum: str, not_found: str) -> models.TripMember:
    member = crud.get_membership(db, user.id, trip_id)
    if member is None:
        raise HTTPException(status_code=404, detail=not_found)
    check_role(member.role, minimum)
    return member


def trip_access(minimum: str):
    """For routes with a {trip_id} path parameter: the caller's membership of
    that trip, requiring at least `minimum`."""

    def dependency(trip_id: int, user: models.User = Depends(current_user), db=Depends(get_db)) -> models.TripMember:
        return _trip_member(db, user, trip_id, minimum, "Trip not found")

    return dependency


@dataclass
class ActivityAccess:
    activity: models.Activity
    role: str


def activity_access(minimum: str):
    """For routes with an {activity_id}."""

    def dependency(activity_id: int, user: models.User = Depends(current_user), db=Depends(get_db)) -> ActivityAccess:
        activity = crud.get_activity(db, activity_id)
        role = crud.activity_role(db, user.id, activity) if activity is not None else None
        if role is None:
            raise HTTPException(status_code=404, detail="Activity not found")
        check_role(role, minimum)
        return ActivityAccess(activity=activity, role=role)

    return dependency


@dataclass
class PlaceAccess:
    place: models.Place
    role: str


def place_access(minimum: str):
    """For routes with a {place_id}."""

    def dependency(place_id: int, user: models.User = Depends(current_user), db=Depends(get_db)) -> PlaceAccess:
        place = crud.get_place(db, place_id)
        role = crud.place_role(db, user.id, place) if place is not None else None
        if role is None:
            raise HTTPException(status_code=404, detail="Place not found")
        check_role(role, minimum)
        return PlaceAccess(place=place, role=role)

    return dependency


@dataclass
class OnTrip:
    """A thing that lives on a trip (stay, travel segment, criterion, dog-care
    booking) plus the caller's membership of that trip."""

    item: object
    member: models.TripMember


def stay_access(minimum: str):
    def dependency(stay_id: int, user: models.User = Depends(current_user), db=Depends(get_db)) -> OnTrip:
        stay = crud.get_stay(db, stay_id)
        member = crud.get_membership(db, user.id, stay.trip_id) if stay is not None else None
        if member is None:
            raise HTTPException(status_code=404, detail="Stay not found")
        check_role(member.role, minimum)
        return OnTrip(stay, member)

    return dependency


def travel_access(minimum: str):
    def dependency(travel_segment_id: int, user: models.User = Depends(current_user), db=Depends(get_db)) -> OnTrip:
        segment = crud.get_travel_segment(db, travel_segment_id)
        member = crud.get_membership(db, user.id, segment.trip_id) if segment is not None else None
        if member is None:
            raise HTTPException(status_code=404, detail="Travel segment not found")
        check_role(member.role, minimum)
        return OnTrip(segment, member)

    return dependency


def criterion_access(minimum: str):
    def dependency(criterion_id: int, user: models.User = Depends(current_user), db=Depends(get_db)) -> OnTrip:
        criterion = crud.get_stay_criterion(db, criterion_id)
        member = crud.get_membership(db, user.id, criterion.trip_id) if criterion is not None else None
        if member is None:
            raise HTTPException(status_code=404, detail="Criterion not found")
        check_role(member.role, minimum)
        return OnTrip(criterion, member)

    return dependency


def dog_care_access():
    """Dog care is the app owner's own business: only an administrator who
    also owns the trip ever reaches it (shared members never do)."""
    from .auth import is_admin

    def dependency(booking_id: int, user: models.User = Depends(current_user), db=Depends(get_db)) -> OnTrip:
        booking = crud.get_dog_care_booking(db, booking_id)
        member = crud.get_membership(db, user.id, booking.trip_id) if booking is not None else None
        if member is None or member.role != models.ROLE_OWNER or not is_admin(user):
            raise HTTPException(status_code=404, detail="Dog care booking not found")
        return OnTrip(booking, member)

    return dependency
