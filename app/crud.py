from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from . import models, schemas

# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------


def get_categories(db: Session):
    return db.query(models.Category).order_by(models.Category.sort_order, models.Category.id).all()


def get_category(db: Session, category_id: int):
    return db.query(models.Category).filter(models.Category.id == category_id).first()


def create_category(db: Session, category: schemas.CategoryCreate):
    # Always appended to the end - same max+10 pattern as time-management's
    # Task.sort_order, leaving gaps so a later reorder only has to touch the
    # two rows being swapped.
    max_order = db.query(func.max(models.Category.sort_order)).scalar() or 0
    db_category = models.Category(**category.model_dump(), sort_order=max_order + 10)
    db.add(db_category)
    db.commit()
    db.refresh(db_category)
    return db_category


def reorder_categories(db: Session, ordered_ids: List[int]):
    db_categories = db.query(models.Category).filter(models.Category.id.in_(ordered_ids)).all()
    by_id = {c.id: c for c in db_categories}
    for index, category_id in enumerate(ordered_ids):
        db_category = by_id.get(category_id)
        if db_category is None:
            continue  # a stale id (deleted mid-drag elsewhere) - skip rather than error
        db_category.sort_order = (index + 1) * 10
    db.commit()
    return get_categories(db)


def update_category(db: Session, category_id: int, updates: schemas.CategoryUpdate):
    db_category = get_category(db, category_id)
    if db_category is None:
        return None
    for field, value in updates.model_dump(exclude_unset=True).items():
        setattr(db_category, field, value)
    db.commit()
    db.refresh(db_category)
    return db_category


def delete_category(db: Session, category_id: int) -> str:
    """Returns 'deleted', 'not_found', or 'in_use' (refuses to delete a
    category still assigned to any activity - the router turns 'in_use'
    into a 409, matching time-management's own Category delete)."""
    db_category = get_category(db, category_id)
    if db_category is None:
        return "not_found"
    in_use = db.query(models.Activity).filter(models.Activity.category_id == category_id).count()
    if in_use > 0:
        return "in_use"
    db.delete(db_category)
    db.commit()
    return "deleted"


# ---------------------------------------------------------------------------
# Trips
# ---------------------------------------------------------------------------


def get_trips(db: Session):
    return db.query(models.Trip).order_by(
        models.Trip.archived,
        models.Trip.start_date.is_(None),
        models.Trip.start_date,
        models.Trip.created_at.desc(),
    ).all()


def get_trip(db: Session, trip_id: int):
    return db.query(models.Trip).filter(models.Trip.id == trip_id).first()


def trip_cost_summary(db: Session):
    """Per non-archived trip: summed cost of its non-archived linked
    activities plus its booked, non-archived stays, travel segments, and
    dog-care bookings. Costs are whole dollars in the DB; returned as
    cents. Consumed by the finances app's trip forecast (GET
    /api/trips/cost-summary)."""
    out = []
    for trip in db.query(models.Trip).filter(models.Trip.archived.is_(False)).all():
        act = (
            db.query(func.coalesce(func.sum(models.Activity.cost), 0))
            .join(models.TripActivity, models.TripActivity.activity_id == models.Activity.id)
            .filter(models.TripActivity.trip_id == trip.id)
            .filter(models.Activity.archived.is_(False))
            .scalar()
        ) or 0
        stay = (
            db.query(func.coalesce(func.sum(models.Stay.cost), 0))
            .filter(models.Stay.trip_id == trip.id)
            .filter(models.Stay.archived.is_(False), models.Stay.booked.is_(True))
            .scalar()
        ) or 0
        travel = (
            db.query(func.coalesce(func.sum(models.TravelSegment.cost), 0))
            .filter(models.TravelSegment.trip_id == trip.id)
            .filter(models.TravelSegment.archived.is_(False), models.TravelSegment.booked.is_(True))
            .scalar()
        ) or 0
        dog_care = (
            db.query(func.coalesce(func.sum(models.DogCareBooking.cost), 0))
            .filter(models.DogCareBooking.trip_id == trip.id)
            .filter(models.DogCareBooking.archived.is_(False), models.DogCareBooking.booked.is_(True))
            .scalar()
        ) or 0
        act, stay, travel, dog_care = int(act), int(stay), int(travel), int(dog_care)
        out.append({
            "id": trip.id,
            "location": trip.location,
            "city": trip.city,
            "start_date": trip.start_date,
            "end_date": trip.end_date,
            "activities_cost_cents": act * 100,
            "stays_cost_cents": stay * 100,
            "travel_cost_cents": travel * 100,
            "dog_care_cost_cents": dog_care * 100,
            "total_cost_cents": (act + stay + travel + dog_care) * 100,
        })
    return out


