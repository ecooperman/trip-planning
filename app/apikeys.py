"""People's own API keys for the paid services the app can call.

Anthropic (reading stay listings and screenshots), Google Maps (distances) and
Jina (an optional fallback for pages that come back thin) cost money per use.
Instead of metering strangers on the owner's bill, each person brings their own
key. Which key a call uses:

1. the signed-in person's own saved key, if they have one;
2. otherwise the server's own ("house") key from the environment - but ONLY for
   an administrator. Anyone else without a key of their own just doesn't have
   that feature, and is told how to turn it on (see require()).

Saved keys are encrypted (Fernet) with KEY_ENCRYPTION_SECRET, never sent back to
the browser (only the last four characters are kept in the clear), and never
logged. Honest limits: this protects a copy of the database file (a backup, a
download for inspection); it can't protect against someone who has taken over
the running server, which holds the secret too.
"""
import base64
import hashlib
import logging
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

import requests
from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException
from sqlalchemy.orm import Session

from . import config, models

log = logging.getLogger(__name__)

TIMEOUT = 10
MIN_LENGTH = 16
MAX_LENGTH = 400

# Used only when no secret is set and we're not in production.
_DEV_SECRET = "local-development-only-not-a-secret"


@dataclass(frozen=True)
class Provider:
    id: str
    label: str
    feature: str  # shown to the person: "<feature> needs your own <label> key"
    description: str
    optional: bool  # the feature works without it, just less well
    get_url: str  # where to create a key
    house: Callable[[], Optional[str]]


def _house_anthropic():
    return config.ANTHROPIC_API_KEY


def _house_google():
    return config.GOOGLE_MAPS_API_KEY


def _house_jina():
    return config.JINA_API_KEY


PROVIDERS: Dict[str, Provider] = {
    "anthropic": Provider(
        id="anthropic",
        label="Anthropic",
        feature="Reading stay listings",
        description="Reads a lodging listing (or a screenshot of one) and fills in the price, rooms and amenities when you import stays.",
        optional=False,
        get_url="https://console.anthropic.com/settings/keys",
        house=_house_anthropic,
    ),
    "google_maps": Provider(
        id="google_maps",
        label="Google Maps",
        feature="Distances and travel times",
        description="Looks up real walking and driving distances between your activities and stays. The key needs the Distance Matrix API turned on.",
        optional=False,
        get_url="https://console.cloud.google.com/apis/credentials",
        house=_house_google,
    ),
    "jina": Provider(
        id="jina",
        label="Jina Reader",
        feature="Reading hard-to-fetch pages",
        description="Optional. Helps the stay importer read listing pages that block normal fetching, so more of them import cleanly.",
        optional=True,
        get_url="https://jina.ai/reader/",
        house=_house_jina,
    ),
}


class KeyStorageNotConfigured(Exception):
    pass


# --- encryption --------------------------------------------------------------


def storage_available() -> bool:
    return bool(config.KEY_ENCRYPTION_SECRET) or config.ENV != "production"


def _fernet() -> Fernet:
    secret = config.KEY_ENCRYPTION_SECRET
    if not secret:
        if config.ENV == "production":
            raise KeyStorageNotConfigured()
        secret = _DEV_SECRET
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest()))


def clean(raw: str) -> str:
    key = (raw or "").strip()
    if not (MIN_LENGTH <= len(key) <= MAX_LENGTH) or any(c.isspace() or ord(c) < 33 for c in key):
        raise ValueError("That doesn't look like an API key - paste the whole key, with no spaces")
    return key


# --- saving, reading, removing -----------------------------------------------


def save(db: Session, user: models.User, provider: str, raw_key: str) -> models.UserApiKey:
    key = clean(raw_key)
    token = _fernet().encrypt(key.encode()).decode()
    row = db.query(models.UserApiKey).filter_by(user_id=user.id, provider=provider).first()
    if row is None:
        row = models.UserApiKey(user_id=user.id, provider=provider, encrypted_key=token, last4=key[-4:])
        db.add(row)
    else:
        row.encrypted_key, row.last4 = token, key[-4:]
    db.commit()
    db.refresh(row)
    return row


def remove(db: Session, user: models.User, provider: str) -> bool:
    row = db.query(models.UserApiKey).filter_by(user_id=user.id, provider=provider).first()
    if row is None:
        return False
    db.delete(row)
    db.commit()
    return True


def _row(db: Session, user: models.User, provider: str) -> Optional[models.UserApiKey]:
    return db.query(models.UserApiKey).filter_by(user_id=user.id, provider=provider).first()


