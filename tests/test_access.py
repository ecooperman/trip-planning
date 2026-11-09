"""Who can see and do what. Every endpoint that takes a trip, activity, place,
stay, travel segment, criterion, dog-care booking or category id must treat
someone else's as nonexistent (404), and a shared trip must give each role
exactly its powers - these tests are the guard against a missed filter leaking
data between people."""
from datetime import datetime, timedelta

import pytest

from app import config, models

START = datetime(2027, 3, 1).isoformat()
END = (datetime(2027, 3, 1) + timedelta(days=3)).isoformat()


def make_trip(person, location="Lisbon", **extra):
    resp = person.post("/api/trips", {"location": location, **extra})
    assert resp.status_code == 200, resp.text
    return resp.json()


def make_activity(person, trip_id=None, name="Pastel de nata", **extra):
    resp = person.post("/api/activities", {"name": name, "trip_id": trip_id, **extra})
    assert resp.status_code == 200, resp.text
    return resp.json()


def make_place(person, name="Cafe", **extra):
    resp = person.post("/api/places", {"name": name, **extra})
    assert resp.status_code == 200, resp.text
    return resp.json()


def make_category(person, name="Food", **extra):
    resp = person.post("/api/categories", {"name": name, "color": "#336699", **extra})
    assert resp.status_code == 200, resp.text
    return resp.json()


def make_stay(person, trip_id, name="Hotel"):
    resp = person.post("/api/stays", {"trip_id": trip_id, "name": name, "start_date": START, "end_date": END})
    assert resp.status_code == 200, resp.text
    return resp.json()


def make_travel(person, trip_id, name="Flight"):
    resp = person.post("/api/travel", {"trip_id": trip_id, "name": name})
    assert resp.status_code == 200, resp.text
    return resp.json()


def share(owner, trip_id, person, role):
    # Only people with an account can be added, and an account is made by
    # signing in - so they do that first.
    person.get("/api/me")
    resp = owner.post(f"/api/trips/{trip_id}/members", {"email": person.email, "role": role})
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest.fixture()
def admin_alice(monkeypatch, alice):
    """Alice as the app's administrator (dog care, the plans link)."""
    monkeypatch.setattr(config, "ADMIN_EMAILS", {alice.email})
    return alice


# --- strangers see nothing ---------------------------------------------------


