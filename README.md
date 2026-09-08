# The Cafe — Menu Sign Generator

Offline macOS app that turns a weekly lunch menu `.docx` into five
3840×600px digital-signage PNGs (Monday–Friday), and pushes them straight
onto a BrightSign-driven display through brightAuthor:connected — no
manual drag-and-drop, no internet connection required.

Built for one specific cafe's workflow (a BrightSign player driving an
86" ultra-wide panel), but the pipeline — docx parsing → HTML/CSS
template → headless-Chromium render → BrightSign schedule/presentation
automation — is a reasonably complete example of turning a manual weekly
chore into a one-click tool.

## What it does

1. **Parses** the week's lunch menu from a `.docx` file — handles a
   Wednesday sushi-only row, Friday's veg/non-veg soup ambiguity, and
   days that simply skip an item (not every day has every line every
   week; a missing item is just left off that day's sign).
2. **Renders** five pixel-exact 3840×600px signs (4x supersampled, Lanczos
   downsampled) matching a fixed maroon digital-signage design, with a
   pre-export check that blocks the export if any text would wrap.
3. **Publishes to BrightSign** two ways:
   - Generates brightAuthor:connected's native schedule file (`.bpsx`)
     from scratch, with each weekday set to recur forever — a one-time
     setup, never repeated.
   - Rewrites each day's existing presentation file (`.bpfx`) in place to
     point at that week's new PNG — the actual weekly task, done with one
     click instead of five manual drag-and-drops in brightAuthor:connected.

Everything runs with **zero network calls** — fonts and the Chromium
rendering engine are bundled inside the packaged `.app`.

## System requirements

**Packaged `.app` (`The Cafe Menu Sign Generator.zip`, from Releases):**
- macOS on **Apple Silicon (arm64)** — M1 or later. The bundled Chromium
  binary and the PyInstaller build are both architecture-specific to
  whatever machine built them; this release was built on an arm64 Mac, so
  it will **not** run on an Intel (x86_64) Mac. Building from source on an
  Intel Mac should still work (see below) — it just needs its own build.
- No minimum macOS version has been formally verified; it was built and
  tested on a current macOS release. If you hit a launch failure on an
  older macOS version, building from source on that machine is the
  fallback.
- No internet connection needed at runtime — fonts and Chromium are
  bundled inside the app.

**Running from source:**
- macOS (Intel or Apple Silicon) — not currently tested on Windows or
  Linux. The GUI (Tkinter), rendering (Playwright/Chromium), and BrightSign
  file handling are all cross-platform libraries in principle, but
  `build_app.sh` packages a macOS `.app` specifically (macOS-only icon
  format, macOS bundle layout for Chromium) — a Windows/Linux build would
  need its own packaging script.
- Python 3.11+
- [brightAuthor:connected](https://www.brightsign.biz/) for the actual
  publish-to-player step (not automated — this app prepares the files
  bAc consumes)

## Setup (run from source)

```
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
playwright install chromium
python3 app/icon_src/make_icon.py   # generates app/AppIcon.icns
cd app
python3 app.py
```

## Download

Prebuilt `.app` releases (Apple Silicon Macs) are available under
[Releases](../../releases) — download the `.zip`, unzip, then right-click
the app → Open (once) to get past Gatekeeper, since it isn't notarized by
Apple.

## Build the standalone offline `.app`

```
./build_app.sh
```

Produces `dist/The Cafe Menu Sign Generator.app` — a double-clickable app
with the Libre Franklin fonts, Chromium, and the BrightSign help
screenshots all bundled inside (~700MB, mostly Chromium). No network
access is used at runtime.

First launch: since the app is only ad-hoc signed (not notarized by
Apple), Gatekeeper will block a plain double-click. Either:
- Right-click the app → Open → Open, once, or
- Run `xattr -cr "dist/The Cafe Menu Sign Generator.app"` once after
  building/copying it.

To distribute to another Mac, zip the `.app` with `ditto` (plain `zip` can
corrupt bundle metadata) and unzip on the other side — it's self-contained:

```
ditto -c -k --sequesterRsrc --keepParent "dist/The Cafe Menu Sign Generator.app" "The Cafe Menu Sign Generator.zip"
```

## Using the app

1. **Pick Today's Special (.docx)…** — choose the weekly menu file.
2. Confirm the **Starting Monday** date (defaults to the upcoming Monday).
3. Pick **House Special** (maroon, default) or **Lighter Fare** (alt) design.
4. **Whip Up a Preview** — review all five days on screen. If any label or
   item text is at risk of wrapping, fix the source document and re-parse.
5. **Update This Week's Presentations…** — the actual weekly task. Check
   off which days should get this week's new image (all 5 by default —
   leave a day unchecked if it hasn't aired yet and shouldn't be
   overwritten early, since there's only one recurring presentation per
   weekday, not a separate "this week"/"next week" slot), then point it
   at the shared brightAuthor:connected folder holding the five
   `Cafe Menu <Day>.bpfx` files. This renders the checked days' PNGs and
   rewrites each presentation to show them. Then in brightAuthor:connected,
   just hit Publish.
6. **Recipe (Instructions)** (or Help menu) — the full step-by-step
   walkthrough, including the one-time schedule setup.

- **Plate It Up (Export PNGs)…** — check off which days to export, then
  saves those PNGs to a folder of your choice without touching any
  presentation, if you just want the images themselves.

Tucked away in the **Advanced** menu (rarely needed day to day):
- **Generate Schedule (.bpsx)… [one-time setup]** — pick which days to
  schedule (all 5 by default), one shared start/end time, and the shared
  Brightsign folder (the same one used by "Update This Week's
  Presentations…"), then save. This only needs to be done **once ever**
  — each day's entry recurs weekly forever. In brightAuthor:connected:
  File → Open, switch the file-type filter to Schedule, open the
  generated file, then Publish.

Output filenames: `The_Cafe_Menu_<Day>_<YYYY-MM-DD>.png`.

## Project layout

- `app/parser.py` — reads the `.docx`, extracts Mon–Fri rows, handles the
  Wednesday sushi line, Friday's veg/non-veg soup ambiguity, and days
  that skip an item entirely.
- `app/template.py` — builds the self-contained HTML/CSS per day (fonts
  embedded as base64 data URIs, no external assets, no logo on the sign
  itself).
- `app/renderer.py` — headless-Chromium screenshot at 4x scale, Lanczos
  downsample to exact 3840×600, plus the pre-export wrap-detection check.
- `app/app.py` — Tkinter GUI (file picker, date, variant, preview, export,
  in-app help). Forces a fixed light color theme regardless of macOS's
  dark/light mode setting.
- `app/fonts/` — bundled Libre Franklin variable font files (roman + italic).
- `app/brightsign_help/` — screenshots shown in the in-app "Recipe
  (Instructions)" panel.
- `app/brightsign_client.py` — talks to a BrightSign player's Local DWS
  REST API directly over the LAN (file listing so far; upload is written
  but not wired to a button — see `context.md` for why it turned out to
  be a dead end on this player's firmware).
- `app/bpsx_schedule.py` — builds a fresh brightAuthor:connected schedule
  (`.bpsx`) file from scratch (day picker + one shared start/end time —
  no existing file needed), with each day set to recur weekly forever.
  Only needs to be generated once, ever.
- `app/bpfx_update.py` — the actual weekly task: rewrites each day's
  existing presentation (`.bpfx`) file in place to show this week's PNG,
  so the schedule never needs to be touched again after the one-time
  setup above.
- `app/icon_src/make_icon.py` — generates `app/AppIcon.icns`, the app's
  Finder/Dock icon. Re-run this if the icon design changes; it's a build
  input, not generated by `build_app.sh` itself.
- `build_app.sh` — packages everything into an offline `.app` with
  PyInstaller, copying the Playwright Chromium binary into
  `Contents/Frameworks/ms-playwright` as a post-build step (PyInstaller's
  auto-codesign can't handle a nested `.app` bundle passed via `--add-data`,
  and `sys._MEIPASS` resolves to `Contents/Frameworks`, not `Resources`).

See [`context.md`](context.md) for the full history, design decisions,
and gotchas behind this project — read that before making non-trivial
changes.

## Re-running the build after code changes

Just re-run `./build_app.sh` — it wipes `build/` and `dist/` each time. If
you change the icon, run `python3 app/icon_src/make_icon.py` first.

---

Built for one cafe's own internal signage workflow — the design spec,
parsing rules, and BrightSign file formats in here are specific to that
setup, not a general-purpose signage tool.
