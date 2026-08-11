from datetime import date, datetime, timedelta
from typing import List, Optional

from sqlalchemy.orm import Session

from . import models, schemas

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
    for field, value in updates.model_dump(exclude_unset=True).items():
        setattr(db_trip, field, value)
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


def update_activity(db: Session, activity_id: int, updates: schemas.ActivityUpdate):
    db_activity = get_activity(db, activity_id)
    if db_activity is None:
        return None
    for field, value in updates.model_dump(exclude_unset=True).items():
        setattr(db_activity, field, value)
    db.commit()
    db.refresh(db_activity)
    return db_activity


def delete_activity(db: Session, activity_id: int) -> bool:
    db_activity = get_activity(db, activity_id)
    if db_activity is None:
        return False
    # No manual join-row cleanup needed - SQLAlchemy removes the matching
    # secondary-table rows automatically as part of deleting either side of
    # a many-to-many relationship.
    db.delete(db_activity)
    db.commit()
    return True


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


def _archive_other_stays(db: Session, trip_id: int, keep_stay_id: int) -> None:
    """Once a stay on a trip is booked, every other stay on that same trip
    becomes archived (and un-booked, in case more than one was booked) -
    they stay around for reference rather than being deleted."""
    db.query(models.Stay).filter(
        models.Stay.trip_id == trip_id, models.Stay.id != keep_stay_id
    ).update({"booked": False, "archived": True}, synchronize_session=False)
    db.commit()


def create_stay(db: Session, stay: schemas.StayCreate):
    db_trip = get_trip(db, stay.trip_id)
    if db_trip is None:
        return None
    db_stay = models.Stay(**stay.model_dump())
    db.add(db_stay)
    db.commit()
    db.refresh(db_stay)
    if db_stay.booked:
        _archive_other_stays(db, db_stay.trip_id, db_stay.id)
        db.refresh(db_stay)
    return db_stay


def update_stay(db: Session, stay_id: int, updates: schemas.StayUpdate):
    db_stay = get_stay(db, stay_id)
    if db_stay is None:
        return None
    for field, value in updates.model_dump(exclude_unset=True).items():
        setattr(db_stay, field, value)
    db.commit()
    db.refresh(db_stay)
    if db_stay.booked:
        _archive_other_stays(db, db_stay.trip_id, db_stay.id)
        db.refresh(db_stay)
    return db_stay


def delete_stay(db: Session, stay_id: int) -> bool:
    db_stay = get_stay(db, stay_id)
    if db_stay is None:
        return False
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
