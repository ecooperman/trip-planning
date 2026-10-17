"""Best-effort fetch of a lodging listing's content - for feeding the AI
stay extractor (app/stay_extraction.py). Pulls three things and stitches
them into one text blob:

  1. structured data (JSON-LD `Hotel`/`LodgingBusiness`/`Product`/`Offer`
     blocks, and `<meta>` tags) - where a machine-readable name, address,
     rating, and *sometimes* a price actually live;
  2. the page's visible body text - amenities, house rules, descriptions;
  3. optionally, a JS-rendered version via a reader proxy (Jina) when
     `JINA_API_KEY` is set and the direct fetch came back thin.

Reality check: the big booking sites (Booking.com, Airbnb, hotel-brand
sites, TripAdvisor) render the nightly price with JavaScript after a date
search, and/or block server-side fetches outright. So a direct fetch
reliably gets the name/location/description but usually NOT the price.
Callers must treat a thin result as "couldn't read it" and fall back to a
stub stay or the screenshot path, not an error.
"""

import json
import os
import re

import requests
from bs4 import BeautifulSoup

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

MAX_CHARS = 18000
# Below this many chars of usable text, the direct fetch is considered a
# bot wall / JS shell and the reader-proxy fallback (if configured) kicks in.
THIN_TEXT_THRESHOLD = 600

# Optional - a Jina Reader (r.jina.ai) key. When set, listings that come
# back thin from a direct fetch are retried through the proxy, which runs
# the page's JavaScript first. Same never-committed, shell-set-locally /
# shared-secrets-file-on-the-droplet pattern as ANTHROPIC_API_KEY /
# GOOGLE_MAPS_API_KEY (see app/config.py).
JINA_API_KEY = os.environ.get("JINA_API_KEY")

# JSON-LD keys worth surfacing to the model, flattened to "key: value"
# lines. Nested price/rating objects are unwrapped by _flatten_ld.
_LD_INTERESTING = {
    "name", "description", "priceRange", "price", "priceCurrency",
    "checkinTime", "checkoutTime", "numberOfRooms", "petsAllowed",
    "ratingValue", "reviewCount", "bestRating",
    "streetAddress", "addressLocality", "addressRegion", "postalCode", "addressCountry",
    "latitude", "longitude",
}


def _flatten_ld(obj, out, depth=0):
    if depth > 6 or not isinstance(obj, (dict, list)):
        return
    if isinstance(obj, list):
        for item in obj:
            _flatten_ld(item, out, depth + 1)
        return
    for key, value in obj.items():
        if key in _LD_INTERESTING and isinstance(value, (str, int, float)):
            out.setdefault(key, str(value))
        elif isinstance(value, (dict, list)):
            _flatten_ld(value, out, depth + 1)


def _structured_summary(soup: BeautifulSoup) -> str:
    """Labeled lines from JSON-LD + key <meta> tags - the reliably
    machine-readable bits, put first so the model doesn't have to dig them
    out of prose."""
    lines = []

    for tag in soup.find_all("script", type="application/ld+json"):
        raw = tag.string or tag.get_text() or ""
        try:
            data = json.loads(raw)
        except (ValueError, TypeError):
            continue
        flat = {}
        _flatten_ld(data, flat)
        for key, value in flat.items():
            lines.append(f"{key}: {value}")

    for prop in ("og:title", "og:description", "og:price:amount", "og:price:currency",
                 "product:price:amount", "product:price:currency", "twitter:description"):
        tag = soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop})
        if tag and tag.get("content"):
            lines.append(f"{prop}: {tag['content'].strip()}")

    desc = soup.find("meta", attrs={"name": "description"})
    if desc and desc.get("content"):
        lines.append(f"meta description: {desc['content'].strip()}")

    # De-dupe, keep order.
    seen = set()
    unique = [ln for ln in lines if not (ln in seen or seen.add(ln))]
    return "STRUCTURED DATA:\n" + "\n".join(unique) if unique else ""


def _visible_text(soup: BeautifulSoup) -> str:
    body = BeautifulSoup(str(soup), "html.parser")
    for tag in body(["script", "style", "noscript", "svg", "head", "template"]):
        tag.decompose()
    return " ".join(body.get_text(" ", strip=True).split())


def _via_jina(url: str, timeout: int) -> str:
    if not JINA_API_KEY:
        return ""
    try:
        response = requests.get(
            f"https://r.jina.ai/{url}",
            headers={"Authorization": f"Bearer {JINA_API_KEY}", "X-Return-Format": "markdown"},
            timeout=timeout,
        )
        response.raise_for_status()
    except requests.RequestException:
        return ""
    return " ".join(response.text.split())


def fetch_page_text(url: str, timeout: int = 12, max_chars: int = MAX_CHARS) -> str:
    """One text blob (structured summary + visible text) for the extractor,
    or "" if nothing usable came back. Never raises."""
    html = ""
    try:
        response = requests.get(url, headers=BROWSER_HEADERS, timeout=timeout)
        response.raise_for_status()
        html = response.text
    except requests.RequestException:
        html = ""

    structured = ""
    visible = ""
    if html:
        soup = BeautifulSoup(html, "html.parser")
        structured = _structured_summary(soup)
        visible = _visible_text(soup)

    # Thin direct fetch (bot wall / JS shell) - try the rendering proxy.
    if len(visible) < THIN_TEXT_THRESHOLD:
        rendered = _via_jina(url, timeout=max(timeout, 30))
        if len(rendered) > len(visible):
            visible = rendered

    parts = [p for p in (structured, visible) if p]
    if not parts:
        return ""
    return "\n\n".join(parts)[:max_chars]
