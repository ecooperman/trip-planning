"""Trips asks the dashboard for what a person saved, with that person's own sign-in cookie, and never fails a page because it cannot."""
import requests
from shared_python import auth, settings


class Reply:
    def __init__(self, status=200, body=None):
        self.status_code, self._body = status, body

    def json(self):
        return self._body


def test_what_the_person_saved_comes_from_the_dashboard_with_their_cookie(alice, monkeypatch):
    calls = []
    monkeypatch.setattr(settings, "DASHBOARD_API_BASE", "http://127.0.0.1:8090")
    monkeypatch.setattr(auth, "oidc_cookie_name", lambda: "oidc_session")
    monkeypatch.setattr(
        requests, "get",
        lambda url, headers=None, timeout=None, allow_redirects=True: calls.append((url, headers)) or Reply(200, {"keys": {"anthropic": {"last4": "wxyz", "added_at": "2026-11-23T10:00:00Z"}}}),
    )
    alice.client.cookies.set("oidc_session", "TOKEN")
    me = alice.get("/api/me").json()
    assert me["can_use"]["anthropic"] is True and me["can_use"]["google_maps"] is False
    asked = [c for c in calls if c[0].endswith("/internal/keys")]
    assert asked and asked[0][1] == {"Cookie": "oidc_session=TOKEN"}  # only the sign-in cookie, so only this person's keys
    profile = alice.get("/api/profile/api-keys").json()["keys"]
    assert next(k for k in profile if k["provider"] == "anthropic")["last4"] == "wxyz"


def test_a_dashboard_that_is_down_does_not_break_the_page_it_only_says_nothing_is_saved(alice, monkeypatch):
    def down(*args, **kwargs):
        raise requests.ConnectionError("down")

    monkeypatch.setattr(settings, "DASHBOARD_API_BASE", "http://127.0.0.1:8090")
    monkeypatch.setattr(requests, "get", down)
    resp = alice.get("/api/me")
    assert resp.status_code == 200 and resp.json()["can_use"] == {"anthropic": False, "google_maps": False, "jina": False}
    assert alice.get("/api/profile/api-keys").status_code == 200


def test_actually_using_a_key_while_the_dashboard_is_down_is_a_sentence_not_a_missing_key(alice, monkeypatch):
    from app import apikeys, models
    from app.database import SessionLocal

    def down(*args, **kwargs):
        raise requests.ConnectionError("down")

    monkeypatch.setattr(settings, "DASHBOARD_API_BASE", "http://127.0.0.1:8090")
    monkeypatch.setattr(requests, "get", down)
    alice.get("/api/me")
    from shared_python import user_keys

    with SessionLocal() as db, user_keys.use(user_keys.KeySession(None)):
        user = db.query(models.User).filter_by(email=alice.email).one()
        try:
            apikeys.require(db, user, "anthropic")
            raised = None
        except Exception as exc:  # noqa: BLE001
            raised = exc
    assert getattr(raised, "status_code", None) == 503 and "try again" in raised.detail
