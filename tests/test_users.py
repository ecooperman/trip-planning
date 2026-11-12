"""Who may use the app: an account here is something the administrator grants
(approving an invite or adding someone), not something anyone who passes
Cloudflare's shared login gate gets by turning up. These cover the Users page's
add / remove / restore / delete and what each leaves behind."""
import pytest
from sqlalchemy import text

from shared_python import cloudflare, notify

from app import models
from app.database import engine
from tests.test_access import (
    make_activity,
    make_category,
    make_place,
    make_stay,
    make_travel,
    make_trip,
    share,
)

URL = "/api/admin/users"


@pytest.fixture()
def allowed(monkeypatch):
    """Stand-in for Cloudflare: the emails that were let through the gate."""
    emails = []
    monkeypatch.setattr(cloudflare, "allow_email", emails.append)
    return emails


@pytest.fixture()
def emails(monkeypatch):
    mails = []
    monkeypatch.setattr(notify, "send_email", lambda to, subject, body: mails.append((to, subject, body)) or True)
    return mails


def user_row(admin, email):
    return next((u for u in admin.get(URL).json() if u["email"] == email), None)


def user_id(admin, email):
    return user_row(admin, email)["id"]


# --- the page's list ---------------------------------------------------------


def test_only_the_administrator_may_use_the_users_endpoints(alice, bob):
    for call in (
        lambda: alice.get(URL),
        lambda: alice.post(URL, {"email": "x@example.com"}),
        lambda: alice.post(f"{URL}/1/revoke"),
        lambda: alice.post(f"{URL}/1/restore"),
        lambda: alice.delete(f"{URL}/1"),
    ):
        assert call().status_code == 403


def test_the_list_shows_everyone_with_what_they_own(admin, alice, bob):
    trip = make_trip(alice, "Lisbon")
    make_activity(alice, trip["id"])
    make_activity(alice, None, "Loose idea")
    make_place(alice)
    make_category(alice)
    share(alice, trip["id"], bob, "edit")
    make_trip(bob, "Porto")

    rows = {u["email"]: u for u in admin.get(URL).json()}
    assert set(rows) == {admin.email, alice.email, bob.email}
    a, b = rows[alice.email], rows[bob.email]
    assert (a["owned_trips"], a["activities"], a["places"], a["categories"], a["people_on_their_trips"]) == (1, 2, 1, 1, 1)
    assert (b["owned_trips"], b["shared_with_them"]) == (1, 1)
    assert a["status"] == "active" and a["is_admin"] is False
    assert "legacy-owner@trips.invalid" not in rows


# --- no account until one is granted ---------------------------------------------


def test_a_removed_person_cant_use_anything_but_keeps_their_data(admin, alice, bob):
    trip = make_trip(alice, "Lisbon")
    make_activity(alice, trip["id"])
    share(alice, trip["id"], bob, "edit")

    row = admin.post(f"{URL}/{user_id(admin, bob.email)}/revoke").json()
    assert row["status"] == "removed"
    for url in ("/api/me", "/api/trips", f"/api/trips/{trip['id']}", "/api/places", "/api/categories", "/api/activities"):
        resp = bob.get(url)
        assert resp.status_code == 403 and "removed" in resp.json()["detail"]
    assert bob.post("/api/trips", {"location": "Sneaky"}).status_code == 403
    # Nothing was erased: the trip is still shared with them in the database.
    assert [m["email"] for m in alice.get(f"/api/trips/{trip['id']}/members").json()][1] == bob.email

    admin.post(f"{URL}/{row['id']}/restore")
    assert [t["location"] for t in bob.get("/api/trips").json()] == ["Lisbon"]


def test_revoking_here_doesnt_touch_cloudflare(admin, alice, monkeypatch):
    calls = []
    monkeypatch.setattr(cloudflare, "allow_email", lambda e: calls.append(e))
    admin.post(f"{URL}/{user_id(admin, alice.email)}/revoke")
    assert calls == []  # another app may still need the person at the gate


def test_the_administrator_cant_be_removed_or_deleted(admin):
    admin.get("/api/me")
    me = user_id(admin, admin.email)
    assert admin.post(f"{URL}/{me}/revoke").status_code == 400
    assert admin.delete(f"{URL}/{me}").status_code == 400


