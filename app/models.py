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
    phone_number = Column(String, nullable=True)
    map_link = Column(String, nullable=True)
    # Separate from `description` (which tends to hold a scraped/copied
    # summary of the place) - notes is for the user's own reminders.
    notes = Column(Text, nullable=True)
    done = Column(Boolean, nullable=False, default=False)

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
