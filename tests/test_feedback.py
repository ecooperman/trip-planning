"""Send feedback in the menu: only someone with an account here may send it, and it goes to the dashboard's inbox as coming from this app."""
import requests
from shared_python import auth, settings

BODY = {"kind": "idea", "body": "It would be nice if..."}


def dashboard(monkeypatch):
    calls = []

    class Reply:
        status_code = 200

        def json(self):
            return {"id": 1}

    monkeypatch.setattr(settings, "DASHBOARD_API_BASE", "http://127.0.0.1:8090")
    monkeypatch.setattr(requests, "post", lambda url, json=None, headers=None, timeout=None, allow_redirects=True: calls.append((url, json)) or Reply())
    return calls


def test_a_member_sends_feedback_to_the_dashboard_as_this_app(alice, monkeypatch):
    calls = dashboard(monkeypatch)
    assert alice.post("/api/feedback", BODY).status_code == 200
    sent = [c for c in calls if c[0].endswith("/internal/feedback")]  # (the first visit of the day is also reported, to another route)
    assert sent == [("http://127.0.0.1:8090/internal/feedback", {"app": "trips", **BODY, "page": None})]


def test_someone_with_no_account_here_cannot(sign_in, monkeypatch):
    calls = dashboard(monkeypatch)
    assert sign_in("nobody@example.com", enabled=False).post("/api/feedback", BODY).status_code == 403
    assert [c for c in calls if c[0].endswith("/internal/feedback")] == []  # nothing was passed on
