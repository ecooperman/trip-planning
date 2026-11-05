"""Tests run against a throwaway SQLite file built by the real migrations, so
they exercise the schema the app actually ships with. DATABASE_URL must be set
before anything imports app.database."""
import os
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_db_file.close()
os.environ["DATABASE_URL"] = f"sqlite:///{_db_file.name}"
os.environ.pop("APP_ENV", None)  # local mode: Cf-Access-Authenticated-User-Email picks the user

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import crud, models  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _migrate():
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    command.upgrade(cfg, "head")
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