def test_everything_alice_owns_is_invisible_to_bob(admin_alice, bob):
    alice = admin_alice
    trip = make_trip(alice)
    tid = trip["id"]
    category = make_category(alice)
    place = make_place(alice, category_ids=[category["id"]])
    activity = make_activity(alice, tid, place_id=place["id"])
    stay = make_stay(alice, tid)
    travel = make_travel(alice, tid)
    criterion = alice.post(f"/api/trips/{tid}/stay-criteria", {"label": "Walkable"}).json()
    booking = alice.post(
        "/api/dog-care", {"trip_id": tid, "company_name": "Pups", "start_date": START, "end_date": END}
    ).json()
    aid, pid, sid, vid = activity["id"], place["id"], stay["id"], travel["id"]

    for listing in ("/api/trips", "/api/activities", "/api/places", "/api/categories", "/api/activities/cities"):
        assert bob.get(listing).json() == [], listing

    probes = [
        bob.get(f"/api/trips/{tid}"),
        bob.patch(f"/api/trips/{tid}", {"location": "Mine now"}),
        bob.delete(f"/api/trips/{tid}"),
        bob.get(f"/api/trips/{tid}/activities"),
        bob.get(f"/api/activities?trip_id={tid}"),
        bob.get(f"/api/trips/{tid}/stays"),
        bob.get(f"/api/trips/{tid}/stay-coverage"),
        bob.get(f"/api/trips/{tid}/travel"),
        bob.get(f"/api/trips/{tid}/dog-care"),
        bob.get(f"/api/trips/{tid}/dog-care-coverage"),
        bob.get(f"/api/trips/{tid}/export.xlsx"),
        bob.get(f"/api/trips/{tid}/members"),
        bob.post(f"/api/trips/{tid}/members", {"email": "x@example.com", "role": "view"}),
        bob.post(f"/api/trips/{tid}/fill-missing-cities"),
        bob.get(f"/api/trips/{tid}/stay-criteria"),
        bob.post(f"/api/trips/{tid}/stay-criteria", {"label": "x"}),
        bob.get(f"/api/trips/{tid}/stay-comparison"),
        bob.post(f"/api/trips/{tid}/stays/import", {"urls": ["https://example.com"]}),
        bob.get(f"/api/activities/{aid}"),
        bob.patch(f"/api/activities/{aid}", {"cost": 1}),
        bob.delete(f"/api/activities/{aid}"),
        bob.post(f"/api/activities/{aid}/scrape"),
        bob.post(f"/api/activities/{aid}/promote-to-place"),
        bob.get(f"/api/activities/{aid}/distances"),
        bob.get(f"/api/places/{pid}"),
        bob.patch(f"/api/places/{pid}", {"name": "x"}),
        bob.delete(f"/api/places/{pid}"),
        bob.get(f"/api/places/{pid}/photos"),
        bob.post(f"/api/places/{pid}/scrape"),
        bob.get(f"/api/stays/{sid}"),
        bob.patch(f"/api/stays/{sid}", {"name": "x"}),
        bob.delete(f"/api/stays/{sid}"),
        bob.get(f"/api/travel/{vid}"),
        bob.patch(f"/api/travel/{vid}", {"name": "x"}),
        bob.delete(f"/api/travel/{vid}"),
        bob.patch(f"/api/stay-criteria/{criterion['id']}", {"label": "x"}),
        bob.delete(f"/api/stay-criteria/{criterion['id']}"),
        bob.put(f"/api/stays/{sid}/verdicts/{criterion['id']}", {"verdict": "yes"}),
        bob.patch(f"/api/categories/{category['id']}", {"color": "#000000"}),
        bob.delete(f"/api/categories/{category['id']}"),
        bob.get(f"/api/dog-care/{booking['id']}"),
        bob.delete(f"/api/dog-care/{booking['id']}"),
        bob.post("/api/stays", {"trip_id": tid, "name": "x", "start_date": START, "end_date": END}),
        bob.post("/api/travel", {"trip_id": tid, "name": "x"}),
        bob.post("/api/activities", {"name": "x", "trip_id": tid}),
        bob.post("/api/distance-matrix", {"origins": [{"kind": "activity", "id": aid}], "destinations": [{"kind": "stay", "id": sid}]}),
    ]
    statuses = [r.status_code for r in probes]
    assert all(code in (400, 404) for code in statuses), statuses
    # and nothing of Alice's changed
    assert alice.get(f"/api/trips/{tid}").json()["location"] == "Lisbon"
    assert alice.get(f"/api/activities/{aid}").status_code == 200


def test_you_cannot_mix_libraries(alice, bob):
    alices_trip = make_trip(alice)
    alices_activity = make_activity(alice, alices_trip["id"])
    alices_place = make_place(alice)
    alices_category = make_category(alice)
    bobs_trip = make_trip(bob)
    bobs_activity = make_activity(bob, bobs_trip["id"])

    # Bob can't use Alice's place or category on his own activity...
    assert bob.post("/api/activities", {"name": "x", "place_id": alices_place["id"]}).status_code == 404
    assert bob.post("/api/activities", {"name": "x", "category_ids": [alices_category["id"]]}).status_code == 404
    assert bob.patch(f"/api/activities/{bobs_activity['id']}", {"place_id": alices_place["id"]}).status_code == 404
    assert bob.post("/api/places", {"name": "x", "category_ids": [alices_category["id"]]}).status_code == 404
    # ...nor move activities between his trip and hers.
    assert bob.post(f"/api/trips/{alices_trip['id']}/activities/{bobs_activity['id']}").status_code in (403, 404)
    assert bob.post(f"/api/trips/{bobs_trip['id']}/activities/{alices_activity['id']}").status_code == 404


