"""The addresses suggested in the sharing box (GET /api/me/people): only people
the signed-in person has already shared with or asked for - never everyone who
has an account, which would leak who else uses the app."""
import pytest

from shared_python import cloudflare, notify

from tests.test_access import make_trip, share
from tests.test_invites import ask


@pytest.fixture(autouse=True)
def _no_outside_calls(monkeypatch):
    monkeypatch.setattr(cloudflare, "allow_email", lambda email: None)
    monkeypatch.setattr(notify, "notify", lambda *a, **kw: None)


def people(person):
    resp = person.get("/api/me/people")
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_nobody_is_suggested_before_anything_is_shared(alice, bob):
    assert people(alice) == []
    make_trip(alice)
    assert people(alice) == []  # their own trip has no one else on it


def test_people_on_a_trip_you_own_are_suggested_sorted_and_without_yourself(alice, bob, carol):
    thing = make_trip(alice)
    share(alice, thing["id"], carol, "view")
    share(alice, thing["id"], bob, "edit")
    assert people(alice) == sorted([bob.email, carol.email])


def test_people_you_asked_for_are_suggested_unless_refused(alice, admin):
    thing = make_trip(alice)
    assert ask(alice, thing["id"], "Waiting@Example.com").status_code == 200
    refused = ask(alice, thing["id"], "no@example.com").json()
    assert admin.post(f"/api/admin/invites/{refused['id']}/decline").status_code == 200
    assert people(alice) == ["waiting@example.com"]


def test_what_others_shared_is_not_suggested_to_you(alice, bob, carol):
    thing = make_trip(alice)
    share(alice, thing["id"], bob, "edit")
    share(alice, thing["id"], carol, "view")
    # bob can see the trip (and so knows its owner), but carol is not his contact.
    assert people(bob) == []
    assert people(carol) == []


def test_other_peoples_invites_are_not_suggested(alice, bob):
    thing = make_trip(alice)
    assert ask(alice, thing["id"], "private@example.com").status_code == 200
    assert people(bob) == []
