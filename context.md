# Context for maintaining The Cafe Menu Sign Generator

This doc is for whoever (human or AI) picks this project back up later. It
covers *why* things are built the way they are, not just what the code
does — read this before making non-trivial changes, especially to
`build_app.sh` or the packaging path logic, since several parts of this
were arrived at by trial and error against real failures.

For day-to-day usage and quick reference, see `README.md`. The original
design brief this project was scoped from is `~/Downloads/CLAUDE.md` — the
menu-sign visual spec (colors, fonts, layout, per-day sizing) still matches
that, with one deliberate deviation: the brand-column logo was removed
from the signs themselves (see "Logo split" below).

## What this is

A double-clickable, fully offline macOS app for one cafe's kitchen staff.
Input: the week's lunch menu as a `.docx`. Output: five 3840×600px PNGs
(Mon–Fri), pixel-matched to a maroon digital-signage design, for a
BrightSign player driving an 86" ultra-wide panel. A second in-app panel
walks through publishing those PNGs to the BrightSign player via
brightAuthor:connected.

## Architecture

```
.docx  →  parser.py (DayMenu/MenuRow)  →  template.py (HTML string)
       →  renderer.py (Playwright/Chromium screenshot, 4x supersample
          → Lanczos downsample to 3840×600, wrap + overflow guard)
       →  PNG files
```

`app.py` is the Tkinter GUI wrapping all of the above, plus two in-app help
panels.

- **`parser.py`** — pure logic, no UI/rendering dependencies. Reads every
  line of the docx in document order (paragraphs *and* table cells, soft
  line breaks split into separate lines), splits it into per-day blocks on
  lines that exactly match a weekday name, then extracts labeled lines. Friday's veg/non-veg soup ambiguity and
  Wednesday's standalone "Assorted Sushi" line are handled here, not in the
  template.
- **`template.py`** — builds one self-contained HTML string per day. Fonts
  are embedded as base64 data URIs (no external font files referenced at
  render time) so the rendered HTML has zero external dependencies.
- **`renderer.py`** — drives headless Chromium via Playwright: renders each
  day's HTML at a 4x device-scale-factor viewport, screenshots, then
  Lanczos-downsamples to the exact 3840×600 target (see "Why supersample"
  below). Also runs the wrap/overflow layout check before allowing export.
- **`player_push.py` / `brightsign_client.py`** — "Push to Player": sends
  PNGs straight to the BrightSign player over its Local DWS API (see
  "Direct push to the player").
- **`app.py`** — Tkinter GUI. Also bootstraps `PLAYWRIGHT_BROWSERS_PATH`
  when running as a frozen PyInstaller build (see "Packaging" below).

## Key decisions and why

### Python + Playwright + bundled Chromium, not native Swift/WKWebView

The original brief flagged this as an open decision requiring sign-off
(bundling Chromium is heavier but lets the existing Python/Playwright
rendering logic port over almost unchanged; WKWebView is lighter but means
a from-scratch Swift rewrite). User chose Python + Playwright. This is why
the shipped `.app` is ~730MB — almost entirely the bundled Chromium.

### Why supersample-then-downsample instead of rendering at 1x

The target panel is exactly 3840×600 physical pixels for an 86" panel —
very low pixel density for that size. Rendering at 1x produces visibly
rougher text edges than rendering at 4x and downsampling with Lanczos. This
is a deliberate, load-bearing design choice from the original spec — don't
"simplify" it back to a 1x screenshot.

### Wrap-detection validation

Every label and item cell gets measured after render; if any cell's
rendered height suggests it wrapped to two lines, export is blocked with an
error naming the day and text. This exists because the *reference* design
this app is based on actually specified a narrower (280px) label column
than what's needed at the shipped font sizes — that mismatch caused a real
wrapping bug once, caught only by manual review. The column width was
widened to 360px, and this automated guard was added so a similar mismatch
can't silently ship again.

**Important implementation detail:** the wrap-check JS in `renderer.py`
only works because `.label` and `.item-cell` in `template.py` do *not* have
`white-space: nowrap` set. An earlier version had `nowrap` on both, which
made the JS check permanently pass (nothing can "wrap" if it's forbidden
from wrapping — it just silently overflows instead). If you ever add
`nowrap` back for some other reason, the validation guard goes blind again;
test it deliberately (see below) if you touch this.

**Vertical overflow is checked too (2026-09-24).** The wrap check only
catches text running out of room *sideways*. `html`/`body` are
`overflow: hidden`, so a day with too many rows would just have its bottom
rows silently clipped off the sign. `LAYOUT_CHECK_JS` now also compares the
`.menu` column's `scrollHeight` to its `clientHeight` and blocks export if
the rows don't fit. Verified that a full 6-row Wednesday (the tallest real
layout) passes in both variants, and a 12-row day is caught.

**How to test the guard still works:** temporarily lengthen a row's label
or item text via `parser.py`'s output in a scratch script, run it through
`render_days(..., strict=True)`, and confirm `RenderValidationError` is
actually raised — don't just trust that the code "looks right." This
bit us once already.

### Missing menu items are dropped, not errors (2026-08-28)

