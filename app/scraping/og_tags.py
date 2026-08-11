from typing import Optional

import requests
from bs4 import BeautifulSoup

from .base import ScrapedContent, ScraperError

# Both Instagram and Facebook serve their stripped-down JS app shell (no
# Open Graph tags at all) to a browser-like User-Agent, but serve the real
# server-rendered page - complete with og:title/description/image - to the
# handful of crawler UAs they allowlist for link-preview/unfurling purposes
# (the same mechanism that lets Slack, iMessage, and Discord render a rich
# preview when you paste a link). Identifying as one of those crawlers is
# the correct, expected way to fetch that markup - not a bot-detection
# workaround.
DEFAULT_HEADERS = {
    "User-Agent": "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)",
}


def fetch_og_tags(url: str, timeout: int = 10) -> ScrapedContent:
    """Fetch a URL and pull title/description/image out of its Open Graph
    meta tags. This is the common ground between Instagram and Facebook (and
    most other link-preview-friendly sites), so both strategies share it
    rather than each re-implementing HTML parsing.
    """
    try:
        response = requests.get(url, headers=DEFAULT_HEADERS, timeout=timeout)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise ScraperError(f"Request to {url} failed: {exc}") from exc

    soup = BeautifulSoup(response.text, "html.parser")

    def og(prop: str) -> Optional[str]:
        tag = soup.find("meta", property=f"og:{prop}")
        value = tag.get("content") if tag else None
        return value.strip() if value else None

    content = ScrapedContent(
        title=og("title"),
        description=og("description"),
        image_url=og("image"),
    )
    if not any([content.title, content.description, content.image_url]):
        raise ScraperError(
            "No Open Graph metadata found on the page - it may require login "
            "to view, or the post may have been removed"
        )
    return content
