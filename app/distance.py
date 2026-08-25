"""Real walking/driving distance and duration between two or more
activities, via Google's Distance Matrix API - not the LLM. An LLM has no
actual map to consult; asked "how far apart are these two addresses," it's
pattern-matching against general geographic knowledge, not doing real
geometry, and a wrong answer here isn't a stylistic miss - it sends you
walking or driving the wrong way. This is a case for the boring,
deterministic tool.

One call handles many origins x many destinations at once (Google returns
the full matrix in a single request) - the same primitive serves every use
case this powers: a full pairwise matrix among a set of candidates (find
the closest pair of cafes), many candidates against one fixed anchor
(which restaurant is closest to the show), or one activity against
everything else (a "nearby" lookup). See routers/activities.py's
/distance-matrix endpoint for how callers actually reach this.

This module only ever talks to Google for a pair (origin, destination,
mode) the caller doesn't already have cached - see the ActivityDistance
table (models.py) and crud.get_cached_distances/cache_distance. Caching is
keyed and invalidated per app/crud.py's _invalidate_activity_distances
(fires only when an activity's address or city actually changes), so a
result is only ever re-fetched when it could genuinely be different, or
the caller explicitly asks via force_refresh.
"""

from typing import List, Optional

import requests
from pydantic import BaseModel

from .config import GOOGLE_MAPS_API_KEY

DISTANCE_MATRIX_URL = "https://maps.googleapis.com/maps/api/distancematrix/json"


class DistanceResult(BaseModel):
    distance_meters: int
    distance_text: str
    duration_seconds: int
    duration_text: str


def _client_configured() -> None:
    if not GOOGLE_MAPS_API_KEY:
        raise RuntimeError("GOOGLE_MAPS_API_KEY is not configured")


def get_distance_matrix(
    origins: List[str], destinations: List[str], mode: str = "walking"
) -> List[List[Optional[DistanceResult]]]:
    """origins/destinations are address (or address-like) query strings, in
    the same order the caller wants rows/columns back in. Returns a
    len(origins) x len(destinations) grid; an entry is None where Google
    couldn't find a route for that specific pair (e.g. one address didn't
    geocode, or there's no walking route - water, highway-only) rather than
    failing the whole request over one bad pair.
    """
    _client_configured()
    if not origins or not destinations:
        return []

    response = requests.get(
        DISTANCE_MATRIX_URL,
        params={
            "origins": "|".join(origins),
            "destinations": "|".join(destinations),
            "mode": mode,
            "key": GOOGLE_MAPS_API_KEY,
        },
        timeout=10,
    )
    response.raise_for_status()
    data = response.json()
    if data.get("status") != "OK":
        raise RuntimeError(f"Distance Matrix request failed: {data.get('status')} {data.get('error_message', '')}".strip())

    rows: List[List[Optional[DistanceResult]]] = []
    for row in data["rows"]:
        row_results: List[Optional[DistanceResult]] = []
        for element in row["elements"]:
            if element.get("status") != "OK":
                row_results.append(None)
                continue
            row_results.append(
                DistanceResult(
                    distance_meters=element["distance"]["value"],
                    distance_text=element["distance"]["text"],
                    duration_seconds=element["duration"]["value"],
                    duration_text=element["duration"]["text"],
                )
            )
        rows.append(row_results)
    return rows


def address_query_for(activity) -> Optional[str]:
    """Best-effort query string for an activity - its real address if it
    has one, else a "name, city" fallback (still enough for Google's own
    geocoding to often resolve a named business, the same way typing a
    place name into Google Maps search works) - None only when there's
    nothing at all to go on."""
    if activity.address:
        return activity.address
    if activity.city:
        return f"{activity.name}, {activity.city}"
    return None
