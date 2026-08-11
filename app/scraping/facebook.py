from urllib.parse import urlparse

from .base import ScrapedContent, ScraperStrategy
from .og_tags import fetch_og_tags

FACEBOOK_HOSTS = {"facebook.com", "m.facebook.com", "fb.watch"}


class FacebookScraper(ScraperStrategy):
    name = "facebook"

    def matches(self, url: str) -> bool:
        host = urlparse(url).netloc.lower()
        return any(host == h or host.endswith(f".{h}") for h in FACEBOOK_HOSTS)

    def scrape(self, url: str) -> ScrapedContent:
        return fetch_og_tags(url)
