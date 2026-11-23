"""Whose key a paid call uses: the caller's own (saved once on the dashboard and fetched for this request), else the house key for an
administrator and nobody else. The dashboard and the calls out to Anthropic, Google and Jina are all stubbed."""
import pytest

from app import apikeys, config, distance, models, stay_extraction
from app.routers import stay_compare
from tests.test_access import make_activity, make_stay, make_trip, share

ALICE_KEY = "sk-ant-alice-0123456789abcdef"
BOB_KEY = "sk-ant-bob---0123456789wxyz"
HOUSE_KEY = "sk-ant-HOUSE-0123456789house"


@pytest.fixture(autouse=True)
def saved_on_the_dashboard(monkeypatch):
    """What each person has saved on the dashboard: {(email, provider): key}. The real lookup forwards the caller's sign-in cookie to the dashboard
    (shared_python.user_keys); here the person is the one in the test."""
    store = {}
    monkeypatch.setattr(apikeys, "_own_key", lambda user, provider: store.get((user.email, provider)))
    monkeypatch.setattr(
        apikeys, "_saved", lambda user: {p: {"last4": k[-4:], "added_at": "2026-11-23T10:00:00Z"} for (e, p), k in store.items() if e == user.email}
    )
    return store


@pytest.fixture()
def keys(saved_on_the_dashboard):
    return saved_on_the_dashboard


@pytest.fixture(autouse=True)
def _remember_store(saved_on_the_dashboard):
    global _STORE
    _STORE = saved_on_the_dashboard


_STORE = {}


def save(person, provider, key):
    _STORE[(person.email, provider)] = key


def unsave(person, provider):
    _STORE.pop((person.email, provider), None)


@pytest.fixture()
def house(monkeypatch):
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", HOUSE_KEY)
    monkeypatch.setattr(config, "GOOGLE_MAPS_API_KEY", "house-google-0123456789")
    monkeypatch.setattr(config, "JINA_API_KEY", "house-jina-0123456789ab")


@pytest.fixture()
def admin_alice(monkeypatch, alice):
    monkeypatch.setattr(config, "ADMIN_EMAILS", {alice.email})
    return alice


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


def test_an_own_key_beats_the_house_key_even_for_an_administrator(admin_alice, house, db):
    save(admin_alice, "anthropic", ALICE_KEY)
    user = db.query(models.User).filter_by(email=admin_alice.email).one()
    assert apikeys.resolve(db, user, "anthropic") == ALICE_KEY
    # ...and removing it falls back to the house key
    unsave(admin_alice, "anthropic")
    assert apikeys.resolve(db, user, "anthropic") == HOUSE_KEY


def test_a_non_administrator_with_their_own_key_can_use_the_feature(bob, house):
    save(bob, "google_maps", "bobs-own-google-key-0123456789")
    me = bob.get("/api/me").json()
    assert me["can_use"]["google_maps"] is True and me["can_use"]["anthropic"] is False


def test_the_profile_page_says_what_is_set_and_never_has_a_key_to_show(alice, house):
    save(alice, "anthropic", ALICE_KEY)
    listing = alice.get("/api/profile/api-keys")
    assert listing.status_code == 200 and ALICE_KEY not in listing.text
    mine = {k["provider"]: k for k in listing.json()["keys"]}
    assert mine["anthropic"]["has_own_key"] is True and mine["anthropic"]["last4"] == ALICE_KEY[-4:] and mine["anthropic"]["usable"] is True
    assert mine["google_maps"]["has_own_key"] is False and mine["google_maps"]["usable"] is False  # alice is not an administrator: no house key
    assert alice.put("/api/profile/api-keys/anthropic", {"key": ALICE_KEY}).status_code == 405  # saving is on the dashboard now
    assert alice.delete("/api/profile/api-keys/anthropic").status_code == 405


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


def test_stay_import_uses_the_signed_in_persons_own_keys(alice, bob, no_network):
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
    assert "Anthropic key" in resp.json()["detail"] and "profile" in resp.json()["detail"]
    assert HOUSE_KEY not in resp.text
    assert no_network == {}  # nothing was fetched or sent anywhere


def test_an_administrator_without_their_own_key_uses_the_house_keys(admin_alice, house, no_network):
    tid = make_trip(admin_alice)["id"]
    resp = admin_alice.post(f"/api/trips/{tid}/stays/import", {"urls": ["https://example.com/stay"]})
    assert resp.status_code == 200, resp.text
    assert no_network["anthropic"] == HOUSE_KEY and no_network["jina"] == "house-jina-0123456789ab"


def test_the_screenshot_reader_uses_the_callers_key(alice, bob, monkeypatch):
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
    assert refused.status_code == 400 and "profile" in refused.json()["detail"] and seen == {}

    save(bob, "anthropic", BOB_KEY)
    bob.client.post(f"/api/stays/{sid}/extract-screenshot", files=upload, headers=bob.headers)
    assert seen["key"] == BOB_KEY


def test_distance_lookups_use_the_callers_google_key_but_cached_ones_need_none(alice, bob, monkeypatch):
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
    unsave(bob, "google_maps")
    cached = bob.post("/api/distance-matrix", request)
    assert cached.status_code == 200 and calls == ["bobs-own-google-key-0123456789"]


