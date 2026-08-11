from urllib.parse import urlparse

from .base import ScrapedContent, ScraperStrategy
from .og_tags import fetch_og_tags


class VrboScraper(ScraperStrategy):
    name = "vrbo"

    def matches(self, url: str) -> bool:
        host = urlparse(url).netloc.lower()
        return host == "vrbo.com" or host.endswith(".vrbo.com")

    def scrape(self, url: str) -> ScrapedContent:
        return fetch_og_tags(url)
