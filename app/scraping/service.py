from typing import Optional, Tuple

from sqlalchemy.orm import Session

from .. import crud, models
from .base import ScrapedContent, ScraperError
from .registry import find_strategy


def _resolve(url: str) -> Tuple[models.ScrapeStatus, Optional[ScrapedContent], Optional[str]]:
    """Run the matching strategy for `url`, without touching the DB - shared
    by scrape_activity/scrape_stay so both persist through their own crud
    function (they're different tables) while sharing this lookup/error
    handling.
    """
    strategy = find_strategy(url)
    if strategy is None:
        return models.ScrapeStatus.unsupported, None, "No scraping strategy is available for this URL yet"

    try:
        content = strategy.scrape(url)
    except ScraperError as exc:
        return models.ScrapeStatus.failed, None, str(exc)

    return models.ScrapeStatus.success, content, None


def scrape_activity(db: Session, activity_id: int, url: str) -> models.Activity:
    """Persist the scrape outcome onto the activity, whatever it is
    (success, failed, or unsupported) - so the UI always has something to
    show rather than silently doing nothing.
    """
    status, content, error = _resolve(url)
    if content is not None:
        return crud.save_activity_scrape_result(
            db, activity_id, status,
            title=content.title, description=content.description, image_url=content.image_url,
        )
    return crud.save_activity_scrape_result(db, activity_id, status, error=error)


def scrape_stay(db: Session, stay_id: int, url: str) -> models.Stay:
    status, content, error = _resolve(url)
    if content is not None:
        return crud.save_stay_scrape_result(
            db, stay_id, status,
            title=content.title, description=content.description, image_url=content.image_url,
        )
    return crud.save_stay_scrape_result(db, stay_id, status, error=error)
