from typing import List, Optional

from .airbnb import AirbnbScraper
from .base import ScraperStrategy
from .facebook import FacebookScraper
from .generic import GenericOgScraper
from .instagram import InstagramScraper
from .vrbo import VrboScraper

# Order matters: the first match wins. The site-specific strategies go
# first (Instagram/Facebook serve their real markup only to allowlisted
# crawler user-agents, which is what those strategies know to send); the
# generic Open-Graph fallback goes last and matches everything, so it only
# ever kicks in once nothing more specific has claimed the URL.
#
# All the site-specific strategies currently just call fetch_og_tags like
# the fallback does - they exist as separate classes so each can grow its
# own quirks later (a different User-Agent, JSON-LD instead of OG tags,
# etc.) without touching the others. Add more the same way as needed
# (hotels.com, Expedia, Kayak, ...).
STRATEGIES: List[ScraperStrategy] = [
    InstagramScraper(),
    FacebookScraper(),
    AirbnbScraper(),
    VrboScraper(),
    GenericOgScraper(),
]


def find_strategy(url: str) -> Optional[ScraperStrategy]:
    for strategy in STRATEGIES:
        if strategy.matches(url):
            return strategy
    return None
