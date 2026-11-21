"""The numbers the dashboard's stats pages read: administrators only, counts and dates only, everyone's accounts."""
from app import models
from tests.test_access import make_activity, make_place, make_trip, share


def test_only_the_administrator_can_read_the_stats(alice, admin):
    assert alice.get("/api/admin/stats").status_code == 403
    assert admin.get("/api/admin/stats").status_code == 200


def test_the_stats_count_each_persons_things_without_showing_any_of_them(admin, alice, bob):
    trip = make_trip(alice, "SECRET TRIP")
    make_activity(alice, trip["id"], "SECRET ACTIVITY")
    make_place(alice, "SECRET PLACE")
    share(alice, trip["id"], bob, "view")
    body = admin.get("/api/admin/stats")
    accounts = {a["email"]: a for a in body.json()["accounts"]}
    a, b = accounts["alice@example.com"]["counts"], accounts["bob@example.com"]["counts"]
    assert a["trips"] == 1 and a["activities"] == 1 and a["places"] == 1
    assert b["trips"] == 0 and b["trips shared with them"] == 1
    for secret in ("SECRET TRIP", "SECRET ACTIVITY", "SECRET PLACE"):
        assert secret not in body.text


def test_using_the_app_notes_when_a_person_was_last_seen(alice, db):
    assert alice.get("/api/me").status_code == 200
    user = db.query(models.User).filter(models.User.email == "alice@example.com").one()
    assert user.active_days == 1 and user.last_seen_at is not None


def test_the_dashboards_account_check_is_not_the_person_being_here(alice, db):
    plain = alice.headers
    alice.headers = {**plain, "X-Brassworks-Probe": "1"}
    assert alice.get("/api/me").status_code == 200
    alice.headers = plain
    user = db.query(models.User).filter(models.User.email == "alice@example.com").one()
    assert user.last_seen_at is None and not user.active_days  # the dashboard looking is not use
    assert alice.get("/api/me").status_code == 200
    db.expire_all()
    assert db.query(models.User).filter(models.User.email == "alice@example.com").one().active_days == 1  # but the person is
