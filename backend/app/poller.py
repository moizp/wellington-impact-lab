"""On-demand, cached official-source fetcher.

Replaces the original always-on background-loop design (see BUILD_PLAN.md's
architecture update) — continuous background polling doesn't reliably
survive Cloud Run's scale-to-zero behaviour. Instead: a public submission
triggers this, which checks a single shared 5-minute in-memory cache before
re-fetching from any source. Wrapped in try/except-and-skip per source — one
bad response should never crash the whole fetch or affect other sources.
"""

import logging
import time
from datetime import datetime, timezone
from typing import Optional

from app.schema import OfficialEvent
from app.sources import geonet, gwrc, metservice, nema, nzta

logger = logging.getLogger("poller")

SOURCES = [geonet, metservice, nzta, nema, gwrc]
CACHE_TTL_SECONDS = 300  # 5-min throttle, per BUILD_PLAN.md — shared across sources

_cache: dict[str, list[OfficialEvent]] = {}
_cache_fetched_at: dict[str, float] = {}
_poll_health: dict[str, dict] = {}


async def get_official_events(force_refresh: bool = False) -> list[OfficialEvent]:
    """Return normalized events from all official sources, using the cache
    where still fresh. A source failure falls back to its last-cached data
    (even if stale) rather than dropping it from the result entirely."""
    all_events: list[OfficialEvent] = []
    now = time.monotonic()

    for source_module in SOURCES:
        name = source_module.NAME
        last_fetched = _cache_fetched_at.get(name)
        is_stale = force_refresh or last_fetched is None or (now - last_fetched) > CACHE_TTL_SECONDS

        if is_stale:
            try:
                events = await source_module.fetch()
                _cache[name] = events
                _cache_fetched_at[name] = now
                _record_poll(name, success=True, count=len(events))
                logger.info(f"[{name}] fetched OK — {len(events)} events")
            except Exception as exc:  # noqa: BLE001 — deliberate catch-all per source
                _record_poll(name, success=False, error=str(exc))
                logger.warning(f"[{name}] fetch failed, using cached data if any: {exc}")

        all_events.extend(_cache.get(name, []))

    return all_events


def _record_poll(name: str, success: bool, count: int = 0, error: Optional[str] = None) -> None:
    _poll_health[name] = {
        "last_fetch_at": datetime.now(timezone.utc).isoformat(),
        "success": success,
        "event_count": count,
        "error": error,
    }


def get_poll_health() -> dict:
    return _poll_health