def fill_missing_activity_cities(db: Session, trip_id: int, city: str) -> int:
    activities = (
        db.query(models.Activity)
        .join(models.TripActivity, models.TripActivity.activity_id == models.Activity.id)
        .filter(models.TripActivity.trip_id == trip_id)
        .filter((models.Activity.city.is_(None)) | (models.Activity.city == ""))
        .all()
    )
    for activity in activities:
        activity.city = city
    db.commit()
    return len(activities)


def create_trip(db: Session, trip: schemas.TripCreate):
    db_trip = models.Trip(**trip.model_dump())
    db.add(db_trip)
    db.commit()
    db.refresh(db_trip)
    return db_trip


def update_trip(db: Session, trip_id: int, updates: schemas.TripUpdate):
    db_trip = get_trip(db, trip_id)
    if db_trip is None:
        return None
    update_data = updates.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_trip, field, value)
    if update_data.get("archived") is True:
        # Archiving a trip archives its activities too - tucked away the
        # same way the trip itself is, not deleted (still there to look
        # back on). Deliberately one-directional: unarchiving the trip
        # does NOT auto-unarchive them back, since an activity may have
        # been archived on its own for an unrelated reason (see
        # Activity.archived's docstring) - undoing that silently as a side
        # effect of the trip would be the same mistake _archive_other_stays
        # used to make for stays.
        for activity in db_trip.activities:
            activity.archived = True
    if "city" in update_data:
        # A stay has no city of its own (see models.Stay / distance.py's
        # stay_address_query_for) - one that has no address either falls
        # back to the trip's city, so a stale cached distance for it needs
        # invalidating too here, same as update_activity does for its own
        # address/city changes. An activity has its own city field, so a
        # trip's city change never affects an activity's cache.
        for stay in db_trip.stays:
            if not stay.address:
                _invalidate_location_distances(db, "stay", stay.id)
    db.commit()
    db.refresh(db_trip)
    return db_trip


def delete_trip(db: Session, trip_id: int, delete_activities: bool = False) -> bool:
    """Delete a trip. `delete_activities` decides whether its activities are
    deleted too or just unlinked and left behind as unassociated activities
    - either way the join rows disappear, via the ORM relationship rather
    than a raw bulk delete (mixing the two against a many-to-many secondary
    table confuses SQLAlchemy's own cascade bookkeeping and raises
    StaleDataError). Stays have no existence outside their trip, so they're
    always deleted with it (see the cascade on Trip.stays in models.py).
    """
    db_trip = get_trip(db, trip_id)
    if db_trip is None:
        return False

    if delete_activities:
        for activity in list(db_trip.activities):
            db.delete(activity)
    else:
        db_trip.activities = []

    db.delete(db_trip)
    db.commit()
    return True


def _date_range(start: date, end: date) -> List[date]:
    days = []
    current = start
    while current <= end:
        days.append(current)
        current += timedelta(days=1)
    return days


def get_trip_stay_coverage(db: Session, trip_id: int) -> Optional[dict]:
    """Whether every day of the trip is covered by at least one
    non-archived stay. Returns None if the trip itself doesn't exist (the
    router turns that into a 404); returns has_dates=False if the trip has
    no start/end date set, since there's nothing to check yet.
    """
    db_trip = get_trip(db, trip_id)
    if db_trip is None:
        return None
    if db_trip.start_date is None or db_trip.end_date is None:
        return {"has_dates": False, "covered": True, "missing_dates": []}

    trip_days = _date_range(db_trip.start_date.date(), db_trip.end_date.date())
    covered_days = set()
    for stay in db_trip.stays:
        if stay.archived:
            continue
        for day in _date_range(stay.start_date.date(), stay.end_date.date()):
            covered_days.add(day)

    missing_days = [d for d in trip_days if d not in covered_days]
    return {
        "has_dates": True,
        "covered": len(missing_days) == 0,
        "missing_dates": [d.isoformat() for d in missing_days],
    }