`parser.py`'s `_parse_day_block()` originally treated every field
(Breakfast, both soups on non-Friday days, Main Entrée, Veggie Entrée,
Wednesday's sushi line) as required, raising `MenuParseError` if any were
absent — reasonable when every real week actually had every item, but the
user reported a real week's document that didn't (e.g. only one soup line
on Monday and Thursday, no Veggie Entrée at all on Friday). Real weekly
menus vary which items appear per day, so a missing line is now simply
left out of that day's rows instead of blocking the whole export.

This works with no `template.py` changes: rows are already sized by CSS
flex-grow (`flex: {weight}` per row, see `DAY_TYPE_SIZING`), not a fixed
row count, so a day with fewer rows just gives each remaining row more
vertical space — verified by rendering a 3-row day and a real 4-row week
(`Aug 31-Sept 4.docx`) and confirming no wrapping and no crash.

**Still treated as real errors** (signals of a malformed document, not an
intentionally sparse day):
- Friday listing *both* a veg and non-veg soup line — still ambiguous,
  since exactly one (or now, none) is expected.
- A day ending up with **zero** recognized rows at all — almost certainly
  a parsing problem (wrong day-name spelling, garbled formatting) rather
  than a day that legitimately has nothing on it.

Note: there's a pre-existing, unrelated layout characteristic — even a
full 5-row day doesn't visually fill the canvas's full 600px height (some
dead space below the last row) — confirmed present on a normal 5-row day
too while investigating this, so it isn't something this change caused.
Left alone since it wasn't part of what was reported broken; worth a
separate look if it ever needs fixing.

### Logo split: on the app icon, not on the menu signs

Earlier iterations put a burger+sushi-roll icon in the brand column of
every sign (where the original spec had a fork+spoon icon). The user later
asked for the icon to be removed from the signs and to exist *only* as the
app's Finder/Dock icon. Current state:
- `template.py` has no icon/logo markup at all — brand column is just
  "THE CAFE" / "— Daily Menu —" up top, day/date pinned to the bottom via
  a flex spacer.
- `app/icon_src/make_icon.py` generates a *separate* square burger+sushi
  icon (maroon background, gold line art) purely for `app/AppIcon.icns`,
  wired into the build via `--icon` in `build_app.sh`.
- These two pieces of art are visually related (same line style) but
  intentionally decoupled — don't reintroduce the icon into the sign
  template without being asked.

### Light and dark mode

Tkinter's native (Aqua) widgets on macOS don't reliably re-theme for dark
mode — plain `tk.Label`/`Frame`/`Button` widgets once rendered with poor
contrast (dark-on-dark) when the OS was in dark mode. The first fix forced
a single light palette everywhere. Since 2026-09-24 the app instead has two
explicit palettes, `LIGHT_PALETTE` and `DARK_PALETTE` in `app.py`, still
drawn entirely by the app (ttk `clam` theme + explicit colors on every
plain tk widget) rather than left to Aqua. Both pass WCAG AA contrast
(≥4.5:1 for text; disabled button text ≥3:1).

- **At launch** the palette follows macOS's appearance, read via
  `::tk::unsupported::MacWindowStyle isdark` (Tk 8.6.10+; anything else
  falls back to light).
- **Live switching:** `App._watch_appearance()` polls every 2s. On a flip it
  re-runs `_setup_style()` (re-themes all ttk widgets) and `_recolor_tree()`
  walks every widget in every open window, swapping old palette colors for
  new ones. The swap is keyed by *role* (background options only hold
  BG/PANEL_BG/ACCENT, foreground options only the *_FG colors), because light
  `BG` and `ACCENT_FG` are the same hex. So within one palette, the
  background colors must be distinct from each other, and so must the
  foreground colors.
- **If you add widgets:** give them colors from the palette names (`BG`,
  `FG`, …) at creation, never literal hex. Anything literal won't follow a
  switch. ttk-only state colors (hover, disabled, scrollbar thumb) live in
  the palette dicts and are applied in `_setup_style()`.
- The sign images themselves are unaffected; they have their own fixed
  "House Special"/"Lighter Fare" designs.

### Food-pun copy voice

By explicit request, all user-facing GUI copy (button labels, status
messages, dialog titles, both help panels) uses light food puns while
keeping the actual instructions literal and unambiguous underneath —
e.g. button says "Plate It Up (Export 5 PNGs)…", not just "Plate It Up".
Keep new copy consistent with this voice, but never let a pun obscure what
an action actually does.

### Packaging quirks (the fragile part — read before touching `build_app.sh`)

Getting this into a working offline `.app` took several failed attempts;
each fix below is there because the naive approach broke:

1. **`sys._MEIPASS` resolves to `Contents/Frameworks`, not
   `Contents/Resources`**, in a `--windowed` onedir PyInstaller build on
   macOS — even though PyInstaller's own `--add-data` assets (fonts,
   brightsign_help images) get mirrored into *both*. Chromium must be
   copied into `Contents/Frameworks/ms-playwright` specifically, or
   `app.py`'s `PLAYWRIGHT_BROWSERS_PATH` bootstrap can't find it and
   Playwright fails at runtime with "Executable doesn't exist."
2. **Chromium can't go through `--add-data` at all.** PyInstaller
   auto-codesigns every Mach-O binary it collects via `--add-data`/
   `--add-binary`, and chokes on a nested `.app` bundle (Chromium ships as
   its own `.app`). Workaround: build without it, then `cp -R` it into
   `Contents/Frameworks/ms-playwright` as a plain post-build shell step.
3. **Don't try to re-sign the whole tree afterward.** Both
   `codesign --deep` and even a non-deep re-sign of the outer app reliably
   fail on the nested Chromium/ffmpeg bundles (`.links` bookkeeping dir,
   embedded signatures, etc.) — for reasons that shifted between attempts
   and aren't worth chasing further. Current approach: don't re-sign at
   all. The downloaded Chromium already carries Google's own valid
   signature; the outer app is already ad-hoc signed by PyInstaller during
   the normal build step. What actually makes it launchable locally is
   clearing the quarantine flag (`xattr -cr`), which `build_app.sh` does
   automatically for the build machine. Moving the `.app` to another Mac
   still requires that Mac's Gatekeeper to be satisfied once — either
   `xattr -cr` there too, or right-click → Open.
