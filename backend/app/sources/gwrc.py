"""GWRC river levels + rainfall telemetry — the live version of the gauge
data this project investigated and deprioritised earlier ("site metadata
only, no live readings"). That finding was against the wrong endpoint — these
two ArcGIS-hosted services (found via the hackathon organisers' data
catalogue) return genuinely live point readings with real lat/lon.

Two sub-feeds, one source module (both GWRC, both flooding-relevant,
combined the way the team decided to treat this as one addition):
- River flows/levels: `Stage_pct` (current level as % of the site's own
  historical min-max range) is what drives severity_hint — a normalised,
  per-site-calibrated signal, more meaningful than an absolute stage value
  that means different things at different sites.
- Rainfall: `RainTot6Hrs` (mm in the past 6 hours) drives severity_hint —
  draft thresholds, not domain-validated (see _severity_hint_rainfall).

Confirmed empirically: some sensors in both feeds return years-stale
`LatestTime` values (one rainfall site's sample was from 2018) — presumably
decommissioned or offline hardware still listed in the service. Filtered out
client-side by recency, same principle as NZTA's `status == "active"` check
— a feed listing a site doesn't mean that site is actually still reporting.

Confirmed empirically, and easy to get wrong: `LatestTime` is **NZ local
time (Pacific/Auckland), not UTC**, and carries no timezone marker — checked
directly against the actual current NZ time when this was written, where the
freshest live readings matched local clock time, not UTC. Naively treating
it as UTC would silently mis-timestamp every event by 12-13 hours (NZST/NZDT)
— wrong `event_time` everywhere downstream, and a recency filter that passes
or rejects exactly the wrong readings.
"""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx

from app.schema import OfficialEvent

NAME = "gwrc"
NZ_TZ = ZoneInfo("Pacific/Auckland")

RIVER_URL = "https://mapping.gw.govt.nz/arcgis/rest/services/GW/River_flows_P_2023/MapServer/0/query"
RAINFALL_URL = "https://mapping.gw.govt.nz/arcgis/rest/services/Rainfall/MapServer/2/query"
PARAMS = {"where": "1=1", "outFields": "*", "outSR": "4326", "f": "json", "returnGeometry": "true"}

MAX_READING_AGE_HOURS = 6  # older than this -> treat the sensor as not currently reporting


def _severity_hint_river(stage_pct: float | None) -> str:
    """Draft thresholds against the site's own historical stage range —
    refine with Sara/GWRC input, same caveat as GeoNet's magnitude bands."""
    if stage_pct is None:
        return "medium"
    if stage_pct >= 100:
        return "high"
    if stage_pct >= 75:
        return "medium"
    return "low"


def _severity_hint_rainfall(rain_6hr_mm: float | None) -> str:
    """Draft thresholds (mm accumulated in 6 hours) — refine with Sara/GWRC
    input; not derived from an official warning-tier definition."""
    if rain_6hr_mm is None:
        return "medium"
    if rain_6hr_mm >= 50:
        return "high"
    if rain_6hr_mm >= 20:
        return "medium"
    return "low"


def _parse_nz_time(value) -> datetime | None:
    """`LatestTime` is NZ local time with no timezone marker — see module
    docstring. Localise to Pacific/Auckland (handles NZST/NZDT correctly via
    zoneinfo), then convert to UTC."""
    if not value:
        return None
    try:
        ts = datetime.fromisoformat(str(value))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=NZ_TZ)
        return ts.astimezone(timezone.utc)
    except ValueError:
        return None


def _is_recent(latest_time: str | None) -> bool:
    ts = _parse_nz_time(latest_time)
    if ts is None:
        return False
    delta = datetime.now(timezone.utc) - ts
    return timedelta(0) <= delta <= timedelta(hours=MAX_READING_AGE_HOURS)


async def _fetch_river(client: httpx.AsyncClient) -> list[OfficialEvent]:
    resp = await client.get(RIVER_URL, params=PARAMS)
    resp.raise_for_status()
    data = resp.json()

    events = []
    for feature in data.get("features", []):
        attrs = feature.get("attributes", {})
        name = attrs.get("Name")
        latest_time = attrs.get("LatestTime")
        if not name or not _is_recent(latest_time):
            continue

        geom = feature.get("geometry") or {}
        stage_pct = attrs.get("Stage_pct")
        flow = attrs.get("LatestFlow")
        change = attrs.get("Change", "")

        summary = f"{name}: flow {flow:.1f} m3/s, {change.lower() if change else 'steady'}"
        if stage_pct is not None:
            summary += f" ({stage_pct:.0f}% of historical range)"

        events.append(
            OfficialEvent(
                source=NAME,
                hazard_type="flooding",
                severity_hint=_severity_hint_river(stage_pct),
                event_time=_to_iso(latest_time),
                lat=geom.get("y"),
                lon=geom.get("x"),
                summary=summary,
                raw_source_url=attrs.get("Link") or "https://www.gw.govt.nz/",
            )
        )
    return events


async def _fetch_rainfall(client: httpx.AsyncClient) -> list[OfficialEvent]:
    resp = await client.get(RAINFALL_URL, params=PARAMS)
    resp.raise_for_status()
    data = resp.json()

    events = []
    for feature in data.get("features", []):
        attrs = feature.get("attributes", {})
        name = attrs.get("Name")
        latest_time = attrs.get("LatestTime")
        if not name or not _is_recent(latest_time):
            continue

        geom = feature.get("geometry") or {}
        rain_6hr = attrs.get("RainTot6Hrs")
        latest = attrs.get("LatestRainfall")

        summary = f"{name}: {rain_6hr:.1f}mm in the past 6h" if rain_6hr is not None else f"{name}: rainfall sensor"
        if latest is not None:
            summary += f" (latest reading {latest:.1f}mm)"

        events.append(
            OfficialEvent(
                source=NAME,
                hazard_type="flooding",
                severity_hint=_severity_hint_rainfall(rain_6hr),
                event_time=_to_iso(latest_time),
                lat=geom.get("y"),
                lon=geom.get("x"),
                summary=summary,
                raw_source_url=attrs.get("Link") or "https://www.gw.govt.nz/",
            )
        )
    return events


async def fetch() -> list[OfficialEvent]:
    async with httpx.AsyncClient(timeout=15) as client:
        river_events = await _fetch_river(client)
        rainfall_events = await _fetch_rainfall(client)
    return river_events + rainfall_events


def _to_iso(value) -> str:
    ts = _parse_nz_time(value)
    return ts.isoformat() if ts is not None else _now_iso()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