def test_a_trip_only_ever_holds_its_owners_activities(alice, bob):
    """The owner-mismatch rule: an editor's own activity can't be put on the
    owner's trip, and the owner can't put an activity she merely has edit
    access to (someone else's) on her own trip - either would let content
    from one person's library leak into another's through a shared trip."""
    alices_trip = make_trip(alice)["id"]
    bobs_trip = make_trip(bob)["id"]
    bobs_activity = make_activity(bob, bobs_trip)
    bobs_loose = make_activity(bob)  # in his library, on no trip
    share(alice, alices_trip, bob, "edit")
    share(bob, bobs_trip, alice, "edit")

    # Bob (an editor of Alice's trip) tries to bring his own activity into it.
    assert bob.post(f"/api/trips/{alices_trip}/activities/{bobs_loose['id']}").status_code == 400
    # Alice (an editor of Bob's trip) can see Bob's activity there, but can't pull it onto her own trip.
    assert alice.post(f"/api/trips/{alices_trip}/activities/{bobs_activity['id']}").status_code == 400
    assert alice.get(f"/api/activities/{bobs_activity['id']}").json()["trips"][0]["id"] == bobs_trip  # still where it was


# --- roles ------------------------------------------------------------------


def test_view_role_can_read_but_not_change_anything(alice, bob):
    trip = make_trip(alice)
    tid = trip["id"]
    place = make_place(alice)
    activity = make_activity(alice, tid, place_id=place["id"])
    stay = make_stay(alice, tid)
    travel = make_travel(alice, tid)
    share(alice, tid, bob, "view")

    seen = bob.get(f"/api/trips/{tid}").json()
    assert seen["my_role"] == "view" and seen["owner_email"] == alice.email and seen["member_count"] == 2
    assert [t["id"] for t in bob.get("/api/trips").json()] == [tid]
    assert [a["id"] for a in bob.get(f"/api/trips/{tid}/activities").json()] == [activity["id"]]
    assert bob.get(f"/api/activities/{activity['id']}").status_code == 200
    assert bob.get(f"/api/trips/{tid}/stays").status_code == 200
    assert bob.get(f"/api/trips/{tid}/travel").status_code == 200
    assert bob.get(f"/api/trips/{tid}/export.xlsx").status_code == 200
    assert bob.get(f"/api/places/{place['id']}").status_code == 200  # through the activity that uses it
    assert bob.get("/api/activities").json() == []  # not in his own library

    refused = [
        bob.patch(f"/api/trips/{tid}", {"location": "x"}),
        bob.delete(f"/api/trips/{tid}"),
        bob.post("/api/activities", {"name": "x", "trip_id": tid}),
        bob.patch(f"/api/activities/{activity['id']}", {"cost": 5}),
        bob.delete(f"/api/activities/{activity['id']}"),
        bob.post(f"/api/activities/{activity['id']}/scrape"),
        bob.post("/api/stays", {"trip_id": tid, "name": "x", "start_date": START, "end_date": END}),
        bob.patch(f"/api/stays/{stay['id']}", {"name": "x"}),
        bob.delete(f"/api/stays/{stay['id']}"),
        bob.post("/api/travel", {"trip_id": tid, "name": "x"}),
        bob.patch(f"/api/travel/{travel['id']}", {"name": "x"}),
        bob.delete(f"/api/travel/{travel['id']}"),
        bob.post(f"/api/trips/{tid}/stay-criteria", {"label": "x"}),
        bob.post(f"/api/trips/{tid}/fill-missing-cities"),
        bob.patch(f"/api/places/{place['id']}", {"name": "x"}),
        bob.delete(f"/api/trips/{tid}/activities/{activity['id']}"),
        bob.get(f"/api/trips/{tid}/members"),
        bob.post(f"/api/trips/{tid}/members", {"email": "x@example.com", "role": "view"}),
    ]
    assert [r.status_code for r in refused] == [403] * len(refused)
    assert alice.get(f"/api/trips/{tid}").json()["location"] == "Lisbon"


