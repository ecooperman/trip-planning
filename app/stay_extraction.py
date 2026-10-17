"""Turns a lodging listing (its page text, or a screenshot of it) into
structured fields for a candidate Stay, via the Claude API. Used by the
"add stays from URLs" bulk importer and the per-stay "re-read from
screenshot" action (see routers/stay_compare.py and static/trip.js).

Like ai_extraction.py's Instagram seeds, this is a first pass meant to be
eyeballed and corrected on the trip page - a stay it imports is flagged
needs_review until saved. A missing or approximate number here is an
expected outcome to fix by hand, not a bug to chase out.
"""

import base64
from typing import Optional

import anthropic
from pydantic import BaseModel

from .config import ANTHROPIC_API_KEY

# Not claude-opus-5 (what ai_extraction.py uses): listing pages are long
# and imported a dozen at a time, and pulling labelled facts out of
# provided text is well within Sonnet's range at several times the speed
# and a fraction of the cost per URL.
MODEL = "claude-sonnet-5"

SYSTEM_PROMPT = """You extract facts about a single lodging listing (a \
hotel room, apartment, vacation rental, B&B) from the content you're \
given, for a traveler comparing options. The content may start with a \
"STRUCTURED DATA:" block of key: value lines pulled from the page's \
metadata - trust those over prose when they conflict.

Rules:
- Only report what the source actually states. Use null for anything not \
present - never guess a bedroom count or an address. Do not invent a \
price.
- Prices: amount as a plain number (no symbol, no commas); ISO 4217 code \
in listing_currency (EUR, GBP, MXN, USD...). A clearly per-night rate -> \
nightly_price, even if it's phrased "from 180" or "180 avg/night" \
(note the approximation in summary). An all-in total shown for specific \
dates -> total_price. Having one and not the other is normal. Cleaning + \
service + tax, summed, -> extra_fees only if listed separately from the \
rate. If the page clearly requires picking dates before any price shows, \
leave both null and say so in summary.
- summary: 2-4 plain-prose sentences (no markdown) of what matters for \
choosing - key amenities (kitchen, washer, AC, parking, pool, elevator), \
cancellation policy, star / review rating and review count, how central \
or walkable it is, standout pros or cons.
- confidence: "low" if the content looks like a bot wall, a login or \
cookie prompt, or is nearly empty, OR if you found essentially nothing \
beyond a name. Otherwise "high"."""


class ExtractedStay(BaseModel):
    name: Optional[str] = None
    listing_currency: Optional[str] = None
    nightly_price: Optional[float] = None
    total_price: Optional[float] = None
    extra_fees: Optional[float] = None
    bedrooms: Optional[int] = None
    bathrooms: Optional[float] = None
    sleeps: Optional[int] = None
    neighborhood: Optional[str] = None
    address: Optional[str] = None
    summary: Optional[str] = None
    confidence: Optional[str] = None

    def worksheet_fields(self) -> dict:
        """The subset that maps onto Stay columns (crud._STAY_EXTRACT_FIELDS)
        - neighborhood is folded into address, summary into description."""
        address = self.address or self.neighborhood
        return {
            "description": self.summary,
            "address": address,
            "listing_currency": self.listing_currency,
            "nightly_price": self.nightly_price,
            "total_price": self.total_price,
            "extra_fees": self.extra_fees,
            "bedrooms": self.bedrooms,
            "bathrooms": self.bathrooms,
            "sleeps": self.sleeps,
        }


def _client() -> anthropic.Anthropic:
    if not ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY is not configured")
    return anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


def extract_from_text(
    url: str,
    og_title: Optional[str],
    og_description: Optional[str],
    page_text: str,
) -> ExtractedStay:
    parts = [f"Listing URL: {url}"]
    if og_title:
        parts.append(f"Link-preview title: {og_title}")
    if og_description:
        parts.append(f"Link-preview description: {og_description}")
    parts.append("\nPage text:\n" + (page_text or "(the page could not be read)"))
    response = _client().messages.parse(
        model=MODEL,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": "\n".join(parts)}],
        output_format=ExtractedStay,
    )
    return response.parsed_output


def extract_from_image(image_bytes: bytes, media_type: str) -> ExtractedStay:
    b64 = base64.standard_b64encode(image_bytes).decode("ascii")
    response = _client().messages.parse(
        model=MODEL,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": media_type, "data": b64},
                    },
                    {
                        "type": "text",
                        "text": "This is a screenshot of a lodging listing. Extract what you can.",
                    },
                ],
            }
        ],
        output_format=ExtractedStay,
    )
    return response.parsed_output
