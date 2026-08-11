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
    """Mixed into any schema with an optional `url` field (Activity, Stay -
    both create/read and update variants) so a PATCH can't write invalid
    data even though every field on the update schema is optional."""

    @field_validator("url", check_fields=False)
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
# Trips
# ---------------------------------------------------------------------------


class TripBase(BaseModel):
    location: str
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


class ActivityBase(UrlValidator, CostValidator):
    name: str
    description: Optional[str] = None
    url: Optional[str] = None
    cost: Optional[int] = None
    confirmation_number: Optional[str] = None


class ActivityCreate(ActivityBase):
    # Not a column on Activity - when set, the activity is associated to
    # this trip as part of creation (see crud.create_activity). Omit it (or
    # send null) to create an unassociated activity, as from /activities.html.
    trip_id: Optional[int] = None


class ActivityUpdate(UrlValidator, CostValidator):
    name: Optional[str] = None
    description: Optional[str] = None
    url: Optional[str] = None
    cost: Optional[int] = None
    confirmation_number: Optional[str] = None


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
