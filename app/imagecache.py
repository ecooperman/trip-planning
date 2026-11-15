"""Keeping a scraped page's picture. A page's og:image is often a signed address
that stops working after a few weeks (Instagram's does), so when a scrape
saves one we download it here and store the bytes; the activity, place or stay
then points at our own copy (/api/cached-images/<id>) instead."""
import hashlib
from datetime import datetime, timedelta

import requests
from sqlalchemy.orm import Session

from . import models
from .netguard import UnsafeURL, safe_get

LOCAL_PREFIX = "/api/cached-images/"

# A picture nothing points at is only removed once it is this old, so one that was saved a moment ago
# (and is still being attached to its activity, place or stay) is never swept away.
UNUSED_GRACE = timedelta(days=1)

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
    digest = hashlib.sha256(data).hexdigest()
    # The same picture again (a re-scrape of the same page): point at the copy already stored.
    image = db.query(models.CachedImage).filter(models.CachedImage.content_hash == digest).first()
    if image is None:
        image = models.CachedImage(content_type=content_type, data=data, content_hash=digest)
        db.add(image)
        db.flush()
    purge_unused(db)
    return f"{LOCAL_PREFIX}{image.id}"


def _referenced_ids(db: Session):
    """The ids of every kept picture an activity, place or stay still points at."""
    ids = set()
    for model in (models.Activity, models.Place, models.Stay):
        for (url,) in db.query(model.scraped_image_url).filter(model.scraped_image_url.like(f"{LOCAL_PREFIX}%")):
            tail = url[len(LOCAL_PREFIX):]
            if tail.isdigit():
                ids.add(int(tail))
    return ids


def purge_unused(db: Session) -> int:
    """Delete kept pictures nothing points at any more (a re-scrape replaced the address, or the
    activity, place or stay was deleted) and that are older than UNUSED_GRACE. Returns how many went.
    Runs whenever a new picture is stored; the caller commits."""
    cutoff = datetime.utcnow() - UNUSED_GRACE
    candidates = [i for (i,) in db.query(models.CachedImage.id).filter(models.CachedImage.created_at < cutoff)]
    if not candidates:
        return 0
    referenced = _referenced_ids(db)
    stale = [i for i in candidates if i not in referenced]
    if stale:
        db.query(models.CachedImage).filter(models.CachedImage.id.in_(stale)).delete(synchronize_session=False)
    return len(stale)
