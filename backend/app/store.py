"""In-memory store for triaged public reports.

Ephemeral by design for this prototype (see BUILD_PLAN.md) — resets on
restart/scale-to-zero. Only ever holds `Event` (triaged public reports) —
official-source data is never stored here, only fetched transiently via
poller.get_official_events() to build context (see context.py).
"""

from typing import Optional

from app.schema import Event

_events: dict[str, Event] = {}


def upsert_event(event: Event) -> bool:
    """Add or update an event. Returns True if this was a new event (not seen before)."""
    is_new = event.id not in _events
    _events[event.id] = event
    return is_new


def get_events(
    suburb: Optional[str] = None,
    hazard_type: Optional[str] = None,
    source_type: Optional[str] = None,
) -> list[Event]:
    items = list(_events.values())
    if suburb:
        items = [e for e in items if e.location.suburb == suburb]
    if hazard_type:
        items = [e for e in items if e.hazard_type == hazard_type]
    if source_type:
        items = [e for e in items if e.source_type == source_type]
    items.sort(key=lambda e: e.event_time, reverse=True)
    return items


def get_event(event_id: str) -> Optional[Event]:
    return _events.get(event_id)
