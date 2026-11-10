"""People's own API keys: stored encrypted, never shown again, and the rule for
whose key a paid call uses - their own, else the house key for an administrator
and nobody else. Calls out to Anthropic, Google and Jina are all stubbed."""
import logging

import pytest

from shared_python import settings as shared_settings

from app import apikeys, config, distance, models, stay_extraction
from app.routers import stay_compare
from tests.test_access import make_activity, make_stay, make_trip, share

ALICE_KEY = "sk-ant-alice-0123456789abcdef"
BOB_KEY = "sk-ant-bob---0123456789wxyz"
HOUSE_KEY = "sk-ant-HOUSE-0123456789house"


@pytest.fixture()
def accepted(monkeypatch):
    """The services accept every key (the live check is stubbed)."""
    monkeypatch.setattr(apikeys, "verify", lambda provider, key: (True, ""))


@pytest.fixture()
def house(monkeypatch):
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", HOUSE_KEY)
    monkeypatch.setattr(config, "GOOGLE_MAPS_API_KEY", "house-google-0123456789")
    monkeypatch.setattr(config, "JINA_API_KEY", "house-jina-0123456789ab")


@pytest.fixture()
def admin_alice(monkeypatch, alice):
    monkeypatch.setattr(config, "ADMIN_EMAILS", {alice.email})
    return alice


def save(person, provider, key):
    return person.put(f"/api/profile/api-keys/{provider}", {"key": key})


# --- storing a key ------------------------------------------------------------


def test_a_saved_key_is_encrypted_in_the_database_and_never_sent_back(alice, accepted, db):
    resp = save(alice, "anthropic", ALICE_KEY)
    assert resp.status_code == 200, resp.text
    assert ALICE_KEY not in resp.text

    row = db.query(models.UserApiKey).one()
    assert ALICE_KEY not in row.encrypted_key and "alice-0123" not in row.encrypted_key
    assert row.last4 == ALICE_KEY[-4:]

    listing = alice.get("/api/profile/api-keys")
    assert listing.status_code == 200
    assert ALICE_KEY not in listing.text
    mine = next(k for k in listing.json()["keys"] if k["provider"] == "anthropic")
    assert mine["has_own_key"] is True and mine["last4"] == ALICE_KEY[-4:]


def test_keys_belong_to_one_person_each(alice, bob, accepted):
    save(alice, "anthropic", ALICE_KEY)
    bobs = {k["provider"]: k for k in bob.get("/api/profile/api-keys").json()["keys"]}
    assert bobs["anthropic"]["has_own_key"] is False and bobs["anthropic"]["last4"] is None
    assert bob.delete("/api/profile/api-keys/anthropic").status_code == 404  # nothing of his to remove
    assert alice.get("/api/profile/api-keys").json()["keys"][0]["has_own_key"] is True


def test_replacing_and_removing_a_key(alice, accepted, db):
    save(alice, "anthropic", ALICE_KEY)
    save(alice, "anthropic", BOB_KEY)
    assert db.query(models.UserApiKey).count() == 1
    assert alice.delete("/api/profile/api-keys/anthropic").status_code == 200
    assert db.query(models.UserApiKey).count() == 0


def test_a_view_only_member_may_keep_their_own_keys(alice, bob, accepted):
    tid = make_trip(alice)["id"]
    share(alice, tid, bob, "view")
    assert save(bob, "anthropic", BOB_KEY).status_code == 200


def test_a_key_the_service_refuses_is_not_saved(alice, db, monkeypatch):
    monkeypatch.setattr(apikeys, "verify", lambda provider, key: (False, "Anthropic didn't accept that key"))
    resp = save(alice, "anthropic", ALICE_KEY)
    assert resp.status_code == 400 and "didn't accept" in resp.json()["detail"]
    assert db.query(models.UserApiKey).count() == 0


def test_a_key_that_could_not_be_checked_is_saved_and_said_to_be_unverified(alice, monkeypatch):
    monkeypatch.setattr(apikeys, "verify", lambda provider, key: (None, "Couldn't reach Anthropic to check the key"))
    resp = save(alice, "anthropic", ALICE_KEY)
    assert resp.status_code == 200
    assert resp.json()["verified"] is None and "not verified" in resp.json()["note"]


def test_something_that_is_not_a_key_is_refused_before_any_call(alice, monkeypatch):
    monkeypatch.setattr(apikeys, "verify", lambda *a: pytest.fail("a malformed key must not reach the service"))
    assert save(alice, "anthropic", "short").status_code == 400
    assert save(alice, "anthropic", "has some spaces in it, not a key at all").status_code == 400
    assert save(alice, "not-a-provider", ALICE_KEY).status_code == 422


