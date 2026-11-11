from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from . import config, models, schemas

# Parked owner of everything that existed before accounts did (see the
# migration); the first person to sign in takes it over (get_or_create_user).
LEGACY_OWNER_EMAIL = "legacy-owner@trips.invalid"

# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------


def normalize_email(email: str) -> str:
    return email.strip().lower()


def get_user_by_email(db: Session, email: str):
    return db.query(models.User).filter(models.User.email == email).first()


def _create_user(db: Session, email: str) -> models.User:
    user = models.User(email=email)
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        # Two first requests from the same person raced; theirs won.
        db.rollback()
        return get_user_by_email(db, email)
    db.refresh(user)
    return user


def get_or_create_user(db: Session, email: str) -> models.User:
    """The person behind an (already normalized) email, created on first
    sight. The first one in who's allowed to takes over the pre-accounts data
    by renaming the placeholder owner to their email - so it all becomes
    theirs without moving a single row."""
    user = get_user_by_email(db, email)
    if user is not None:
        return user
    if config.ADOPT_LEGACY_ANY or email in config.ADMIN_EMAILS:
        legacy = get_user_by_email(db, LEGACY_OWNER_EMAIL)
        if legacy is not None:
            legacy.email = email
            db.commit()
            return legacy
    return _create_user(db, email)


# ---------------------------------------------------------------------------
# Access: who can reach what
#
# A trip is reached through the caller's TripMember row. Everything on a trip
# (stays, travel, criteria, its activities) follows the trip's role. An
# activity that isn't on any trip is its owner's alone. A place is its
# owner's, and others can see it only through an activity on a trip shared
# with them (it supplies that activity's name and address). Categories are
# the owner's; others see them only attached to what they can see.
# ---------------------------------------------------------------------------


def _best_role(roles):
    roles = [r for r in roles if r]
    return max(roles, key=lambda r: models.ROLE_RANK[r]) if roles else None


def get_membership(db: Session, user_id: int, trip_id: int):
    return db.query(models.TripMember).filter_by(user_id=user_id, trip_id=trip_id).first()


def activity_role(db: Session, user_id: int, activity: models.Activity):
    """owner / edit / view, or None - the caller's best access to this activity."""
    if activity.owner_id == user_id:
        return models.ROLE_OWNER
    roles = (
        db.query(models.TripMember.role)
        .join(models.TripActivity, models.TripActivity.trip_id == models.TripMember.trip_id)
        .filter(models.TripActivity.activity_id == activity.id, models.TripMember.user_id == user_id)
        .all()
    )
    return _best_role(role for (role,) in roles)


def place_role(db: Session, user_id: int, place: models.Place):
    if place.owner_id == user_id:
        return models.ROLE_OWNER
    reachable = (
        db.query(models.Activity.id)
        .join(models.TripActivity, models.TripActivity.activity_id == models.Activity.id)
        .join(models.TripMember, models.TripMember.trip_id == models.TripActivity.trip_id)
        .filter(models.Activity.place_id == place.id, models.TripMember.user_id == user_id)
        .first()
    )
    return models.ROLE_VIEW if reachable else None


def trip_views(db: Session, members):
    """The member rows' trips, each decorated for the person the row belongs
    to (see schemas.Trip): their role, who owns it, how many people share it."""
    trip_ids = [m.trip_id for m in members]
    member_counts = dict(
        db.query(models.TripMember.trip_id, func.count(models.TripMember.user_id))
        .filter(models.TripMember.trip_id.in_(trip_ids))
        .group_by(models.TripMember.trip_id)
        .all()
    )
    views = []
    for member in members:
        trip = member.trip
        trip.my_role = member.role
        trip.owner_email = trip.owner.email
        trip.member_count = member_counts.get(member.trip_id, 1)
        views.append(trip)
    return views


def get_trips(db: Session, user_id: int):
    members = (
        db.query(models.TripMember)
        .join(models.Trip, models.Trip.id == models.TripMember.trip_id)
        .filter(models.TripMember.user_id == user_id)
        .order_by(
            models.Trip.archived,
            models.Trip.start_date.is_(None),
            models.Trip.start_date,
            models.Trip.created_at.desc(),
        )
        .all()
    )
    return trip_views(db, members)


def trip_view(db: Session, member: models.TripMember):
    return trip_views(db, [member])[0]


