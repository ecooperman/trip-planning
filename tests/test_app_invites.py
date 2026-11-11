"""Invites to the app itself (not to one trip): anyone asks for a person with no
account to be let in, the administrator decides, and approving only lets them in
(they get an account, with nothing shared yet). The Cloudflare call and the
notifications are stubbed here; what matters is who may ask and decide, the shared
allowance, and what each outcome leaves behind."""
import pytest
from shared_python import cloudflare, notify
from sqlalchemy.exc import IntegrityError

from app import config, models
from tests.test_access import make_trip, share

NEWBIE = "newbie@example.com"


@pytest.fixture()
def allowed(monkeypatch):
    """Stand-in for Cloudflare: the emails that were let through the gate."""
    emails = []
    monkeypatch.setattr(cloudflare, "allow_email", emails.append)
    return emails


@pytest.fixture()
def alerts(monkeypatch):
    """Stand-in for the administrator's alert channels."""
    messages = []
    monkeypatch.setattr(notify, "notify", lambda title, message, link=None: messages.append((title, message, link)))
    return messages


@pytest.fixture()
def emailed(monkeypatch):
    """Stand-in for email: (to, subject, body) of each message sent."""
    sent = []
    monkeypatch.setattr(notify, "send_email", lambda to, subject, body: sent.append((to, subject, body)) or True)
    return sent


def ask(person, email=NEWBIE):
    return person.post("/api/app-invites", {"email": email})


def ask_on_trip(person, trip_id, email=NEWBIE, role="edit"):
    return person.post(f"/api/trips/{trip_id}/invites", {"email": email, "role": role})


# --- asking ----------------------------------------------------------------------


def test_asking_waits_for_approval_and_shows_in_the_administrators_queue(alice, admin, allowed, alerts):
    resp = ask(alice, "  NewBie@Example.com ")
    assert resp.status_code == 200 and resp.json()["email"] == NEWBIE and resp.json()["status"] == "pending"
    assert allowed == []  # nobody is let through until the administrator says so
    assert admin.get("/api/me").json()["pending_invites"] == 1
    waiting = admin.get("/api/admin/invites").json()
    assert [(w["email"], w["for_app"], w["invited_by_email"], w["trip_name"]) for w in waiting] == [(NEWBIE, True, alice.email, None)]


def test_the_administrator_is_told_without_an_access_level(alice, admin, allowed, alerts):
    ask(alice)
    assert len(alerts) == 1
    title, message, link = alerts[0]
    assert "invite waiting for approval" in title and alice.email in message and NEWBIE in message
    assert "(can" not in message and link.endswith("/invites.html")


def test_a_failing_alert_doesnt_fail_the_request(alice, allowed, monkeypatch):
    def broken(title, message, link):
        raise RuntimeError("push service is down")

    monkeypatch.setattr(notify, "CHANNELS", {"ntfy": broken})
    assert ask(alice).status_code == 200


def test_an_administrators_own_request_is_approved_straight_away(admin, allowed, alerts, emailed, db):
    resp = ask(admin)
    assert resp.status_code == 200 and resp.json()["status"] == "approved"
    assert allowed == [NEWBIE] and alerts == []
    assert db.query(models.User).filter_by(email=NEWBIE).count() == 1
    assert emailed and emailed[0][0] == NEWBIE and "invited you to" in emailed[0][1]


def test_a_bad_address_is_refused(alice):
    assert ask(alice, "not-an-email").status_code == 400


def test_someone_who_can_already_sign_in_is_not_invited(alice, bob):
    bob.get("/api/me")  # an account exists, and with no Cloudflare to ask that is what counts
    resp = ask(alice, bob.email)
    assert resp.status_code == 409 and "already sign in" in resp.json()["detail"]
    assert alice.get("/api/app-invites").json() == []


def test_a_repeat_request_is_refused_whoever_makes_it(alice, bob, allowed, alerts):
    assert ask(alice).status_code == 200
    again = ask(bob)
    assert again.status_code == 409 and "already waiting" in again.json()["detail"]
    assert ask(alice, NEWBIE.upper()).status_code == 409


def test_a_declined_person_cant_be_asked_for_again(alice, bob, admin, allowed, alerts):
    invite = ask(alice).json()
    admin.post(f"/api/admin/invites/{invite['id']}/decline")
    resp = ask(bob)
    assert resp.status_code == 409 and "declined" in resp.json()["detail"]


