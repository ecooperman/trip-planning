import enum
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from .database import Base


class ScrapeStatus(str, enum.Enum):
    not_started = "not_started"
    success = "success"
    failed = "failed"
    unsupported = "unsupported"


class Category(Base):
    """A user-managed label (name + color) an activity can optionally
    belong to - same shape as time-management's Category, except here
    Activity.category_id is nullable: activities are often created quickly
    (tap-to-create on the agenda, the trip-clipper extension) without
    picking one, and that's a normal, expected state here, not just a
    defensive fallback."""

    __tablename__ = "categories"

    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    color = Column(String, nullable=False)
    # "dark" or "light" - which text color reads legibly against `color`,
    # picked by the user rather than computed, since contrast is subjective
    # and cheap to just ask for.
    text_color = Column(String, nullable=False, default="dark", server_default="dark")
    # User-controlled display order (Manage Categories' reorder buttons) -
    # drives both that list's own order and "sort by category" on the
    # activities/agenda pages, so reordering categories once affects both
    # places at once. Same append-to-the-end-with-gaps pattern as Task's
    # sort_order in time-management (new rows get max+10, see
    # crud.create_category) - not a plain 0,1,2... sequence, so a reorder
    # only ever has to touch the two swapped rows.
    sort_order = Column(Integer, nullable=False, default=0, server_default="0")

    activities = relationship("Activity", back_populates="category")


class TripActivity(Base):
    """Join table linking trips and activities.

    Modeled as many-to-many from day one - an activity could in principle
    belong to several trips - even though today the API only ever lets an
    activity be linked to one trip at a time (enforced in
    crud.associate_activity, not by the schema). Relaxing that rule later
    is a one-line change here, not a migration.
    """

    __tablename__ = "trip_activities"

    trip_id = Column(Integer, ForeignKey("trips.id"), primary_key=True)
    activity_id = Column(Integer, ForeignKey("activities.id"), primary_key=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Trip(Base):
    __tablename__ = "trips"

    id = Column(Integer, primary_key=True)
    location = Column(String, nullable=False)
    # A clean city name, separate from `location` - `location` is more of a
    # trip title ("Toronto Music," "Raj's Cabin in New Lisbon Wisconsin")
    # than a reliable city string, same reason Activity.city (below) isn't
    # parsed out of addresses either. Used to bulk-fill Activity.city for
    # activities that don't have their own yet (see crud.fill_missing_activity_cities).
    city = Column(String, nullable=True)
    start_date = Column(DateTime, nullable=True)
    end_date = Column(DateTime, nullable=True)
    archived = Column(Boolean, nullable=False, default=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    activities = relationship(
        "Activity", secondary="trip_activities", back_populates="trips"
    )
    # Unlike activities, a stay has no meaning outside its trip - so this is
    # a plain one-to-many (not a join table), and deleting a trip deletes
    # its stays with it rather than leaving them orphaned.
    stays = relationship(
        "Stay", back_populates="trip", cascade="all, delete-orphan"
    )


class Activity(Base):
    __tablename__ = "activities"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    url = Column(String, nullable=True)
    cost = Column(Integer, nullable=True)
    confirmation_number = Column(String, nullable=True)
    address = Column(String, nullable=True)
    # Explicit, not parsed out of `address` - real addresses in this app
    # come from too many different sources (manual entry, Yelp scrapes,
    # Instagram imports) with wildly inconsistent formatting for a comma-
    # split to reliably find the city (confirmed against real data before
    # building this: some have no comma at all, some have the city as the
    # last segment rather than the second). Lets you filter to "what did we
    # skip in a city we're revisiting" on activities.html.
    city = Column(String, nullable=True)
    phone_number = Column(String, nullable=True)
    map_link = Column(String, nullable=True)
    # Separate from `description` (which tends to hold a scraped/copied
    # summary of the place) - notes is for the user's own reminders.
    notes = Column(Text, nullable=True)
    done = Column(Boolean, nullable=False, default=False)
    # Independent of done, same reasoning as Stay.archived - a trip you
    # archive cascades to archive its activities (see crud.update_trip),
    # but an activity can also be archived on its own. "Didn't do this and
    # never will" is archived, not done; "did this" is done, not archived;
    # an activity can't sensibly be both, but nothing enforces that at the
    # schema level - it's just never set that way in practice.
    archived = Column(Boolean, nullable=False, default=False)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)

    # Both optional - null means "not yet scheduled," which is what puts it
    # in the agenda page's unscheduled sidebar rather than a day column.
    # Duration is end-start rather than a stored field, same as Stay.
    scheduled_start = Column(DateTime, nullable=True)
    scheduled_end = Column(DateTime, nullable=True)

    scrape_status = Column(Enum(ScrapeStatus), nullable=False, default=ScrapeStatus.not_started)
    scraped_title = Column(String, nullable=True)
    scraped_description = Column(String, nullable=True)
    scraped_image_url = Column(String, nullable=True)
    scraped_at = Column(DateTime, nullable=True)
    scrape_error = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    trips = relationship(
        "Trip", secondary="trip_activities", back_populates="activities"
    )
    category = relationship("Category", back_populates="activities")


class Stay(Base):
    """A lodging option (or booking) for a trip. Always belongs to exactly
    one trip - created from within the trip's page, not standalone.

    booked and archived are independent per-stay flags, not mutually
    exclusive across a trip's stays - a trip can have several booked stays
    at once (different, non-overlapping date ranges). archived is a manual
    "not considering this option anymore" marker (see the stay's own
    Archive/Unarchive button), never an automatic side effect of another
    stay being booked.
    """

    __tablename__ = "stays"

    id = Column(Integer, primary_key=True)
    trip_id = Column(Integer, ForeignKey("trips.id"), nullable=False)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    url = Column(String, nullable=True)
    address = Column(String, nullable=True)
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=False)
    booked = Column(Boolean, nullable=False, default=False)
    archived = Column(Boolean, nullable=False, default=False)

    scrape_status = Column(Enum(ScrapeStatus), nullable=False, default=ScrapeStatus.not_started)
    scraped_title = Column(String, nullable=True)
    scraped_description = Column(String, nullable=True)
    scraped_image_url = Column(String, nullable=True)
    scraped_at = Column(DateTime, nullable=True)
    scrape_error = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    trip = relationship("Trip", back_populates="stays")