def test_the_placeholder_owner_and_unknown_ids_are_not_people(admin):
    for call in (
        lambda i: admin.post(f"{URL}/{i}/revoke"),
        lambda i: admin.post(f"{URL}/{i}/restore"),
        lambda i: admin.delete(f"{URL}/{i}"),
    ):
        assert call(999).status_code == 404
    # (The administrator's first request above took over the migration's placeholder.)
    with engine.begin() as conn:
        conn.execute(text("insert into users (email) values ('legacy-owner@trips.invalid')"))
        placeholder = conn.execute(text("select id from users where email = 'legacy-owner@trips.invalid'")).scalar()
    assert admin.post(f"{URL}/{placeholder}/revoke").status_code == 404


def test_you_cant_share_with_or_invite_someone_who_was_removed(admin, alice, bob):
    trip = make_trip(alice)
    admin.post(f"{URL}/{user_id(admin, bob.email)}/revoke")
    add = alice.post(f"/api/trips/{trip['id']}/members", {"email": bob.email, "role": "view"})
    ask = alice.post(f"/api/trips/{trip['id']}/invites", {"email": bob.email, "role": "view"})
    app_ask = alice.post("/api/app-invites", {"email": bob.email})
    for resp in (add, ask, app_ask):
        assert resp.status_code == 409 and "removed" in resp.json()["detail"] and bob.email in resp.json()["detail"]


def test_an_approved_invite_for_a_removed_person_switches_them_back_on(admin, alice, allowed):
    # An invite that was waiting when they were removed: approving it is the administrator's decision.
    from app import crud
    from app.database import SessionLocal

    with SessionLocal() as s:
        invite, _ = crud.create_invite(s, None, crud.get_account(s, alice.email), "newbie@example.com", "view", for_app=True)
        invite_id = invite.id
        crud.enable_user(s, "newbie@example.com")
        crud.set_user_status(s, crud.get_account(s, "newbie@example.com"), models.USER_REMOVED)
    assert admin.post(f"/api/admin/invites/{invite_id}/approve").status_code == 200
    assert user_row(admin, "newbie@example.com")["status"] == "active"


# --- adding and restoring --------------------------------------------------------------


def test_adding_someone_lets_them_through_the_gate_gives_an_account_and_emails_them(admin, sign_in, allowed, emails):
    dana = sign_in("dana@example.com", enabled=False)
    assert dana.get("/api/trips").status_code == 403

    resp = admin.post(URL, {"email": "  Dana@Example.com "})
    assert resp.status_code == 200 and resp.json()["email"] == "dana@example.com" and resp.json()["status"] == "active"
    assert allowed == ["dana@example.com"]
    assert dana.get("/api/trips").json() == []
    assert [to for to, _, _ in emails] == ["dana@example.com"]
    assert "one-time PIN" in emails[0][2]


def test_adding_someone_who_already_has_access_is_refused(admin, alice, allowed):
    resp = admin.post(URL, {"email": alice.email})
    assert resp.status_code == 409 and alice.email in resp.json()["detail"]
    assert allowed == []


def test_adding_a_removed_person_restores_them_with_their_data(admin, alice, allowed):
    make_trip(alice, "Lisbon")
    admin.post(f"{URL}/{user_id(admin, alice.email)}/revoke")
    assert admin.post(URL, {"email": alice.email}).json()["status"] == "active"
    assert [t["location"] for t in alice.get("/api/trips").json()] == ["Lisbon"]


def test_adding_rejects_things_that_are_not_emails(admin, allowed):
    assert admin.post(URL, {"email": "nope"}).status_code in (400, 422)
    assert allowed == []


@pytest.mark.parametrize(
    "error, status",
    [
        (cloudflare.NotConfigured("off"), 503),
        (cloudflare.SeatCapReached("full"), 409),
        (cloudflare.CloudflareError("down"), 502),
    ],
)
def test_if_cloudflare_cant_do_it_nobody_is_added_or_restored(admin, alice, monkeypatch, error, status):
    def fail(email):
        raise error

    monkeypatch.setattr(cloudflare, "allow_email", fail)
    assert admin.post(URL, {"email": "dana@example.com"}).status_code == status
    assert user_row(admin, "dana@example.com") is None

    admin.post(f"{URL}/{user_id(admin, alice.email)}/revoke")
    assert admin.post(f"{URL}/{user_id(admin, alice.email)}/restore").status_code == status
    assert user_row(admin, alice.email)["status"] == "removed"