def test_an_app_invite_and_an_invite_to_a_trip_for_the_same_person_are_separate(alice, bob, allowed, alerts):
    thing = make_trip(alice)
    assert ask_on_trip(alice, thing["id"]).status_code == 200
    assert ask(bob).status_code == 200  # a different kind of request, not a duplicate


def test_only_one_app_invite_per_email_is_possible_even_if_two_race_in(db, alice):
    alice.get("/api/me")
    inviter = db.query(models.User).filter_by(email=alice.email).one()
    db.add(models.Invite(email=NEWBIE, role="view", invited_by_id=inviter.id, for_app=True))
    db.commit()
    db.add(models.Invite(email=NEWBIE, role="view", invited_by_id=inviter.id, for_app=True))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_invites_to_a_deleted_trip_dont_collide_with_each_other(db, alice):
    alice.get("/api/me")
    inviter = db.query(models.User).filter_by(email=alice.email).one()
    for _ in range(2):  # approved invites outlive their trip with no trip: many may share an email
        db.add(models.Invite(email=NEWBIE, role="view", invited_by_id=inviter.id, status=models.INVITE_APPROVED))
    db.commit()
    assert db.query(models.Invite).count() == 2


# --- the allowance ----------------------------------------------------------------


def test_the_allowance_is_shared_with_invites_to_a_trip(alice, admin, allowed, alerts, monkeypatch):
    monkeypatch.setattr(config, "INVITES_PER_USER", 2)
    thing = make_trip(alice)
    assert ask_on_trip(alice, thing["id"], "a@example.com").status_code == 200
    assert ask(alice, "b@example.com").status_code == 200
    third = ask(alice, "c@example.com")
    assert third.status_code == 403 and "used all 2" in third.json()["detail"]
    assert alice.get("/api/me").json()["invites_left"] == 0
    assert admin.get("/api/me").json()["invites_left"] is None


def test_withdrawing_a_waiting_request_gives_the_invite_back(alice, allowed, alerts):
    invite = ask(alice).json()
    left = alice.get("/api/me").json()["invites_left"]
    assert alice.delete(f"/api/app-invites/{invite['id']}").status_code == 200
    assert alice.get("/api/me").json()["invites_left"] == left + 1
    assert alice.get("/api/app-invites").json() == []


def test_only_your_own_waiting_app_requests_can_be_withdrawn(alice, bob, admin, allowed, alerts):
    invite = ask(alice).json()
    assert bob.delete(f"/api/app-invites/{invite['id']}").status_code == 404
    on_trip = ask_on_trip(alice, make_trip(alice)["id"], "other@example.com").json()
    assert alice.delete(f"/api/app-invites/{on_trip['id']}").status_code == 404  # that one is the trip's to withdraw
    admin.post(f"/api/admin/invites/{invite['id']}/approve")
    assert alice.delete(f"/api/app-invites/{invite['id']}").status_code == 409  # decided: too late


def test_people_see_only_their_own_app_requests_and_never_a_trips(alice, bob, allowed, alerts):
    ask(alice)
    ask_on_trip(alice, make_trip(alice)["id"], "other@example.com")
    assert [i["email"] for i in alice.get("/api/app-invites").json()] == [NEWBIE]
    assert bob.get("/api/app-invites").json() == []
    trip_id = alice.get("/api/trips").json()[0]["id"]
    assert [i["email"] for i in alice.get(f"/api/trips/{trip_id}/invites").json()] == ["other@example.com"]  # not the app one


# --- the administrator decides -----------------------------------------------------


def test_approving_lets_them_in_with_an_account_but_nothing_shared(alice, admin, sign_in, allowed, alerts, emailed, db):
    invite = ask(alice).json()
    resp = admin.post(f"/api/admin/invites/{invite['id']}/approve")
    assert resp.status_code == 200 and resp.json()["status"] == "approved" and resp.json()["for_app"] is True
    assert allowed == [NEWBIE]
    assert db.query(models.User).filter_by(email=NEWBIE).count() == 1
    to, subject, body = emailed[0]
    assert to == NEWBIE and alice.email in subject and "invited you to" in subject and NEWBIE in body
    newcomer = sign_in(NEWBIE)
    assert newcomer.get("/api/trips").json() == []  # signed in, empty account, free to create their own
    assert newcomer.post("/api/trips", {"location": "Rome"}).status_code == 200


