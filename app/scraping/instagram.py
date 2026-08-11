from urllib.parse import urlparse

from .base import ScrapedContent, ScraperStrategy
from .og_tags import fetch_og_tags


class InstagramScraper(ScraperStrategy):
    name = "instagram"

    def matches(self, url: str) -> bool:
        host = urlparse(url).netloc.lower()
        return host == "instagram.com" or host.endswith(".instagram.com")

    def scrape(self, url: str) -> ScrapedContent:
        return fetch_og_tags(url)
