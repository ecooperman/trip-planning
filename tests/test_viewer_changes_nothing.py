"""A view-only member of a trip must not be able to change anything on it.

The per-endpoint tests in test_access.py check the cases someone thought of. This
one walks EVERY route that writes (POST/PUT/PATCH/DELETE), fills in real ids from
a trip that has one of everything on it, and calls each as a view-only member. A
new endpoint added later without a role check shows up here as a 2xx, with no one
having to remember to write a test for it."""
import re

import pytest

from app import config
from app.main import app
from tests.test_access import (
    END,
    START,
    make_activity,
    make_category,
    make_place,
    make_stay,
    make_travel,
    make_trip,
    share,
)

WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

# What a viewer is rightly allowed to do, even though it is a write: things that
# only touch their OWN data, or take nothing from the trip.
ALLOWED_FOR_VIEWERS = {
    ("POST", "/api/trips"),  # a trip of their own
    ("POST", "/api/places"),  # their own library
    ("POST", "/api/categories"),
    ("POST", "/api/categories/reorder"),
    ("POST", "/api/distance-matrix"),  # a lookup, writes nothing of the trip's
    ("DELETE", "/api/trips/{trip_id}/members/{user_id}"),  # leaving the trip (checked separately below)
}


@pytest.fixture()
def world(monkeypatch, alice, bob):
    """Alice (an administrator, so dog care exists) owns a trip with a stay, a
    travel segment, an activity, a place, a category, a criterion and a verdict,
    and Bob is on it as a viewer."""
    monkeypatch.setattr(config, "ADMIN_EMAILS", {alice.email})
    tid = make_trip(alice)["id"]
    stay = make_stay(alice, tid)
    travel = make_travel(alice, tid)
    place = make_place(alice)
    category = make_category(alice)
    activity = make_activity(alice, tid, place_id=place["id"])
    criterion = alice.post(f"/api/trips/{tid}/stay-criteria", {"label": "Quiet"})
    assert criterion.status_code == 200, criterion.text
    booking = alice.post("/api/dog-care", {"trip_id": tid, "company_name": "Pups", "start_date": START, "end_date": END})
    assert booking.status_code == 200, booking.text
    share(alice, tid, bob, "view")
    bob_id = next(m["user_id"] for m in alice.get(f"/api/trips/{tid}/members").json() if m["email"] == bob.email)
    return {
        "trip_id": tid,
        "stay_id": stay["id"],
        "travel_segment_id": travel["id"],
        "place_id": place["id"],
        "category_id": category["id"],
        "activity_id": activity["id"],
        "criterion_id": criterion.json()["id"],
        "booking_id": booking.json()["id"],
        "user_id": bob_id,
        "invite_id": 1,
        "photo_id": 1,
        "kind": "photo",
        "segment": 1,
    }


def _write_routes():
    """Every (method, path) that writes, straight from the app's own OpenAPI
    description - routers are wrapped when included, so app.routes isn't flat."""
    for path, operations in app.openapi()["paths"].items():
        if not path.startswith("/api/"):
            continue
        for method in operations:
            if method.upper() in WRITE_METHODS:
                yield method.upper(), path


# Bodies for the routes that check the caller's role INSIDE the handler (after
# validating the body), so an empty body would hide a missing check behind a 422.
BODIES = {
    ("POST", "/api/stays"): lambda w: {"trip_id": w["trip_id"], "name": "X", "start_date": START, "end_date": END},
    ("POST", "/api/travel"): lambda w: {"trip_id": w["trip_id"], "name": "X"},
    ("POST", "/api/activities"): lambda w: {"name": "X", "trip_id": w["trip_id"]},
    ("POST", "/api/dog-care"): lambda w: {"trip_id": w["trip_id"], "company_name": "X", "start_date": START, "end_date": END},
    ("POST", "/api/trips/{trip_id}/stay-criteria"): lambda w: {"label": "X"},
    ("PATCH", "/api/trips/{trip_id}"): lambda w: {"location": "Hacked"},
    ("PATCH", "/api/stays/{stay_id}"): lambda w: {"name": "Hacked"},
    ("PATCH", "/api/travel/{travel_segment_id}"): lambda w: {"name": "Hacked"},
    ("PATCH", "/api/activities/{activity_id}"): lambda w: {"name": "Hacked"},
    ("PATCH", "/api/stay-criteria/{criterion_id}"): lambda w: {"label": "Hacked"},
    ("PATCH", "/api/dog-care/{booking_id}"): lambda w: {"company_name": "Hacked"},
    ("PATCH", "/api/places/{place_id}"): lambda w: {"name": "Hacked"},
    ("PATCH", "/api/categories/{category_id}"): lambda w: {"name": "Hacked"},
    ("PUT", "/api/stays/{stay_id}/verdicts/{criterion_id}"): lambda w: {"verdict": "yes"},
    ("POST", "/api/trips/{trip_id}/members"): lambda w: {"email": "x@example.com", "role": "edit"},
    ("PATCH", "/api/trips/{trip_id}/members/{user_id}"): lambda w: {"role": "edit"},
    ("POST", "/api/trips/{trip_id}/invites"): lambda w: {"email": "x@example.com", "role": "edit"},
}


def _fill(path, world):
    def sub(match):
        return str(world[match.group(1)])

    return re.sub(r"\{(\w+)(?::\w+)?\}", sub, path)


def test_the_walk_actually_covers_the_apps_write_routes():
    """If routing is ever restructured so this finds almost nothing, the test
    below would pass vacuously - fail loudly instead."""
    assert len(list(_write_routes())) >= 40


def test_a_view_only_member_cannot_change_anything(world, bob):
    problems = []
    for method, path in _write_routes():
        if (method, path) in ALLOWED_FOR_VIEWERS:
            continue
        body = BODIES.get((method, path), lambda w: {})(world)
        url = _fill(path, world)
        response = bob.client.request(method, url, headers=bob.headers, json=body)
        if response.status_code < 300 or response.status_code >= 500:
            problems.append(f"{method} {path} -> {response.status_code} {response.text[:120]}")
    assert not problems, "a view-only member got through on:\n" + "\n".join(problems)


def test_what_a_viewer_may_do_is_only_their_own_things(world, alice, bob):
    # They can leave the trip (and only themselves).
    other = world["user_id"]
    assert bob.delete(f"/api/trips/{world['trip_id']}/members/{other}").status_code == 200