# ---------------------------------------------------------------------------
# Activities
# ---------------------------------------------------------------------------


def get_all_cities(db: Session) -> List[str]:
    """Every distinct city in use, from both Trip.city and Activity.city -
    powers the datalist on both the trip and activity forms (so naming
    stays consistent no matter where you set it) and the city filter on
    activities.html. Not a managed table like Category - just whatever
    strings are actually in use, alphabetized."""
    trip_cities = {c for (c,) in db.query(models.Trip.city).filter(models.Trip.city.isnot(None), models.Trip.city != "").distinct()}
    activity_cities = {c for (c,) in db.query(models.Activity.city).filter(models.Activity.city.isnot(None), models.Activity.city != "").distinct()}
    return sorted(trip_cities | activity_cities)


def get_activities(
    db: Session, trip_id: Optional[int] = None, unassociated: bool = False
):
    query = db.query(models.Activity)
    if trip_id is not None:
        query = query.join(
            models.TripActivity, models.TripActivity.activity_id == models.Activity.id
        ).filter(models.TripActivity.trip_id == trip_id)
    elif unassociated:
        linked_ids = db.query(models.TripActivity.activity_id)
        query = query.filter(~models.Activity.id.in_(linked_ids))
    return query.order_by(models.Activity.created_at.desc()).all()


def get_activity(db: Session, activity_id: int):
    return db.query(models.Activity).filter(models.Activity.id == activity_id).first()


def create_activity(db: Session, activity: schemas.ActivityCreate):
    data = activity.model_dump(exclude={"trip_id"})
    db_activity = models.Activity(**data)
    db.add(db_activity)
    db.commit()
    db.refresh(db_activity)
    if activity.trip_id is not None:
        associated = associate_activity(db, activity.trip_id, db_activity.id)
        if associated is not None:
            db_activity = associated
    return db_activity


def _invalidate_location_distances(db: Session, kind: str, location_id: int):
    """Drops every cached LocationDistance row (either direction, any
    mode) involving this location (an activity or a stay) - see the
    model's docstring for why."""
    db.query(models.LocationDistance).filter(
        ((models.LocationDistance.origin_kind == kind) & (models.LocationDistance.origin_id == location_id))
        | ((models.LocationDistance.destination_kind == kind) & (models.LocationDistance.destination_id == location_id))
    ).delete(synchronize_session=False)


def update_activity(db: Session, activity_id: int, updates: schemas.ActivityUpdate):
    db_activity = get_activity(db, activity_id)
    if db_activity is None:
        return None
    update_data = updates.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_activity, field, value)
    # Only address/city changes actually affect distance - a renamed
    # activity or a new cost doesn't, so this doesn't fire on every edit.
    if "address" in update_data or "city" in update_data:
        _invalidate_location_distances(db, "activity", activity_id)
    db.commit()
    db.refresh(db_activity)
    return db_activity


def delete_activity(db: Session, activity_id: int) -> bool:
    db_activity = get_activity(db, activity_id)
    if db_activity is None:
        return False
    # No manual join-row cleanup needed for TripActivity - SQLAlchemy
    # removes the matching secondary-table rows automatically as part of
    # deleting either side of a many-to-many relationship. LocationDistance
    # isn't a secondary table though (a real row with its own columns), so
    # it needs the explicit cleanup below.
    _invalidate_location_distances(db, "activity", activity_id)
    db.delete(db_activity)
    db.commit()
    return True


# ---------------------------------------------------------------------------
# Distance cache (Google Distance Matrix - see app/distance.py)
# ---------------------------------------------------------------------------


def _kind_groups(refs):
    """[(kind, id), ...] -> {kind: [id, ...]} - groups a mixed list of
    location refs by kind so a query can filter each kind's ids with its
    own IN clause (see get_cached_distances below)."""
    groups: Dict[str, List[int]] = {}
    for kind, location_id in refs:
        groups.setdefault(kind, []).append(location_id)
    return groups


def _kind_id_filter(column_kind, column_id, refs):
    """SQLAlchemy filter matching any (kind, id) pair in refs, against a
    (kind_column, id_column) pair - the composite-key equivalent of a plain
    .in_(ids) filter, since a location is identified by kind+id together
    (see models.LocationDistance)."""
    groups = _kind_groups(refs)
    return or_(*[(column_kind == kind) & (column_id.in_(ids)) for kind, ids in groups.items()])