def get_members(db: Session, trip_id: int):
    return (
        db.query(models.TripMember)
        .filter(models.TripMember.trip_id == trip_id)
        .order_by((models.TripMember.role == models.ROLE_OWNER).desc(), models.TripMember.user_id)
        .all()
    )


def get_member(db: Session, trip_id: int, user_id: int):
    return get_membership(db, user_id, trip_id)


def get_account(db: Session, email: str):
    """The person with this (already normalized) email if the app has an
    account for them (they've signed in, or were let in by an approved
    invite). Not the same as being able to sign in now - see
    routers/trips.py's _can_sign_in, which also asks Cloudflare."""
    if email == LEGACY_OWNER_EMAIL:
        return None
    return get_user_by_email(db, email)


def create_account(db: Session, email: str) -> models.User:
    """An account for someone Cloudflare lets in who hasn't opened this app yet."""
    return get_account(db, email) or _create_user(db, email)


def add_member(db: Session, trip_id: int, user: models.User, role: str):
    """Give an existing user access to a trip. Returns the new membership, or
    None if they're already on it."""
    if get_membership(db, user.id, trip_id) is not None:
        return None
    member = models.TripMember(trip_id=trip_id, user_id=user.id, role=role)
    db.add(member)
    db.commit()
    db.refresh(member)
    return member


def set_member_role(db: Session, member: models.TripMember, role: str):
    member.role = role
    db.commit()
    db.refresh(member)
    return member


def remove_member(db: Session, member: models.TripMember):
    db.delete(member)
    db.commit()


# ---------------------------------------------------------------------------
# Asking for someone with no account to be let in. A trip's owner asks, an
# administrator decides (see app/routers/invites.py for the Cloudflare step).


def _is_admin_email(user: models.User) -> bool:
    return user.email in config.ADMIN_EMAILS


def invites_left(db: Session, user: models.User):
    """How many more people this person may ask for, or None for no limit
    (administrators). Each different email they've asked for counts once, in
    any state - waiting, approved, declined - until they cancel a waiting one,
    so being refused doesn't hand the slot back to be spent again."""
    if _is_admin_email(user):
        return None
    used = (
        db.query(func.count(func.distinct(models.Invite.email))).filter(models.Invite.invited_by_id == user.id).scalar()
    )
    return max(config.INVITES_PER_USER - used, 0)


def create_invite(db: Session, trip_id: Optional[int], inviter: models.User, email: str, role: str, for_app: bool = False):
    """Returns (invite, None), or (None, reason) with reason "duplicate" (this
    person was already asked for on this trip, or for the app) or "none_left".
    An invite to the app itself (for_app) has no trip."""
    if for_app:
        already = db.query(models.Invite).filter_by(for_app=True, email=email).first()
    else:
        already = db.query(models.Invite).filter_by(trip_id=trip_id, email=email).first()
    if already is not None:
        return None, "duplicate"
    left = invites_left(db, inviter)
    asked_before = db.query(models.Invite).filter_by(invited_by_id=inviter.id, email=email).first() is not None
    if left is not None and left <= 0 and not asked_before:
        return None, "none_left"
    invite = models.Invite(trip_id=trip_id, email=email, role=role, invited_by_id=inviter.id, for_app=for_app)
    db.add(invite)
    try:
        db.commit()
    except IntegrityError:  # the same request raced in twice
        db.rollback()
        return None, "duplicate"
    db.refresh(invite)
    return invite, None


def get_app_invite(db: Session, email: str):
    """The request already made to let this email into the app itself, in any state."""
    return db.query(models.Invite).filter_by(for_app=True, email=email).first()


def get_declined_invites(db: Session):
    """Every declined request (to the app or to a trip), newest decision first, for the
    administrator to review and, if they like, allow again."""
    invites = (
        db.query(models.Invite)
        .options(joinedload(models.Invite.trip), joinedload(models.Invite.invited_by))
        .filter(models.Invite.status == models.INVITE_DECLINED)
        .order_by(models.Invite.decided_at.desc(), models.Invite.id.desc())
        .all()
    )
    for invite in invites:
        invite.invited_by_email = invite.invited_by.email
        invite.trip_name = invite.trip.location if invite.trip is not None else None
    return invites


def get_my_app_invites(db: Session, user: models.User):
    """The requests this person made to let people into the app itself, any state."""
    return db.query(models.Invite).filter_by(for_app=True, invited_by_id=user.id).order_by(models.Invite.id).all()


