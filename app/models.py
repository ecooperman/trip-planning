import enum
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Enum, Float, ForeignKey, Integer, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from .database import Base


class ScrapeStatus(str, enum.Enum):
    not_started = "not_started"
    success = "success"
    failed = "failed"
    unsupported = "unsupported"


class CriterionVerdict(str, enum.Enum):
    """How a candidate stay scores against one of a trip's comparison
    criteria (see TripStayCriterion). Stored as a plain string column, not
    a DB Enum - same lightweight treatment as LocationDistance.mode -
    since the set is tiny and stable and the schema layer already
    validates it. "unknown" is the implicit default for any (stay,
    criterion) pair with no row yet, so the comparison grid always has a
    value to render even before anyone's judged it."""

    yes = "yes"
    partial = "partial"
    no = "no"
    unknown = "unknown"


class TravelType(str, enum.Enum):
    flight = "flight"
    train = "train"
    rental_car = "rental_car"
    ferry = "ferry"
    other = "other"


class Category(Base):
    """A user-managed label (name + color) an activity or place can
    optionally belong to - zero, one, or several at once (see
    ActivityCategory/PlaceCategory below) - same shape as time-management's
    Category, except here it's optional and multi-valued: activities are
    often created quickly (tap-to-create on the agenda, the web-capture
    extension) without picking one, and a place can genuinely be more than
    one thing at once (a cafe that's also a bookstore), so forcing a single
    choice was the wrong constraint, not just a missing nice-to-have."""

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

    # back_populates targets Activity.own_categories/Place.categories (not
    # "activities"/"places" mirrored 1:1 - these are many-to-many now, see
    # ActivityCategory/PlaceCategory below and Activity's own docstring on
    # why the activity side is "own_categories" specifically, not
    # "categories").
    activities = relationship("Activity", secondary="activity_categories", back_populates="own_categories")
    places = relationship("Place", secondary="place_categories", back_populates="categories")


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