def test_edit_role_works_with_the_trips_content_but_not_the_trip_itself(alice, bob):
    trip = make_trip(alice)
    tid = trip["id"]
    place = make_place(alice)
    category = make_category(alice)
    share(alice, tid, bob, "edit")

    # An activity Bob adds belongs to ALICE's library, and may use her place and category.
    added = bob.post(
        "/api/activities",
        {"name": "Added by Bob", "trip_id": tid, "place_id": place["id"], "category_ids": [category["id"]]},
    )
    assert added.status_code == 200, added.text
    aid = added.json()["id"]
    assert [a["id"] for a in alice.get("/api/activities").json()] == [aid]
    assert bob.get("/api/activities").json() == []

    assert bob.patch(f"/api/activities/{aid}", {"cost": 12}).json()["cost"] == 12
    assert bob.patch(f"/api/trips/{tid}", {"location": "Lisbon & Sintra", "city": "Lisbon"}).status_code == 200
    stay = make_stay(bob, tid)
    assert bob.patch(f"/api/stays/{stay['id']}", {"name": "Better hotel"}).status_code == 200
    make_travel(bob, tid)
    assert bob.post(f"/api/trips/{tid}/stay-criteria", {"label": "Walkable"}).status_code == 200
    assert bob.post(f"/api/trips/{tid}/fill-missing-cities").status_code == 200
    assert bob.delete(f"/api/activities/{aid}").status_code == 200

    # Unlinking sends an activity back to the owner's library - and out of Bob's sight.
    second = bob.post("/api/activities", {"name": "Second", "trip_id": tid}).json()["id"]
    assert bob.delete(f"/api/trips/{tid}/activities/{second}").status_code == 200
    assert bob.get(f"/api/activities/{second}").status_code == 404
    assert bob.post(f"/api/trips/{tid}/activities/{second}").status_code == 404  # can't link what he can't see
    assert alice.get(f"/api/activities/{second}").status_code == 200
    assert alice.post(f"/api/trips/{tid}/activities/{second}").status_code == 200  # the owner can put it back

    make_activity(alice, tid, place_id=place["id"])  # the place is now on the shared trip, so Bob can see it
    refused = [
        bob.patch(f"/api/trips/{tid}", {"archived": True}),
        bob.delete(f"/api/trips/{tid}"),
        bob.get(f"/api/trips/{tid}/members"),
        bob.post(f"/api/trips/{tid}/members", {"email": "x@example.com", "role": "view"}),
        bob.patch(f"/api/places/{place['id']}", {"name": "Bob's rename"}),
        bob.delete(f"/api/places/{place['id']}"),
        bob.patch(f"/api/categories/{category['id']}", {"color": "#000000"}),
    ]
    assert [r.status_code for r in refused] == [403, 403, 403, 403, 403, 403, 404]
    activity = make_activity(alice, tid)
    assert bob.post(f"/api/activities/{activity['id']}/promote-to-place").status_code in (400, 403)


def test_a_place_is_visible_only_through_a_trip_that_uses_it(alice, bob, carol):
    place = make_place(alice, review="Alice's private opinion")
    unused = make_place(alice, name="Unused")
    trip = make_trip(alice)
    make_activity(alice, trip["id"], place_id=place["id"])
    share(alice, trip["id"], bob, "view")

    assert bob.get(f"/api/places/{place['id']}").status_code == 200
    assert bob.get(f"/api/places/{unused['id']}").status_code == 404  # in her library, not on the shared trip
    assert carol.get(f"/api/places/{place['id']}").status_code == 404
    assert bob.get("/api/places").json() == []


# --- sharing management ---------------------------------------------------------


def test_only_the_owner_manages_sharing(alice, bob, carol):
    tid = make_trip(alice)["id"]
    added = share(alice, tid, bob, "view")
    assert added["email"] == bob.email and added["role"] == "view"

    members = alice.get(f"/api/trips/{tid}/members").json()
    assert [(m["email"], m["role"]) for m in members] == [(alice.email, "owner"), (bob.email, "view")]

    assert alice.patch(f"/api/trips/{tid}/members/{added['user_id']}", {"role": "edit"}).json()["role"] == "edit"
    assert alice.post(f"/api/trips/{tid}/members", {"email": bob.email, "role": "view"}).status_code == 409
    assert alice.post(f"/api/trips/{tid}/members", {"email": "nope", "role": "view"}).status_code == 400
    owner_row = members[0]
    assert alice.patch(f"/api/trips/{tid}/members/{owner_row['user_id']}", {"role": "view"}).status_code == 400
    assert alice.delete(f"/api/trips/{tid}/members/{owner_row['user_id']}").status_code == 400

    assert alice.delete(f"/api/trips/{tid}/members/{added['user_id']}").status_code == 200
    assert bob.get(f"/api/trips/{tid}").status_code == 404


