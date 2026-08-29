import re
from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from .models import ScrapeStatus, TravelType

# Basic http(s) URL shape check - scheme + a non-empty host. Fields using
# this are optional free text usually pasted straight from a browser
# address bar, so this just needs to catch obvious typos before they reach
# the scraper, not be a fully RFC-3986-compliant parser.
URL_RE = re.compile(r"^https?://[^\s/$.?#][^\s]*$", re.IGNORECASE)


class UrlValidator(BaseModel):
    """Mixed into any schema with an optional `url` and/or `map_link` field
    (Activity, Stay - both create/read and update variants) so a PATCH
    can't write invalid data even though every field on the update schema
    is optional. check_fields=False lets this apply to whichever of the two
    field names a given model actually has - Stay has no map_link."""

    @field_validator("url", "map_link", check_fields=False)
    @classmethod
    def _check_url(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return None
        if not URL_RE.match(v):
            raise ValueError("URL must be a valid http(s) URL, e.g. https://example.com")
        return v


class CostValidator(BaseModel):
    @field_validator("cost", check_fields=False)
    @classmethod
    def _check_cost(cls, v: Optional[int]) -> Optional[int]:
        if v is None:
            return None
        if v < 0:
            raise ValueError("Cost must be a non-negative whole number of dollars")
        return v


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------


class CategoryBase(BaseModel):
    name: str
    color: str
    text_color: str = "dark"  # "dark" or "light"


class CategoryCreate(CategoryBase):
    pass


class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    color: Optional[str] = None
    text_color: Optional[str] = None
    # Set via the Manage Categories move-up/move-down buttons (see
    # crud.update_category) - not exposed on CategoryCreate, new categories
    # are always appended to the end (crud.create_category picks the value).
    sort_order: Optional[int] = None


class Category(CategoryBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sort_order: int


class CategoryReorderRequest(BaseModel):
    # The full new order, as category ids - not id/sort_order pairs, since
    # the client (a drag in Manage Categories) only ever knows the final
    # order, not particular sort_order values. The server resequences
    # everyone to clean 10/20/30... values from this (see
    # crud.reorder_categories), the same "just tell me the final order"
    # shape as time-management's Task reorder endpoint.
    ordered_ids: List[int]


# ---------------------------------------------------------------------------
# Instagram import
# ---------------------------------------------------------------------------


class InstagramPost(BaseModel):
    """One saved post as scraped from a collection's grid page (see the
    trip-clipper extension) - just what's passively present in the page
    the human is already looking at, no extra navigation."""

    permalink: str
    caption: str
    thumbnail_url: Optional[str] = None


class InstagramImportRequest(BaseModel):
    posts: List[InstagramPost]
    # Optional - omit to create unassociated activities, same as any other
    # creation path (see ActivityCreate.trip_id).
    trip_id: Optional[int] = None


class InstagramImportResult(BaseModel):
    posts_processed: int
    posts_skipped: int
    activities_created: int
    created_names: List[str]


# ---------------------------------------------------------------------------
# Trips
# ---------------------------------------------------------------------------


class TripBase(BaseModel):
    location: str
    city: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    archived: bool = False

    @model_validator(mode="after")
    def _check_date_order(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self


class TripCreate(TripBase):
    pass


class TripUpdate(BaseModel):
    location: Optional[str] = None
    city: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    archived: Optional[bool] = None

    @model_validator(mode="after")
    def _check_date_order(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self


class Trip(TripBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


class DateRangeCoverage(BaseModel):
    """Whether every day of a trip is covered by at least one non-archived
    record of some kind - a stay (GET /{trip_id}/stay-coverage) or a
    dog-care booking (GET /{trip_id}/dog-care-coverage) both return this
    same shape, since it's the same underlying question either way: does
    every day away have this thing arranged. has_dates is False (and
    covered defaults True) when the trip itself has no start/end date set
    - there's nothing to check yet."""

    has_dates: bool
    covered: bool
    missing_dates: List[str] = []


class TripCostSummary(BaseModel):
    """One row per non-archived trip: the summed cost of its non-archived
    linked activities, its booked non-archived stays, travel segments, and
    dog-care bookings, in cents. Consumed by the finances app (GET
    /api/trips/cost-summary) to forecast trip spend - not used by this
    app's own UI."""

    id: int
    location: str
    city: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    activities_cost_cents: int
    stays_cost_cents: int
    travel_cost_cents: int
    dog_care_cost_cents: int
    total_cost_cents: int


# ---------------------------------------------------------------------------
# Activities
# ---------------------------------------------------------------------------


class ScheduleValidator(BaseModel):
    """Shared scheduled_start/scheduled_end ordering check - same
    end-on-or-after-start rule used for Trip and Stay, mixed in wherever
    those two fields appear."""

    @model_validator(mode="after")
    def _check_schedule_order(self):
        start = getattr(self, "scheduled_start", None)
        end = getattr(self, "scheduled_end", None)
        if start and end and end < start:
            raise ValueError("scheduled_end must be on or after scheduled_start")
        return self


class ActivityBase(UrlValidator, CostValidator, ScheduleValidator):
    name: str
    description: Optional[str] = None
    url: Optional[str] = None
    cost: Optional[int] = None
    confirmation_number: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    phone_number: Optional[str] = None
    map_link: Optional[str] = None
    # Separate from `description` - notes is for the user's own reminders,
    # not a scraped/copied summary of the place.
    notes: Optional[str] = None
    # Null means "not yet scheduled" - see agenda.html, which lists
    # activities with no scheduled_start in an unscheduled sidebar.
    scheduled_start: Optional[datetime] = None
    scheduled_end: Optional[datetime] = None
    done: bool = False
    archived: bool = False
    category_id: Optional[int] = None


class ActivityCreate(ActivityBase):
    # Not a column on Activity - when set, the activity is associated to
    # this trip as part of creation (see crud.create_activity). Omit it (or
    # send null) to create an unassociated activity, as from /activities.html.
    trip_id: Optional[int] = None


class ActivityUpdate(UrlValidator, CostValidator, ScheduleValidator):
    name: Optional[str] = None
    description: Optional[str] = None
    url: Optional[str] = None
    cost: Optional[int] = None
    confirmation_number: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    phone_number: Optional[str] = None
    map_link: Optional[str] = None
    notes: Optional[str] = None
    scheduled_start: Optional[datetime] = None
    scheduled_end: Optional[datetime] = None
    done: Optional[bool] = None
    archived: Optional[bool] = None
    category_id: Optional[int] = None


class Activity(ActivityBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    scrape_status: ScrapeStatus
    scraped_title: Optional[str] = None
    scraped_description: Optional[str] = None
    scraped_image_url: Optional[str] = None
    scraped_at: Optional[datetime] = None
    scrape_error: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    # Today an activity has at most one trip (enforced in crud, not here),
    # but this stays a list so the schema doesn't have to change if that
    # rule is relaxed later.
    trips: List[Trip] = []


# ---------------------------------------------------------------------------
# Stays
# ---------------------------------------------------------------------------


class StayBase(UrlValidator, CostValidator):
    name: str
    description: Optional[str] = None
    url: Optional[str] = None
    address: Optional[str] = None
    cost: Optional[int] = None
    start_date: datetime
    end_date: datetime
    booked: bool = False

    @model_validator(mode="after")
    def _check_date_order(self):
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self


class StayCreate(StayBase):
    trip_id: int


class StayUpdate(UrlValidator, CostValidator):
    name: Optional[str] = None
    description: Optional[str] = None
    url: Optional[str] = None
    address: Optional[str] = None
    cost: Optional[int] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    booked: Optional[bool] = None
    archived: Optional[bool] = None

    @model_validator(mode="after")
    def _check_date_order(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self


class Stay(StayBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    trip_id: int
    archived: bool
    scrape_status: ScrapeStatus
    scraped_title: Optional[str] = None
    scraped_description: Optional[str] = None
    scraped_image_url: Optional[str] = None
    scraped_at: Optional[datetime] = None
    scrape_error: Optional[str] = None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Travel segments (flights, trains, rental cars, ferries - see models.TravelSegment)
# ---------------------------------------------------------------------------


class TravelSegmentBase(UrlValidator, CostValidator):
    type: TravelType = TravelType.flight
    name: str
    url: Optional[str] = None
    confirmation_number: Optional[str] = None
    carrier: Optional[str] = None
    number: Optional[str] = None
    departure_location: Optional[str] = None
    arrival_location: Optional[str] = None
    departure_time: Optional[datetime] = None
    arrival_time: Optional[datetime] = None
    cost: Optional[int] = None
    notes: Optional[str] = None
    booked: bool = False

    @model_validator(mode="after")
    def _check_time_order(self):
        # Both optional (see models.TravelSegment) - only checked when both
        # happen to be set, same conditional pattern as StayUpdate's own
        # date-order check below.
        if self.departure_time and self.arrival_time and self.arrival_time < self.departure_time:
            raise ValueError("arrival_time must be on or after departure_time")
        return self


class TravelSegmentCreate(TravelSegmentBase):
    trip_id: int


class TravelSegmentUpdate(UrlValidator, CostValidator):
    type: Optional[TravelType] = None
    name: Optional[str] = None
    url: Optional[str] = None
    confirmation_number: Optional[str] = None
    carrier: Optional[str] = None
    number: Optional[str] = None
    departure_location: Optional[str] = None
    arrival_location: Optional[str] = None
    departure_time: Optional[datetime] = None
    arrival_time: Optional[datetime] = None
    cost: Optional[int] = None
    notes: Optional[str] = None
    booked: Optional[bool] = None
    archived: Optional[bool] = None

    @model_validator(mode="after")
    def _check_time_order(self):
        if self.departure_time and self.arrival_time and self.arrival_time < self.departure_time:
            raise ValueError("arrival_time must be on or after departure_time")
        return self


class TravelSegment(TravelSegmentBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    trip_id: int
    archived: bool
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Dog care bookings (see models.DogCareBooking)
# ---------------------------------------------------------------------------


class DogCareBookingBase(UrlValidator, CostValidator):
    company_name: str
    walker_name: Optional[str] = None
    url: Optional[str] = None
    cost: Optional[int] = None
    start_date: datetime
    end_date: datetime
    booked: bool = False

    @model_validator(mode="after")
    def _check_date_order(self):
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self


class DogCareBookingCreate(DogCareBookingBase):
    trip_id: int


class DogCareBookingUpdate(UrlValidator, CostValidator):
    company_name: Optional[str] = None
    walker_name: Optional[str] = None
    url: Optional[str] = None
    cost: Optional[int] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    booked: Optional[bool] = None
    archived: Optional[bool] = None

    @model_validator(mode="after")
    def _check_date_order(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self


class DogCareBooking(DogCareBookingBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    trip_id: int
    archived: bool
    # Attachment presence/filename only - the raw bytes never go in a JSON
    # response (see the dedicated GET .../attachments/{kind} download
    # route instead, which streams them with the right content type).
    invoice_filename: Optional[str] = None
    instructions_filename: Optional[str] = None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Distance (Google Distance Matrix - see app/distance.py)
# ---------------------------------------------------------------------------


class LocationRef(BaseModel):
    """One endpoint of a distance comparison - an activity or a stay (a
    trip's lodging, usable as a fixed "home base" - see
    routers/distance.py). kind+id together identify it, the same
    composite key models.LocationDistance itself is keyed on."""

    kind: Literal["activity", "stay"]
    id: int


class DistanceMatrixRequest(BaseModel):
    origins: List[LocationRef]
    destinations: List[LocationRef]
    mode: Literal["walking", "driving"] = "walking"
    # Bypasses the cache (see LocationDistance) and re-asks Google for
    # every requested pair, overwriting whatever was cached - same idea as
    # an activity's manual re-scrape button, for when you want to double-
    # check a result rather than trust what's on file (a place moved, a
    # road changed, or you just want to be sure).
    force_refresh: bool = False


class DistancePair(BaseModel):
    origin_kind: Literal["activity", "stay"]
    origin_id: int
    origin_label: str
    destination_kind: Literal["activity", "stay"]
    destination_id: int
    destination_label: str
    distance_meters: Optional[int] = None
    distance_text: Optional[str] = None
    duration_seconds: Optional[int] = None
    duration_text: Optional[str] = None
    # Set (instead of the fields above) when this pair couldn't be
    # computed - "no address" (the location has neither an address nor a
    # city to fall back to) or "no route found" (Google couldn't resolve
    # one or both addresses, or there's genuinely no route for the given
    # mode - e.g. across water on foot).
    skipped_reason: Optional[str] = None
    # True if this result was read from LocationDistance rather than just
    # spent on a live Google Distance Matrix call - None for a skipped pair,
    # where the concept doesn't apply (a "no address" skip never reaches
    # Google or the cache either way; a "no route found" pair is never
    # cached at all, so it's freshly re-checked every time regardless).
    from_cache: Optional[bool] = None


class DistanceMatrixResponse(BaseModel):
    pairs: List[DistancePair]


class DistanceModeInfo(BaseModel):
    distance_text: str
    duration_text: str


class ActivityDistanceEntry(BaseModel):
    """One cached distance between this activity and another location
    (another activity, or a stay) - see GET /api/activities/{id}/distances.
    direction is "to" (this activity was the origin when it was computed)
    or "from" (this activity was the destination) - shown separately
    rather than merged, since which direction got cached depends on how
    the comparison was run (a many-candidates-vs-one-anchor comparison,
    for instance, only ever caches candidates -> anchor, never the
    reverse) and isn't necessarily the same distance/time either way
    (one-way streets, etc.)."""

    other_kind: Literal["activity", "stay"]
    other_id: int
    other_name: str
    other_city: Optional[str] = None
    direction: Literal["to", "from"]
    walking: Optional[DistanceModeInfo] = None
    driving: Optional[DistanceModeInfo] = None
