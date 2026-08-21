"""Generates a brightAuthor:connected schedule (.bpsx) file from scratch.

.bpsx is bAc's native schedule file — confirmed via BrightSign's own
support forum to be plain JSON, opened via File > Open with the file-type
filter switched to Schedule. The internal structure isn't publicly
documented, so it was reverse-engineered from a real exported schedule
file (the user's own autoschedule.bpsx, covering weeks from 2026-07-17
through 2026-08-21):

{
  "schedulePresentations": {
    "schedulePresentationsById": {
      "<uuid>": {
        "id": "<uuid>",
        "presentationLocator": {
          "name": "Cafe Menu Monday.bpfx",
          "path": "/Users/.../Brightsign/",
          "networkId": 0, "location": "Local",
          "assetType": "Project", "scope": "<opaque per-installation id>"
        },
        "dateTime": "2026-07-20T06:00:00.000Z",
        "duration": 600,                    # minutes; end = start + duration
        "allDayEveryDay": false,
        "recurrence": false,                # see note below
        "recurrencePattern": "Custom",
        "recurrencePatternDaysOfWeek": 2,   # bitmask, Sun=1, Mon=2, ... Sat=64
        "recurrenceStartDate": "...",
        "recurrenceGoesForever": false,
        "recurrenceEndDate": "...",
        "interruption": false
      },
      ...
    },
    # List of the same keys as schedulePresentationsById, in insertion
    # order. NOT optional — bAc's own importer iterates this with
    # .forEach and crashes on open ("Cannot read properties of undefined
    # (reading 'forEach')") if it's missing, rather than failing
    # gracefully. Found by shipping a file without it and watching bAc's
    # own eventLog.txt.
    "allSchedulePresentations": ["<uuid>", "..."]
  },
  "modifiedTime": {"lastModifiedTime": "<iso timestamp>"}
}

An earlier version of this generator matched the user's original real file,
which showed every week added as its own one-off dated entry
(recurrence: false) — explaining a real scheduling mistake visible in that
file (a Wednesday entry from the week of 2026-08-10 tagged with Tuesday's
day-of-week bitmask), exactly the kind of manual slip this generator exists
to eliminate.

That's since been superseded: once the "just edit the .bpfx image each
week" pivot (see bpfx_update.py) meant the schedule itself never needs to
change, one-off dated entries became a liability — they'd silently stop
firing once their date range ran out. build_schedule() now generates true
forever-recurring entries instead, matching a real manually-configured
example the user exported (autoscheduleforever.bpsx, 2026-08-21):

  "dateTime": "2026-08-17T06:00:00.000Z",       # == recurrenceStartDate
  "recurrence": true,
  "recurrencePattern": "Custom",
  "recurrencePatternDaysOfWeek": 2,             # bitmask for this day
  "recurrenceStartDate": "2026-08-17T06:00:00.000Z",
  "recurrenceGoesForever": true,
  "recurrenceEndDate": "2026-08-18T06:59:59.999Z",

recurrenceEndDate is one day after recurrenceStartDate, with the same hour
as the start time and minute/second forced to 59:59.999 — this held across
all 5 real entries and appears to be a required-but-otherwise-unused
placeholder once recurrenceGoesForever is true (bAc's UI still needs some
end-date value even for a schedule that never actually ends).

PRESENTATION_PATH and SCOPE below are specific to this cafe's one bAc
installation/project (confirmed identical across all entries in the real
exported file) — they're not something a fresh install could safely guess,
so they're hardcoded constants rather than parameters. If the user ever
recreates their bAc project setup, re-export a schedule from bAc and check
its presentationLocator.path/scope match these before trusting this again.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
import json

DAY_BITMASK = {
    "Monday": 2,
    "Tuesday": 4,
    "Wednesday": 8,
    "Thursday": 16,
    "Friday": 32,
}

PRESENTATION_PATH = "/Users/stbpa/Documents/Brightsign/"
SCOPE = "755c3be30c4ebb4f"


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def _new_entry(day_name: str, day_date: date, duration_minutes: int, start: time) -> dict:
    start_dt = datetime(day_date.year, day_date.month, day_date.day, start.hour, start.minute, tzinfo=timezone.utc)
    end_date = day_date + timedelta(days=1)
    recurrence_end = datetime(end_date.year, end_date.month, end_date.day, start.hour, 59, 59, 999000, tzinfo=timezone.utc)
    return {
        "id": str(uuid.uuid4()),
        "presentationLocator": {
            "name": f"Cafe Menu {day_name}.bpfx",
            "path": PRESENTATION_PATH,
            "networkId": 0,
            "location": "Local",
            "assetType": "Project",
            "scope": SCOPE,
        },
        "dateTime": _iso(start_dt),
        "duration": duration_minutes,
        "allDayEveryDay": False,
        "recurrence": True,
        "recurrencePattern": "Custom",
        "recurrencePatternDaysOfWeek": DAY_BITMASK[day_name],
        "recurrenceStartDate": _iso(start_dt),
        "recurrenceGoesForever": True,
        "recurrenceEndDate": _iso(recurrence_end),
        "interruption": False,
    }


def build_schedule(day_entries: list[tuple[str, date]], start: time, end: time) -> dict:
    """Builds a fresh .bpsx schedule (as a dict, ready for write_schedule)
    containing one forever-recurring entry per (day_name, date) in
    day_entries, all running from `start` to `end` every week (same time
    every day). day_entries is expected to be a subset of Monday..Friday,
    in any order. Since each entry recurs forever, this only needs to be
    generated once — week-to-week menu changes are handled by
    bpfx_update.py rewriting each day's presentation image instead."""
    if not day_entries:
        raise ValueError("No days selected — pick at least one day to schedule.")

    start_minutes = start.hour * 60 + start.minute
    end_minutes = end.hour * 60 + end.minute
    duration_minutes = end_minutes - start_minutes
    if duration_minutes <= 0:
        raise ValueError("End time must be later than start time.")

    by_id = {}
    for day_name, day_date in day_entries:
        entry = _new_entry(day_name, day_date, duration_minutes, start)
        by_id[entry["id"]] = entry

    return {
        "schedulePresentations": {
            "schedulePresentationsById": by_id,
            # bAc's own importer (openScheduleFromAsset) calls .forEach on
            # this — a file missing it crashes on open with "Cannot read
            # properties of undefined (reading 'forEach')" rather than
            # failing gracefully. Confirmed required the hard way: the
            # first version of this generator omitted it entirely.
            "allSchedulePresentations": list(by_id.keys()),
        },
        "modifiedTime": {"lastModifiedTime": _iso(datetime.now(timezone.utc))},
    }


def write_schedule(schedule: dict, out_path: Path) -> None:
    out_path.write_text(json.dumps(schedule, indent=2))