4. **Icon must be generated before building**, not generated by
   `build_app.sh` itself — `app/AppIcon.icns` is a checked-in build input.
   Run `python3 app/icon_src/make_icon.py` if the icon art changes, before
   `./build_app.sh`.

### Distribution zip

`.app` bundles must be zipped with `ditto -c -k --sequesterRsrc
--keepParent`, not plain `zip` — plain zip can mangle bundle metadata.
Every rebuild in this project's history was re-verified by actually
extracting the zip to a scratch location and launching it before treating
the packaging step as "done." Keep doing that — a build that merely
completes without error is not proof it actually works when moved to
another machine.

### Bug-check pass (2026-09-24, v0.1.6)

A full read-through turned up several bugs, each fixed and verified with a
scratch test (not just by reading the code):

- **Error dialogs silently never appeared.** Background-thread error
  handlers did `except X as e: root.after(0, lambda: ... str(e))`. Python
  *unbinds* `e` when the `except` block exits, so the lambda raised
  `NameError` when Tk ran it — no dialog, status text frozen, and the
  Export/Update button stuck disabled until restart. This hit the most
  common real failure (text wrap blocking an export) and the player
  browser's `BrightSignError` path. **Rule: never reference the `except`
  variable inside a deferred callback — copy it to a local first**
  (`msg = str(e)`), as the generic `except Exception` handlers already did
  with `err`.
- **"Closed" detection swallowed real menus.** `_closed_reason()` marked a
  day closed if *any* colon-less line mentioned "closed", despite its
  docstring saying "no menu lines". A day with a full menu plus "Cafe
  closed early at 1pm" rendered as a CLOSED sign. Now a day is only closed
  if it has no recognized menu line at all (`_is_menu_line()`).
- **`update_week()` atomicity** — see the `.bpfx` section below.
- **Parser robustness.** Labels are matched through `_key()` (NFC
  normalize, Unicode dashes → `-`, any whitespace incl. NBSP → one space,
  lowercased) because Word AutoFormat look-alikes made labels like
  "Non‑Vegetarian Soup Du Jour" (non-breaking hyphen) silently fail to
  match and the row just vanished. Item text on the sign is left exactly as
  typed — `_key()` is for matching only. Tables are now read (via
  `iter_inner_content()`, needs python-docx ≥ 1.0; cells are walked via
  `tr.tc_lst` so a horizontally merged cell isn't read once per grid
  column). Soft line breaks (Shift+Enter) split into separate lines —
  previously the second line got glued onto the first item. A duplicated
  day heading is now an error; before, it silently discarded the first
  block.
- **GUI state.** One `App._set_busy()` now locks Preview, Export, Update,
  and Advanced → Generate Schedule for the duration of any background job,
  and on unlock only re-enables the action buttons if `self.days` is set.
  `self.days` is only assigned in `_show_previews()` — a parse is held in a
  local until its preview renders — so a failed reparse/preview leaves
  export/update acting on what's still on screen. (This supersedes the
  `had_prior_days` fix from 2026-09-08.) Each day-picker dialog snapshots
  `self.days` when opened. `self.variant.get()` is read on the main thread
  and passed into workers, since Tk isn't thread-safe.

## The "Recipe (Instructions)" panel

`app.py`'s `show_brightsign_instructions()` and `BRIGHTSIGN_STEPS` render a
second in-app help window (Help menu → "Recipe (Instructions)", and a
button next to "Update This Week's Presentations…"). Originally titled
"Send to BrightSign" and mirrored the old manual publish workflow
(brightAuthor:connected → per-day Content tab swap → Schedule tab
drag-and-drop → Publish); rewritten (2026-08-20, alongside the button
reorganization below) once that manual workflow was replaced by the
forever-recurring schedule + `bpfx_update.py` pivot. It's still not generic
BrightSign documentation — it mirrors this cafe's actual (now much
shorter) publish workflow, sourced from a real walkthrough the user wrote
plus real screenshots of their own brightAuthor:connected setup.

**Restructured 2026-09-24 around Push to Player.** Both the Recipe window
and Chef's Instructions (`INSTRUCTIONS_TEXT`) now lead with the weekly
path as *preview → Push to Player*, and put everything brightAuthor:
connected in a section at the bottom: the one-time setup (Publish the five
presentations once — push only swaps images inside presentations already
on the player — and generate the forever-recurring schedule), the old
"Update This Week's Presentations → Publish" route, and the rule that
before *any* bAc Publish you must run Update for the current week first
(a Publish sends whatever images the `.bpfx` files point at, which lag
behind if the week only went out by push). `BRIGHTSIGN_STEPS` entries of
the form `(title, None, None)` render as section headings.

