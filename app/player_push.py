"""Pushes new menu PNGs straight onto the BrightSign player over its Local
DWS API — no brightAuthor:connected Publish needed. Proven live against the
cafe's player on 2026-09-24 (see context.md, "Direct push to the player").

How a bAc-published player finds each day's image:

  sd/local-sync.json   manifest bAc writes on every Publish. files.download
                       is a list of {name, link, size, hash: {method, hex}},
                       mapping each published file's *name* to where its
                       bytes live in the content pool.
  sd/pool/<a>/<b>/sha1-<hex>
                       the bytes, stored under the SHA1 of their raw
                       contents; <a>/<b> are the hex's last two characters.
  autoplay-Cafe Menu <Day>.json
                       each day's presentation (itself a pool file listed in
                       the manifest). Refers to its image only by file name
                       ("fileName": "The_Cafe_Menu_Monday_2026-09-21.png").

So to change a day's image: upload the new PNG into the pool under its own
SHA1, then repoint that day's image *name* in the manifest at the new pool
file (hash/link/size), leaving the name alone so the presentation still
finds it. The player only reads the manifest at startup, so it's rebooted
afterwards (~25s of blank screen on the real player).

Nothing here touches the presentations or the schedule. The next Publish
from bAc will overwrite the manifest with whatever its own .bpfx files
point at — which is why the app's "Update This Week's Presentations" (which
rewrites those .bpfx files) and this push should be kept in step.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from brightsign_client import BrightSignError, Player

MANIFEST = "local-sync.json"
DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".bmp")
BACKUP_DIR = Path.home() / ".cafe_menu_player_backups"


class PlayerPushError(Exception):
    pass


@dataclass
class DayChange:
    day_name: str
    image_name: str       # the name the day's presentation uses (unchanged)
    old_hash: str
    new_png: bytes
    new_hash: str

    @property
    def unchanged(self) -> bool:
        return self.old_hash == self.new_hash


def next_showing(day_name: str, today: date) -> date:
    """The next date the player will show `day_name`'s presentation: today
    if today is that weekday, otherwise that weekday's next occurrence. The
    schedule repeats every week forever, so this is the only week a pushed
    image can land in."""
    return today + timedelta(days=(DAY_NAMES.index(day_name) - today.weekday()) % 7)


def date_mismatches(day_dates: dict[str, date], today: date) -> list[tuple[str, date, date]]:
    """(day, date on the sign, date it'll actually be shown) for every day
    whose sign is dated for a different week than the one it'll air in.

    Catches two real mistakes: pushing with the wrong Starting Monday (this
    shipped a Thursday sign dated October 1 on September 24 — the default
    is the *upcoming* Monday), and overwriting a day early, e.g. pushing
    next week's Friday before this week's Friday has aired.

    Deliberately NOT flagged: days of the current week that have already
    aired (pushing this week's full menu on a Thursday re-sends Monday–
    Wednesday, whose next showing is next week — harmless, since next
    week's push replaces them). Warning on every correct mid-week push
    would teach people to click straight past the warning."""
    this_monday = today - timedelta(days=today.weekday())
    return [
        (day, sign_date, next_showing(day, today))
        for day, sign_date in day_dates.items()
        if sign_date != next_showing(day, today) and not (this_monday <= sign_date < today)
    ]


def pool_link(sha1_hex: str) -> str:
    return f"pool/{sha1_hex[-2]}/{sha1_hex[-1]}/sha1-{sha1_hex}"


def _downloads(manifest: dict) -> list[dict]:
    try:
        return manifest["files"]["download"]
    except (KeyError, TypeError) as e:
        raise PlayerPushError(f"The player's {MANIFEST} isn't in the expected format (missing files.download).") from e


def _entries(manifest: dict, name: str) -> list[dict]:
    # bAc lists a file once per presentation that uses it — on the real
    # player the clock widget and device web page each appear 5 times. So a
    # name can have several entries, and every one must be kept in step.
    return [d for d in _downloads(manifest) if d.get("name") == name]


def _entry(manifest: dict, name: str) -> dict | None:
    found = _entries(manifest, name)
    return found[0] if found else None


def _image_names_in(presentation: object) -> set[str]:
    """Every image file name a presentation JSON refers to via "fileName"."""
    found: set[str] = set()
    if isinstance(presentation, dict):
        for k, v in presentation.items():
            if k == "fileName" and isinstance(v, str) and v.lower().endswith(IMAGE_EXTS):
                found.add(v)
            else:
                found |= _image_names_in(v)
    elif isinstance(presentation, list):
        for v in presentation:
            found |= _image_names_in(v)
    return found


def find_day_image(player: Player, manifest: dict, day_name: str) -> dict:
    """Returns the manifest entry for the image `day_name`'s presentation
    shows, by reading that presentation off the player — not by guessing
    from file names."""
    pres_name = f"autoplay-Cafe Menu {day_name}.json"
    pres = _entry(manifest, pres_name)
    if pres is None:
        raise PlayerPushError(
            f"{day_name}: the player has no published '{pres_name}'. Publish the "
            "presentations from brightAuthor:connected once before pushing directly."
        )
    try:
        pres_json = json.loads(player.read_file(pres["link"]))
    except ValueError as e:
        raise PlayerPushError(f"{day_name}: couldn't read the published presentation on the player.") from e
    names = _image_names_in(pres_json)
    if len(names) != 1:
        raise PlayerPushError(
            f"{day_name}: expected the presentation to show exactly one image, found "
            f"{len(names)} ({', '.join(sorted(names)) or 'none'})."
        )
    image_name = names.pop()
    entry = _entry(manifest, image_name)
    if entry is None:
        raise PlayerPushError(f"{day_name}: '{image_name}' isn't in the player's {MANIFEST}.")
    return entry


def plan(player: Player, day_to_png: dict[str, Path]) -> tuple[str, dict, list[DayChange]]:
    """Reads the player's current state and works out every change, without
    writing anything. Raises PlayerPushError (listing every problem) if any
    selected day can't be pushed, so a week is never half-pushed.
    Returns (original manifest text, parsed manifest, changes)."""
    manifest_text = player.read_file(MANIFEST).decode("utf-8")
    try:
        manifest = json.loads(manifest_text)
    except ValueError as e:
        raise PlayerPushError(f"The player's {MANIFEST} isn't valid JSON.") from e

    changes: list[DayChange] = []
    problems: list[str] = []
    for day_name, png_path in day_to_png.items():
        try:
            entry = find_day_image(player, manifest, day_name)
        except (PlayerPushError, BrightSignError) as e:
            problems.append(str(e))
            continue
        data = png_path.read_bytes()
        new_hash = hashlib.sha1(data).hexdigest()
        old_hashes = {e.get("hash", {}).get("hex", "") for e in _entries(manifest, entry["name"])}
        changes.append(DayChange(
            day_name=day_name, image_name=entry["name"],
            # If copies of the entry disagree, record no single old hash, so
            # the day counts as changed and every copy gets brought in line.
            old_hash=old_hashes.pop() if len(old_hashes) == 1 else "",
            new_png=data, new_hash=new_hash,
        ))

    # A day's image is found by *name*, and a name maps to one pool file. If
    # another day's presentation shows the same image name, changing it for
    # one day would silently change it for the other too — refuse instead.
    if not problems:
        pushing = {c.image_name: c.day_name for c in changes}
        for other_day in DAY_NAMES:
            if other_day in day_to_png or _entry(manifest, f"autoplay-Cafe Menu {other_day}.json") is None:
                continue
            try:
                other_image = find_day_image(player, manifest, other_day)["name"]
            except PlayerPushError:
                continue  # that day isn't a normal single-image presentation; can't share
            if other_image in pushing:
                problems.append(
                    f"{pushing[other_image]} and {other_day} show the same image file "
                    f"('{other_image}'), so pushing {pushing[other_image]} would change "
                    f"{other_day} too. Include {other_day} in this push, or give each "
                    "day its own image with Update This Week's Presentations + a Publish."
                )
        by_image: dict[str, list[DayChange]] = {}
        for c in changes:
            by_image.setdefault(c.image_name, []).append(c)
        for name, group in by_image.items():
            if len({c.new_hash for c in group}) > 1:
                problems.append(
                    f"{' and '.join(c.day_name for c in group)} show the same image file "
                    f"('{name}') on the player, so they can't be given different signs "
                    "by a push. Give each day its own image with Update This Week's "
                    "Presentations + a Publish from brightAuthor:connected."
                )
    if problems:
        raise PlayerPushError("\n".join(problems))
    return manifest_text, manifest, changes


def apply_to_manifest(manifest: dict, changes: list[DayChange]) -> str:
    """Returns the new manifest text with each changed day's image entry
    repointed at its new pool file. Only hash/link/size change; everything
    else (names, order, the other entries, meta) is kept as-is."""
    for c in changes:
        for entry in _entries(manifest, c.image_name):
            entry["hash"] = {"hex": c.new_hash, "method": "SHA1"}
            entry["link"] = pool_link(c.new_hash)
            entry["size"] = len(c.new_png)
    return json.dumps(manifest, indent=1, ensure_ascii=False)


def backup_manifest(manifest_text: str) -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    path = BACKUP_DIR / f"local-sync-{datetime.now():%Y%m%d-%H%M%S}.json"
    path.write_text(manifest_text, encoding="utf-8")
    return path


def push(player: Player, day_to_png: dict[str, Path], progress=lambda msg: None) -> tuple[list[DayChange], Path]:
    """The whole push: plan (read-only) → back up the manifest locally →
    upload new PNGs to the pool → upload the new manifest and verify it →
    reboot. Returns (changes, local manifest backup path).

    Order matters for safety: new pool files are unreferenced (harmless)
    until the manifest points at them, and the manifest is only swapped
    once every PNG is verified on the player. If the manifest upload itself
    doesn't verify, the original is put back before anything reboots."""
    progress("Reading the player's current setup…")
    manifest_text, manifest, changes = plan(player, day_to_png)
    backup = backup_manifest(manifest_text)

    to_send = [c for c in changes if not c.unchanged]
    if not to_send:
        return changes, backup

    uploaded: set[str] = set()
    for c in to_send:
        if c.new_hash in uploaded:
            continue  # identical bytes already sent for another day
        progress(f"Uploading {c.day_name}…")
        folder, filename = pool_link(c.new_hash).rsplit("/", 1)
        player.upload(c.new_png, folder, filename)
        uploaded.add(c.new_hash)

    progress("Updating the player's content list…")
    new_text = apply_to_manifest(manifest, to_send)
    player.upload(new_text.encode("utf-8"), "", MANIFEST)
    # upload() already byte-verifies; double-check it still parses and
    # points where intended before rebooting into it.
    check = json.loads(player.read_file(MANIFEST))
    for c in to_send:
        found = _entries(check, c.image_name)
        if not found or any(e.get("link") != pool_link(c.new_hash) for e in found):
            player.upload(manifest_text.encode("utf-8"), "", MANIFEST)
            raise PlayerPushError(
                "The player's content list didn't update correctly, so the original was put "
                "back and the player was not restarted. Nothing on screen has changed."
            )

    progress("Restarting the player (the sign goes blank for about 30 seconds)…")
    player.reboot_and_wait()
    return changes, backup
