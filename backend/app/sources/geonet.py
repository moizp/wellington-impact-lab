"""GeoNet quake feed — earthquake data for the Wellington region.

Confirmed working endpoint (verified against live data): GET /quake with an
MMI (shaking intensity) filter. See https://api.geonet.org.nz/ for the full spec.

Always carries real point coordinates (confirmed empirically — every quake
feature has lat/lon, zero exceptions observed).
"""

from datetime import datetime, timezone

import httpx

from app.schema import OfficialEvent

NAME = "geonet"

URL = "https://api.geonet.org.nz/quake?MMI=3"
HEADERS = {"Accept": "application/vnd.geo+json;version=2"}


def _severity_hint(magnitude: float | None) -> str:
    """Deterministic magnitude thresholds — draft, refine with Sara/WCC input."""
    if magnitude is None:
        return "low"
    if magnitude > 5:
        return "high"
    if magnitude >= 3.5:
        return "medium"
    return "low"


async def fetch() -> list[OfficialEvent]:
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(URL, headers=HEADERS)
        resp.raise_for_status()
        data = resp.json()

    events = []
    for feature in data.get("features", []):
        props = feature.get("properties", {})
        geom = feature.get("geometry", {})
        coords = geom.get("coordinates", [None, None])
        public_id = props.get("publicID")
        if not public_id:
            continue

        magnitude = props.get("magnitude")
        depth = props.get("depth")
        locality = props.get("locality", "unknown location")

        summary = (
            f"M{magnitude:.1f} earthquake, {depth:.0f}km deep, {locality}"
            if magnitude is not None and depth is not None
            else locality
        )

        events.append(
            OfficialEvent(
                source=NAME,
                hazard_type="earthquake",
                severity_hint=_severity_hint(magnitude),
                event_time=props.get("time", _now_iso()),
                lat=coords[1],
                lon=coords[0],
                summary=summary,
                raw_source_url=f"https://www.geonet.org.nz/earthquake/{public_id}",
            )
        )
    return events


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
