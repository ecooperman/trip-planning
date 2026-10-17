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
    category still assigned to any activity or place - the router turns
    'in_use' into a 409, matching time-management's own Category delete).
    Checks Activity.own_categories specifically (via the actual join
    table, not the resolving category_ids property, which isn't backed by
    a plain column) - a place-linked activity's effective categories are
    checked via its place instead."""
    db_category = get_category(db, category_id)
    if db_category is None:
        return "not_found"
    in_use = (
        db.query(models.Activity).filter(models.Activity.own_categories.any(models.Category.id == category_id)).count()
        + db.query(models.Place).filter(models.Place.categories.any(models.Category.id == category_id)).count()
    )
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
    # place_id IS NULL excludes place-linked activities on purpose - their
    # effective city comes from the linked place (see models.Activity), so
    # there's nothing meaningful to fill on the activity's own row; that
    # place's own city is a separate, deliberate edit, not something this
    # bulk action should reach into.
    activities = (
        db.query(models.Activity)
        .join(models.TripActivity, models.TripActivity.activity_id == models.Activity.id)
        .filter(models.TripActivity.trip_id == trip_id)
        .filter(models.Activity.place_id.is_(None))
        .filter((models.Activity.own_city.is_(None)) | (models.Activity.own_city == ""))
        .all()
    )
    for activity in activities:
        activity.own_city = city
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
    """Every distinct city in use, from Trip.city, Activity.own_city, and
    Place.city - powers the datalist on the trip/activity/place forms (so
    naming stays consistent no matter where you set it) and the city
    filter on activities.html. Queries own_city (the real column) rather
    than the resolving city property, which isn't a real column - a
    place-linked activity's city is already covered by scanning Place.city
    directly. Not a managed table like Category - just whatever strings
    are actually in use, alphabetized."""
    trip_cities = {c for (c,) in db.query(models.Trip.city).filter(models.Trip.city.isnot(None), models.Trip.city != "").distinct()}
    activity_cities = {
        c for (c,) in db.query(models.Activity.own_city).filter(models.Activity.own_city.isnot(None), models.Activity.own_city != "").distinct()
    }
    place_cities = {c for (c,) in db.query(models.Place.city).filter(models.Place.city.isnot(None), models.Place.city != "").distinct()}
    return sorted(trip_cities | activity_cities | place_cities)


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


def _resolve_categories(db: Session, category_ids):
    """[id, ...] -> [Category, ...] - the actual ORM objects a many-to-many
    relationship needs, since a plain @property setter (like the scalar
    own_* fields use) has no clean way to query the DB for them. Shared by
    activities and places."""
    if not category_ids:
        return []
    return db.query(models.Category).filter(models.Category.id.in_(category_ids)).all()


def create_activity(db: Session, activity: schemas.ActivityCreate):
    data = activity.model_dump(exclude={"trip_id", "category_ids"})
    db_activity = models.Activity(**data)
    db_activity.own_categories = _resolve_categories(db, activity.category_ids)
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
    # Not a plain column - see _resolve_categories - so it can't go through
    # the generic setattr loop below like every other field here does.
    category_ids = update_data.pop("category_ids", None)
    # Linking to a place (via a plain PATCH, not crud.promote_activity_to_
    # place - that path clears these itself before this is ever called)
    # makes this activity's own venue fields dormant (see models.Activity's
    # docstring) - clear them so the DB doesn't keep stale, invisible data
    # lying around once the place is the source of truth.
    if update_data.get("place_id") is not None:
        db_activity.own_name = None
        db_activity.own_description = None
        db_activity.own_url = None
        db_activity.own_address = None
        db_activity.own_city = None
        db_activity.own_phone_number = None
        db_activity.own_map_link = None
        db_activity.own_categories = []
    for field, value in update_data.items():
        setattr(db_activity, field, value)
    if category_ids is not None:
        db_activity.own_categories = _resolve_categories(db, category_ids)
    # Address/city change distance directly; place_id changes it
    # indirectly (a newly linked - or unlinked - place has its own address/
    # city). A renamed activity or a new cost doesn't affect distance at
    # all, so this doesn't fire on every edit.
    if "address" in update_data or "city" in update_data or "place_id" in update_data:
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
# Places (see models.Place) - reusable, cross-trip; not tied to any one trip
# or activity the way Stay/TravelSegment/DogCareBooking are tied to a trip.
# ---------------------------------------------------------------------------


def get_places(db: Session):
    return db.query(models.Place).order_by(models.Place.name).all()


def get_place(db: Session, place_id: int):
    return db.query(models.Place).filter(models.Place.id == place_id).first()


def create_place(db: Session, place: schemas.PlaceCreate):
    db_place = models.Place(**place.model_dump(exclude={"category_ids"}))
    db_place.categories = _resolve_categories(db, place.category_ids)
    db.add(db_place)
    db.commit()
    db.refresh(db_place)
    return db_place


def update_place(db: Session, place_id: int, updates: schemas.PlaceUpdate):
    db_place = get_place(db, place_id)
    if db_place is None:
        return None
    update_data = updates.model_dump(exclude_unset=True)
    category_ids = update_data.pop("category_ids", None)
    for field, value in update_data.items():
        setattr(db_place, field, value)
    if category_ids is not None:
        db_place.categories = _resolve_categories(db, category_ids)
    if "address" in update_data or "city" in update_data:
        # Every activity delegating to this place just had its effective
        # address/city change too (see models.Activity's address/city
        # properties), even though none of their own columns did -
        # invalidate each one's cached distances the same as if its own
        # address had changed directly.
        for activity in db_place.activities:
            _invalidate_location_distances(db, "activity", activity.id)
    db.commit()
    db.refresh(db_place)
    return db_place


def delete_place(db: Session, place_id: int) -> str:
    """Returns 'deleted', 'not_found', or 'in_use' (refuses to delete a
    place any activity still links to - unlink or delete those first; a
    place-linked activity's own name/address/etc. were cleared when it was
    linked, so silently unlinking here would leave it with no venue info
    at all, same reasoning as delete_category's 'in_use')."""
    db_place = get_place(db, place_id)
    if db_place is None:
        return "not_found"
    if db.query(models.Activity).filter(models.Activity.place_id == place_id).count() > 0:
        return "in_use"
    db.delete(db_place)
    db.commit()
    return "deleted"


def save_place_scrape_result(
    db: Session,
    place_id: int,
    status: models.ScrapeStatus,
    title: Optional[str] = None,
    description: Optional[str] = None,
    image_url: Optional[str] = None,
    error: Optional[str] = None,
):
    db_place = get_place(db, place_id)
    if db_place is None:
        return None
    db_place.scrape_status = status
    db_place.scraped_title = title
    db_place.scraped_description = description
    db_place.scraped_image_url = image_url
    db_place.scrape_error = error
    db_place.scraped_at = datetime.utcnow()
    db.commit()
    db.refresh(db_place)
    return db_place


def promote_activity_to_place(db: Session, activity_id: int):
    """Creates a new Place from this activity's own current name/
    description/url/address/city/phone_number/map_link/categories, links
    the activity to it, and clears those columns on the activity (see
    models.Activity's docstring - from this point on they resolve through
    the place instead). Returns the updated activity, or None if it
    doesn't exist, is already place-linked, or has no name (nothing to
    promote - see schemas.ActivityCreate's own name-or-place_id rule)."""
    db_activity = get_activity(db, activity_id)
    if db_activity is None or db_activity.place_id is not None or not db_activity.own_name:
        return None

    db_place = models.Place(
        name=db_activity.own_name,
        description=db_activity.own_description,
        url=db_activity.own_url,
        address=db_activity.own_address,
        city=db_activity.own_city,
        phone_number=db_activity.own_phone_number,
        map_link=db_activity.own_map_link,
        categories=list(db_activity.own_categories),
    )
    db.add(db_place)
    db.flush()  # assigns db_place.id without a full commit yet

    db_activity.place_id = db_place.id
    db_activity.own_name = None
    db_activity.own_description = None
    db_activity.own_url = None
    db_activity.own_address = None
    db_activity.own_city = None
    db_activity.own_phone_number = None
    db_activity.own_map_link = None
    db_activity.own_categories = []

    # Same reasoning as update_activity's place_id branch - the activity's
    # effective address just changed (from its own to the new place's,
    # copied from the same values, so not truly different yet, but this
    # keeps the rule simple and exactly matches update_activity's own
    # place_id handling rather than special-casing "these happen to start
    # out equal").
    _invalidate_location_distances(db, "activity", activity_id)

    db.commit()
    db.refresh(db_activity)
    return db_activity


# ---------------------------------------------------------------------------
# Place photos (see models.PlaceImage) - plain binary storage, no
# processing, same pattern as DogCareBooking's invoice/instructions except
# one-to-many.
# ---------------------------------------------------------------------------


def get_place_images(db: Session, place_id: int):
    return db.query(models.PlaceImage).filter(models.PlaceImage.place_id == place_id).order_by(models.PlaceImage.created_at).all()


def get_place_image(db: Session, image_id: int):
    return db.query(models.PlaceImage).filter(models.PlaceImage.id == image_id).first()


def add_place_image(db: Session, place_id: int, filename: str, content_type: str, data: bytes):
    if get_place(db, place_id) is None:
        return None
    image = models.PlaceImage(place_id=place_id, filename=filename, content_type=content_type, data=data)
    db.add(image)
    db.commit()
    db.refresh(image)
    return image


def delete_place_image(db: Session, place_id: int, image_id: int) -> bool:
    image = (
        db.query(models.PlaceImage)
        .filter(models.PlaceImage.id == image_id, models.PlaceImage.place_id == place_id)
        .first()
    )
    if image is None:
        return False
    db.delete(image)
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
# Candidate-stay bulk import + the comparison grid (compare.html)
# ---------------------------------------------------------------------------

# Worksheet/detail fields the AI importer and the screenshot re-extract are
# allowed to write onto a Stay - deliberately not name/url/dates (those are
# set once at create time or by the user), just the stuff worth having a
# model take a first pass at.
_STAY_EXTRACT_FIELDS = (
    "description", "address", "listing_currency", "nightly_price",
    "total_price", "extra_fees", "bedrooms", "bathrooms", "sleeps",
)


def _apply_extracted_fields(db_stay: "models.Stay", fields: Optional[dict]) -> bool:
    """Writes whichever of _STAY_EXTRACT_FIELDS `fields` actually has a
    value for onto db_stay - shared by create_imported_stay,
    apply_stay_extraction, and update_imported_stay, so "only overwrite
    what the model actually found" is one rule, not three copies of it.
    Returns True if anything was written."""
    touched = False
    for key in _STAY_EXTRACT_FIELDS:
        value = (fields or {}).get(key)
        if value is not None:
            setattr(db_stay, key, value)
            touched = True
    return touched


def create_imported_stay(
    db: Session,
    trip_id: int,
    *,
    name: str,
    url: Optional[str],
    start_date: datetime,
    end_date: datetime,
    fields: Optional[dict] = None,
    needs_review: bool = True,
    scrape_status: models.ScrapeStatus = models.ScrapeStatus.not_started,
    scraped_title: Optional[str] = None,
    scraped_description: Optional[str] = None,
    scraped_image_url: Optional[str] = None,
    scrape_error: Optional[str] = None,
):
    """One candidate stay from the bulk URL importer. `fields` is the
    subset of _STAY_EXTRACT_FIELDS the AI managed to pull; everything else
    is left blank for the user to fill in on the trip page."""
    if get_trip(db, trip_id) is None:
        return None
    db_stay = models.Stay(
        trip_id=trip_id,
        name=name,
        url=url or None,
        start_date=start_date,
        end_date=end_date,
        needs_review=needs_review,
        scrape_status=scrape_status,
        scraped_title=scraped_title,
        scraped_description=scraped_description,
        scraped_image_url=scraped_image_url,
        scrape_error=scrape_error,
        scraped_at=datetime.utcnow() if scrape_status != models.ScrapeStatus.not_started else None,
    )
    _apply_extracted_fields(db_stay, fields)
    db.add(db_stay)
    db.commit()
    db.refresh(db_stay)
    return db_stay


def find_stay_by_url(db: Session, trip_id: int, url: Optional[str]):
    """The trip's existing candidate stay for this exact URL, if any -
    scoped to the trip (the same listing could legitimately be a candidate
    on two different trips). Used by the bulk importer to refresh a
    previously-imported stay in place instead of creating a duplicate on
    re-import - see routers/stay_compare.py."""
    if not url:
        return None
    return (
        db.query(models.Stay)
        .filter(models.Stay.trip_id == trip_id, models.Stay.url == url)
        .first()
    )


# A name the importer made up itself ("Stay from airbnb.com") because
# nothing better was found at the time - update_imported_stay only
# overwrites the name when it still looks like this, so a name you've
# since typed in by hand is never silently replaced.
_PLACEHOLDER_NAME_PREFIX = "Stay from "


def update_imported_stay(
    db: Session,
    stay_id: int,
    *,
    name: Optional[str] = None,
    fields: Optional[dict] = None,
    scrape_status: Optional[models.ScrapeStatus] = None,
    scraped_title: Optional[str] = None,
    scraped_description: Optional[str] = None,
    scraped_image_url: Optional[str] = None,
    scrape_error: Optional[str] = None,
):
    """Refreshes an already-imported stay with a fresh read, in place -
    what re-running the bulk URL importer does for a URL it's seen before
    on this trip (see find_stay_by_url), rather than creating a second
    candidate for the same listing. Only touches worksheet fields the new
    read actually found a value for, and the name only when it's still the
    importer's own placeholder - your dates, cost, booked/archived state,
    and anything you've typed by hand are left alone."""
    db_stay = get_stay(db, stay_id)
    if db_stay is None:
        return None
    touched = _apply_extracted_fields(db_stay, fields)
    if name and (not db_stay.name or db_stay.name.startswith(_PLACEHOLDER_NAME_PREFIX)):
        db_stay.name = name
        touched = True
    if scrape_status is not None:
        db_stay.scrape_status = scrape_status
        db_stay.scraped_title = scraped_title
        db_stay.scraped_description = scraped_description
        db_stay.scraped_image_url = scraped_image_url
        db_stay.scrape_error = scrape_error
        db_stay.scraped_at = datetime.utcnow()
    if touched:
        db_stay.needs_review = True
    db.commit()
    db.refresh(db_stay)
    return db_stay


def apply_stay_extraction(db: Session, stay_id: int, fields: dict):
    """Patch an existing stay with a fresh AI read (the screenshot
    re-extract) - only overwrites a field when the model actually returned
    a value, so a partial read never blanks out something already there.
    Re-flags the stay for review."""
    db_stay = get_stay(db, stay_id)
    if db_stay is None:
        return None
    if _apply_extracted_fields(db_stay, fields):
        db_stay.needs_review = True
    db.commit()
    db.refresh(db_stay)
    return db_stay


def get_stay_criteria(db: Session, trip_id: int):
    return (
        db.query(models.TripStayCriterion)
        .filter(models.TripStayCriterion.trip_id == trip_id)
        .order_by(models.TripStayCriterion.sort_order, models.TripStayCriterion.id)
        .all()
    )


def get_stay_criterion(db: Session, criterion_id: int):
    return (
        db.query(models.TripStayCriterion)
        .filter(models.TripStayCriterion.id == criterion_id)
        .first()
    )


def create_stay_criterion(db: Session, trip_id: int, data: schemas.StayCriterionCreate):
    if get_trip(db, trip_id) is None:
        return None
    max_order = (
        db.query(func.max(models.TripStayCriterion.sort_order))
        .filter(models.TripStayCriterion.trip_id == trip_id)
        .scalar()
        or 0
    )
    db_criterion = models.TripStayCriterion(
        trip_id=trip_id, sort_order=max_order + 10, **data.model_dump()
    )
    db.add(db_criterion)
    db.commit()
    db.refresh(db_criterion)
    return db_criterion


def update_stay_criterion(db: Session, criterion_id: int, updates: schemas.StayCriterionUpdate):
    db_criterion = get_stay_criterion(db, criterion_id)
    if db_criterion is None:
        return None
    for field, value in updates.model_dump(exclude_unset=True).items():
        setattr(db_criterion, field, value)
    db.commit()
    db.refresh(db_criterion)
    return db_criterion


def delete_stay_criterion(db: Session, criterion_id: int) -> bool:
    db_criterion = get_stay_criterion(db, criterion_id)
    if db_criterion is None:
        return False
    db.delete(db_criterion)  # cascade drops its verdict rows
    db.commit()
    return True


def set_criterion_verdict(
    db: Session, stay_id: int, criterion_id: int, verdict: str, note: Optional[str]
):
    """Upsert one (stay, criterion) cell of the grid. Returns None if
    either side doesn't exist or they belong to different trips."""
    db_stay = get_stay(db, stay_id)
    db_criterion = get_stay_criterion(db, criterion_id)
    if db_stay is None or db_criterion is None or db_stay.trip_id != db_criterion.trip_id:
        return None
    row = (
        db.query(models.StayCriterionVerdict)
        .filter(
            models.StayCriterionVerdict.stay_id == stay_id,
            models.StayCriterionVerdict.criterion_id == criterion_id,
        )
        .first()
    )
    if row is None:
        row = models.StayCriterionVerdict(stay_id=stay_id, criterion_id=criterion_id)
        db.add(row)
    row.verdict = verdict
    row.note = note or None
    db.commit()
    db.refresh(row)
    return row


def get_stay_comparison(db: Session, trip_id: int):
    trip = get_trip(db, trip_id)
    if trip is None:
        return None
    criteria = get_stay_criteria(db, trip_id)
    stays = get_stays(db, trip_id)
    verdicts = (
        db.query(models.StayCriterionVerdict)
        .join(
            models.TripStayCriterion,
            models.TripStayCriterion.id == models.StayCriterionVerdict.criterion_id,
        )
        .filter(models.TripStayCriterion.trip_id == trip_id)
        .all()
    )
    return {
        "home_currency": trip.home_currency or "USD",
        "criteria": criteria,
        "stays": stays,
        "verdicts": verdicts,
    }


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


# --- plan links (see routers/plan_links.py) -----------------------------------


def get_plan_linked_activities(db: Session, plan_id: Optional[int] = None):
    query = db.query(models.Activity).filter(models.Activity.plan_id.isnot(None))
    if plan_id is not None:
        query = query.filter(models.Activity.plan_id == plan_id)
    return query.order_by(models.Activity.created_at).all()


def find_plan_activity(db: Session, plan_id: int, trip_id: Optional[int]):
    """The activity already created from this plan in the same place the
    import would put it - on this trip, or unassociated when trip_id is
    None - so re-importing a plan is a no-op rather than a duplicate."""
    for activity in get_plan_linked_activities(db, plan_id):
        trip_ids = [t.id for t in activity.trips]
        if (trip_id is None and not trip_ids) or trip_id in trip_ids:
            return activity
    return None


def create_activity_from_plan(db: Session, plan: dict, trip_id: Optional[int]):
    """Copies a plan's details into a new activity (see models.Activity.
    plan_id on why it's a copy, not a live delegation), including its
    scraped preview so the card isn't blank until someone re-fetches."""
    db_activity = create_activity(
        db,
        schemas.ActivityCreate(
            name=plan["name"],
            description=plan.get("description"),
            url=plan.get("url"),
            plan_id=plan["id"],
            trip_id=trip_id,
        ),
    )
    if plan.get("scrape_status") == models.ScrapeStatus.success.value:
        db_activity.scrape_status = models.ScrapeStatus.success
        db_activity.scraped_title = plan.get("scraped_title")
        db_activity.scraped_description = plan.get("scraped_description")
        db_activity.scraped_image_url = plan.get("scraped_image_url")
        db_activity.scraped_at = datetime.utcnow()
        db.commit()
        db.refresh(db_activity)
    return db_activity