- Source screenshots live in `app/brightsign_help/` (bundled into the
  `.app` via `build_app.sh`'s `--add-data`), renamed from the originals in
  `Screenshots/` for clarity (`01_open_baconnected.png` etc.). Two of the
  five original screenshots (`02_content_tab.png`, `04_schedule_event.png`)
  are no longer referenced by any step — they depicted the manual
  per-day Content-tab swap and Schedule-tab drag-and-drop, both now done
  by the app — but were left in `brightsign_help/` rather than deleted,
  in case a future rewrite needs them again.
- The **"Cafe Menu Last Friday" fallback slot** is gone — but the
  underlying problem it solved is NOT gone, and an earlier version of
  this doc wrongly claimed it was. Each weekday is now one persistent
  presentation tied to a forever-recurring schedule entry (no more
  dated blocks, so no schedule range to run out of, and updating
  Monday–Thursday early genuinely can't disturb each other). But there's
  still only **one** `Cafe Menu Friday.bpfx` — the schedule can't tell
  "this Friday" from "next Friday", it's the same recurring block. If
  next week's `.docx` arrives before the current week's Friday has aired
  and you update all 5 days, Friday's image gets overwritten with next
  week's menu before this week's Friday plays. This is why "Push to
  Player…" and "Update This Week's Presentations…" each have a day-picker (all 5 checked by
  default, mirroring the schedule generator's) — leave Friday unchecked
  until the current week's Friday has actually aired if you're prepping
  ahead. See `update_presentations()` in `app.py`.
- If the BrightSign player's UI changes (new brightAuthor:connected
  version, renamed player, etc.), the steps and/or screenshots will need
  updating to match — nothing here validates itself against the real
  BrightSign software.

## Direct-to-player upload — first attempt (history; superseded)

> **Superseded 2026-09-24.** The conclusion at the end of this section
> ("this player cannot do direct-to-device upload") turned out to be wrong:
> port 8080 was never the DWS API at all. Direct push now works and ships
> as "Push to Player" — see **"Direct push to the player"** below. This
> section is kept for the history and debugging lessons.

The user asked whether the app could upload straight to the BrightSign
player instead of going through brightAuthor:connected by hand. Findings:

- **brightAuthor:connected itself has no CLI/scripting interface** — it's
  GUI-only, confirmed via BrightSign's own support forum. Automating "click
  Publish in bAc" isn't possible.
- **The player itself exposes a documented Local DWS REST API** (separate
  from bAc): `GET`/`PUT http://<player-ip>/api/v1/files/<storage>/<path>`,
  authenticated with standard HTTP Digest auth (default `admin` / the
  player's serial number as password). This was confirmed by reading the
  source of BrightSign's own reference CLI,
  [player-cli](https://github.com/brightsign/player-cli) — not from
  docs.brightsign.biz directly, which is JS-rendered and returns 404 to a
  plain HTML fetch. If that site becomes fetchable later, it's the more
  authoritative source to re-check against.
- Local DWS access must already be enabled on the player (off by default
  since BrightSignOS 9.0.218+); the user confirmed it's already on for the
  Cafe Menu player.
- **The port is not reliably 80.** This cafe's actual player (firmware
  9.1.93.2) serves Local DWS on **port 8080**. Debugging this live: ping to
  the player's IP succeeded, but both a browser and `list_files()` hung/
  failed against port 80 — the giveaway was that the *browser* also
  couldn't load `http://<ip>/...`, which ruled out our code and pointed at
  network/port instead of credentials. Loading `http://<ip>:8080` directly
  in a browser confirmed it — that's DWS's own plain landing page (shows
  player name, serial, firmware, links to "Diagnostic Page"). `port` is now
  a required, explicit argument to every `brightsign_client.py` function
  and a GUI field (defaulting to 8080, since that's confirmed for this
  player) — don't reintroduce a hardcoded port-80 default.
- Password: this player accepts a **blank password** with username `admin`
  — never got a chance to confirm the serial-number fallback since blank
  already worked once the port was fixed. bAc's own player "gear icon" opens
  an unrelated "Player Credential" (Email/Password) dialog — that's a
  BSN.Cloud login prompt, not the Local DWS credential; don't confuse the
  two if troubleshooting this again.
- **The one open unknown, not yet resolved:** does a presentation's zone in
  brightAuthor:connected read its image from a fixed, predictable filename
  on the player's storage (so a direct overwrite would update the live
  display without touching bAc at all), or does bAc rename/rehash the
  asset file on every Publish (which would make a blind overwrite silently
  do nothing)? This determines whether direct-upload can ever actually
  replace the manual Content-tab swap step. The user didn't know off-hand.

**What's built so far (`app/brightsign_client.py` + Help → "Browse Player
Files"):** a read-only panel that connects to the player's Local DWS and
lists file/folder contents at a given path, so the user can find the
actual filename/path a zone reads from. `list_files()` is wired into the
GUI; `upload_file()` exists in the client module but is **deliberately not
wired to any button yet** — don't add an upload button until the path
question above is answered, since pushing to an unconfirmed path on a live
signage device is either a no-op or a real mistake, not a safe guess.

**Next step, once the user reports back the real path:** add an actual
"Push this week's PNGs to the player" feature using `upload_file()` against
the confirmed `dest_dir`, most likely gated by an explicit confirmation
dialog before it touches the live device. The connection panel already
persists IP/username/storage (not password) to
`~/.cafe_menu_brightsign_player.json` for convenience across sessions —
follow that same pattern rather than inventing a new config mechanism.

**Testing note:** no real BrightSign player is reachable from this dev
environment. Everything in `brightsign_client.py` was verified against a
local mock HTTP server (stdlib `http.server`) simulating the exact
response shapes from the real API — both the success path and a 401
rejection — plus a real Tkinter `mainloop()` click-through test of the
"List" button end to end. That's a substitute for testing against real
hardware, not equivalent to it — the first real-player test should be
treated as the actual verification, not a formality. This was borne out in
practice: the mock-server tests all passed, and the feature still failed
completely the first time it hit the real player (wrong port — see above),
and then hung silently the *second* time against the real player, for a
different reason described next.

**Bug found on first real-player use, now fixed: silent hang on JSON
shape mismatch.** Once the port was fixed, "Browse Player Files" got stuck
forever on "Listing sd/(root)..." with no error. Root cause: the response-
formatting loop in `app.py`'s `do_list()`/`worker()` assumed every file
entry is a dict with `.get("name")`/`.get("mime")`/`.get("size")` — an
assumption read from `player-cli`'s source, never confirmed against this
player's actual firmware (9.1.93.2). That formatting code ran *outside*
the `try/except brightsign_client.BrightSignError` block, so the moment
the real response's shape didn't match the assumption, an uncaught
exception silently killed the background thread — the GUI's status text
just never got updated again, indistinguishable from a real hang.

Fix: the entire `worker()` body is now one broad `try/except`, and
`brightsign_client.list_files()` records the raw response text in a
module-level `last_raw_response` dict so any parse failure can show the
*actual* bytes the player sent instead of a generic Python traceback. If
you touch this code path again: never let GUI-side response formatting
live outside error handling, and prefer "show the raw response" over
"assume the shape and hope" when working against a real device whose exact
API response hasn't been directly observed yet. This exact bug is why the
`list_files()` return type should be treated as "probably a list of dicts,
per someone else's client library" rather than a confirmed contract until
proven against a real player's response.

**Conclusion: this player cannot do direct-to-device upload, on any
firmware tested.** Live diagnosis via `curl` against the real player
(model XT245) confirmed:
- DWS itself works — its plain landing page loads fine on port 8080.
- Every single `/api/v1/*` route 404s with `{"Missing handler"}` —
  including `/api/v1/health`, a completely different endpoint group from
  `/api/v1/files/...`, ruling out "just the files API is missing."
- This was re-tested identically after upgrading the player's firmware
  from 9.1.93.2 to **10.0.16** (a real production firmware upgrade, done
  live during this investigation) and after re-enabling DWS + re-publishing
  + rebooting. Same 404 on both firmware versions.
- HTTPS on 8080 fails at the TLS handshake (plaintext-only port); port 443
  is refused outright.

This means the JSON REST layer that `player-cli` and BrightSign's docs
describe simply isn't present in this DWS build, independent of firmware
version, config, or reboot. **(Wrong — see the note at the top of this
section.)** The real cause: 8080 on this player is the brightAuthor:connected
*presentation's own* web server (`BSP.localServer`, advertised over Bonjour
as `BRIGHTSIGN-LWS-SERVICE`, `functionality=content`), which naturally has
no `/api/v1` handlers. The actual Local DWS API was switched off; once the
user enabled it, it appeared on 80 → redirecting to **HTTPS 443**.

