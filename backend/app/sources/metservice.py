"""MetService CAP feed — official severe weather warnings (RSS/XML).

Confirmed working endpoint (verified against live data): the same feed
Civil Defence and broadcasters use.

Confirmed empirically: no coordinates anywhere in this feed, and it's a
NATIONWIDE feed, not Wellington-specific — relevance filtering (Wellington
gazetteer keyword match) happens in the aggregator (context.py), not here.
This module only normalizes and derives hazard_type/severity_hint.
"""

import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import httpx

from app.schema import OfficialEvent

NAME = "metservice"

URL = "https://alerts.metservice.com/cap/rss"


def _hazard_type(title: str) -> str:
    """Deterministic keyword match — a warning title's own vocabulary already
    tells us the category, no inference needed."""
    lowered = title.lower()
    if "road" in lowered:
        return "road_hazard"
    if "rain" in lowered or "flood" in lowered:
        return "flooding"
    return "severe_weather"


def _severity_hint(title: str) -> str:
    lowered = title.lower()
    if "red" in lowered:
        return "high"
    if "orange" in lowered or "severe" in lowered:
        return "medium"
    return "low"


async def fetch() -> list[OfficialEvent]:
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(URL)
        resp.raise_for_status()
        xml_text = resp.text

    root = ET.fromstring(xml_text)
    events = []
    for item in root.iter("item"):
        guid = _text(item, "guid")
        title = _text(item, "title")
        description = _text(item, "description")
        pub_date = _text(item, "pubDate")
        if not guid:
            continue

        event_time = _now_iso()
        if pub_date:
            try:
                event_time = parsedate_to_datetime(pub_date).astimezone(timezone.utc).isoformat()
            except (ValueError, TypeError):
                pass

        summary = f"{title}: {description}" if description else title or "MetService alert"

        events.append(
            OfficialEvent(
                source=NAME,
                hazard_type=_hazard_type(title),
                severity_hint=_severity_hint(title),
                event_time=event_time,
                lat=None,  # confirmed: never present in this feed
                lon=None,
                summary=summary,
                raw_source_url="https://www.metservice.com/warnings",
            )
        )
    return events


def _text(item: ET.Element, tag: str) -> str:
    el = item.find(tag)
    return el.text.strip() if el is not None and el.text else ""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
