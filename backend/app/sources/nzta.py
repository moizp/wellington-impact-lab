"""NZTA road events — real-time road incidents/closures.

Confirmed working endpoint (verified against live data). Note: the old TREIS
REST endpoint (trafficnz.info/service/traffic/rest/4) is fully retired as of
this build — it now redirects to a consumer journey-planner page, not an API.
Use the current ArcGIS Hub dataset instead.

Always carries real point coordinates (confirmed empirically — all 104 live
features checked had Point geometry, zero nulls).
"""

from datetime import datetime, timezone

import httpx

from app.schema import OfficialEvent

NAME = "nzta"

URL = "https://opendata-nzta.opendata.arcgis.com/datasets/NZTA::road-events.geojson"

# Draft lookup — "Caution" is the only value confirmed from live data so far;
# other impact values still need enumerating from more samples (see
# FINETUNE_PLAN.md). Unknown values default to "medium" as a safe middle
# ground rather than silently under- or over-stating severity.
_IMPACT_SEVERITY = {
    "caution": "low",
    "closed": "high",
    "delays": "medium",
}


def _severity_hint(impact: str | None) -> str:
    if not impact:
        return "medium"
    return _IMPACT_SEVERITY.get(impact.strip().lower(), "medium")


async def fetch() -> list[OfficialEvent]:
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        resp = await client.get(URL)
        resp.raise_for_status()
        data = resp.json()

    events = []
    for feature in data.get("features", []):
        props = feature.get("properties", {})
        geom = feature.get("geometry", {}) or {}
        coords = geom.get("coordinates", [None, None])
        event_id = props.get("eventId") or props.get("GlobalID")
        if not event_id:
            continue

        # Only surface events the source itself still considers active — a
        # closed/resolved event is no longer road-hazard context.
        status = (props.get("status") or "").strip().lower()
        if status and status != "active":
            continue

        event_type = props.get("eventType", "Road event")
        description = props.get("eventDescription", "")
        location_area = props.get("locationArea", "")
        comments = props.get("eventComments", "")
        impact = props.get("impact")
        created = props.get("eventCreated")

        summary = f"{event_type} ({description}): {location_area}"
        if comments:
            summary += f". {comments}"

        events.append(
            OfficialEvent(
                source=NAME,
                hazard_type="road_hazard",
                severity_hint=_severity_hint(impact),
                event_time=_to_iso(created),
                lat=coords[1] if coords else None,
                lon=coords[0] if coords else None,
                summary=summary,
                raw_source_url="https://www.journeys.nzta.govt.nz/traffic/",
            )
        )
    return events


def _to_iso(value) -> str:
    if not value:
        return _now_iso()
    try:
        if isinstance(value, (int, float)):  # ArcGIS epoch millis
            return datetime.fromtimestamp(value / 1000, tz=timezone.utc).isoformat()
        return str(value)
    except (ValueError, OSError):
        return _now_iso()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