def test_without_an_encryption_secret_production_refuses_to_save(alice, accepted, monkeypatch):
    monkeypatch.setattr(apikeys, "storage_available", lambda: False)
    assert save(alice, "anthropic", ALICE_KEY).status_code == 503
    assert alice.get("/api/profile/api-keys").json()["can_save"] is False


def test_a_key_saved_under_another_secret_is_unreadable_not_leaked(alice, accepted, monkeypatch, caplog, db):
    monkeypatch.setattr(shared_settings, "KEY_ENCRYPTION_SECRET", "the-original-secret-long-enough")
    save(alice, "anthropic", ALICE_KEY)
    monkeypatch.setattr(shared_settings, "KEY_ENCRYPTION_SECRET", "a-different-secret-entirely-now")
    user = db.query(models.User).filter_by(email=alice.email).one()
    with caplog.at_level(logging.WARNING):
        assert apikeys.resolve(db, user, "anthropic") is None
    assert "could not be decrypted" in caplog.text and ALICE_KEY not in caplog.text
    mine = next(k for k in alice.get("/api/profile/api-keys").json()["keys"] if k["provider"] == "anthropic")
    assert mine["has_own_key"] is True and mine["own_key_readable"] is False and mine["usable"] is False


# --- whose key a call uses ----------------------------------------------------


