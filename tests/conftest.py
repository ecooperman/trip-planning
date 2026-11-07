"""Tests run against a throwaway SQLite file built by the real migrations, so
they exercise the schema the app actually ships with. DATABASE_URL must be set
before anything imports app.database."""
import logging
import os
import smtplib
import tempfile
from pathlib import Path

import pytest
import requests

ROOT = Path(__file__).resolve().parent.parent
_db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_db_file.close()
os.environ["DATABASE_URL"] = f"sqlite:///{_db_file.name}"
os.environ.pop("APP_ENV", None)  # local mode: Cf-Access-Authenticated-User-Email picks the user

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import config, crud, models  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _migrate():
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    command.upgrade(cfg, "head")
    # migrations/env.py configures logging from alembic.ini, which switches off
    # every logger that already exists (the app's, here - it was imported
    # first). The running app never does that, so turn them back on or tests
    # of what gets logged would silently see nothing.
    for name in logging.root.manager.loggerDict:
        logging.getLogger(name).disabled = False
    yield
    os.unlink(_db_file.name)


@pytest.fixture(autouse=True)
def clean_db():
    """Empty every table before each test, leaving just the placeholder owner
    the migration creates (so legacy adoption can be tested)."""
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())
        conn.execute(models.User.__table__.insert().values(email=crud.LEGACY_OWNER_EMAIL))
    yield


@pytest.fixture(autouse=True)
def _nothing_leaves_the_machine(monkeypatch):
    """Whatever is set in the developer's shell (a real Cloudflare token, a
    real ntfy topic), a test must never reach out with it: the settings are
    blanked, and any HTTP or SMTP call a test didn't stub fails loudly."""
    for name in (
        "CF_API_TOKEN", "CF_ACCOUNT_ID", "CF_INVITEES_GROUP_ID", "NTFY_TOPIC", "NTFY_TOKEN",
        "PUSHOVER_APP_TOKEN", "PUSHOVER_USER_KEY", "SMTP_HOST", "SMTP_USERNAME", "SMTP_PASSWORD",
        "SMTP_FROM", "NOTIFY_EMAIL",
    ):
        monkeypatch.setattr(config, name, None)
    monkeypatch.setattr(config, "INVITES_PER_USER", 5)
    monkeypatch.setattr(config, "ACCESS_SEAT_CAP", 50)

    def refuse(*args, **kwargs):
        raise AssertionError(f"a test made a real network call: {args[:2]}")

    monkeypatch.setattr(requests, "request", refuse)
    monkeypatch.setattr(requests, "post", refuse)
    monkeypatch.setattr(smtplib, "SMTP", refuse)
    monkeypatch.setattr(smtplib, "SMTP_SSL", refuse)


class Person:
    """A client that makes every request as one email."""

    def __init__(self, client: TestClient, email: str):
        self.client, self.email = client, email
        self.headers = {"Cf-Access-Authenticated-User-Email": email}

    def _call(self, method, url, **kwargs):
        return getattr(self.client, method)(url, headers=self.headers, **kwargs)

    def get(self, url, **kw):
        return self._call("get", url, **kw)

    def post(self, url, json=None, **kw):
        return self._call("post", url, json=json, **kw)

    def patch(self, url, json=None, **kw):
        return self._call("patch", url, json=json, **kw)

    def put(self, url, json=None, **kw):
        return self._call("put", url, json=json, **kw)

    def delete(self, url, **kw):
        return self._call("delete", url, **kw)


@pytest.fixture()
def client():
    return TestClient(app)


@pytest.fixture()
def db():
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture()
def alice(client):
    return Person(client, "alice@example.com")


@pytest.fixture()
def bob(client):
    return Person(client, "bob@example.com")


@pytest.fixture()
def carol(client):
    return Person(client, "carol@example.com")


@pytest.fixture()
def admin(client):
    """The app's administrator (ADMIN_EMAILS includes the dev user locally)."""
    return Person(client, config.DEV_USER_EMAIL)


@pytest.fixture()
def sign_in(client):
    """Make a person from any email: sign_in("dana@example.com")."""
    return lambda email: Person(client, email)