def get_cached_distances(db: Session, origins: List[tuple], destinations: List[tuple], mode: str):
    """Every cached row whose origin is in origins AND destination is in
    destinations (each a list of (kind, id) tuples), for this mode - keyed
    by ((origin_kind, origin_id), (destination_kind, destination_id)) - the
    same "pair of refs" shape the caller's own valid_pairs/missing_pairs
    sets use, so a lookup is just `cached.get(pair)` - for O(1) lookup. May
    include rows for pairs the caller didn't actually ask for (this is a
    plain IN x IN cross-match, not an exact-pairs match) - harmless, the
    caller only looks up the specific keys it needs."""
    rows = (
        db.query(models.LocationDistance)
        .filter(models.LocationDistance.mode == mode)
        .filter(_kind_id_filter(models.LocationDistance.origin_kind, models.LocationDistance.origin_id, origins))
        .filter(_kind_id_filter(models.LocationDistance.destination_kind, models.LocationDistance.destination_id, destinations))
        .all()
    )
    return {
        ((row.origin_kind, row.origin_id), (row.destination_kind, row.destination_id)): row
        for row in rows
    }


def get_location_distance_rows(db: Session, kind: str, location_id: int):
    """Every cached distance row involving this location, in either
    direction - (outbound rows, inbound rows). See
    routers/activities.py's /distances endpoint, which turns these into
    one entry per (other location, direction)."""
    outbound = (
        db.query(models.LocationDistance)
        .filter(models.LocationDistance.origin_kind == kind, models.LocationDistance.origin_id == location_id)
        .all()
    )
    inbound = (
        db.query(models.LocationDistance)
        .filter(models.LocationDistance.destination_kind == kind, models.LocationDistance.destination_id == location_id)
        .all()
    )
    return outbound, inbound


def cache_distance(db: Session, origin_kind: str, origin_id: int, destination_kind: str, destination_id: int, mode: str, result):
    """Upsert - a later comparison that happens to re-fetch a pair already
    cached (see the router's rectangular-sub-grid re-fetch) just refreshes
    it rather than erroring on the unique constraint."""
    existing = (
        db.query(models.LocationDistance)
        .filter_by(origin_kind=origin_kind, origin_id=origin_id, destination_kind=destination_kind, destination_id=destination_id, mode=mode)
        .first()
    )
    if existing is None:
        existing = models.LocationDistance(
            origin_kind=origin_kind, origin_id=origin_id, destination_kind=destination_kind, destination_id=destination_id, mode=mode
        )
        db.add(existing)
    existing.distance_meters = result.distance_meters
    existing.distance_text = result.distance_text
    existing.duration_seconds = result.duration_seconds
    existing.duration_text = result.duration_text
    existing.computed_at = datetime.utcnow()
    db.commit()
    return existing


def save_activity_scrape_result(
    db: Session,
    activity_id: int,
    status: models.ScrapeStatus,
    title: Optional[str] = None,
    description: Optional[str] = None,
    image_url: Optional[str] = None,
    error: Optional[str] = None,
):
    db_activity = get_activity(db, activity_id)
    if db_activity is None:
        return None
    db_activity.scrape_status = status
    db_activity.scraped_title = title
    db_activity.scraped_description = description
    db_activity.scraped_image_url = image_url
    db_activity.scrape_error = error
    db_activity.scraped_at = datetime.utcnow()
    db.commit()
    db.refresh(db_activity)
    return db_activity


# ---------------------------------------------------------------------------
# Trip <-> Activity associations
# ---------------------------------------------------------------------------


def associate_activity(db: Session, trip_id: int, activity_id: int):
    """Link an activity to a trip. An activity is only ever linked to at
    most one trip today, so linking to a new trip first clears any
    existing link rather than erroring - it reads as "move this activity
    to this trip." The join table itself is many-to-many; dropping that
    one clearing step is all it'd take to allow multiple trips later.
    """
    db_trip = get_trip(db, trip_id)
    db_activity = get_activity(db, activity_id)
    if db_trip is None or db_activity is None:
        return None
    # Assigning the relationship (rather than a raw insert/delete against
    # the join table) lets SQLAlchemy compute and apply the diff itself -
    # this both replaces any existing association and avoids the
    # StaleDataError that comes from mixing bulk queries with its own
    # many-to-many bookkeeping.
    db_activity.trips = [db_trip]
    db.commit()
    db.refresh(db_activity)
    return db_activity