def get_trip_invite(db: Session, trip_id: int, email: str):
    """The request already made for this email on this trip, in any state."""
    return db.query(models.Invite).filter_by(trip_id=trip_id, email=email).first()


def get_invite(db: Session, invite_id: int):
    return (
        db.query(models.Invite)
        .options(joinedload(models.Invite.trip), joinedload(models.Invite.invited_by))
        .filter(models.Invite.id == invite_id)
        .first()
    )


def get_trip_invites(db: Session, trip_id: int):
    """Requests on this trip still to be (or already) answered - approved ones
    are people on the trip by now, so they show up as members instead."""
    return (
        db.query(models.Invite)
        .filter(models.Invite.trip_id == trip_id, models.Invite.status != models.INVITE_APPROVED)
        .order_by(models.Invite.id)
        .all()
    )


def known_people(db: Session, user: models.User):
    """Emails to suggest when this person is sharing something: everyone on a
    trip they own (other than themselves) and everyone they have asked to be
    let in (except those refused), lowercased and sorted. Only people they have
    already dealt with - never everyone who has an account here."""
    owned = (
        db.query(models.TripMember.trip_id)
        .filter(models.TripMember.user_id == user.id, models.TripMember.role == models.ROLE_OWNER)
        .subquery()
    )
    shared_with = (
        db.query(models.User.email)
        .join(models.TripMember, models.TripMember.user_id == models.User.id)
        .filter(models.TripMember.trip_id.in_(db.query(owned.c.trip_id)), models.User.id != user.id)
    )
    asked = db.query(models.Invite.email).filter(
        models.Invite.invited_by_id == user.id, models.Invite.status != models.INVITE_DECLINED
    )
    return sorted({email.lower() for (email,) in shared_with.union(asked).all()} - {user.email.lower()})


def pending_invite_count(db: Session) -> int:
    return db.query(func.count(models.Invite.id)).filter(models.Invite.status == models.INVITE_PENDING).scalar()


def get_pending_invites(db: Session):
    invites = (
        db.query(models.Invite)
        .options(joinedload(models.Invite.trip), joinedload(models.Invite.invited_by))
        .filter(models.Invite.status == models.INVITE_PENDING)
        .order_by(models.Invite.id)
        .all()
    )
    for invite in invites:
        invite.invited_by_email = invite.invited_by.email
        invite.trip_name = invite.trip.location if invite.trip is not None else None
    return invites


def cancel_invite(db: Session, invite: models.Invite) -> None:
    db.delete(invite)
    db.commit()


def grant_invite(db: Session, invite: models.Invite) -> models.Invite:
    """Record that the invited person was let in: they get an account (picked
    up when they first sign in) and their place on the trip."""
    user = create_account(db, invite.email)
    if invite.trip_id is not None:
        add_member(db, invite.trip_id, user, invite.role)  # None if they're somehow on it already
    invite.status = models.INVITE_APPROVED
    invite.decided_at = datetime.utcnow()
    db.commit()
    return invite


def decline_invite(db: Session, invite: models.Invite) -> models.Invite:
    invite.status = models.INVITE_DECLINED
    invite.decided_at = datetime.utcnow()
    db.commit()
    return invite


def categories_owned(db: Session, owner_id: int, category_ids) -> bool:
    """True if every id is a category of this owner (no stranger's labels
    on someone's content)."""
    ids = set(category_ids or [])
    if not ids:
        return True
    return db.query(models.Category).filter(models.Category.owner_id == owner_id, models.Category.id.in_(ids)).count() == len(ids)


def place_owned(db: Session, owner_id: int, place_id: int) -> bool:
    return db.query(models.Place.id).filter(models.Place.owner_id == owner_id, models.Place.id == place_id).first() is not None

# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------


def get_categories(db: Session, owner_id: int):
    return (
        db.query(models.Category)
        .filter(models.Category.owner_id == owner_id)
        .order_by(models.Category.sort_order, models.Category.id)
        .all()
    )


def get_category(db: Session, owner_id: int, category_id: int):
    return (
        db.query(models.Category)
        .filter(models.Category.owner_id == owner_id, models.Category.id == category_id)
        .first()
    )