## Direct push to the player (shipped 2026-09-24)

"Push to Player…" sends the week's PNGs straight to the BrightSign player
and restarts it — no brightAuthor:connected Publish. Proven live before it
was built: Thursday was swapped to the alt design mid-day, confirmed via a
player screenshot, then restored the same way.

**Connection.** Player "Cafe Menu", XT245, serial URF4DT001627, BrightSignOS
9.1.151, at 192.168.1.37 on the bAc Mac's *second* network interface (a USB
ethernet adapter on 192.168.1.x — the Mac's main connection is a different
subnet). Local DWS REST API on **HTTPS 443** with a self-signed cert
(`verify=False` — see `brightsign_client.py`), digest auth, user `admin`,
password set by the user when enabling DWS. The password is remembered
in the macOS login Keychain (`app/credentials.py`), keyed by
`username@ip`, and only after a push/listing it worked for — never in the
repo or in `~/.cafe_menu_brightsign_player.json` (which holds IP/username/
port only). It goes through `/usr/bin/security` on stdin, not a Python
keyring library: Keychain ties items to the creating program, and
`security` is stable across ad-hoc-signed rebuilds and source-vs-.app runs,
so there's no "allow access?" prompt after every build. It's per macOS
user account. "Clear IP" / "Clear password" in the Push dialog forget them. Found via Bonjour: `dns-sd -B _http._tcp local`.

**How a bAc-published player finds each day's image** (read off the real
player — `player_push.py`'s docstring has the details):
- `sd/local-sync.json` — manifest bAc writes on Publish; `files.download`
  maps each file *name* to `pool/<h[-2]>/<h[-1]>/sha1-<h>`, where `h` is the
  SHA1 of the file's raw bytes (verified against a real pool file).
- `autoplay-Cafe Menu <Day>.json` — each day's presentation, itself a pool
  file; refers to its image only by `"fileName"`.
- No signature on the manifest; the player re-reads it at boot.

So a push = upload each new PNG into the pool under its SHA1 → repoint that
day's image *name* in the manifest (hash/link/size only; the name stays, so
the presentation still finds it) → verify → `PUT /api/v1/control/reboot`.
The day's image name is found by reading the day's published presentation,
not by guessing from file names. Reboot took ~25s on the real player.

**Safety ordering** (all covered by an offline test using the real
manifest): every selected day is resolved before anything is written; the
manifest is backed up to `~/.cafe_menu_player_backups/` first; new pool
files are harmless until referenced; the manifest is swapped last and
read back — if it doesn't verify, the original is re-uploaded and the
player is *not* rebooted. Days whose image hash is unchanged are skipped,
and if nothing changed there's no reboot at all (renders are deterministic —
re-rendering the published week produced byte-identical PNGs).

