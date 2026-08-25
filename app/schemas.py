import re
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from .models import ScrapeStatus

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


class StayCoverage(BaseModel):
    """Whether every day of a trip is covered by at least one non-archived
    stay. has_dates is False (and covered defaults True) when the trip
    itself has no start/end date set - there's nothing to check yet."""

    has_dates: bool
    covered: bool
    missing_dates: List[str] = []


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


class StayBase(UrlValidator):
    name: str
    description: Optional[str] = None
    url: Optional[str] = None
    address: Optional[str] = None
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


class StayUpdate(UrlValidator):
    name: Optional[str] = None
    description: Optional[str] = None
    url: Optional[str] = None
    address: Optional[str] = None
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
