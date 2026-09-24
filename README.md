# The Cafe — Menu Sign Generator

Offline macOS app that turns a weekly lunch menu `.docx` into five
3840×600px digital-signage PNGs (Monday–Friday), and pushes them straight
onto a BrightSign-driven display — directly over the local network, or
through brightAuthor:connected — no manual drag-and-drop, no internet
connection required.

Built for one specific cafe's workflow (a BrightSign player driving an
86" ultra-wide panel), but the pipeline — docx parsing → HTML/CSS
template → headless-Chromium render → BrightSign schedule/presentation
automation — is a reasonably complete example of turning a manual weekly
chore into a one-click tool.

## What it does

1. **Parses** the week's lunch menu from a `.docx` file — plain lines or
   a Word table — and handles a Wednesday sushi-only row, Friday's
   veg/non-veg soup ambiguity, office-closed days, and days that simply
   skip an item (not every day has every line every week; a missing item
   is just left off that day's sign). Tolerates Word's AutoFormat
   look-alike characters (non-breaking hyphens/spaces, curly dashes) in
   labels.
2. **Renders** five pixel-exact 3840×600px signs (4x supersampled, Lanczos
   downsampled) matching a fixed maroon digital-signage design, with a
   pre-export check that blocks the export if any text would wrap or a
   day's rows wouldn't fit in the sign's height.
3. **Publishes to BrightSign** three ways:
   - **Push to Player** — sends the new PNGs straight to the player over
     its Local DWS API (HTTPS on the local network) and restarts it, no
     brightAuthor:connected Publish needed.
   - Generates brightAuthor:connected's native schedule file (`.bpsx`)
     from scratch, with each weekday set to recur forever — a one-time
     setup, never repeated.
   - Rewrites each day's existing presentation file (`.bpfx`) in place to
     point at that week's new PNG — the actual weekly task, done with one
     click instead of five manual drag-and-drops in brightAuthor:connected.

Nothing uses the internet — fonts and the Chromium rendering engine are
bundled inside the packaged `.app`. The only network traffic is to the
BrightSign player on the local network, when you push to it or browse
its files.

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
- [brightAuthor:connected](https://www.brightsign.biz/) to set up and
  first-publish the presentations; after that, weekly updates can go
  straight to the player with Push to Player (needs the player's Local
  DWS enabled)

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
[Releases](../../releases). Download the `.zip` and unzip it. The app
isn't signed with an Apple Developer ID, so macOS blocks it the first time.
Get past that once, either way:

- **Recommended:** open Terminal and run (adjust the path if you moved it):
  ```
  xattr -cr ~/Downloads/"The Cafe Menu Sign Generator.app"
  ```
- Or double-click the app, dismiss the "Apple could not verify…" message,
  then go to **System Settings → Privacy & Security** and click
  **Open Anyway**.

If macOS says the app **"is damaged and can't be opened"**, that's a
release from before this was fixed (v0.2.0's first upload and earlier) —
use the Terminal command above; it works for those too.

## Build the standalone offline `.app`

```
./build_app.sh
```

Produces `dist/The Cafe Menu Sign Generator.app` — a double-clickable app
with the Libre Franklin fonts, Chromium, and the BrightSign help
screenshots all bundled inside (~700MB, mostly Chromium). No internet
access is used at runtime (only the local BrightSign player, on request).

The build re-signs the app after bundling Chromium and refuses to finish
if the signature doesn't verify (see `context.md`, "Packaging quirks").
It's only ad-hoc signed (not notarized by Apple), so on any other Mac
Gatekeeper blocks the first launch — see **Download** above for the
two ways past it. The build machine itself is cleared automatically.

To distribute to another Mac, zip the `.app` with `ditto` (plain `zip` can
corrupt bundle metadata) and unzip on the other side — it's self-contained:

```
ditto -c -k --sequesterRsrc --keepParent "dist/The Cafe Menu Sign Generator.app" "The Cafe Menu Sign Generator.zip"
```

## Using the app

### Every week

1. **Pick Today's Special (.docx)…** — choose the weekly menu file.
2. Confirm the **Starting Monday** date (defaults to the upcoming Monday).
3. Pick **House Special** (maroon, default) or **Lighter Fare** (alt) design.
4. **Whip Up a Preview** — review all five days on screen. If any label or
   item text is at risk of wrapping, fix the source document and re-parse.
   A failed re-parse leaves the previous preview (and what the action
   buttons act on) in place; action buttons are greyed out while a job runs.
5. **Push to Player…** — with the laptop plugged into the player's
   network, check off which days should get this week's new image (all 5
   by default — leave a day unchecked if it hasn't aired yet and
   shouldn't be overwritten early, since there's only one recurring
   presentation per weekday, not a separate "this week"/"next week"
   slot). The app sends those signs straight to the BrightSign player,
   restarts it (~30 seconds blank), and shows a screenshot of the sign.
   - The player's IP is remembered from the first time you enter it; its
     password is remembered in the Mac's login Keychain after the first
     push that works — never in the repo or the app's files. **Clear IP**
     / **Clear password** forget them.
   - The confirmation warns (defaulting to **No**) if any sign is dated for
     a different week than the one the player will show it in — e.g. the
     Starting Monday left on its default (the *upcoming* Monday) while
     pushing this week's menu mid-week.
   - Unchanged days are skipped (no restart if nothing changed). Every
     checked day is validated before anything is sent, and a backup of
     the player's previous content list is saved to
     `~/.cafe_menu_player_backups/`.

- **Plate It Up (Export PNGs)…** — check off which days to export, then
  saves those PNGs to a folder of your choice without touching the
  player or any presentation, if you just want the images themselves.
- **Recipe (Instructions)** (or Help menu) — the full step-by-step
  walkthrough.

### brightAuthor:connected — one-time setup, and the old way

Push to Player swaps the images inside presentations that are already
published on the player, so brightAuthor:connected is still needed once:

- **One-time setup** (already done for the cafe's player; only again if
  the player is replaced or reset):
  - Publish the five `Cafe Menu <Day>.bpfx` presentations from
    brightAuthor:connected once.
  - **Advanced → Generate Schedule (.bpsx)… [one-time setup]** — pick
    which days to schedule (all 5 by default), one shared start/end time,
    and the shared Brightsign folder holding the `.bpfx` files, then save.
    Each day's entry recurs weekly forever. In brightAuthor:connected:
    File → Open, switch the file-type filter to Schedule, open the
    generated file, then Publish.
- **Update This Week's Presentations…** — the old weekly way. Check off
  the days, point it at the shared folder holding the five
  `Cafe Menu <Day>.bpfx` files, and it rewrites each presentation to show
  the new signs (every checked day's `.bpfx` is validated first — if any
  is missing or malformed, nothing is written). Then Publish from
  brightAuthor:connected.
- **Before any Publish from brightAuthor:connected**, run Update This
  Week's Presentations for the current week first. A Publish sends
  whatever images the `.bpfx` files point at; if the week only went out
  by Push to Player, they still point at an older week, and the Publish
  would put those back on the sign.

Output filenames: `The_Cafe_Menu_<Day>_<YYYY-MM-DD>.png`.

## Project layout

- `app/parser.py` — reads the `.docx` (paragraphs and tables, in document
  order), extracts Mon–Fri rows, handles the Wednesday sushi line,
  Friday's veg/non-veg soup ambiguity, office-closed days, and days that
  skip an item entirely.
- `app/template.py` — builds the self-contained HTML/CSS per day (fonts
  embedded as base64 data URIs, no external assets, no logo on the sign
  itself).
- `app/renderer.py` — headless-Chromium screenshot at 4x scale, Lanczos
  downsample to exact 3840×600, plus the pre-export layout check (text
  wrapping and rows overflowing the sign's height).
- `app/app.py` — Tkinter GUI (file picker, date, variant, preview, export,
  in-app help). Follows macOS's Light/Dark appearance with its own
  light and dark palettes, switching live if the setting changes.
- `app/fonts/` — bundled Libre Franklin variable font files (roman + italic).
- `app/brightsign_help/` — screenshots shown in the in-app "Recipe
  (Instructions)" panel.
- `app/brightsign_client.py` — talks to a BrightSign player's Local DWS
  REST API over the LAN (HTTPS, digest auth): list/read/upload files,
  reboot, screenshot.
- `app/player_push.py` — "Push to Player": uploads new PNGs into the
  player's content pool and repoints each day's image in the published
  `local-sync.json`, then reboots. See `context.md` for how and why.
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
  `Contents/Resources/ms-playwright` as a post-build step (PyInstaller's
  auto-codesign can't handle a nested `.app` bundle passed via `--add-data`),
  then re-signs the app and verifies the signature.

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
