"""The aggregator — builds the two deterministic context blocks the Triage
Classifier reads (see FINETUNE_PLAN.md "Official context format"), and
inherits `hazard_type` deterministically. No LLM calls anywhere in this file.
"""

from datetime import datetime, timezone
from typing import Optional

from app.gazetteer import WELLINGTON_SUBURB_COORDS, mentions_wellington_region
from app.geo import haversine_km
from app.schema import Event, Location, OfficialContextItem, OfficialEvent

RADIUS_KM = 20.0  # GeoNet/NZTA relevance radius
GEONET_RECENCY_MINUTES = 1440  # 24h — an emergency situation can persist well past the initial
# shake itself (aftershocks, delayed damage reports, ongoing structural assessment), so a quake
# from earlier the same day is still relevant context, not stale. Tune here if a different window
# is wanted — this is the one place that decision lives.
MAX_CONTEXT_ITEMS = 3

RELATED_REPORT_RADIUS_KM = 2.0  # tighter — same specific incident, not a general area
RELATED_REPORT_WINDOW_MINUTES = 60


def resolve_location(location: Location) -> tuple[Optional[float], Optional[float]]:
    """Real coordinates if given, else an approximate suburb centroid, else unknown."""
    if location.lat is not None and location.lon is not None:
        return location.lat, location.lon
    if location.suburb:
        coords = WELLINGTON_SUBURB_COORDS.get(location.suburb.strip().lower())
        if coords:
            return coords
    return None, None


def _minutes_ago(event_time: str) -> float:
    then = datetime.fromisoformat(event_time)
    now = datetime.now(timezone.utc)
    return (now - then).total_seconds() / 60


def build_official_context(
    report_location: Location, official_events: list[OfficialEvent]
) -> list[OfficialContextItem]:
    lat, lon = resolve_location(report_location)

    candidates: list[tuple[Optional[float], float, OfficialEvent]] = []
    for oe in official_events:
        minutes_ago = _minutes_ago(oe.event_time)
        # Recency cutoff only applies to GeoNet — quake relevance fades fast.
        # NZTA/MetService have no equivalent cutoff here: their own source
        # module already filters to what that feed still lists as active
        # (NZTA's status=="active" check, MetService's feed only ever listing
        # current warnings), so a road closure or weather watch that's been
        # active for several days is still correctly relevant, not stale.
        if oe.source == "geonet" and minutes_ago > GEONET_RECENCY_MINUTES:
            continue

        if oe.source == "metservice":
            # No coordinates exist for this source (confirmed) — relevance is
            # gazetteer keyword match only, never distance.
            if not mentions_wellington_region(oe.summary):
                continue
            distance_km: Optional[float] = None
        else:
            if oe.lat is None or oe.lon is None:
                continue
            if lat is None or lon is None:
                # No report location at all, and GeoNet/NZTA have no
                # region-independent relevance signal the way MetService's
                # gazetteer match does (confirmed empirically — with no
                # location, distance-blind fallback surfaced quakes 150km+
                # from Wellington, e.g. Kaikoura). Can't judge relevance
                # without a location, so don't guess — exclude, matching the
                # same principle already used in find_related_report().
                continue
            distance_km = haversine_km(lat, lon, oe.lat, oe.lon)
            if distance_km > RADIUS_KM:
                continue

        candidates.append((distance_km, minutes_ago, oe))

    # Known distance ranks first (closest first); unknown-distance items sort
    # after, by recency only.
    candidates.sort(key=lambda c: (c[0] if c[0] is not None else float("inf"), c[1]))
    top = candidates[:MAX_CONTEXT_ITEMS]

    return [
        OfficialContextItem(
            source=oe.source,
            hazard_type=oe.hazard_type,
            severity_hint=oe.severity_hint,
            distance_km=round(distance_km, 1) if distance_km is not None else None,
            minutes_ago=int(minutes_ago),
            summary=oe.summary,
        )
        for distance_km, minutes_ago, oe in top
    ]


def find_related_report(new_report: Event, existing_reports: list[Event]) -> Optional[Event]:
    """At most one related pre-existing public report — capped deliberately
    at one so the Triage Classifier reads it as qualitative corroborating
    evidence, not something to count (see FINETUNE_PLAN.md)."""
    lat, lon = resolve_location(new_report.location)

    candidates: list[tuple[float, Event]] = []
    for r in existing_reports:
        if r.id == new_report.id:
            continue
        minutes_ago = _minutes_ago(r.event_time)
        if minutes_ago > RELATED_REPORT_WINDOW_MINUTES:
            continue

        r_lat, r_lon = resolve_location(r.location)
        if lat is not None and lon is not None and r_lat is not None and r_lon is not None:
            if haversine_km(lat, lon, r_lat, r_lon) > RELATED_REPORT_RADIUS_KM:
                continue
        elif new_report.location.suburb and r.location.suburb:
            if new_report.location.suburb.strip().lower() != r.location.suburb.strip().lower():
                continue
        else:
            # No usable location signal on one or both sides — can't judge
            # proximity, so don't guess.
            continue

        candidates.append((minutes_ago, r))

    if not candidates:
        return None
    candidates.sort(key=lambda c: c[0])  # most recent first
    return candidates[0][1]


def inherit_hazard_type(official_context: list[OfficialContextItem]) -> str:
    """Deterministic — never the LLM's job. official_context is already
    ranked closest/most-recent first, so the top item is what's inherited."""
    if not official_context:
        return "other"
    return official_context[0].hazard_type


def _format_minutes_ago(minutes: int) -> str:
    """Human-readable elapsed time. NZTA/MetService have no recency cutoff
    (see build_official_context) — a road work active for months would
    otherwise render as something unreadable like "435154 min ago"."""
    if minutes < 60:
        return f"{minutes} min ago"
    hours = minutes / 60
    if hours < 24:
        return f"{hours:.0f}h ago"
    days = hours / 24
    return f"{days:.0f} days ago"


def render_context_text(
    official_context: list[OfficialContextItem], related_report: Optional[Event]
) -> str:
    """Canonical render — the exact text handed to the Triage Classifier.
    Must be used identically for training data generation and live serving
    (see FINETUNE_PLAN.md)."""
    lines: list[str] = []

    if official_context:
        count = len(official_context)
        lines.append(f"Official context ({count} item{'s' if count != 1 else ''} found near this location):")
        for item in official_context:
            distance_part = f"{item.distance_km:.1f}km away, " if item.distance_km is not None else ""
            lines.append(
                f"- {item.source.capitalize()}: {item.summary} "
                f"({distance_part}{_format_minutes_ago(item.minutes_ago)}) [severity: {item.severity_hint}]"
            )
    else:
        lines.append("Official context: No relevant official data found for this location/time.")

    if related_report:
        lines.append("")
        lines.append("Related public report:")
        text = related_report.clarified_text or related_report.raw_text
        lines.append(f'- "{text}"')

    return "\n".join(lines)
