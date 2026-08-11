from .base import ScrapedContent, ScraperStrategy
from .og_tags import fetch_og_tags


class GenericOgScraper(ScraperStrategy):
    """Fallback strategy for any site that isn't Instagram or Facebook.
    Most link-preview-friendly pages (hotels, restaurants, attractions,
    booking sites, ...) expose Open Graph tags the same way those two do,
    so this reuses the same fetch_og_tags helper. Registered last in the
    registry so a more specific strategy always wins if one exists.
    """

    name = "generic"

    def matches(self, url: str) -> bool:
        return True

    def scrape(self, url: str) -> ScrapedContent:
        return fetch_og_tags(url)
