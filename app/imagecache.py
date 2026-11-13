"""Keeping a scraped page's picture. A page's og:image is often a signed address
that stops working after a few weeks (Instagram's does), so when a scrape
saves one we download it here and store the bytes; the activity, place or stay
then points at our own copy (/api/cached-images/<id>) instead."""
import requests
from sqlalchemy.orm import Session

from . import models
from .netguard import UnsafeURL, safe_get

LOCAL_PREFIX = "/api/cached-images/"

# A browser-like agent: some image hosts refuse anything that looks like a script.
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "image/avif,image/webp,image/png,image/jpeg,*/*;q=0.8",
}


def localize(db: Session, url):
    """Return the address to store for a scraped image: our own copy when the
    download works, otherwise the original address (so nothing is lost if the
    download fails - it may still show for a while). Empty stays empty, and an
    address that is already one of ours is left alone. Adds the copy to the
    session; the caller commits."""
    if not url or url.startswith(LOCAL_PREFIX):
        return url
    try:
        response = safe_get(url, headers=_HEADERS, timeout=10)
    except (UnsafeURL, requests.RequestException):
        return url
    content_type = response.headers.get("Content-Type", "").split(";")[0].strip().lower()
    # Never svg: it can carry script, and this is served from the app's own address.
    if response.status_code != 200 or not content_type.startswith("image/") or content_type == "image/svg+xml":
        return url
    data = response.content
    if not data:
        return url
    image = models.CachedImage(content_type=content_type, data=data)
    db.add(image)
    db.flush()
    return f"{LOCAL_PREFIX}{image.id}"