def test_a_member_can_leave_but_not_remove_others(alice, bob, carol):
    tid = make_trip(alice)["id"]
    b = share(alice, tid, bob, "edit")
    c = share(alice, tid, carol, "view")
    assert bob.delete(f"/api/trips/{tid}/members/{c['user_id']}").status_code == 403
    assert bob.delete(f"/api/trips/{tid}/members/{b['user_id']}").status_code == 200
    assert bob.get(f"/api/trips/{tid}").status_code == 404
    assert carol.get(f"/api/trips/{tid}").status_code == 200


def test_deleting_a_trip_removes_it_for_everyone(alice, bob):
    tid = make_trip(alice)["id"]
    aid = make_activity(alice, tid)["id"]
    share(alice, tid, bob, "edit")
    assert alice.delete(f"/api/trips/{tid}").status_code == 200
    assert bob.get("/api/trips").json() == []
    assert bob.get(f"/api/activities/{aid}").status_code == 404
    assert alice.get(f"/api/activities/{aid}").status_code == 200  # unlinked, still hers


def test_someone_cloudflare_lets_in_can_be_added_before_they_have_ever_signed_in(alice, carol, monkeypatch):
    from shared_python import cloudflare

    monkeypatch.setattr(cloudflare, "is_let_in", lambda email, admin_emails=(): email == carol.email)
    tid = make_trip(alice)["id"]
    resp = alice.post(f"/api/trips/{tid}/members", {"email": carol.email, "role": "view"})
    assert resp.status_code == 200, resp.text
    # Their account is picked up when they first open the app.
    assert [(t["location"], t["my_role"]) for t in carol.get("/api/trips").json()] == [("Lisbon", "view")]


def test_losing_access_to_a_trip_takes_its_activities_with_it(alice, bob):
    tid = make_trip(alice)["id"]
    aid = make_activity(alice, tid)["id"]
    b = share(alice, tid, bob, "edit")
    assert bob.get(f"/api/activities/{aid}").status_code == 200
    alice.delete(f"/api/trips/{tid}/members/{b['user_id']}")
    assert bob.get(f"/api/activities/{aid}").status_code == 404
    assert bob.patch(f"/api/activities/{aid}", {"cost": 1}).status_code == 404


# --- categories ---------------------------------------------------------------


def test_categories_are_private_and_names_are_unique_per_person(alice, bob):
    a = make_category(alice, "Work")
    assert alice.post("/api/categories", {"name": "work", "color": "#112233"}).status_code == 409
    assert make_category(bob, "Work")["id"] != a["id"]  # same name, different person
    assert [c["id"] for c in bob.get("/api/categories").json()] != [a["id"]]
    assert bob.patch(f"/api/categories/{a['id']}", {"color": "#000000"}).status_code == 404
    assert bob.post("/api/categories/reorder", {"ordered_ids": [a["id"]]}).status_code == 200
    assert alice.get("/api/categories").json()[0]["sort_order"] == a["sort_order"]  # untouched by Bob


# --- dog care and the plans link are the administrator's alone ------------------


def test_dog_care_is_only_for_an_administrator_who_owns_the_trip(admin_alice, bob, carol):
    alice = admin_alice
    tid = make_trip(alice)["id"]
    body = {"trip_id": tid, "company_name": "Pups", "start_date": START, "end_date": END}
    booking = alice.post("/api/dog-care", body)
    assert booking.status_code == 200
    bid = booking.json()["id"]
    assert alice.get(f"/api/trips/{tid}/dog-care").status_code == 200

    share(alice, tid, bob, "edit")  # a shared editor never sees it
    assert bob.get(f"/api/trips/{tid}/dog-care").status_code == 403
    assert bob.get(f"/api/dog-care/{bid}").status_code == 404
    assert bob.post("/api/dog-care", body).status_code == 403
    assert bob.delete(f"/api/dog-care/{bid}").status_code == 404

    own = make_trip(carol)["id"]  # and nobody who isn't an administrator can add it, even to their own trip
    assert carol.post("/api/dog-care", {**body, "trip_id": own}).status_code == 403


def test_plan_links_are_for_the_administrator_only(admin_alice, bob):
    for call in (
        bob.get("/api/plan-links/locations"),
        bob.get("/api/plan-links/plans"),
        bob.post("/api/plan-links/import", {"plan_ids": [1], "trip_id": None}),
    ):
        assert call.status_code == 403
    assert bob.get("/api/plan-links").json() == []  # his own, so nothing


