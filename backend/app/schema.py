"""Shared data shapes — see docs/BUILD_PLAN.md "Proposed event schema" and
docs/FINETUNE_PLAN.md "Official context format" for the full rationale.

Three distinct shapes, not one generic "event" anymore (this changed from the
original design — see BUILD_PLAN.md's architecture update):

- `Event` — a triaged PUBLIC report. The only thing ever stored/displayed.
- `OfficialEvent` — a normalized item from an official source (GeoNet/
  MetService/NZTA), used only transiently to build context. Never stored,
  never displayed standalone.
- `OfficialContextItem` — the small, deterministic summary of a relevant
  OfficialEvent that actually gets shown to staff and handed to the Triage
  Classifier as input.
"""

from typing import Literal, Optional

from pydantic import BaseModel


class Location(BaseModel):
    suburb: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None


class OfficialEvent(BaseModel):
    """Output of a source module's fetch(). hazard_type and severity_hint are
    deterministic, rule-derived per source — never an LLM call (see
    FINETUNE_PLAN.md's "Official context format")."""

    source: Literal["geonet", "metservice", "nzta", "nema", "gwrc"]
    hazard_type: str
    severity_hint: Literal["low", "medium", "high"]
    event_time: str  # ISO 8601, UTC
    lat: Optional[float] = None  # None for MetService — no coordinates exist (confirmed)
    lon: Optional[float] = None
    summary: str
    raw_source_url: Optional[str] = None


class OfficialContextItem(BaseModel):
    """The deterministic, aggregator-built summary of one relevant
    OfficialEvent — this is what the Triage Classifier actually sees, and
    what's shown to staff so the "why" is inspectable."""

    source: str
    hazard_type: str
    severity_hint: Literal["low", "medium", "high"]
    distance_km: Optional[float] = None  # None when unknown (no report location, or MetService)
    minutes_ago: int
    summary: str


class Event(BaseModel):
    """A triaged public report. The only thing ever stored or displayed —
    official-source events never exist as standalone items (see BUILD_PLAN.md
    "System summary")."""

    id: str
    source: str = "community"
    source_type: str = "community"
    ingested_at: str  # ISO 8601, UTC
    event_time: str  # ISO 8601, UTC
    location: Location

    raw_text: str
    clarified_text: Optional[str] = None
    clarification_question: Optional[str] = None  # Clarifier Call 1 output
    clarification_answer: Optional[str] = None  # submitter's answer to Call 1's question
    actions: list[str] = []  # Clarifier Call 2 output (1-2 items) — see FINETUNE_PLAN.md "Model 1"
    contact: Optional[str] = None  # optional, collected at the final step (Call 2) — see BUILD_PLAN.md

    official_context: list[OfficialContextItem] = []
    related_report_id: Optional[str] = None

    hazard_type: Optional[str] = None  # deterministic, set by the aggregator — never the LLM
    severity: Optional[str] = None  # Triage Classifier output
    rationale: Optional[str] = None  # Triage Classifier output

    # "awaiting_clarification": Phase 2 only, Call 1 done, waiting on the submitter's answer.
    # "new": Phase 1's whole lifetime before triage, or Phase 2's state right after Call 2
    # finishes and triage is about to run. "triaged": final, both phases.
    status: Literal["awaiting_clarification", "new", "triaged"] = "new"
