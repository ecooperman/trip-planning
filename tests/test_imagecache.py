"""A scraped page's picture is kept, not hot-linked: Instagram-style signed
addresses stop working after a few weeks (see app/imagecache.py)."""
import pytest
import requests

from app import crud, imagecache, models
from app.netguard import UnsafeURL

from conftest import Person

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 40


class FakeResponse:
    def __init__(self, content=PNG, content_type="image/png", status_code=200):
        self.content, self.status_code = content, status_code
        self.headers = {"Content-Type": content_type}


def fetching(monkeypatch, response=None, error=None):
    """Make the download return `response` (or raise `error`), recording the addresses asked for."""
    asked = []

    def fake(url, headers=None, timeout=10):
        asked.append(url)
        if error:
            raise error
        return response

    monkeypatch.setattr(imagecache, "safe_get", fake)
    return asked


def test_a_downloaded_image_is_stored_and_its_address_replaced(db, monkeypatch):
    fetching(monkeypatch, FakeResponse())
    stored = imagecache.localize(db, "https://scontent.cdninstagram.com/pic.jpg?oe=1")
    db.commit()
    assert stored.startswith("/api/cached-images/")
    image = db.get(models.CachedImage, int(stored.rsplit("/", 1)[1]))
    assert image.data == PNG and image.content_type == "image/png"


@pytest.mark.parametrize("given", [None, "", "/api/cached-images/7"])
def test_nothing_to_fetch_leaves_the_value_alone(db, monkeypatch, given):
    asked = fetching(monkeypatch, FakeResponse())
    assert imagecache.localize(db, given) == given
    assert asked == []


@pytest.mark.parametrize(
    "response, error",
    [
        (FakeResponse(content_type="text/html"), None),  # a login page, not a picture
        (FakeResponse(content_type="image/svg+xml"), None),  # can carry script
        (FakeResponse(status_code=403), None),  # already expired
        (FakeResponse(content=b""), None),
        (None, UnsafeURL("private")),
        (None, requests.RequestException("timeout")),
    ],
)
def test_when_it_cannot_be_kept_the_original_address_is_stored(db, monkeypatch, response, error):
    fetching(monkeypatch, response, error)
    url = "https://example.com/pic.jpg"
    assert imagecache.localize(db, url) == url
    assert db.query(models.CachedImage).count() == 0


def test_a_saved_place_points_at_its_own_copy(client, db, monkeypatch):
    alice = Person(client, "alice@example.com")
    place = alice.post("/api/places", json={"name": "Cafe"}).json()
    fetching(monkeypatch, FakeResponse())
    saved = crud.save_place_scrape_result(db, place["id"], models.ScrapeStatus.success, title="Cafe", image_url="https://example.com/p.jpg")
    assert saved.scraped_image_url.startswith("/api/cached-images/")
    loaded = alice.get(saved.scraped_image_url)
    assert loaded.status_code == 200 and loaded.content == PNG
    assert loaded.headers["content-type"] == "image/png"


def test_only_people_enabled_in_the_app_can_load_one(client, db, monkeypatch):
    fetching(monkeypatch, FakeResponse())
    url = imagecache.localize(db, "https://example.com/p.jpg")
    db.commit()
    assert Person(client, "stranger@example.com", enabled=False).get(url).status_code == 403
    assert Person(client, "alice@example.com").get(url).status_code == 200
    assert Person(client, "alice@example.com").get("/api/cached-images/99999").status_code == 404


# --- the same picture is stored once, and pictures nothing uses are cleaned up ---


def test_the_same_picture_again_reuses_the_stored_copy(db, monkeypatch):
    fetching(monkeypatch, FakeResponse())
    first = imagecache.localize(db, "https://scontent.example/pic.jpg?sig=aaa")
    db.commit()
    # A re-scrape: a different signed address, byte-for-byte the same picture.
    second = imagecache.localize(db, "https://scontent.example/pic.jpg?sig=bbb")
    db.commit()
    assert first == second
    assert db.query(models.CachedImage).count() == 1


def test_a_different_picture_is_stored_separately(db, monkeypatch):
    fetching(monkeypatch, FakeResponse(content=PNG))
    first = imagecache.localize(db, "https://example.com/a.png")
    fetching(monkeypatch, FakeResponse(content=PNG + b"1"))
    second = imagecache.localize(db, "https://example.com/b.png")
    db.commit()
    assert first != second
    assert db.query(models.CachedImage).count() == 2


def _kept(db, data, age_days):
    image = models.CachedImage(
        content_type="image/png", data=data, content_hash=imagecache.hashlib.sha256(data).hexdigest(),
        created_at=imagecache.datetime.utcnow() - imagecache.timedelta(days=age_days),
    )
    db.add(image)
    db.commit()
    return image.id


def test_old_pictures_nothing_points_at_are_removed(client, db):
    alice = Person(client, "alice@example.com")
    place = alice.post("/api/places", json={"name": "Cafe"}).json()
    used, orphan, fresh_orphan = _kept(db, b"used", 5), _kept(db, b"orphan", 5), _kept(db, b"fresh", 0)
    row = db.get(models.Place, place["id"])
    row.scraped_image_url = f"{imagecache.LOCAL_PREFIX}{used}"
    db.commit()
    assert imagecache.purge_unused(db) == 1
    db.commit()
    left = {i for (i,) in db.query(models.CachedImage.id)}
    assert left == {used, fresh_orphan}  # in use stays; a just-saved one gets a day's grace
    assert orphan not in left


def test_storing_a_new_picture_cleans_up_old_unused_ones(db, monkeypatch):
    old = _kept(db, b"old and unused", 30)
    fetching(monkeypatch, FakeResponse())
    imagecache.localize(db, "https://example.com/new.png")
    db.commit()
    assert db.get(models.CachedImage, old) is None
    assert db.query(models.CachedImage).count() == 1
