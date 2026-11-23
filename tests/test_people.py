"""The people suggested in the sharing box (GET /api/me/people): only an administrator gets any. Everyone else types the whole address,
because suggestions would tell them who else uses the apps."""
import sqlite3

from tests.test_access import make_trip, share
from tests.test_users import fake_apps


def people(person):
    resp = person.get("/api/me/people")
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_an_ordinary_person_gets_no_suggestions_even_after_sharing(alice, bob, carol, tmp_path, monkeypatch):
    fake_apps(tmp_path, monkeypatch, finances=("finances.db", ["someone@example.com", bob.email]))
    assert people(alice) == []
    thing = make_trip(alice)
    share(alice, thing["id"], bob, "edit")
    assert people(alice) == []  # nor people they now share with
    assert people(bob) == [] and people(carol) == []


def test_an_administrator_is_offered_everyone_with_their_names_but_not_themselves(admin, tmp_path, monkeypatch):
    fake_apps(tmp_path, monkeypatch, finances=("finances.db", ["Ann@Example.com", "bob@example.com", admin.email]))
    (tmp_path / "dashboard").mkdir()
    connection = sqlite3.connect(tmp_path / "dashboard" / "people.db")
    connection.execute("CREATE TABLE names (email TEXT PRIMARY KEY, first_name TEXT, last_name TEXT)")
    connection.execute("INSERT INTO names VALUES ('ann@example.com', 'Ann', 'Lee')")
    connection.commit()
    connection.close()
    assert people(admin) == [{"email": "ann@example.com", "name": "Ann Lee"}, {"email": "bob@example.com", "name": ""}]
