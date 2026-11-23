"""The paid services the app can call, and whose key a call uses.

Anthropic (reading stay listings and screenshots), Google Maps (distances) and Jina (an optional fallback for pages that come back thin) cost
money per use. Instead of metering strangers on the owner's bill, each person brings their own key, which they save ONCE on their Profile page on
the dashboard (dashboard/app/keys.py) and which every app then uses (shared_python.user_keys). This app keeps no keys of its own. Which key a
call uses:

1. the signed-in person's own saved key, if they have one (fetched from the dashboard for this request, held in memory only);
2. otherwise the server's own ("house") key from the environment - but ONLY for an administrator. Anyone else without a key of their own just
   doesn't have that feature, and is told how to turn it on (see require()).
"""
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from fastapi import HTTPException
from shared_python import user_keys
from sqlalchemy.orm import Session

from . import config, models


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


# --- whose key a call uses ----------------------------------------------------


def _own_key(user: models.User, provider: str) -> Optional[str]:
    """The key this person saved on the dashboard, or None. `user` is the signed-in caller: the key is fetched with THEIR sign-in cookie for
    this request, so it can only ever be theirs (tests replace this function to give each test person a key)."""
    return user_keys.fetch(provider)


def _saved(user: models.User) -> dict:
    """{provider: {"last4", "added_at"}} for what the caller saved (never a key). Only for showing what is set (the pages hide or explain a
    feature): if the dashboard cannot be reached this says nothing is saved, rather than failing the page, which does not need a key.
    (Actually using a key, below, does fail with a sentence when the dashboard is down: that is a real problem for the call.)"""
    try:
        return user_keys.status()
    except HTTPException:
        return {}


def can_use_house_key(user: models.User) -> bool:
    """Only administrators spend the server's own keys."""
    return user.email in config.ADMIN_EMAILS


def resolve(db: Session, user: models.User, provider: str) -> Optional[str]:
    """The key to use for this person, or None (see the module docstring)."""
    own = _own_key(user, provider)
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
        detail=f"{p.feature} needs your own {p.label} key - add it on your Brassworks profile (the dashboard's Your profile page).",
    )


def available(db: Session, user: models.User) -> Dict[str, bool]:
    """Which services this person can use right now (own key, or the house key
    if they're an administrator) - for the pages to show or hide features."""
    saved = _saved(user)
    house_ok = can_use_house_key(user)
    return {pid: pid in saved or bool(house_ok and p.house()) for pid, p in PROVIDERS.items()}


def status(db: Session, user: models.User) -> List[dict]:
    saved = _saved(user)
    house_ok = can_use_house_key(user)
    out = []
    for p in PROVIDERS.values():
        mine = saved.get(p.id)
        house_key = bool(house_ok and p.house())
        out.append(
            {
                "provider": p.id,
                "label": p.label,
                "feature": p.feature,
                "description": p.description,
                "optional": p.optional,
                "get_url": p.get_url,
                "has_own_key": mine is not None,
                "last4": mine["last4"] if mine else None,
                "added_at": mine["added_at"] if mine else None,
                "using_house_key": house_key and mine is None,
                "usable": mine is not None or house_key,
            }
        )
    return out
