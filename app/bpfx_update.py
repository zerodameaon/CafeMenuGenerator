"""Updates an existing brightAuthor:connected presentation (.bpfx) file in
place to point at a freshly generated menu PNG, instead of generating a new
schedule every week.

Rationale (2026-08-20 pivot): if each weekday's schedule entry is set to
recur forever (recurrenceGoesForever: true — see bpsx_schedule.py), the
schedule only needs to be created once, ever. The only thing that changes
week to week is the *image* each day's presentation shows. So instead of
regenerating a schedule, we edit the five existing "Cafe Menu <Day>.bpfx"
files to reference this week's PNG, and the user just hits Publish in bAc.

.bpfx structure relevant here (reverse-engineered from the cafe's real
"Cafe Menu Monday.bpfx" et al., brightAuthorVersion 1.85.0): the day's menu
image is referenced across three id spaces that must all be kept in sync
(the assetMap id and the mediaState id are NOT the same value — the
mediaState links to its asset via contentItem.assetId), or bAc's own UI
shows the old filename even though the underlying asset changed:

  bsdm.mediaStates.mediaStatesById.<id>.name                (display name)
  bsdm.mediaStates.mediaStatesById.<id>.contentItem.name    (display name)
  bsdm.events.<id>.name             (named "<pngname>_ev", cosmetic only)
  bsdm.transitions.transitionsById.<id>.name  ("<pngname>_tr", cosmetic only)
  bsdm.assetMap.<id>.{name, path, locator, fileSize, lastModifiedDate}

The events/transitions names are cosmetic (bAc doesn't appear to re-parse
them), but are updated anyway so nothing in the UI shows a stale filename.
fileSize and lastModifiedDate in assetMap must match the real PNG on disk —
bAc uses these to decide whether the asset needs re-uploading to the player
on Publish.

Each day's asset is found by mediaType == "Image" in assetMap; every real
file inspected had exactly one such asset (the Time/Clock zone is a
built-in widget, not an image asset), so no day-name matching is required
inside the file itself — only the caller needs to already know which
.bpfx corresponds to which weekday.

One more wrinkle, learned the hard way: an earlier version of this module
hardcoded the asset's new path/locator to a fixed remote path
("/Users/stbpa/Documents/Brightsign/") — a guess at what the bAc
computer's own absolute path to the shared folder would be. That broke in
practice: bAc showed "Open presentation error — file not found" for the
image, because the .bpfx was actually opened from wherever the user
really saved it (a different Mac, a different account, a different
folder name), which didn't match the hardcoded guess. There's no way to
know that path in advance, and no need to guess it: whatever folder
local_write_dir points to (the folder passed in — normally wherever the
user picked when running "Update This Week's Presentations…") is by
definition where the .bpfx and its PNG both actually live once written,
on whatever computer is running this. So the path/locator fields are
always derived straight from local_write_dir itself, not any hardcoded
constant — this makes the written file self-consistent and portable
across machines and accounts, since bAc opens the .bpfx from that same
real folder.
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


class BpfxUpdateError(Exception):
    pass


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def update_presentation(
    bpfx_path: Path,
    new_png_path: Path,
    local_write_dir: Path,
) -> Path:
    """Rewrites bpfx_path in place so its one image asset points at
    new_png_path, copying new_png_path into local_write_dir. The .bpfx's
    path/locator fields are written using local_write_dir's own resolved
    absolute path — wherever the PNG is actually being saved is where bAc
    needs to find it, on whatever machine this happens to run on. Returns
    the local path the PNG was copied to.

    Raises BpfxUpdateError if the file doesn't have exactly one image asset
    to update (the shape this was built against).
    """
    data = json.loads(bpfx_path.read_text())

    asset_map = data["bsdm"]["assetMap"]
    image_assets = [(k, v) for k, v in asset_map.items() if v.get("mediaType") == "Image"]
    if len(image_assets) != 1:
        raise BpfxUpdateError(
            f"{bpfx_path.name}: expected exactly one image asset, found {len(image_assets)}."
        )
    asset_id, asset = image_assets[0]
    old_name = asset["name"]

    media_states_by_id = data["bsdm"]["mediaStates"]["mediaStatesById"]
    matching_states = [
        (mid, ms)
        for mid, ms in media_states_by_id.items()
        if ms.get("contentItem", {}).get("assetId") == asset_id
    ]
    if len(matching_states) != 1:
        raise BpfxUpdateError(
            f"{bpfx_path.name}: expected exactly one mediaState referencing "
            f"asset {asset_id}, found {len(matching_states)}."
        )
    media_state_id, media_state = matching_states[0]

    new_name = new_png_path.name
    dest_path = local_write_dir / new_name

    local_write_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(new_png_path, dest_path)

    stat = dest_path.stat()
    last_modified = _iso(datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc))

    resolved_dir = str(local_write_dir.resolve())
    if not resolved_dir.endswith("/"):
        resolved_dir += "/"

    asset["name"] = new_name
    asset["path"] = resolved_dir
    asset["locator"] = f"file://{resolved_dir}{new_name}"
    asset["fileSize"] = stat.st_size
    asset["lastModifiedDate"] = last_modified

    media_state["name"] = new_name
    media_state["contentItem"]["name"] = new_name

    for event in data["bsdm"]["events"].values():
        if event.get("mediaStateId") == media_state_id and event["name"] == f"{old_name}_ev":
            event["name"] = f"{new_name}_ev"

    for transition in data["bsdm"]["transitions"]["transitionsById"].values():
        if transition.get("targetMediaStateId") == media_state_id and transition["name"] == f"{old_name}_tr":
            transition["name"] = f"{new_name}_tr"

    bpfx_path.write_text(json.dumps(data, indent=2))

    if new_name != old_name:
        old_path = local_write_dir / old_name
        if old_path.exists() and old_path != dest_path:
            old_path.unlink()

    return dest_path


def update_week(
    bpfx_dir: Path,
    day_to_png: dict[str, Path],
) -> list[Path]:
    """Updates "Cafe Menu <Day>.bpfx" for each day_name -> png_path pair in
    day_to_png (e.g. {"Monday": Path(...), ...}). bpfx_dir doubles as
    local_write_dir — the PNGs are copied into the same shared folder the
    .bpfx files live in. Returns the list of PNG destination paths written.
    Raises BpfxUpdateError (with all problems listed) if any day's .bpfx is
    missing or doesn't match the expected single-image-asset shape —
    nothing is written for any day until every day has been validated, so
    a partial week never gets half-applied.
    """
    problems: list[str] = []
    resolved: dict[str, Path] = {}
    for day_name in day_to_png:
        bpfx_path = bpfx_dir / f"Cafe Menu {day_name}.bpfx"
        if not bpfx_path.exists():
            problems.append(f"{bpfx_path.name} not found in {bpfx_dir}")
            continue
        resolved[day_name] = bpfx_path

    if problems:
        raise BpfxUpdateError("\n".join(problems))

    written: list[Path] = []
    for day_name, png_path in day_to_png.items():
        written.append(
            update_presentation(resolved[day_name], png_path, bpfx_dir)
        )
    return written
