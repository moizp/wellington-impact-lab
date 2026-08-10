"""NEMA Emergency Mobile Alert CAP polygons — the actual broadcast areas of
declared emergency alerts (tsunami/civil defence-grade), not forecasts.

Confirmed working endpoint (verified against live data), found via the
hackathon organisers' data catalogue (claudecommunity-nz/wcc-emergency-gis-data),
not our own earlier source list. Real polygon geometry (confirmed — every
feature carries `esriGeometryPolygon`, requested as lat/lon via `outSR=4326`
rather than the service's native Web Mercator projection).

Nationwide feed, same as MetService/NZTA — Wellington-region relevance is
handled by context.py's existing Haversine distance filter, same as
GeoNet/NZTA (this source has real coordinates, unlike MetService).

`historic=0` (server-side query filter) is what actually confirms an alert is
still current — verified empirically: 3 sample historic=1 records included a
years-old Northland civil defence alert AND a literal "TEST MESSAGE -
Emergency Mobile Alert" test record with severity="Severe", which would have
been dangerously misleading if surfaced as real. Kept `status == "Actual"`
and excluding `event == "Test Message"` as client-side safety nets on top of
the server-side filter, not instead of it.
"""

from datetime import datetime, timezone

import httpx

from app.schema import OfficialEvent

NAME = "nema"

URL = (
    "https://services5.arcgis.com/cJn6oR1QqErYBL5d/arcgis/rest/services/"
    "NZ_CAP_Alerts_(Read_only)/FeatureServer/0/query"
)
PARAMS = {
    "where": "historic=0",
    "outFields": "identifier,status,msg_type,category,event,urgency,severity,certainty,headline,description,sent,expires",
    "outSR": "4326",
    "f": "json",
    "returnGeometry": "true",
}

# CAP's standard category vocabulary, mapped onto our existing hazard_type
# taxonomy (see FINETUNE_PLAN.md) — no new hazard_type value needed, every
# CAP category observed maps onto one already in use.
_CATEGORY_HAZARD = {
    "fire": "fire",
    "met": "severe_weather",
    "geo": "earthquake",  # closest existing bucket for geological events
    "transport": "road_hazard",
}

# CAP's standard severity vocabulary (Extreme/Severe/Moderate/Minor/Unknown).
_SEVERITY_HINT = {
    "extreme": "high",
    "severe": "high",
    "moderate": "medium",
    "minor": "low",
}


def _hazard_type(category: str | None) -> str:
    if not category:
        return "other"
    return _CATEGORY_HAZARD.get(category.strip().lower(), "other")


def _severity_hint(severity: str | None) -> str:
    if not severity:
        return "medium"
    return _SEVERITY_HINT.get(severity.strip().lower(), "medium")


def _centroid(geometry: dict | None) -> tuple[float | None, float | None]:
    """Simple vertex-average centroid of the alert polygon's outer ring —
    an approximation, not area-weighted, but adequate for a ~20km relevance
    radius check, matching this project's other MVP-scale geo approximations
    (see gazetteer.py's suburb centroids)."""
    if not geometry:
        return None, None
    rings = geometry.get("rings")
    if not rings:
        return None, None
    ring = rings[0]
    if not ring:
        return None, None
    lon = sum(p[0] for p in ring) / len(ring)
    lat = sum(p[1] for p in ring) / len(ring)
    return lat, lon


async def fetch() -> list[OfficialEvent]:
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(URL, params=PARAMS)
        resp.raise_for_status()
        data = resp.json()

    events = []
    for feature in data.get("features", []):
        attrs = feature.get("attributes", {})
        identifier = attrs.get("identifier")
        if not identifier:
            continue

        # Safety nets on top of the server-side historic=0 filter.
        if (attrs.get("status") or "").strip().lower() != "actual":
            continue
        if (attrs.get("event") or "").strip().lower() == "test message":
            continue

        lat, lon = _centroid(feature.get("geometry"))
        headline = attrs.get("headline") or attrs.get("event") or "NEMA emergency alert"

        events.append(
            OfficialEvent(
                source=NAME,
                hazard_type=_hazard_type(attrs.get("category")),
                severity_hint=_severity_hint(attrs.get("severity")),
                event_time=_to_iso(attrs.get("sent")),
                lat=lat,
                lon=lon,
                summary=headline,
                raw_source_url="https://www.civildefence.govt.nz/",
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
