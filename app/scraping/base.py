from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class ScrapedContent:
    title: Optional[str] = None
    description: Optional[str] = None
    image_url: Optional[str] = None


class ScraperError(Exception):
    """Raised when a strategy matches a URL but fails to extract content."""


class ScraperStrategy(ABC):
    """One implementation per source site (Instagram, Facebook, ...).

    Each strategy owns both the decision of whether it applies to a given
    URL (`matches`) and the extraction logic for that site (`scrape`), so
    adding support for a new site is just adding a new strategy and
    registering it - nothing else in the app needs to change.
    """

    name: str

    @abstractmethod
    def matches(self, url: str) -> bool:
        ...

    @abstractmethod
    def scrape(self, url: str) -> ScrapedContent:
        ...