def _decrypt(row: models.UserApiKey) -> Optional[str]:
    """The saved key, or None if it can't be read (the secret changed, or the
    server has none). Logged without anything from the key."""
    try:
        return _fernet().decrypt(row.encrypted_key.encode()).decode()
    except (InvalidToken, KeyStorageNotConfigured):
        log.warning("A saved %s key could not be decrypted (was KEY_ENCRYPTION_SECRET changed?)", row.provider)
        return None


def can_use_house_key(user: models.User) -> bool:
    """Only administrators spend the server's own keys."""
    return user.email in config.ADMIN_EMAILS


def resolve(db: Session, user: models.User, provider: str) -> Optional[str]:
    """The key to use for this person, or None (see the module docstring)."""
    row = _row(db, user, provider)
    if row is not None:
        own = _decrypt(row)
        if own:
            return own
    if can_use_house_key(user):
        return PROVIDERS[provider].house() or None
    return None


def require(db: Session, user: models.User, provider: str) -> str:
    """resolve(), or a plain explanation of how to turn the feature on."""
    key = resolve(db, user, provider)
    if key:
        return key
    p = PROVIDERS[provider]
    raise HTTPException(
        status_code=400,
        detail=f"{p.feature} needs your own {p.label} key - add it on your Profile page.",
    )


def available(db: Session, user: models.User) -> Dict[str, bool]:
    """Which services this person can use right now (own key, or the house key
    if they're an administrator) - for the pages to show or hide features."""
    return {pid: resolve(db, user, pid) is not None for pid in PROVIDERS}


def status(db: Session, user: models.User) -> List[dict]:
    out = []
    house_ok = can_use_house_key(user)
    for p in PROVIDERS.values():
        row = _row(db, user, p.id)
        readable = row is not None and _decrypt(row) is not None
        house_key = bool(house_ok and p.house())
        out.append(
            {
                "provider": p.id,
                "label": p.label,
                "feature": p.feature,
                "description": p.description,
                "optional": p.optional,
                "get_url": p.get_url,
                "has_own_key": row is not None,
                "own_key_readable": readable if row is not None else True,
                "last4": row.last4 if row is not None else None,
                "added_at": row.updated_at if row is not None else None,
                "using_house_key": house_key and not readable,
                "usable": readable or house_key,
            }
        )
    return out


# --- checking a key before it's saved ---------------------------------------
#
# One tiny real call per provider, so a typo (or a Google key without the
# Distance Matrix API enabled) is caught while the person is still on the page.
# Returns (True, "") if the provider accepted it, (False, why) if it refused it,
# or (None, why) if we couldn't tell (the service was unreachable) - in which
# case the key is saved anyway and the person is told it wasn't verified.


def _scrub(text: str, key: str) -> str:
    return " ".join((text or "").replace(key, "...").split())[:200]


def _verify_anthropic(key: str) -> Tuple[Optional[bool], str]:
    r = requests.get(
        "https://api.anthropic.com/v1/models",
        params={"limit": 1},
        headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
        timeout=TIMEOUT,
    )
    if r.status_code in (401, 403):
        return False, "Anthropic didn't accept that key"
    if r.ok:
        return True, ""
    return None, f"Anthropic answered with an error ({r.status_code})"


def _verify_google(key: str) -> Tuple[Optional[bool], str]:
    r = requests.get(
        "https://maps.googleapis.com/maps/api/distancematrix/json",
        params={"origins": "Boston, MA", "destinations": "Cambridge, MA", "mode": "walking", "key": key},
        timeout=TIMEOUT,
    )
    data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    result = data.get("status")
    if result == "OK":
        return True, ""
    if result in ("REQUEST_DENIED", "INVALID_REQUEST"):
        return False, "Google refused that key: " + _scrub(data.get("error_message") or result, key)
    if result == "OVER_QUERY_LIMIT":
        return True, ""  # a real key that is simply out of quota right now
    return None, f"Google answered with an unexpected status ({result or r.status_code})"


def _verify_jina(key: str) -> Tuple[Optional[bool], str]:
    r = requests.get("https://r.jina.ai/https://example.com", headers={"Authorization": f"Bearer {key}"}, timeout=TIMEOUT)
    if r.status_code in (401, 403):
        return False, "Jina didn't accept that key"
    if r.ok:
        return True, ""
    return None, f"Jina answered with an error ({r.status_code})"


_VERIFIERS = {"anthropic": _verify_anthropic, "google_maps": _verify_google, "jina": _verify_jina}


def verify(provider: str, key: str) -> Tuple[Optional[bool], str]:
    try:
        return _VERIFIERS[provider](key)
    except (requests.RequestException, ValueError) as exc:
        # The type only: a library's message can echo the URL, and a URL can carry the key.
        log.warning("Checking a %s key failed: %s", provider, type(exc).__name__)
        return None, f"Couldn't reach {PROVIDERS[provider].label} to check the key"