class ActivityCategory(Base):
    """Join table linking activities and categories - many-to-many, an
    activity can carry zero or several category tags at once (see
    Category's docstring). Links Activity's own_categories specifically -
    a place-linked activity's *effective* categories come through its
    place instead (Activity.category_ids), but the activity's own row here
    stays untouched either way, same "dormant, not deleted" treatment as
    its other own_* fields."""

    __tablename__ = "activity_categories"

    activity_id = Column(Integer, ForeignKey("activities.id"), primary_key=True)
    category_id = Column(Integer, ForeignKey("categories.id"), primary_key=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class PlaceCategory(Base):
    """Join table linking places and categories - many-to-many, same
    reasoning as ActivityCategory."""

    __tablename__ = "place_categories"

    place_id = Column(Integer, ForeignKey("places.id"), primary_key=True)
    category_id = Column(Integer, ForeignKey("categories.id"), primary_key=True)
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
    # ISO 4217 code the trip's costs are reasoned about in - what a stay's
    # imported foreign-currency price gets converted to (via the per-stay
    # fx_rate) for an apples-to-apples comparison, and the unit the
    # existing whole-dollar `cost` fields are already assumed to be in.
    # Defaults to USD; only really matters to set for an international trip.
    home_currency = Column(String, nullable=False, default="USD", server_default="USD")

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
    # The user-defined checklist this trip's candidate stays are scored
    # against on compare.html - see TripStayCriterion. Trip-scoped (unlike
    # the cross-trip Category list) because "walkable to the conference
    # venue" or "sleeps 6" only means anything for one specific trip.
    stay_criteria = relationship(
        "TripStayCriterion",
        back_populates="trip",
        cascade="all, delete-orphan",
        order_by="TripStayCriterion.sort_order",
    )


class Activity(Base):
    """A specific planned/actual visit - "we're going to Cacao on
    Thursday at 7pm," not "Cacao" itself. Venue details (name, address,
    url, category, ...) can either live on the activity directly (the
    original, still fully supported shape) or be delegated to a linked
    Place (see place_id) - a reusable, cross-trip record of the place
    itself, so a spot you love isn't re-typed from scratch every time you
    plan another visit there.

    The delegation is implemented as a set of properties (name, address,
    city, etc. below) shadowing renamed "own_*" columns - own_name holds
    this activity's own data (used whenever place_id is null, exactly the
    original behavior), while the property resolves to place.name instead
    once place_id is set. This is deliberately transparent to every
    existing caller: schemas.py's Pydantic serialization, distance.py's
    address_query_for, export.py's row builder, and the whole frontend all
    just read activity.address/activity.city/etc. same as before and get
    the right value either way, with no awareness that a Place might be
    involved. See crud.promote_activity_to_place for how an activity
    starts using a place instead of its own columns (copies own_* into a
    new Place, then clears own_* here), and crud.update_activity for the
    same clearing when an activity is linked to an *existing* place via a
    plain PATCH.

    rating/review are per-visit, deliberately never delegated to a place -
    two visits to the same place can go completely differently (a great
    first time, a disappointing second), so each activity keeps its own
    independent rating even when it shares a place with others. Place has
    its own separate rating/review for "our overall take on this place."
    """

    __tablename__ = "activities"

    id = Column(Integer, primary_key=True)
    # nullable despite representing a required-when-unlinked field (see the
    # name property below and schemas.ActivityCreate's validator) - a
    # place-linked activity legitimately has no own_name at all.
    own_name = Column("name", String, nullable=True)
    own_description = Column("description", Text, nullable=True)
    own_url = Column("url", String, nullable=True)
    cost = Column(Integer, nullable=True)
    confirmation_number = Column(String, nullable=True)
    own_address = Column("address", String, nullable=True)
    # Explicit, not parsed out of `address` - real addresses in this app
    # come from too many different sources (manual entry, Yelp scrapes,
    # Instagram imports) with wildly inconsistent formatting for a comma-
    # split to reliably find the city (confirmed against real data before
    # building this: some have no comma at all, some have the city as the
    # last segment rather than the second). Lets you filter to "what did we
    # skip in a city we're revisiting" on activities.html.
    own_city = Column("city", String, nullable=True)
    own_phone_number = Column("phone_number", String, nullable=True)
    own_map_link = Column("map_link", String, nullable=True)
    # Separate from `description` (which tends to hold a scraped/copied
    # summary of the place) - notes is for the user's own reminders about
    # this specific visit.
    notes = Column(Text, nullable=True)
    # 1-5, this visit's own rating - see the class docstring on why this
    # never delegates to a linked place's rating.
    rating = Column(Integer, nullable=True)
    review = Column(Text, nullable=True)
    done = Column(Boolean, nullable=False, default=False)
    # Independent of done, same reasoning as Stay.archived - a trip you
    # archive cascades to archive its activities (see crud.update_trip),
    # but an activity can also be archived on its own. "Didn't do this and
    # never will" is archived, not done; "did this" is done, not archived;
    # an activity can't sensibly be both, but nothing enforces that at the
    # schema level - it's just never set that way in practice.
    archived = Column(Boolean, nullable=False, default=False)

    place_id = Column(Integer, ForeignKey("places.id"), nullable=True)

    # The social-planning (plans.evancooperman.com) Plan this activity was
    # created from, if any - see routers/plan_links.py. A plain integer, not
    # a ForeignKey: the plan lives in a different app's database. Set once
    # at creation (the plan's name/description/url are copied over, not
    # delegated live like place_id) and never edited, so the plans app can
    # ask "where did plan 42 end up?" via GET /api/plan-links.
    plan_id = Column(Integer, nullable=True, index=True)

    # Both optional - null means "not yet scheduled," which is what puts it
    # in the agenda page's unscheduled sidebar rather than a day column.
    # Duration is end-start rather than a stored field, same as Stay.
    scheduled_start = Column(DateTime, nullable=True)
    scheduled_end = Column(DateTime, nullable=True)

    # This activity's own scrape state - always independent of any linked
    # place (a place gets its own separate scrape_status/scraped_* columns
    # for scraping its own url, see Place below). Once place_id is set
    # these just go dormant/unused - scraping a preview for a place-linked
    # activity happens on the place instead, since that's where the url
    # now lives.
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
    # This activity's own category tags - always independent of any linked
    # place's, same "own_* is dormant, not deleted, once place-linked"
    # treatment as every other own_* field (see the class docstring and
    # the category_ids property below, which is what actually resolves
    # which set is "effective").
    own_categories = relationship("Category", secondary="activity_categories", back_populates="activities")
    place = relationship("Place", back_populates="activities")

    # --- delegating properties - see the class docstring -------------------

    @property
    def name(self):
        return self.place.name if self.place_id else self.own_name

    @name.setter
    def name(self, value):
        self.own_name = value

    @property
    def description(self):
        return self.place.description if self.place_id else self.own_description

    @description.setter
    def description(self, value):
        self.own_description = value

    @property
    def url(self):
        return self.place.url if self.place_id else self.own_url

    @url.setter
    def url(self, value):
        self.own_url = value

    @property
    def address(self):
        return self.place.address if self.place_id else self.own_address

    @address.setter
    def address(self, value):
        self.own_address = value

    @property
    def city(self):
        return self.place.city if self.place_id else self.own_city

    @city.setter
    def city(self, value):
        self.own_city = value

    @property
    def phone_number(self):
        return self.place.phone_number if self.place_id else self.own_phone_number

    @phone_number.setter
    def phone_number(self, value):
        self.own_phone_number = value

    @property
    def map_link(self):
        return self.place.map_link if self.place_id else self.own_map_link

    @map_link.setter
    def map_link(self, value):
        self.own_map_link = value

    @property
    def category_ids(self):
        # Read-only, unlike the scalar properties above - setting a
        # many-to-many relationship from a list of ids needs a DB session
        # to look up the actual Category rows, which a plain property
        # setter has no clean access to. Writes go through
        # crud._set_activity_categories instead.
        if self.place_id:
            return [c.id for c in self.place.categories] if self.place else []
        return [c.id for c in self.own_categories]


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


class Place(Base):
    """A real-world place - a restaurant, cafe, museum, shop - that
    exists independent of any one trip or visit, so it can be pulled from
    a reusable list and linked to multiple activities over time instead of
    re-entering the same name/address/url every time you plan another
    visit there. Not trip-scoped at all (unlike Stay/TravelSegment/
    DogCareBooking) - the same place is just as relevant on a future trip
    back to the same city.

    rating/review here are this place's own overall rating ("our take on
    this place in general") - see Activity's rating/review for the
    separate per-visit rating, which can differ from this one (a great
    first visit, a worse second one) and from each other.
    """

    __tablename__ = "places"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    url = Column(String, nullable=True)
    address = Column(String, nullable=True)
    city = Column(String, nullable=True)
    phone_number = Column(String, nullable=True)
    map_link = Column(String, nullable=True)

    rating = Column(Integer, nullable=True)
    review = Column(Text, nullable=True)

    scrape_status = Column(Enum(ScrapeStatus), nullable=False, default=ScrapeStatus.not_started)
    scraped_title = Column(String, nullable=True)
    scraped_description = Column(String, nullable=True)
    scraped_image_url = Column(String, nullable=True)
    scraped_at = Column(DateTime, nullable=True)
    scrape_error = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    categories = relationship("Category", secondary="place_categories", back_populates="places")
    activities = relationship("Activity", back_populates="place")
    images = relationship("PlaceImage", back_populates="place", cascade="all, delete-orphan")

    @property
    def category_ids(self):
        # schemas.Place reads this (Pydantic's from_attributes getattr's
        # field names off the ORM object) - `categories` itself holds the
        # actual Category objects, not their ids, and writes go through
        # crud._resolve_categories the same way Activity's do (see that
        # class's category_ids docstring on why a plain property setter
        # can't do this on its own).
        return [c.id for c in self.categories]


class PlaceImage(Base):
    """One photo attached to a Place - plain binary storage (same pattern
    as DogCareBooking's invoice/instructions), no processing of any kind;
    the browser does all the scaling/thumbnailing when it's rendered as an
    <img>. One-to-many (unlike DogCareBooking's single invoice/
    instructions slots) since a place can reasonably have several photos,
    ordered by upload time (created_at) - oldest first, no separate
    sort_order column since manual reordering isn't a need here yet."""

    __tablename__ = "place_images"

    id = Column(Integer, primary_key=True)
    place_id = Column(Integer, ForeignKey("places.id"), nullable=False)
    filename = Column(String, nullable=False)
    content_type = Column(String, nullable=False)
    data = Column(LargeBinary, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    place = relationship("Place", back_populates="images")


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
    # Whole dollars in the trip's home_currency, same as Activity.cost.
    # Feeds the finances app's trip cost forecast (booked stays are
    # counted; see GET /api/trips/cost-summary). The price-worksheet
    # fields below are the scratch input that *produces* this number for a
    # candidate stay - "Use as cost" on compare.html copies the computed
    # estimated_total here; nothing writes it automatically.
    cost = Column(Integer, nullable=True)
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=False)
    booked = Column(Boolean, nullable=False, default=False)
    archived = Column(Boolean, nullable=False, default=False)

    # --- price worksheet, mostly filled by the URL/screenshot importer
    # (see app/stay_extraction.py) and then eyeballed/corrected by hand.
    # Amounts are in listing_currency (None = the trip's home_currency).
    # A listing usually gives EITHER a per-night rate OR an all-in total
    # for the dates, not both - estimated_total below copes with either.
    listing_currency = Column(String, nullable=True)  # ISO 4217, e.g. "EUR"
    nightly_price = Column(Float, nullable=True)
    total_price = Column(Float, nullable=True)
    extra_fees = Column(Float, nullable=True)  # cleaning + service + taxes, lumped
    # Home-currency units per 1 listing-currency unit (manual - no live FX
    # feed by design). None is treated as 1.0, correct whenever
    # listing_currency is None/blank or already the home currency.
    fx_rate = Column(Float, nullable=True)
    bedrooms = Column(Integer, nullable=True)
    bathrooms = Column(Float, nullable=True)  # half-baths are real
    sleeps = Column(Integer, nullable=True)
    # Set by the bulk importer, cleared the first time the stay is saved
    # from its edit pane - "these numbers came from an AI read of the page
    # and nobody's checked them yet," surfaced as a badge on the card and
    # the compare grid.
    needs_review = Column(Boolean, nullable=False, default=False, server_default="0")

    scrape_status = Column(Enum(ScrapeStatus), nullable=False, default=ScrapeStatus.not_started)
    scraped_title = Column(String, nullable=True)
    scraped_description = Column(String, nullable=True)
    scraped_image_url = Column(String, nullable=True)
    scraped_at = Column(DateTime, nullable=True)
    scrape_error = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    trip = relationship("Trip", back_populates="stays")
    criterion_verdicts = relationship(
        "StayCriterionVerdict", back_populates="stay", cascade="all, delete-orphan"
    )

    @property
    def nights(self) -> int:
        if not self.start_date or not self.end_date:
            return 0
        return max((self.end_date - self.start_date).days, 0)

    @property
    def estimated_total(self):
        """Best-guess all-in cost in the trip's home currency, from the
        price worksheet - None until there's enough to compute one.
        total_price wins over nightly_price*nights when both are set."""
        base = self.total_price
        if base is None and self.nightly_price is not None:
            base = self.nightly_price * self.nights
        if base is None:
            return None
        return round((base + (self.extra_fees or 0)) * (self.fx_rate or 1.0))


class TripStayCriterion(Base):
    """One row of a trip's "what matters for lodging on this trip"
    checklist - the columns of the comparison grid on compare.html. Each
    candidate stay gets a per-criterion verdict (see StayCriterionVerdict).

    weight scales how much a met criterion contributes to a stay's score;
    must_have flips it from "nice to have" to "disqualifying if not met" -
    a stay that fails any must_have is flagged regardless of its score.
    sort_order is the same append-with-gaps (max+10) pattern as Category,
    so reordering only touches the two swapped rows.
    """

    __tablename__ = "trip_stay_criteria"

    id = Column(Integer, primary_key=True)
    trip_id = Column(Integer, ForeignKey("trips.id"), nullable=False)
    label = Column(String, nullable=False)
    weight = Column(Integer, nullable=False, default=1, server_default="1")
    must_have = Column(Boolean, nullable=False, default=False, server_default="0")
    sort_order = Column(Integer, nullable=False, default=0, server_default="0")
    created_at = Column(DateTime, default=datetime.utcnow)

    trip = relationship("Trip", back_populates="stay_criteria")
    verdicts = relationship(
        "StayCriterionVerdict", back_populates="criterion", cascade="all, delete-orphan"
    )


class StayCriterionVerdict(Base):
    """How one candidate stay measures up against one of its trip's
    criteria - yes / partial / no / unknown (see models.CriterionVerdict).
    Composite-keyed on (stay_id, criterion_id), same shape as the
    TripActivity / ActivityCategory join classes. A missing row means
    "unknown" - the grid never requires every cell to be filled in.
    """

    __tablename__ = "stay_criterion_verdicts"

    stay_id = Column(Integer, ForeignKey("stays.id"), primary_key=True)
    criterion_id = Column(Integer, ForeignKey("trip_stay_criteria.id"), primary_key=True)
    verdict = Column(String, nullable=False, default="unknown", server_default="unknown")
    note = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    stay = relationship("Stay", back_populates="criterion_verdicts")
    criterion = relationship("TripStayCriterion", back_populates="verdicts")


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