def test_if_cloudflare_refuses_the_request_stays_waiting(alice, admin, monkeypatch, alerts, db):
    def refuse(email):
        raise cloudflare.SeatCapReached("The Access group is full (50 people).")

    monkeypatch.setattr(cloudflare, "allow_email", refuse)
    invite = ask(alice).json()
    resp = admin.post(f"/api/admin/invites/{invite['id']}/approve")
    assert resp.status_code == 409 and "full" in resp.json()["detail"]
    assert db.query(models.Invite).one().status == models.INVITE_PENDING
    assert db.query(models.User).filter_by(email=NEWBIE).count() == 0


def test_declining_emails_nobody_and_leaves_no_account(alice, admin, allowed, alerts, emailed, db):
    invite = ask(alice).json()
    assert admin.post(f"/api/admin/invites/{invite['id']}/decline").json()["status"] == "declined"
    assert emailed == [] and allowed == []
    assert db.query(models.User).filter_by(email=NEWBIE).count() == 0


def test_only_the_administrator_decides_app_requests(alice, bob, admin, allowed, alerts):
    invite = ask(alice).json()
    for person in (alice, bob):
        assert person.post(f"/api/admin/invites/{invite['id']}/approve").status_code == 403
        assert person.get("/api/admin/invites").status_code == 403


# --- declined requests can be allowed again -------------------------------------------


def decline(admin, invite):
    return admin.post(f"/api/admin/invites/{invite['id']}/decline")


def test_the_administrator_sees_declined_requests_of_every_kind_and_only_those(alice, admin, allowed, alerts):
    thing = make_trip(alice)
    app_invite = ask(alice, "app@example.com").json()
    on_thing = ask_on_trip(alice, thing["id"], "thing@example.com").json()
    ask(alice, "waiting@example.com")  # still waiting: not declined
    approved = ask(admin, "ok@example.com").json()  # the administrator's own: approved at once
    assert approved["status"] == "approved"
    decline(admin, app_invite), decline(admin, on_thing)
    declined = admin.get("/api/admin/invites/declined").json()
    assert sorted((d["email"], d["for_app"], d["trip_name"]) for d in declined) == [
        ("app@example.com", True, None),
        ("thing@example.com", False, thing["location"]),
    ]
    assert all(d["invited_by_email"] == alice.email and d["decided_at"] and d["status"] == "declined" for d in declined)


def test_only_the_administrator_sees_or_allows_again_declined_requests(alice, bob, admin, allowed, alerts):
    invite = ask(alice).json()
    decline(admin, invite)
    for person in (alice, bob):
        assert person.get("/api/admin/invites/declined").status_code == 403
        assert person.post(f"/api/admin/invites/{invite['id']}/reinstate").status_code == 403
    assert len(admin.get("/api/admin/invites/declined").json()) == 1  # nothing was removed


def test_allowing_again_lets_the_person_be_asked_for_and_gives_the_invite_back(alice, bob, admin, allowed, alerts):
    invite = ask(alice).json()
    left = alice.get("/api/me").json()["invites_left"]
    decline(admin, invite)
    assert ask(bob).status_code == 409  # blocked while declined
    assert admin.post(f"/api/admin/invites/{invite['id']}/reinstate").status_code == 200
    assert admin.get("/api/admin/invites/declined").json() == []
    assert alice.get("/api/me").json()["invites_left"] == left + 1
    assert ask(bob).status_code == 200  # anyone may ask again now


def test_a_declined_invite_to_a_trip_can_be_allowed_again_too(alice, admin, allowed, alerts):
    thing = make_trip(alice)
    invite = ask_on_trip(alice, thing["id"]).json()
    decline(admin, invite)
    assert ask_on_trip(alice, thing["id"]).status_code == 409
    assert admin.post(f"/api/admin/invites/{invite['id']}/reinstate").status_code == 200
    assert ask_on_trip(alice, thing["id"]).status_code == 200


def test_only_a_declined_request_can_be_allowed_again(alice, admin, allowed, alerts, db):
    waiting = ask(alice).json()
    assert admin.post(f"/api/admin/invites/{waiting['id']}/reinstate").status_code == 409
    assert admin.post("/api/admin/invites/999/reinstate").status_code == 404
    assert db.query(models.Invite).count() == 1  # the waiting request is untouched
    admin.post(f"/api/admin/invites/{waiting['id']}/approve")
    assert admin.post(f"/api/admin/invites/{waiting['id']}/reinstate").status_code == 409  # approved ones stay
