"""FastAPI entrypoint — backend, poller, and models all in one process
(see BUILD_PLAN.md "Deployment map" for why this is deliberately one service).

Phased rollout (agreed explicitly — see BUILD_PLAN.md "Public-submission-
triggered flow" and FINETUNE_PLAN.md "Model 1 — Clarifier" for the full
design):

- Phase 1 (submit_community_report, below): single-step public submission.
  No clarifier call at all — `clarified_text`/`clarification_question` stay
  null. Submit -> triage (poller fetch -> aggregation -> Triage Classifier ->
  deterministic hazard_type -> store) runs the same way either phase. This
  endpoint is untouched by the Phase 2 work below — it's the fallback when
  the frontend's clarifier flag is off, and stays exactly as tested.
- Phase 2 (submit_for_clarification + submit_clarification_answer, below):
  the frontend adds a feature-flagged (query-param controlled) two-step flow
  instead — submit gets back a clarifying question (Call 1), answering it
  gets back 1-2 suggested actions (Call 2) and *then* triggers triage. Two
  separate endpoints because there's a real interaction in between (the
  submitter answering) that has to complete before triage can meaningfully
  start — one endpoint can't do both.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app import classifier, clarifier, context, poller, store
from app.schema import Event, Location

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main")

app = FastAPI()

# No CORS middleware existed at all until this was checked directly — would
# have silently blocked the frontend (a different origin on Vercel) from
# calling this backend on Cloud Run, and blocks the "common operating
# picture" requirement (other teams' tools pointing at GET /events) the
# same way. No auth on this API regardless (see BUILD_PLAN.md "Hosting"), so
# open origins matches what's already true, not a new exposure.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok", "poll_health": poller.get_poll_health()}


@app.get("/events")
def get_events(
    suburb: Optional[str] = None,
    hazard_type: Optional[str] = None,
    source_type: Optional[str] = None,
):
    return store.get_events(suburb=suburb, hazard_type=hazard_type, source_type=source_type)


class CommunityReport(BaseModel):
    raw_text: str
    suburb: Optional[str] = None
    lat: Optional[float] = None  # from the browser's Geolocation API, if granted
    lon: Optional[float] = None


def _new_event_id() -> str:
    return f"community-{int(datetime.now(timezone.utc).timestamp() * 1000)}"


def _report_location(report: "CommunityReport") -> Location:
    """The submitted location with coordinates resolved once, at intake.

    `context.resolve_location()` already prefers real GPS coordinates over the
    suburb centroid, but it was only ever called *internally* by
    build_official_context() for distance matching — the resolved centroid was
    never written back onto the stored event. So any report from a submitter
    who declined the geolocation prompt was stored with lat/lon null, and the
    dashboard map (which skips events without coordinates) could never plot
    it. Resolving here means the stored event matches what BUILD_PLAN's event
    schema documents: coordinates from the Geolocation API if granted, else
    the gazetteer's suburb centroid.

    Both remain null when the suburb is unknown/unrecognised — an unplottable
    report still belongs in the feed, it just has no map position.
    """
    submitted = Location(suburb=report.suburb, lat=report.lat, lon=report.lon)
    lat, lon = context.resolve_location(submitted)
    return Location(suburb=report.suburb, lat=lat, lon=lon)


@app.post("/events/community-report")
async def submit_community_report(report: CommunityReport):
    """Phase 1: single-step submission, no clarifier call — see module
    docstring. clarified_text/clarification_question/actions stay null/empty."""
    now = datetime.now(timezone.utc).isoformat()
    event = Event(
        id=_new_event_id(),
        ingested_at=now,
        event_time=now,
        location=_report_location(report),
        raw_text=report.raw_text,
        status="new",
    )
    store.upsert_event(event)

    # Submitter is thanked now (this response returns immediately) — triage
    # runs in the background and does not block them.
    asyncio.create_task(_triage(event.id))

    return event


@app.post("/events/community-report/clarify")
def submit_for_clarification(report: CommunityReport):
    """Phase 2, step 1 (Clarifier Call 1 — "ask"). Returns the event with
    clarification_question set. Does NOT trigger triage yet — that only
    happens once the submitter's answer comes back via
    submit_clarification_answer(), since the two-call exchange is the
    "nothing downstream blocks them" phase now, not just this first step."""
    now = datetime.now(timezone.utc).isoformat()
    question = clarifier.ask(report.raw_text)

    event = Event(
        id=_new_event_id(),
        ingested_at=now,
        event_time=now,
        location=_report_location(report),
        raw_text=report.raw_text,
        clarification_question=question,
        status="awaiting_clarification",
    )
    store.upsert_event(event)
    return event


class ClarificationAnswer(BaseModel):
    answer: str
    contact: Optional[str] = None  # optional — asked here, not on the first form, to keep initial
    # friction low (see BUILD_PLAN.md). No validation on shape (email vs. phone) — free text,
    # staff read it directly, not parsed/used programmatically anywhere yet.


@app.post("/events/{event_id}/clarification-answer")
async def submit_clarification_answer(event_id: str, body: ClarificationAnswer):
    """Phase 2, step 2 (Clarifier Call 2 — "act"). Returns the event with
    actions set, and triggers async triage — this is the point that finally
    starts the background poller/aggregation/triage pipeline in Phase 2."""
    event = store.get_event(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="event not found")
    if event.status != "awaiting_clarification":
        raise HTTPException(status_code=400, detail=f"event is not awaiting clarification (status={event.status})")

    actions = clarifier.act(event.raw_text, event.clarification_question or "", body.answer)

    event.clarification_answer = body.answer
    event.clarified_text = clarifier.build_clarified_text(event.raw_text, body.answer)
    event.actions = actions
    event.contact = body.contact
    event.status = "new"
    store.upsert_event(event)

    asyncio.create_task(_triage(event.id))

    return event


async def _triage(event_id: str) -> None:
    event = store.get_event(event_id)
    if event is None:
        return

    official_events = await poller.get_official_events()
    official_context = context.build_official_context(event.location, official_events)

    existing_reports = store.get_events(source_type="community")
    related_report = context.find_related_report(event, existing_reports)

    context_text = context.render_context_text(official_context, related_report)
    severity, rationale = classifier.triage(event.clarified_text or event.raw_text, context_text)

    event.official_context = official_context
    event.related_report_id = related_report.id if related_report else None
    event.hazard_type = context.inherit_hazard_type(official_context)
    event.severity = severity
    event.rationale = rationale
    event.status = "triaged"

    store.upsert_event(event)
    logger.info(f"[{event_id}] triaged: severity={event.severity} hazard_type={event.hazard_type}")