**Quirks found the hard way:**
- `PUT /api/v1/files/sd/<dir>` into a folder that doesn't exist yet only
  **creates the folder** and still returns `success: true` — no file is
  written. `Player.upload()` therefore reads back and SHA1-checks every
  upload and retries once.
- `POST /api/v1/snapshot` returns only a thumbnail; the full 3840×600
  image is saved on the player at `sd/remote_snapshots/…` and read back.
- File reads are `GET /api/v1/files/sd/<path>?contents` → base64 in
  `data.result.contents`. Listings: entries have `type` ("file"/"dir") and
  `stat.size` — *not* the `mime`/`size` player-cli implied.
- In zsh, a shell loop variable named `path` clobbers `PATH` (it's tied
  to it) — "command not found: curl" while debugging this was that.

**Wrong-week guard (2026-09-24).** The first real pushes shipped this
week's menu with *next* week's dates — the Starting Monday defaults to the
upcoming Monday, and on Thursday Sept 24 the live sign showed "Thursday,
October 1" (in the alt design, which was also still selected). Every image
was exactly what the settings asked for; nothing in the push path was
wrong. So `player_push.date_mismatches()` now compares each sign's date
with the date the player will next show that weekday (today if it's that
weekday — the schedule recurs forever, so that's the only week a pushed
image can land in), and the confirmation becomes a warning defaulting to
"No". Days of the current week that have already aired are deliberately
*not* flagged: re-sending Monday–Wednesday on a Thursday is harmless, and
warning on every correct mid-week push would train people to click past
it.

**Shared images.** A day's image is found by name and a name maps to one
pool file, so if two days' presentations ever show the same file,
`plan()` refuses to push one without the other (or to give them different
signs). bAc lists a shared file once per presentation — the real manifest
has the clock widget 5 times — so every copy of an entry is updated.

**Interaction with bAc.** Nothing here touches the presentations or the
schedule. The next Publish from bAc overwrites `local-sync.json` with
whatever its `.bpfx` files point at, so keep running "Update This Week's
Presentations" as well — then both paths agree. Old pool files are left
behind; bAc's next Publish cleans up the pool.

## Auto-generated schedule (.bpsx) — the pivot that actually shipped

Since direct upload is a dead end, the user pivoted to a different,
lower-risk target: auto-generating brightAuthor:connected's **schedule**
file each week, so the only manual bAc step left is File → Open (with the
file-type filter switched to Schedule) → Publish — eliminating the
error-prone manual drag-and-drop scheduling entirely.

**Format**: `.bpsx` is bAc's native schedule file — confirmed via
BrightSign's own support forum to be plain, human-readable JSON, opened via
File → Open with the file-type filter switched to Schedule (not a separate
"Import" command — corrected by the user after I initially assumed
File → Import from a support-forum paraphrase). Reverse-engineered
end-to-end from the user's own real `autoschedule.bpsx` (a genuine
accumulated history of every week since 2026-07-17) since the format isn't
publicly documented. Structure: a flat dict of schedule entries keyed by
UUID, each with a `presentationLocator` (references a `.bpfx` presentation
by name + local path), a `dateTime`, a `duration` in minutes, and a
day-of-week bitmask (Sun=1, Mon=2, Tue=4, Wed=8, Thu=16, Fri=32, Sat=64) —
see the full annotated example at the top of `app/bpsx_schedule.py`.

**Real findings from the user's actual file** (valuable evidence, not
guesses): despite bAc supporting true weekly recurrence, every real week
in that file was added as its own one-off dated entry
(`"recurrence": false`) — nobody had actually been using recurrence in
practice, which is *why* the manual process was so tedious and error-prone
in the first place. There's even a real scheduling mistake preserved in
that history: a Wednesday entry from the week of 2026-08-10 was tagged
with Tuesday's day-of-week bitmask (4) instead of Wednesday's (8) — a
concrete example of exactly the kind of manual slip this generator exists
to prevent, not a hypothetical.

**First real-world test passed.** The very first Claude-generated `.bpsx`
was opened in bAc's Schedule tab (File → Open, filter switched to
Schedule) and rendered correctly — five colored day blocks in the right
calendar columns at the right times. That resolved the one open unknown
from the first version of this feature: bAc does accept a file it didn't
generate itself, with no complaint.