# --- deleting ---------------------------------------------------------------------------


def test_deleting_needs_the_person_removed_first(admin, alice):
    make_trip(alice)
    resp = admin.delete(f"{URL}/{user_id(admin, alice.email)}")
    assert resp.status_code == 409
    assert user_row(admin, alice.email)["owned_trips"] == 1


def count(db, model):
    db.expire_all()
    return db.query(model).count()


def test_deleting_erases_what_they_own_and_keeps_a_removed_account(admin, alice, bob, allowed, db):
    from app import crud

    mine = make_trip(alice, "Lisbon")
    place = make_place(alice, "Cafe")
    category = make_category(alice, "Food")
    make_activity(alice, mine["id"], "Dinner", place_id=place["id"], category_ids=[category["id"]])
    make_activity(alice, None, "Loose idea")
    stay = make_stay(alice, mine["id"])
    make_travel(alice, mine["id"])
    share(alice, mine["id"], bob, "view")
    bobs = make_trip(bob, "Porto")
    share(bob, bobs["id"], alice, "edit")
    # cached distances for her stay, her API key, a request she made, and one made on her trip
    db.add(models.LocationDistance(origin_kind="stay", origin_id=stay["id"], destination_kind="activity", destination_id=999,
                                   mode="walking", distance_meters=1, distance_text="1 m", duration_seconds=1, duration_text="1 s"))
    db.add(models.UserApiKey(user_id=crud.get_account(db, alice.email).id, provider="anthropic", encrypted_key="x", last4="1234"))
    db.commit()
    assert alice.post("/api/app-invites", {"email": "newbie@example.com"}).status_code == 200
    assert alice.post(f"/api/trips/{mine['id']}/invites", {"email": "other@example.com", "role": "view"}).status_code == 200
    bob_activities = make_activity(bob, bobs["id"], "Bob's activity")

    alice_id = user_id(admin, alice.email)
    admin.post(f"{URL}/{alice_id}/revoke")
    assert admin.delete(f"{URL}/{alice_id}").json() == {"ok": True}

    row = user_row(admin, alice.email)
    assert row["status"] == "removed"
    assert (row["owned_trips"], row["activities"], row["places"], row["categories"], row["shared_with_them"]) == (0, 0, 0, 0, 0)
    # Her trip is gone for bob too; bob's own trip is intact and she is no longer on it.
    assert [t["location"] for t in bob.get("/api/trips").json()] == ["Porto"]
    assert [m["email"] for m in bob.get(f"/api/trips/{bobs['id']}/members").json()] == [bob.email]
    assert [a["name"] for a in bob.get("/api/activities").json()] == ["Bob's activity"]
    for model in (models.Invite, models.Stay, models.TravelSegment, models.UserApiKey, models.LocationDistance, models.Place):
        assert count(db, model) == 0, model
    assert count(db, models.Category) == 0 and count(db, models.Activity) == 1
    # She still can't walk back in with a fresh account.
    assert alice.get("/api/trips").status_code == 403
    assert db.query(models.User).filter_by(email=alice.email).count() == 1

    # Restoring gives her a clean, empty account.
    admin.post(f"{URL}/{alice_id}/restore")
    assert alice.get("/api/trips").json() == []


def test_deleting_one_person_leaves_everyone_elses_data_alone(admin, alice, bob):
    trip = make_trip(bob, "Porto")
    make_activity(bob, trip["id"])
    make_place(bob, "Bar")
    make_category(bob, "Drinks")
    make_trip(alice)
    admin.post(f"{URL}/{user_id(admin, alice.email)}/revoke")
    admin.delete(f"{URL}/{user_id(admin, alice.email)}")
    row = user_row(admin, bob.email)
    assert (row["owned_trips"], row["activities"], row["places"], row["categories"]) == (1, 1, 1, 1)


def test_people_the_deleted_person_let_in_keep_their_accounts(admin, alice, allowed):
    alice.post("/api/app-invites", {"email": "dana@example.com"})
    invite = admin.get("/api/admin/invites").json()[0]
    admin.post(f"/api/admin/invites/{invite['id']}/approve")
    admin.post(f"{URL}/{user_id(admin, alice.email)}/revoke")
    admin.delete(f"{URL}/{user_id(admin, alice.email)}")
    assert user_row(admin, "dana@example.com")["status"] == "active"


