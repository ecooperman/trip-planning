from urllib.parse import urlparse

from .base import ScrapedContent, ScraperStrategy
from .og_tags import fetch_og_tags


class AirbnbScraper(ScraperStrategy):
    name = "airbnb"

    def matches(self, url: str) -> bool:
        host = urlparse(url).netloc.lower()
        return host == "airbnb.com" or host.endswith(".airbnb.com")

    def scrape(self, url: str) -> ScrapedContent:
        return fetch_og_tags(url)