**Design evolved after that first real test, per direct user feedback —
this is the current, correct design, not the original one:**
- **No template file needed.** The original version required picking an
  existing `.bpsx` to copy `presentationLocator.path` and the opaque
  `scope` field from, and *appended* new entries to that file's full
  history. The user rejected this UX ("it should not be asking for an
  existing file, it should be creating the file") — so `presentationLocator.path`
  and `scope` were initially both hardcoded constants at the top of
  `bpsx_schedule.py` (confirmed identical across all 26 real historical
  entries), and `build_schedule()` creates a **fresh, standalone** file
  from scratch containing only the days you pick — it no longer reads or
  merges with any existing schedule file at all. (The hardcoded path was
  later found to be wrong on a different machine and turned into a
  required `presentation_path` argument instead — see the path-problem
  note further down; `SCOPE` is still hardcoded, since it's an opaque id
  with no folder-derived equivalent.)
- **Day picker, not a fixed Mon–Fri list.** A small dialog shows a
  checkbox per day (from `self.days`, so dates are always right),
  all checked by default, so an unusual week (holiday closure, etc.) can
  exclude a day without editing code.
- **One start/end time, applied to every selected day equally** — not a
  Friday-specific yes/no toggle like the first version had. The user was
  explicit that this should be asked once and shared across all days,
  even though the real historical file showed Friday sometimes running a
  shorter day (540 vs 600 minutes) — that's a deliberate simplification
  the user chose over preserving that historical variation.
- Every week is still its own one-off dated entry (`recurrence: false`),
  matching the real file's actual pattern — see the "real findings" note
  above for why that pattern exists in the first place.

**GUI**: "Generate Schedule (.bpsx)… [one-time setup]" — originally a
bottom-bar button, moved into the Advanced menu (see the button
reorganization note in the next section) since it's a one-time setup
step, not a weekly action. Enabled right after a successful preview
(`app.py`, `generate_schedule()`). Opens a dialog with day checkboxes +
one start/end time pair, then a save dialog; writes the file and tells
the user the exact bAc steps (File → Open → switch filter to Schedule →
Publish).

**Bug found on the very next real-world test, now fixed: missing
`allSchedulePresentations`.** The fresh-from-scratch `build_schedule()`
initially only wrote `schedulePresentationsById`, matching the *first*
version's understanding of the format. Opening that file in bAc crashed
immediately with `openScheduleFromAsset TypeError: Cannot read properties
of undefined (reading 'forEach')`, found by reading bAc's own
`eventLog.txt` (the user provided the path directly). Root cause: the real exported file has a second top-level field
alongside `schedulePresentationsById` — `allSchedulePresentations`, a
flat list of the same entry IDs, same order, that bAc's importer iterates
with `.forEach()`. My first structural inspection of the real file only
printed `data['schedulePresentations']['schedulePresentationsById']` and
never checked whether `schedulePresentations` itself had sibling keys —
an incomplete inspection, not a format ambiguity. Fixed by doing a full
recursive dump of every key at every level (now the standard way to
inspect any new file format encountered here — see the dump technique in
this fix's commit) and confirming all 26 real entries share one identical
key-set with no exceptions. `build_schedule()` now always emits
`allSchedulePresentations` as `list(by_id.keys())`.

**Lesson for next time a file format needs reverse-engineering from a
single real example**: don't stop at "the parts I looked at parse and
look reasonable" — recursively dump every key at every nesting level
before considering the schema understood. A field that's simple, small,
and easy to miss (a flat ID list) is exactly the kind of thing a partial
read skips right past.

**Testing note**: `build_schedule()` was verified for the happy path, the
day-subset case (fewer than 5 days), and both error cases (no days
selected, end time not after start time). The full GUI dialog — including
actually unchecking a day's checkbox and confirming it's excluded from the
output — was driven end-to-end with the file-save dialog monkeypatched,
not just the underlying function tested in isolation (this project has
already been bitten once by "the module works, the GUI wiring doesn't" —
see the silent-hang bug above).

## The second pivot: forever-recurring schedule + weekly `.bpfx` image swap

The user realized (2026-08-20) that regenerating a `.bpsx` schedule every
week is only necessary because the schedule entries were dated/one-off. If
each weekday's entry instead recurs forever, the schedule only needs to be
created **once**, and the only thing that changes week to week is *which
image* each day's `.bpfx` presentation shows — so the actual weekly task
becomes "swap 5 images and hit Publish," no re-scheduling ever again.

**`.bpsx` now generates forever-recurring entries.** Reverse-engineered
from a second real example the user manually configured in bAc and
exported (`autoscheduleforever.bpsx`, one weekday set to recur weekly with
no end date) — not guessed, since a guess here already burned us once (the
missing `allSchedulePresentations` bug above). Generated output now matches
that real file byte-for-byte per entry (name, dateTime, bitmask,
recurrenceStartDate, recurrenceEndDate, recurrence/recurrenceGoesForever
flags — id is naturally the only thing that differs). Two things worth
remembering:
- `recurrence: true` and `recurrenceGoesForever: true` replace the old
  `false`/`false` pair; `recurrenceStartDate` now equals `dateTime` instead
  of the Monday-of-week; there's no more `week_monday` parameter since
  recurring entries aren't anchored to a specific week at all.
- `recurrenceEndDate` is one day after the entry's date, at the *same
  start hour*, with minute/second/millisecond forced to `59:59.999` — this
  held true across all 5 real entries and looks like a required-but-inert
  placeholder bAc's UI still needs even though `recurrenceGoesForever`
  means it's never actually enforced. `_iso()` had to be fixed too — it
  was hardcoding `.000Z` regardless of actual microseconds, which silently
  dropped this exact `.999` and would have been a byte-level mismatch from
  the real file if not caught by the structural diff test.
- The real file's Friday entry had `"interruption": true` while the other
  four had `false` — confirmed with the user this was accidental, not a
  deliberate Friday-specific setting, so the generator keeps `interruption:
  false` for every day (already matched 4/5 real entries; no code change
  needed).

**New module `app/bpfx_update.py` edits an existing `.bpfx` in place** to
point at a freshly rendered PNG, instead of generating anything from
scratch — reverse-engineered from the cafe's real
`Cafe Menu Monday.bpfx` (brightAuthorVersion 1.85.0). The day's menu image
is referenced across three id spaces that must all be kept in sync:
`bsdm.assetMap.<assetId>` (name/path/locator/fileSize/lastModifiedDate),
`bsdm.mediaStates.mediaStatesById.<mediaStateId>` (name +
`contentItem.name`) — **note `assetId` and `mediaStateId` are different
values**, linked only via `mediaState.contentItem.assetId`, a real bug hit
during testing (the first version assumed they were the same key) — and
the `_ev`/`_tr`-suffixed cosmetic names in `bsdm.events` /
`bsdm.transitions.transitionsById`. `update_presentation()` finds the
single `mediaType == "Image"` entry in `assetMap` and the one `mediaState`
whose `contentItem.assetId` matches it; `update_week()` does this for all
five `"Cafe Menu <Day>.bpfx"` files at once, atomically (loads and
validates every day's file — exists, is readable JSON, has the expected
sections and single-image shape — *before* writing any of them, so a
partial week never gets half-applied). Until 2026-09-24 this only checked
that each file *existed*; the shape check ran mid-write, so a malformed
Wednesday file left Monday/Tuesday already rewritten. The shape check now
lives in `_locate_image()`, called by both the upfront pass and
`update_presentation()` itself.

**The path problem, and a real bug it caused (2026-08-28).** Each asset's
original `path` field (`/Users/stbpa/Downloads/files(2)/`) doesn't live in
the shared `Documents/Brightsign/` folder at all, so the new path/locator
has to point somewhere else. The first fix guessed at a fixed remote path
(`/Users/stbpa/Documents/Brightsign/`, matching the then-hardcoded
`PRESENTATION_PATH` in `bpsx_schedule.py`) and had `update_presentation()`
take a separate `local_write_dir` (where this process actually writes the
PNG) and `remote_path` (what gets written into the JSON) — reasoning that
bAc always ran on one specific other Mac reachable only via a shared
mount. That guess broke in practice: bAc showed "Open presentation error
— file not found" for the image, because the app was actually run
somewhere the hardcoded path didn't match. Fixed by dropping the
hardcoded path/parameter entirely — `update_presentation()` now writes
`local_write_dir.resolve()` itself into the `.bpfx`'s path/locator fields,
so wherever the PNG is actually saved is exactly what bAc is told to open,
on whatever machine and account is actually running this. The identical
bug existed in `bpsx_schedule.py`'s `PRESENTATION_PATH` for the schedule's
`presentationLocator.path` (same hardcoded-guess pattern, just not yet
reported since the schedule is only generated once) — `build_schedule()`
now takes `presentation_path` as a required argument instead, and
`generate_schedule()` in `app.py` prompts for the shared folder the same
way `update_presentations()` already did. `SCOPE` (an opaque per-bAc-
installation id, not a filesystem path) is unaffected and still
hardcoded — there's no folder-derived way to guess it, and no evidence
yet that it's actually wrong.

**GUI**: "Update This Week's Presentations…" is the main bottom-bar
button, enabled after a successful preview. Prompts for the shared
Brightsign folder (containing the five `Cafe Menu <Day>.bpfx` files),
renders the current `self.days` to a temp directory, then calls
`bpfx_update.update_week()`. Tells the user to just hit Publish in bAc
afterward — no re-opening or re-scheduling needed, as long as the
schedule is already set up to recur forever.

**Bottom-bar reorganization (2026-08-20)**, per direct user request now
that this button is the actual weekly task: "Plate It Up (Export 5 PNGs)…"
and "Generate Schedule (.bpsx)…" moved out of the bottom bar into a new
**Advanced** menu in the menu bar (both one-off/rare actions now — export
is only needed if you want the raw PNGs, and schedule generation is a
one-time setup). (Plate It Up has since moved back to a main-screen
button — see git history, 2026-09-03 — so only Generate Schedule remains
in Advanced, at `Menu.entryconfig` index 0. All enable/disable state now
goes through `App._set_busy()`; if another Advanced item is ever added
*before* it, update the index there.) The
former "Send to BrightSign →" button was renamed **"Recipe
(Instructions)"** (the Help-menu item was renamed to match), and its
content (`BRIGHTSIGN_STEPS`) was rewritten for the new workflow — the
one-time schedule setup, then "Update This Week's Presentations…", then
Publish — instead of the old per-day Content-tab and Schedule-tab
drag-and-drop steps.

**Verified so far**: `update_presentation()` tested against a *copy* of
the real `Cafe Menu Monday.bpfx` — confirmed the only JSON values that
changed were the ones intended to change (full recursive key-structure
diff against the original passed), and the copied PNG landed correctly in
the write directory with old-name cleanup. `build_schedule()`'s
forever-recurrence output was diffed field-by-field against the real
`autoscheduleforever.bpsx` and matches exactly (aside from the
Friday-interruption outlier, confirmed accidental — see above). **Not yet
verified**: an actual real-world Publish from bAc using a
`.bpfx` this app rewrote — that first real attempt is the true test, same
pattern as everything else in this project's BrightSign integration.

## Known non-goals / intentionally out of scope

- Internet access of any kind — the whole point is offline operation.
  Don't add telemetry, auto-update checks, or font/browser downloads at
  runtime. The one deliberate exception is LAN traffic to the cafe's own
  BrightSign player, only when the user pushes to or browses it.
- Notarization/proper Apple code signing — ad-hoc signing + quarantine
  clearing is the accepted tradeoff for an internal single-cafe tool.
- Generic/reusable BrightSign instructions — the panel is deliberately
  specific to this one player and workflow.

## If you need to change the visual design

The maroon/alt color values, typography, per-day-type font sizes, and row
layout all live in `template.py`'s `DAY_TYPE_SIZING` dict and the inline
CSS in `build_day_html()`. After any visual change, re-render a real test
docx (there's historically been a `test_menu.docx` and/or the user's real
weekly docx used for this) and visually inspect at least one Standard day,
Wednesday (6 rows + sushi), and Friday (4 rows) before considering the
change done — the per-day-type sizing exists precisely because these three
layouts have different constraints.