# --- the schema -----------------------------------------------------------------------


def test_accounts_that_existed_before_the_column_are_active():
    """The migration's default is what makes today's accounts keep working."""
    with engine.begin() as conn:
        conn.execute(text("insert into users (email) values ('old@example.com')"))
        status = conn.execute(text("select status from users where email = 'old@example.com'")).scalar()
    assert status == "active"


# --- the pages ---------------------------------------------------------------------


PAGES = ("/", "/activities.html", "/places.html", "/trip.html", "/agenda.html", "/compare.html", "/invites.html", "/profile.html")


def test_pages_open_for_people_with_access(alice, admin):
    for page in PAGES:
        assert alice.get(page).status_code == 200
        assert admin.get(page).status_code == 200


def test_pages_explain_instead_of_showing_an_empty_app_to_people_without_access(sign_in, admin, alice):
    stranger = sign_in("stranger@example.com", enabled=False)
    for page in PAGES + ("/users.html",):
        resp = stranger.get(page)
        assert resp.status_code == 403
        assert "have access yet" in resp.text and "stranger@example.com" in resp.text
        assert "Log out" in resp.text and "app-nav-mount" not in resp.text  # none of the app itself

    admin.post(f"{URL}/{user_id(admin, alice.email)}/revoke")
    removed = alice.get("/")
    assert removed.status_code == 403 and "Your access was removed" in removed.text


def test_the_users_page_is_for_the_administrator_only(admin, alice):
    assert admin.get("/users.html").status_code == 200
    resp = alice.get("/users.html")
    assert resp.status_code == 403 and "Administrators only" in resp.text


# --- who counts as able to sign in ---------------------------------------------------------------


def test_a_second_administrator_gets_an_account_on_first_sight(admin, sign_in, monkeypatch, db):
    from app import config

    other = sign_in("boss2@example.com", enabled=False)
    monkeypatch.setattr(config, "ADMIN_EMAILS", config.ADMIN_EMAILS | {"boss2@example.com"})
    admin.get("/api/me")  # the first administrator takes over the pre-accounts placeholder
    assert other.get("/api/me").json()["is_admin"] is True
    assert db.query(models.User).filter_by(email="boss2@example.com").count() == 1


def test_can_sign_in_needs_an_active_account(db):
    from app import crud
    from app.signin import can_sign_in

    assert can_sign_in(db, "nobody@example.com") is False  # no account
    user = crud.enable_user(db, "dana@example.com")
    assert can_sign_in(db, "dana@example.com") is True
    crud.set_user_status(db, user, models.USER_REMOVED)
    assert can_sign_in(db, "dana@example.com") is False


def test_anyone_else_has_to_be_let_in_first(sign_in, db):
    stranger = sign_in("stranger@example.com", enabled=False)
    for url in ("/api/me", "/api/trips", "/api/places"):
        resp = stranger.get(url)
        assert resp.status_code == 403 and "haven't been given access" in resp.json()["detail"]
    assert stranger.post("/api/trips", {"location": "Mine"}).status_code == 403
    # Turning up leaves no account behind to be quietly enabled later.
    assert db.query(models.User).filter_by(email="stranger@example.com").first() is None


# --- the service token (other apps on this machine) ------------------------------------------


def test_the_service_user_is_created_on_first_use_but_not_when_removed(client, admin, monkeypatch, db):
    from app import config, crud

    monkeypatch.setattr(config, "SERVICE_TOKEN", "s3cret-token")
    monkeypatch.setattr(config, "SERVICE_USER_EMAIL", "robot@example.com")
    headers = {"X-Service-Token": "s3cret-token"}
    # No account yet: the operator configured this identity, so it is created.
    assert crud.get_account(db, "robot@example.com") is None
    crud.service_user(db, "robot@example.com")
    db.expire_all()
    account = crud.get_account(db, "robot@example.com")
    assert account is not None and account.status == "active"
    assert client.get("/api/trips", headers=headers).status_code == 200  # works through the token
    # An administrator who removed it keeps it out.
    admin.post(f"{URL}/{account.id}/revoke")
    assert client.get("/api/trips", headers=headers).status_code == 403
    admin.post(f"{URL}/{account.id}/restore")
    assert client.get("/api/trips", headers=headers).status_code == 200