def unlink_activity(db: Session, trip_id: int, activity_id: int) -> bool:
    db_trip = get_trip(db, trip_id)
    db_activity = get_activity(db, activity_id)
    if db_trip is None or db_activity is None:
        return False
    if db_activity not in db_trip.activities:
        return False
    db_trip.activities.remove(db_activity)
    db.commit()
    return True


# ---------------------------------------------------------------------------
# Stays
# ---------------------------------------------------------------------------


def get_stays(db: Session, trip_id: int):
    return db.query(models.Stay).filter(models.Stay.trip_id == trip_id).order_by(
        models.Stay.archived, models.Stay.start_date
    ).all()


def get_stay(db: Session, stay_id: int):
    return db.query(models.Stay).filter(models.Stay.id == stay_id).first()


def create_stay(db: Session, stay: schemas.StayCreate):
    db_trip = get_trip(db, stay.trip_id)
    if db_trip is None:
        return None
    db_stay = models.Stay(**stay.model_dump())
    db.add(db_stay)
    db.commit()
    db.refresh(db_stay)
    return db_stay


def update_stay(db: Session, stay_id: int, updates: schemas.StayUpdate):
    # booked and archived are both plain, independent flags on the stay
    # itself - no cross-stay side effects. A trip can legitimately have
    # more than one booked stay at once (different date ranges), so
    # marking one booked must never silently touch its siblings. Archiving
    # an option you're no longer considering is a deliberate, separate
    # action (see the Archive/Unarchive button on the stay's view pane).
    db_stay = get_stay(db, stay_id)
    if db_stay is None:
        return None
    update_data = updates.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_stay, field, value)
    # Same reasoning as update_activity - only an address change can affect
    # a cached distance (a stay has no city of its own to change; a trip's
    # city change is handled separately, see update_trip below).
    if "address" in update_data:
        _invalidate_location_distances(db, "stay", stay_id)
    db.commit()
    db.refresh(db_stay)
    return db_stay


def delete_stay(db: Session, stay_id: int) -> bool:
    db_stay = get_stay(db, stay_id)
    if db_stay is None:
        return False
    _invalidate_location_distances(db, "stay", stay_id)
    db.delete(db_stay)
    db.commit()
    return True


def save_stay_scrape_result(
    db: Session,
    stay_id: int,
    status: models.ScrapeStatus,
    title: Optional[str] = None,
    description: Optional[str] = None,
    image_url: Optional[str] = None,
    error: Optional[str] = None,
):
    db_stay = get_stay(db, stay_id)
    if db_stay is None:
        return None
    db_stay.scrape_status = status
    db_stay.scraped_title = title
    db_stay.scraped_description = description
    db_stay.scraped_image_url = image_url
    db_stay.scrape_error = error
    db_stay.scraped_at = datetime.utcnow()
    db.commit()
    db.refresh(db_stay)
    return db_stay


# ---------------------------------------------------------------------------
# Travel segments (flights, trains, rental cars, ferries - see models.TravelSegment)
# ---------------------------------------------------------------------------


def get_travel_segments(db: Session, trip_id: int):
    return (
        db.query(models.TravelSegment)
        .filter(models.TravelSegment.trip_id == trip_id)
        .order_by(models.TravelSegment.archived, models.TravelSegment.departure_time)
        .all()
    )


def get_travel_segment(db: Session, travel_segment_id: int):
    return db.query(models.TravelSegment).filter(models.TravelSegment.id == travel_segment_id).first()


def create_travel_segment(db: Session, segment: schemas.TravelSegmentCreate):
    db_trip = get_trip(db, segment.trip_id)
    if db_trip is None:
        return None
    db_segment = models.TravelSegment(**segment.model_dump())
    db.add(db_segment)
    db.commit()
    db.refresh(db_segment)
    return db_segment