def category_name_taken(db: Session, owner_id: int, name: str, exclude_id: Optional[int] = None) -> bool:
    query = db.query(models.Category).filter(
        models.Category.owner_id == owner_id, func.lower(models.Category.name) == name.strip().lower()
    )
    if exclude_id is not None:
        query = query.filter(models.Category.id != exclude_id)
    return query.first() is not None


def create_category(db: Session, owner_id: int, category: schemas.CategoryCreate):
    # Always appended to the end - same max+10 pattern as time-management's
    # Task.sort_order, leaving gaps so a later reorder only has to touch the
    # two rows being swapped.
    max_order = (
        db.query(func.max(models.Category.sort_order)).filter(models.Category.owner_id == owner_id).scalar() or 0
    )
    db_category = models.Category(owner_id=owner_id, **category.model_dump(), sort_order=max_order + 10)
    db.add(db_category)
    db.commit()
    db.refresh(db_category)
    return db_category


def reorder_categories(db: Session, owner_id: int, ordered_ids: List[int]):
    db_categories = (
        db.query(models.Category).filter(models.Category.owner_id == owner_id, models.Category.id.in_(ordered_ids)).all()
    )
    by_id = {c.id: c for c in db_categories}
    for index, category_id in enumerate(ordered_ids):
        db_category = by_id.get(category_id)
        if db_category is None:
            continue  # a stale id (deleted mid-drag elsewhere) - skip rather than error
        db_category.sort_order = (index + 1) * 10
    db.commit()
    return get_categories(db, owner_id)


def update_category(db: Session, owner_id: int, category_id: int, updates: schemas.CategoryUpdate):
    db_category = get_category(db, owner_id, category_id)
    if db_category is None:
        return None
    for field, value in updates.model_dump(exclude_unset=True).items():
        setattr(db_category, field, value)
    db.commit()
    db.refresh(db_category)
    return db_category


def delete_category(db: Session, owner_id: int, category_id: int) -> str:
    """Returns 'deleted', 'not_found', or 'in_use' (refuses to delete a
    category still assigned to any activity or place - the router turns
    'in_use' into a 409, matching time-management's own Category delete).
    Checks Activity.own_categories specifically (via the actual join
    table, not the resolving category_ids property, which isn't backed by
    a plain column) - a place-linked activity's effective categories are
    checked via its place instead."""
    db_category = get_category(db, owner_id, category_id)
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


def get_trip(db: Session, trip_id: int):
    return db.query(models.Trip).filter(models.Trip.id == trip_id).first()


def trip_cost_summary(db: Session, owner_id: int):
    """Per non-archived trip this person owns (trips shared with them are
    someone else's spending): summed cost of its non-archived linked
    activities plus its booked, non-archived stays, travel segments, and
    dog-care bookings. Costs are whole dollars in the DB; returned as
    cents. Consumed by the finances app's trip forecast (GET
    /api/trips/cost-summary)."""
    out = []
    for trip in db.query(models.Trip).filter(models.Trip.owner_id == owner_id, models.Trip.archived.is_(False)).all():
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


def create_trip(db: Session, user: models.User, trip: schemas.TripCreate):
    db_trip = models.Trip(owner_id=user.id, **trip.model_dump())
    db.add(db_trip)
    db.flush()
    db.add(models.TripMember(trip_id=db_trip.id, user_id=user.id, role=models.ROLE_OWNER))
    db.commit()
    return trip_view(db, get_membership(db, user.id, db_trip.id))


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

    # Unfinished invite requests go with the trip; approved ones stay (the
    # ORM nulls their trip_id) because the person was let in and still counts
    # against what their inviter may ask for.
    db.query(models.Invite).filter(
        models.Invite.trip_id == db_trip.id, models.Invite.status != models.INVITE_APPROVED
    ).delete()
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


def get_all_cities(db: Session, owner_id: int) -> List[str]:
    """Every distinct city in use, from Trip.city, Activity.own_city, and
    Place.city - powers the datalist on the trip/activity/place forms (so
    naming stays consistent no matter where you set it) and the city
    filter on activities.html. Queries own_city (the real column) rather
    than the resolving city property, which isn't a real column - a
    place-linked activity's city is already covered by scanning Place.city
    directly. Not a managed table like Category - just whatever strings
    are actually in use, alphabetized."""
    trip_cities = {
        c
        for (c,) in db.query(models.Trip.city)
        .filter(models.Trip.owner_id == owner_id, models.Trip.city.isnot(None), models.Trip.city != "")
        .distinct()
    }
    activity_cities = {
        c
        for (c,) in db.query(models.Activity.own_city)
        .filter(models.Activity.owner_id == owner_id, models.Activity.own_city.isnot(None), models.Activity.own_city != "")
        .distinct()
    }
    place_cities = {
        c
        for (c,) in db.query(models.Place.city)
        .filter(models.Place.owner_id == owner_id, models.Place.city.isnot(None), models.Place.city != "")
        .distinct()
    }
    return sorted(trip_cities | activity_cities | place_cities)


