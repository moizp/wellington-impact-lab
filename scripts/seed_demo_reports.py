#!/usr/bin/env python3
"""Seed the staff dashboard with simulated public reports for the demo.

Why this exists
---------------
`docs/PITCH.md` declares public reports as the *simulated* half of this build
(no live public reporting channel exists yet) while the official sources stay
real and live. This script is that simulated half, made repeatable.

It sends **explicit lat/lon** on every report rather than relying on the
backend's suburb-centroid lookup. That matters right now: the centroid fix in
commit 9ded1a0 is committed but NOT deployed to Cloud Run, so the live backend
still stores `lat: null` for a suburb-only report — which means no map pin and
no distance-based official-source match. Sending coordinates sidesteps the
redeploy completely.

Coordinates are real, taken from the WREMO Community Emergency Hub register
(`community-emergency-hubs` in the WCC GIS catalogue), not hand-typed.

Nothing here fabricates official data. Each report goes through the ordinary
`POST /events/community-report` endpoint and is triaged against whatever the
five official sources genuinely return at that moment.

Usage
-----
    python3 scripts/seed_demo_reports.py                 # against deployed backend
    python3 scripts/seed_demo_reports.py --dry-run       # print, send nothing
    python3 scripts/seed_demo_reports.py --api http://localhost:8000
    python3 scripts/seed_demo_reports.py --delay 3       # seconds between reports

Python 3.9 compatible (stdlib only) — the backend itself needs 3.10+, but this
runs from any machine.
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from typing import Optional

DEFAULT_API = "https://wellington-poller-ii3mghfupa-ts.a.run.app"

# Real suburb coordinates — WREMO Community Emergency Hub register.
SUBURBS = {
    "Berhampore": (-41.3207, 174.7733),
    "Newtown": (-41.3109, 174.7797),
    "Island Bay": (-41.3355, 174.7754),
    "Brooklyn": (-41.3059, 174.7666),
    "Hataitai": (-41.3031, 174.7974),
    "Mount Cook": (-41.2977, 174.7787),
    "Karori": (-41.2852, 174.7383),
    "Kilbirnie": (-41.3206, 174.7939),
    "Thorndon": (-41.2747, 174.7821),
    "Miramar": (-41.3179, 174.8172),
    "Houghton Bay": (-41.3339, 174.7870),
    "Aro Valley": (-41.2955, 174.7685),
}

# Simulated public reports, written to span the full range a triage desk sees:
# concrete impact, ambiguous, trivial, and a near-duplicate pair so the
# related-report logic has something to find.
#
# Deliberately invented but plausible. No real street addresses, no real
# people, no reconstruction of anything an actual person said during a real
# event — this repo is public and the 20 April 2026 flood affected real
# residents.
REPORTS = [
    # --- concrete impact, should read as serious ---
    ("Berhampore", "The retaining wall at the back of our section has given way and "
                   "there's mud and water across the driveway. We can't get the car out."),
    ("Newtown", "Water is coming through the ground floor of our building. It's about "
                "ankle deep inside and still rising. Two flats affected."),

    # --- moderate, real but contained ---
    ("Island Bay", "Surface flooding across the road near the shops, about half the "
                   "width. Cars are going through slowly but a couple have turned back."),
    ("Brooklyn", "There's a slip come down across the walking track above us. No "
                 "houses affected that I can see, but the track is completely blocked."),
    ("Hataitai", "Stormwater drain outside is overflowing and the water is starting to "
                 "pool up against the front of the property."),

    # --- near-duplicate pair (same location, same incident, different reporter) ---
    ("Mount Cook", "Big pool of water forming at the bottom of the street, it's up over "
                   "the kerb and onto the footpath now."),
    ("Mount Cook", "Same street as I think someone else has probably reported — the "
                   "water at the bottom is getting deeper, maybe knee deep at the worst bit."),

    # --- ambiguous / needs clarification ---
    ("Karori", "Something's not right with the stream at the end of our road, it looks "
               "much higher than normal but I'm not sure if that's just the rain."),
    ("Thorndon", "Heard a loud bang and there's water running down the hill but I can't "
                 "see where it's coming from."),

    # --- low / trivial, should NOT be escalated ---
    ("Kilbirnie", "Bit of surface water on the corner, nothing you couldn't drive "
                  "through. Just flagging it."),
    ("Miramar", "Gutter's overflowing outside our place. Not causing any problems, "
                "just probably needs clearing at some point."),

    # --- no concrete impact but near a monitored catchment ---
    ("Houghton Bay", "Rain's very heavy here at the moment. Nothing wrong yet but "
                     "thought you'd want to know."),
]


def post_report(api: str, text: str, suburb: str, lat: float, lon: float,
                timeout: int = 60) -> Optional[dict]:
    body = json.dumps({
        "raw_text": text,
        "suburb": suburb,
        "lat": lat,
        "lon": lon,
    }).encode("utf-8")
    req = urllib.request.Request(
        api.rstrip("/") + "/events/community-report",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        print("    HTTP %s: %s" % (exc.code, exc.read().decode("utf-8", "replace")[:200]))
    except Exception as exc:  # noqa: BLE001 — one bad report shouldn't stop the seed
        print("    failed: %s" % exc)
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", default=DEFAULT_API, help="backend base URL")
    parser.add_argument("--delay", type=float, default=4.0,
                        help="seconds between reports (triage runs async on CPU)")
    parser.add_argument("--dry-run", action="store_true", help="print only, send nothing")
    args = parser.parse_args()

    print("Seeding %d simulated public reports -> %s" % (len(REPORTS), args.api))
    if args.dry_run:
        print("(dry run — nothing will be sent)\n")

    sent = 0
    for i, (suburb, text) in enumerate(REPORTS, 1):
        lat, lon = SUBURBS[suburb]
        print("[%2d/%d] %-13s (%.4f, %.4f)  %s" % (
            i, len(REPORTS), suburb, lat, lon, text[:58] + ("..." if len(text) > 58 else "")))
        if args.dry_run:
            continue
        result = post_report(args.api, text, suburb, lat, lon)
        if result:
            sent += 1
            loc = result.get("location") or {}
            print("    -> %s  stored lat=%s lon=%s" % (
                result.get("id"), loc.get("lat"), loc.get("lon")))
        if i < len(REPORTS):
            time.sleep(args.delay)

    if not args.dry_run:
        print("\nSent %d/%d. Triage runs asynchronously — allow ~%ds, then check:"
              % (sent, len(REPORTS), max(15, int(args.delay * 3))))
        print("  curl -s %s/events | python3 -m json.tool | head -40" % args.api.rstrip("/"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