def test_the_house_key_is_for_administrators_only(db, alice, bob, house, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_EMAILS", {alice.email})
    alice.get("/api/me"), bob.get("/api/me")
    a = db.query(models.User).filter_by(email=alice.email).one()
    b = db.query(models.User).filter_by(email=bob.email).one()
    assert apikeys.resolve(db, a, "anthropic") == HOUSE_KEY
    assert apikeys.resolve(db, b, "anthropic") is None  # never, however it is configured
    assert apikeys.available(db, b) == {"anthropic": False, "google_maps": False, "jina": False}
    assert alice.get("/api/me").json()["can_use"] == {"anthropic": True, "google_maps": True, "jina": True}


def test_an_own_key_beats_the_house_key_even_for_an_administrator(admin_alice, house, accepted, db):
    save(admin_alice, "anthropic", ALICE_KEY)
    user = db.query(models.User).filter_by(email=admin_alice.email).one()
    assert apikeys.resolve(db, user, "anthropic") == ALICE_KEY
    # ...and removing it falls back to the house key
    admin_alice.delete("/api/profile/api-keys/anthropic")
    assert apikeys.resolve(db, user, "anthropic") == HOUSE_KEY


def test_a_non_administrator_with_their_own_key_can_use_the_feature(bob, house, accepted, db):
    save(bob, "google_maps", "bobs-own-google-key-0123456789")
    me = bob.get("/api/me").json()
    assert me["can_use"]["google_maps"] is True and me["can_use"]["anthropic"] is False


# --- the three places a key is used -------------------------------------------


@pytest.fixture()
def no_network(monkeypatch):
    """Stay import without fetching anything, recording which keys it was given."""
    seen = {}
    monkeypatch.setattr(stay_compare, "resolve_scrape", lambda url: ("failed", None, "stubbed"))

    def page_text(url, jina_key=None, **kw):
        seen["jina"] = jina_key
        return "some page text"

    def extract(url, title, description, text, api_key):
        seen["anthropic"] = api_key
        raise ValueError("stub: stop after recording the key")

    monkeypatch.setattr(stay_compare, "fetch_page_text", page_text)
    monkeypatch.setattr(stay_extraction, "extract_from_text", extract)
    return seen


def test_stay_import_uses_the_signed_in_persons_own_keys(alice, bob, accepted, no_network):
    tid = make_trip(alice)["id"]
    share(alice, tid, bob, "edit")
    save(bob, "anthropic", BOB_KEY)
    save(bob, "jina", "bobs-jina-key-0123456789ab")
    resp = bob.post(f"/api/trips/{tid}/stays/import", {"urls": ["https://example.com/stay"]})
    assert resp.status_code == 200, resp.text
    assert no_network["anthropic"] == BOB_KEY and no_network["jina"] == "bobs-jina-key-0123456789ab"


def test_stay_import_without_a_key_says_how_to_turn_it_on_and_does_no_work(alice, bob, house, no_network):
    tid = make_trip(alice)["id"]
    share(alice, tid, bob, "edit")  # an editor, but not an administrator: the house key is not for them
    resp = bob.post(f"/api/trips/{tid}/stays/import", {"urls": ["https://example.com/stay"]})
    assert resp.status_code == 400
    assert "Anthropic key" in resp.json()["detail"] and "Profile" in resp.json()["detail"]
    assert HOUSE_KEY not in resp.text
    assert no_network == {}  # nothing was fetched or sent anywhere


def test_an_administrator_without_their_own_key_uses_the_house_keys(admin_alice, house, no_network):
    tid = make_trip(admin_alice)["id"]
    resp = admin_alice.post(f"/api/trips/{tid}/stays/import", {"urls": ["https://example.com/stay"]})
    assert resp.status_code == 200, resp.text
    assert no_network["anthropic"] == HOUSE_KEY and no_network["jina"] == "house-jina-0123456789ab"


def test_the_screenshot_reader_uses_the_callers_key(alice, bob, accepted, monkeypatch):
    seen = {}

    def fake(data, media_type, api_key):
        seen["key"] = api_key
        raise RuntimeError("stop here")

    monkeypatch.setattr(stay_extraction, "extract_from_image", fake)
    tid = make_trip(alice)["id"]
    sid = make_stay(alice, tid)["id"]
    share(alice, tid, bob, "edit")
    upload = {"file": ("s.png", b"\x89PNG\r\n\x1a\n" + b"0" * 20, "image/png")}

    # Without a key: refused with the explanation, and nothing was sent anywhere.
    refused = bob.client.post(f"/api/stays/{sid}/extract-screenshot", files=upload, headers=bob.headers)
    assert refused.status_code == 400 and "Profile" in refused.json()["detail"] and seen == {}

    save(bob, "anthropic", BOB_KEY)
    bob.client.post(f"/api/stays/{sid}/extract-screenshot", files=upload, headers=bob.headers)
    assert seen["key"] == BOB_KEY


def test_distance_lookups_use_the_callers_google_key_but_cached_ones_need_none(alice, bob, accepted, monkeypatch):
    calls = []

    def fake(origins, destinations, api_key, mode="walking"):
        calls.append(api_key)
        rows = [[distance.DistanceResult(distance_meters=500, distance_text="0.3 mi", duration_seconds=400, duration_text="7 mins") for _ in destinations] for _ in origins]
        return rows

    monkeypatch.setattr(distance, "get_distance_matrix", fake)
    tid = make_trip(alice)["id"]
    a = make_activity(alice, tid, name="One", address="1 Main St")["id"]
    b = make_activity(alice, tid, name="Two", address="2 Main St")["id"]
    share(alice, tid, bob, "edit")
    request = {"origins": [{"kind": "activity", "id": a}], "destinations": [{"kind": "activity", "id": b}]}

    refused = bob.post("/api/distance-matrix", request)
    assert refused.status_code == 400 and "Google Maps key" in refused.json()["detail"] and calls == []

    save(bob, "google_maps", "bobs-own-google-key-0123456789")
    first = bob.post("/api/distance-matrix", request)
    assert first.status_code == 200 and calls == ["bobs-own-google-key-0123456789"]

    # The answer is now cached on those locations: someone with no key at all can still read it.
    bob.delete("/api/profile/api-keys/google_maps")
    cached = bob.post("/api/distance-matrix", request)
    assert cached.status_code == 200 and calls == ["bobs-own-google-key-0123456789"]


# --- the live check -----------------------------------------------------------


def test_checking_a_key_never_raises_and_never_echoes_it(monkeypatch, caplog):
    import requests

    def boom(*a, **k):
        raise requests.ConnectionError(f"HTTPSConnectionPool(host='x'): key={ALICE_KEY}")

    monkeypatch.setattr(requests, "get", boom)
    with caplog.at_level(logging.WARNING):
        result = apikeys.verify("anthropic", ALICE_KEY)
    assert result[0] is None and ALICE_KEY not in result[1]
    assert ALICE_KEY not in caplog.text and "ConnectionError" in caplog.text


def test_googles_refusal_message_is_shown_without_the_key(monkeypatch):
    class Reply:
        headers = {"content-type": "application/json"}
        status_code = 200

        def json(self):
            return {"status": "REQUEST_DENIED", "error_message": f"This API project is not authorized to use this API. key={ALICE_KEY}"}

    import requests

    monkeypatch.setattr(requests, "get", lambda *a, **k: Reply())
    ok, why = apikeys.verify("google_maps", ALICE_KEY)
    assert ok is False and "not authorized" in why and ALICE_KEY not in why