# --- other apps calling this one (finances, social-planning) ---------------------


@pytest.fixture()
def service(monkeypatch, admin_alice):
    monkeypatch.setattr(config, "SERVICE_TOKEN", "s3cret-token")
    monkeypatch.setattr(config, "SERVICE_USER_EMAIL", None)
    return {"X-Service-Token": "s3cret-token"}


def test_the_service_token_acts_as_the_administrator(service, admin_alice, bob, client):
    alice = admin_alice
    tid = make_trip(alice, "Lisbon")["id"]
    make_trip(bob, "Bob's trip")
    activity = make_activity(alice, tid, cost=40)

    # No Cloudflare identity at all - just the token, as finances and the plans app send it.
    trips = client.get("/api/trips", headers=service).json()
    assert [t["location"] for t in trips] == ["Lisbon"]
    summary = client.get("/api/trips/cost-summary", headers=service).json()
    assert [row["location"] for row in summary] == ["Lisbon"]
    assert summary[0]["activities_cost_cents"] == 4000
    assert client.get("/api/plan-links", headers=service).status_code == 200


def test_a_wrong_or_unconfigured_service_token_is_refused(service, client, monkeypatch):
    assert client.get("/api/trips", headers={"X-Service-Token": "wrong"}).status_code == 401
    assert client.get("/api/trips", headers={"X-Service-Token": ""}).status_code == 401
    monkeypatch.setattr(config, "SERVICE_TOKEN", None)
    assert client.get("/api/trips", headers=service).status_code == 401  # the feature is off


def test_the_service_token_opens_only_the_endpoints_meant_for_it(service, client):
    for path in ("/api/places", "/api/categories", "/api/activities", "/api/me"):
        resp = client.get(path, headers=service)
        # falls through to normal sign-in (here the local dev user), never to the administrator's data by token
        assert resp.status_code == 200
    from app import crud  # noqa: F401  (the service user is created on first use, like anyone)


# --- accounts ------------------------------------------------------------------


def test_the_first_admin_to_sign_in_takes_over_pre_accounts_data(client, db, bob):
    from app import crud
    from tests.conftest import Person

    legacy = db.query(models.User).filter_by(email=crud.LEGACY_OWNER_EMAIL).one()
    trip = models.Trip(location="Old trip", owner_id=legacy.id)
    db.add(trip)
    db.flush()
    db.add(models.TripMember(trip_id=trip.id, user_id=legacy.id, role="owner"))
    db.commit()

    assert bob.get("/api/trips").json() == []  # someone who isn't an admin signing in first doesn't get it
    owner = Person(client, config.DEV_USER_EMAIL)
    assert [(t["location"], t["my_role"]) for t in owner.get("/api/trips").json()] == [("Old trip", "owner")]
    assert db.query(models.User).filter_by(email=crud.LEGACY_OWNER_EMAIL).first() is None


def test_adding_someone_already_on_the_trip_says_so(alice, bob):
    tid = make_trip(alice)["id"]
    share(alice, tid, bob, "edit")

    # Typing your own address is the likeliest slip - and it isn't about Cloudflare at all.
    mine = alice.post(f"/api/trips/{tid}/members", {"email": alice.email, "role": "view"})
    assert mine.status_code == 409
    assert "That's you" in mine.json()["detail"]

    again = alice.post(f"/api/trips/{tid}/members", {"email": bob.email.upper(), "role": "view"})
    assert again.status_code == 409
    detail = again.json()["detail"]
    assert bob.email in detail and "already on this trip" in detail and "can edit" in detail


def test_someone_on_the_trip_is_reported_even_if_cloudflare_no_longer_lets_them_in(alice, bob, monkeypatch):
    from shared_python import cloudflare

    tid = make_trip(alice)["id"]
    share(alice, tid, bob, "view")
    monkeypatch.setattr(cloudflare, "is_let_in", lambda email, admin_emails=(): False)
    resp = alice.post(f"/api/trips/{tid}/members", {"email": bob.email, "role": "edit"})
    # Not "can't sign in yet", which would offer to invite someone already here.
    assert resp.status_code == 409
    assert "already on this trip" in resp.json()["detail"]
