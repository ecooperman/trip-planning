import enum
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Integer, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from .database import Base


class ScrapeStatus(str, enum.Enum):
    not_started = "not_started"
    success = "success"
    failed = "failed"
    unsupported = "unsupported"


class TravelType(str, enum.Enum):
    flight = "flight"
    train = "train"
    rental_car = "rental_car"
    ferry = "ferry"
    other = "other"


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
    # Same reasoning as stays - a travel segment (flight, train, rental
    # car, ...) has no meaning outside the trip it was booked for.
    travel_segments = relationship(
        "TravelSegment", back_populates="trip", cascade="all, delete-orphan"
    )
    # Same reasoning as stays/travel_segments.
    dog_care_bookings = relationship(
        "DogCareBooking", back_populates="trip", cascade="all, delete-orphan"
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


class LocationDistance(Base):
    """A cached real walking/driving distance+duration between two
    "locations" (Google's Distance Matrix API - see app/distance.py) - an
    activity or a stay (a trip's lodging, useful as a fixed "home base" to
    compare activities against - see the distance-matrix endpoint and
    Compare distances on trip.html). Directional (origin -> destination),
    not a plain unordered pair - routing isn't always symmetric (one-way
    streets, etc.), so each direction is cached separately; cached per mode
    too, since walking and driving obviously differ.

    kind+id together identify one endpoint, rather than a single FK column
    - an id alone is ambiguous (activity 5 and stay 5 are different rows in
    different tables), and there's no single table a plain FK could point
    at here. Invalidated (deleted) whenever that location's address or
    city changes - see crud._invalidate_location_distances, called from
    update_activity/delete_activity and update_stay/delete_stay - a stale
    cached distance for an address that no longer applies would be
    actively misleading, not just outdated."""

    __tablename__ = "location_distances"

    id = Column(Integer, primary_key=True)
    origin_kind = Column(String, nullable=False)  # "activity" or "stay"
    origin_id = Column(Integer, nullable=False)
    destination_kind = Column(String, nullable=False)  # "activity" or "stay"
    destination_id = Column(Integer, nullable=False)
    mode = Column(String, nullable=False)  # "walking" or "driving"
    distance_meters = Column(Integer, nullable=False)
    distance_text = Column(String, nullable=False)
    duration_seconds = Column(Integer, nullable=False)
    duration_text = Column(String, nullable=False)
    computed_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint(
            "origin_kind", "origin_id", "destination_kind", "destination_id", "mode",
            name="uq_location_distance_pair_mode",
        ),
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
    # Whole dollars, same as Activity.cost. Feeds the finances app's trip
    # cost forecast (booked stays are counted; see GET /api/trips/cost-summary).
    cost = Column(Integer, nullable=True)
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


class TravelSegment(Base):
    """One leg of travel for a trip - a flight, train, rental car, ferry,
    etc. Always belongs to exactly one trip, same pattern as Stay (created
    from within the trip's page, deleted along with it). `type` picks the
    shape of the underlying travel; the rest of the fields are shared
    across every type rather than a separate table per type (a rental car
    doesn't have a departure/arrival airport in the flight sense, but
    departure_location/arrival_location read fine as "pickup"/"dropoff"
    too - same generalization Stay itself represents any lodging, not
    specifically "hotel").

    booked and archived are independent flags, same reasoning as Stay's -
    a trip can have several booked segments (an outbound and a return
    flight are both "booked" at once), and archived just means "not going
    with this option anymore," not "already traveled."

    No URL-scraping support (unlike Activity/Stay) - airline/rail/rental
    confirmation pages are far less uniform than the review-site sources
    those scrapers target, so `url` here is just a plain link to keep
    alongside the manually-entered details, not an auto-fill source.
    """

    __tablename__ = "travel_segments"

    id = Column(Integer, primary_key=True)
    trip_id = Column(Integer, ForeignKey("trips.id"), nullable=False)
    type = Column(Enum(TravelType), nullable=False, default=TravelType.flight)
    name = Column(String, nullable=False)
    url = Column(String, nullable=True)
    confirmation_number = Column(String, nullable=True)
    # Airline / rail line / rental company - free text, not an enum, for
    # the same reason Activity has no fixed list of venue names.
    carrier = Column(String, nullable=True)
    # Flight/train number, if applicable - blank for a rental car or ferry.
    number = Column(String, nullable=True)
    departure_location = Column(String, nullable=True)
    arrival_location = Column(String, nullable=True)
    # Both nullable (unlike Stay's required start_date/end_date) - a
    # segment is often added as a placeholder ("we're flying Delta") before
    # exact times are known, same reasoning as Activity.scheduled_start/end.
    departure_time = Column(DateTime, nullable=True)
    arrival_time = Column(DateTime, nullable=True)
    # Whole dollars, same as Activity.cost/Stay.cost. Feeds the finances
    # app's trip cost forecast (booked segments are counted; see
    # GET /api/trips/cost-summary).
    cost = Column(Integer, nullable=True)
    notes = Column(Text, nullable=True)
    booked = Column(Boolean, nullable=False, default=False)
    archived = Column(Boolean, nullable=False, default=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    trip = relationship("Trip", back_populates="travel_segments")


class DogCareBooking(Base):
    """Dog care (boarding, sitting, walking - a company or a private
    walker) covering some or all of a trip. Always belongs to exactly one
    trip, same pattern as Stay/TravelSegment - including the same
    date-range coverage concept Stay already has (see
    crud.get_trip_dog_care_coverage / GET /{trip_id}/dog-care-coverage):
    you want to know every day you're away is actually covered, the same
    way you want to know every night has lodging booked.

    booked/archived are independent flags, same reasoning as Stay's own -
    coverage counts any non-archived option (even one you're still
    deciding on), but cost (see crud.trip_cost_summary) only counts
    booked, non-archived ones - the same "candidate vs. confirmed" split
    used everywhere else costs are tracked in this app.

    invoice/instructions are optional raw file attachments (a PDF from the
    company, and your own written care instructions) - stored as plain
    binary blobs in SQLite alongside everything else, no parsing or
    processing of their contents at all. A public (no-login) link for
    instructions - so it's easy to send a walker who has no account here -
    is a deliberately deferred future addition, not built yet; both
    attachments are private downloads today, gated the same as every other
    route in this app (Cloudflare Access, not app-level auth).
    """

    __tablename__ = "dog_care_bookings"

    id = Column(Integer, primary_key=True)
    trip_id = Column(Integer, ForeignKey("trips.id"), nullable=False)
    company_name = Column(String, nullable=False)
    walker_name = Column(String, nullable=True)
    url = Column(String, nullable=True)
    cost = Column(Integer, nullable=True)
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=False)
    booked = Column(Boolean, nullable=False, default=False)
    archived = Column(Boolean, nullable=False, default=False)

    invoice_filename = Column(String, nullable=True)
    invoice_content_type = Column(String, nullable=True)
    invoice_data = Column(LargeBinary, nullable=True)

    instructions_filename = Column(String, nullable=True)
    instructions_content_type = Column(String, nullable=True)
    instructions_data = Column(LargeBinary, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    trip = relationship("Trip", back_populates="dog_care_bookings")