def get_activities(
    db: Session, owner_id: int, trip_id: Optional[int] = None, unassociated: bool = False
):
    """With a trip_id: everything on that trip (the caller's access to the
    trip has been checked - it may be someone else's, shared with them).
    Otherwise: the caller's own activities."""
    query = db.query(models.Activity)
    if trip_id is not None:
        query = query.join(
            models.TripActivity, models.TripActivity.activity_id == models.Activity.id
        ).filter(models.TripActivity.trip_id == trip_id)
    else:
        query = query.filter(models.Activity.owner_id == owner_id)
        if unassociated:
            linked_ids = db.query(models.TripActivity.activity_id)
            query = query.filter(~models.Activity.id.in_(linked_ids))
    return query.order_by(models.Activity.created_at.desc()).all()


def get_activity(db: Session, activity_id: int):
    return db.query(models.Activity).filter(models.Activity.id == activity_id).first()


def _resolve_categories(db: Session, category_ids, owner_id: Optional[int] = None):
    """[id, ...] -> [Category, ...] - the actual ORM objects a many-to-many
    relationship needs, since a plain @property setter (like the scalar
    own_* fields use) has no clean way to query the DB for them. Shared by
    activities and places."""
    if not category_ids:
        return []
    query = db.query(models.Category).filter(models.Category.id.in_(category_ids))
    if owner_id is not None:
        query = query.filter(models.Category.owner_id == owner_id)
    return query.all()


def create_activity(db: Session, owner_id: int, activity: schemas.ActivityCreate):
    """`owner_id` is whose content this is: the caller's own, or - for an
    activity an editor adds to a trip shared with them - the trip owner's."""
    data = activity.model_dump(exclude={"trip_id", "category_ids"})
    db_activity = models.Activity(owner_id=owner_id, **data)
    db_activity.own_categories = _resolve_categories(db, activity.category_ids, owner_id)
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
        db_activity.own_categories = _resolve_categories(db, category_ids, db_activity.owner_id)
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


def get_places(db: Session, owner_id: int):
    return db.query(models.Place).filter(models.Place.owner_id == owner_id).order_by(models.Place.name).all()


def get_place(db: Session, place_id: int):
    return db.query(models.Place).filter(models.Place.id == place_id).first()


def create_place(db: Session, owner_id: int, place: schemas.PlaceCreate):
    db_place = models.Place(owner_id=owner_id, **place.model_dump(exclude={"category_ids"}))
    db_place.categories = _resolve_categories(db, place.category_ids, owner_id)
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
        db_place.categories = _resolve_categories(db, category_ids, db_place.owner_id)
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
        owner_id=db_activity.owner_id,
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


def get_plan_linked_activities(db: Session, owner_id: int, plan_id: Optional[int] = None):
    query = db.query(models.Activity).filter(models.Activity.owner_id == owner_id, models.Activity.plan_id.isnot(None))
    if plan_id is not None:
        query = query.filter(models.Activity.plan_id == plan_id)
    return query.order_by(models.Activity.created_at).all()


def find_plan_activity(db: Session, owner_id: int, plan_id: int, trip_id: Optional[int]):
    """The activity already created from this plan in the same place the
    import would put it - on this trip, or unassociated when trip_id is
    None - so re-importing a plan is a no-op rather than a duplicate."""
    for activity in get_plan_linked_activities(db, owner_id, plan_id):
        trip_ids = [t.id for t in activity.trips]
        if (trip_id is None and not trip_ids) or trip_id in trip_ids:
            return activity
    return None


def create_activity_from_plan(db: Session, owner_id: int, plan: dict, trip_id: Optional[int]):
    """Copies a plan's details into a new activity (see models.Activity.
    plan_id on why it's a copy, not a live delegation), including its
    scraped preview so the card isn't blank until someone re-fetches."""
    db_activity = create_activity(
        db,
        owner_id,
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
