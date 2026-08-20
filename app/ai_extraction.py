"""Turns a saved Instagram post's caption into zero or more candidate
Activities, via the Claude API. Used by the "import a saved collection"
flow (see routers/instagram_import.py and the trip-clipper extension's
collection-grid extractor).

One caption can describe several distinct real places (a numbered
neighborhood guide, a "top 5 spots" post, ...) - see extract_activities'
docstring for how that's handled. This is deliberately a seed generator,
not a finisher: results are meant to be reviewed/edited on trip.html
after import, the same way tap-to-create and the single-post clipper
already work - so a wrong or approximate name is an acceptable, expected
outcome, not a bug to chase out here.
"""

from typing import List, Optional

import anthropic
from pydantic import BaseModel

from .config import ANTHROPIC_API_KEY

MODEL = "claude-opus-5"

SYSTEM_PROMPT = """You read Instagram captions and decide whether they \
describe real-world places or activities a traveler could actually visit \
(a restaurant, cafe, shop, museum, hike, neighborhood, landmark, etc.).

Many captions are NOT about a visitable place at all - a meme, a personal \
photo, a product ad, a life update, a repost with no location. For those, \
return an empty list.

Some captions describe exactly one place. Others are a guide or roundup \
that names several distinct places - a numbered list, a "top N spots" \
post, or a neighborhood guide. In that case, extract EACH distinct place \
as its own entry, not one combined entry.

Places are sometimes named in plain prose ("Le Comptoir on Rue X"), and \
sometimes only via an Instagram @handle for that business's own account \
(e.g. "@wonderpens"). For an @handle, turn it into a plausible readable \
business name (e.g. "@wonderpens" -> "Wonder Pens") using whatever you \
know of the real place if you recognize it, or a reasonable cleaned-up \
guess otherwise - note in that entry's notes that the name is inferred \
from the handle, not stated outright, so it's easy to spot and fix.

For each place, write 1-3 sentences of notes capturing whatever the \
caption actually says about it (why it's recommended, what to get/do \
there, hours or tips mentioned) - don't invent details the caption \
doesn't contain."""


class ExtractedActivity(BaseModel):
    name: str
    notes: str


class CaptionExtraction(BaseModel):
    activities: List[ExtractedActivity]


def _client() -> anthropic.Anthropic:
    if not ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY is not configured")
    return anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


def extract_activities(caption: str) -> List[ExtractedActivity]:
    """Returns the candidate activities found in one caption - an empty
    list if the caption doesn't describe a visitable place at all."""
    if not caption or not caption.strip():
        return []

    client = _client()
    response = client.messages.parse(
        model=MODEL,
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": caption}],
        output_format=CaptionExtraction,
    )
    return response.parsed_output.activities