def update_travel_segment(db: Session, travel_segment_id: int, updates: schemas.TravelSegmentUpdate):
    # booked and archived are independent flags, same reasoning as
    # update_stay - an outbound and return flight can both be booked at
    # once, and archiving one is a deliberate "not going with this option"
    # action, not an automatic side effect of anything else.
    db_segment = get_travel_segment(db, travel_segment_id)
    if db_segment is None:
        return None
    update_data = updates.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_segment, field, value)
    db.commit()
    db.refresh(db_segment)
    return db_segment


def delete_travel_segment(db: Session, travel_segment_id: int) -> bool:
    db_segment = get_travel_segment(db, travel_segment_id)
    if db_segment is None:
        return False
    db.delete(db_segment)
    db.commit()
    return True


# ---------------------------------------------------------------------------
# Dog care bookings (see models.DogCareBooking)
# ---------------------------------------------------------------------------


def get_dog_care_bookings(db: Session, trip_id: int):
    return (
        db.query(models.DogCareBooking)
        .filter(models.DogCareBooking.trip_id == trip_id)
        .order_by(models.DogCareBooking.archived, models.DogCareBooking.start_date)
        .all()
    )


def get_dog_care_booking(db: Session, booking_id: int):
    return db.query(models.DogCareBooking).filter(models.DogCareBooking.id == booking_id).first()


def create_dog_care_booking(db: Session, booking: schemas.DogCareBookingCreate):
    db_trip = get_trip(db, booking.trip_id)
    if db_trip is None:
        return None
    db_booking = models.DogCareBooking(**booking.model_dump())
    db.add(db_booking)
    db.commit()
    db.refresh(db_booking)
    return db_booking


def update_dog_care_booking(db: Session, booking_id: int, updates: schemas.DogCareBookingUpdate):
    # booked and archived are independent flags, same reasoning as
    # update_stay/update_travel_segment.
    db_booking = get_dog_care_booking(db, booking_id)
    if db_booking is None:
        return None
    update_data = updates.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_booking, field, value)
    db.commit()
    db.refresh(db_booking)
    return db_booking


def delete_dog_care_booking(db: Session, booking_id: int) -> bool:
    db_booking = get_dog_care_booking(db, booking_id)
    if db_booking is None:
        return False
    db.delete(db_booking)
    db.commit()
    return True


def set_dog_care_attachment(db: Session, booking_id: int, kind: str, filename: str, content_type: str, data: bytes):
    """kind is "invoice" or "instructions" - sets that attachment's three
    columns (…_filename/…_content_type/…_data), overwriting whatever was
    there before (a re-upload replaces, it doesn't keep history)."""
    db_booking = get_dog_care_booking(db, booking_id)
    if db_booking is None:
        return None
    setattr(db_booking, f"{kind}_filename", filename)
    setattr(db_booking, f"{kind}_content_type", content_type)
    setattr(db_booking, f"{kind}_data", data)
    db.commit()
    db.refresh(db_booking)
    return db_booking


def clear_dog_care_attachment(db: Session, booking_id: int, kind: str):
    db_booking = get_dog_care_booking(db, booking_id)
    if db_booking is None:
        return None
    setattr(db_booking, f"{kind}_filename", None)
    setattr(db_booking, f"{kind}_content_type", None)
    setattr(db_booking, f"{kind}_data", None)
    db.commit()
    db.refresh(db_booking)
    return db_booking


def get_trip_dog_care_coverage(db: Session, trip_id: int) -> Optional[dict]:
    """Whether every day of the trip is covered by at least one
    non-archived dog-care booking - same shape/logic as
    get_trip_stay_coverage, see DateRangeCoverage's docstring."""
    db_trip = get_trip(db, trip_id)
    if db_trip is None:
        return None
    if db_trip.start_date is None or db_trip.end_date is None:
        return {"has_dates": False, "covered": True, "missing_dates": []}

    trip_days = _date_range(db_trip.start_date.date(), db_trip.end_date.date())
    covered_days = set()
    for booking in db_trip.dog_care_bookings:
        if booking.archived:
            continue
        for day in _date_range(booking.start_date.date(), booking.end_date.date()):
            covered_days.add(day)

    missing_days = [d for d in trip_days if d not in covered_days]
    return {
        "has_dates": True,
        "covered": len(missing_days) == 0,
        "missing_dates": [d.isoformat() for d in missing_days],
    }
