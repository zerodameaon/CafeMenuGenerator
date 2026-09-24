"""The Cafe — Digital Menu Sign Generator. Offline Tkinter desktop app."""
from __future__ import annotations

import io
import os
import sys
import tempfile
import threading
import time
import traceback
from datetime import date, datetime, timedelta
from pathlib import Path
from tkinter import (
    Tk, Frame, Label, Button, Entry, StringVar, BooleanVar, filedialog, messagebox, ttk, Canvas, NW,
    Menu, Toplevel, Text, Scrollbar, RIGHT, Y, BOTH, WORD,
)

from PIL import Image, ImageTk

if getattr(sys, "frozen", False):
    # Running as a PyInstaller-built .app: point Playwright at the Chromium
    # bundled inside the app (Contents/Resources/ms-playwright — see
    # build_app.sh for why it's there and not in Frameworks) instead of
    # downloading one at runtime, which would need the internet.
    # sys.executable is Contents/MacOS/<name>.
    browsers = Path(sys.executable).resolve().parents[1] / "Resources" / "ms-playwright"
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(browsers)
    # A copy downloaded from GitHub carries macOS's quarantine flag on every
    # file. Once the user has approved the app itself (Open Anyway), the
    # bundled Chromium — only ad-hoc signed by Playwright — can still be
    # refused on first launch while flagged. The flag isn't part of the code
    # signature, so clearing it on our own files is safe. Best effort: it
    # can't be done if macOS is running the app from a read-only
    # "translocated" copy, which is why the README's one-line xattr command
    # stays the recommended first-launch step.
    try:
        import subprocess
        subprocess.run(["/usr/bin/xattr", "-dr", "com.apple.quarantine", str(browsers)],
                       capture_output=True, timeout=30)
    except Exception:
        pass
    # PyInstaller's own data files (fonts, help screenshots) are found via
    # sys._MEIPASS, which is Contents/Frameworks in a --windowed onedir .app.
    app_dir = Path(sys._MEIPASS)
else:
    app_dir = Path(__file__).parent

sys.path.insert(0, str(app_dir))

BRIGHTSIGN_HELP_DIR = app_dir / "brightsign_help"

from parser import parse_menu_docx, MenuParseError, DayMenu, format_month_day
from renderer import render_days, render_preview_png_bytes, RenderValidationError
import brightsign_client
import bpsx_schedule
import bpfx_update
import credentials
import player_push

PREVIEW_W = 760

# Light and dark palettes, matched to macOS's appearance setting at launch
# and switched live if it changes while the app is open (App._watch_appearance).
# Tkinter's native (Aqua) widgets don't reliably re-theme themselves —
# labels/status text once rendered dark-on-dark — so the app never relies on
# them: a 'clam' ttk theme with explicit colors, plus explicit colors on every
# plain tk widget, drawn from whichever palette is active.
#
# Palette values are read when each widget is created, so always use these
# names (BG, FG, …), never literal colors. The live switch works by finding
# every widget option still set to an old palette color and swapping in the
# new one, keyed by role: background-type options only ever hold the
# *_BG/ACCENT colors and foreground-type options only the *_FG colors. So
# within one palette, the background colors must all differ from each other
# and so must the foreground colors (light BG and ACCENT_FG may match — one
# is only ever a background, the other only ever a foreground).
LIGHT_PALETTE = dict(
    BG="#faf7f2", PANEL_BG="#f1ece2", ACCENT="#6b2f20",
    FG="#2b1d16", MUTED_FG="#6b5c50", GOOD_FG="#2f7a3d", BAD_FG="#b3392c", ACCENT_FG="#faf7f2",
    # ttk-only (set through styles, never on plain widgets)
    ACCENT_ACTIVE="#82412e", DISABLED_BG="#d9d1c7", DISABLED_FG="#6e6156",
    SCROLL_THUMB="#ddd4c8",
)
DARK_PALETTE = dict(
    BG="#1e1814", PANEL_BG="#2a221d", ACCENT="#8e3f2b",
    FG="#f2ebe3", MUTED_FG="#b3a597", GOOD_FG="#7ccf8c", BAD_FG="#ff8a7a", ACCENT_FG="#fbf6ef",
    ACCENT_ACTIVE="#a24a33", DISABLED_BG="#3b322c", DISABLED_FG="#8c8076",
    SCROLL_THUMB="#4a3f37",
)
BG_ROLE = ("BG", "PANEL_BG", "ACCENT")
FG_ROLE = ("FG", "MUTED_FG", "GOOD_FG", "BAD_FG", "ACCENT_FG")
BG_OPTIONS = ("background", "activebackground", "highlightbackground")
FG_OPTIONS = ("foreground", "activeforeground", "insertbackground")

BG = PANEL_BG = FG = MUTED_FG = GOOD_FG = BAD_FG = ACCENT = ACCENT_FG = ""  # set by _use_palette
_palette: dict = {}


def _use_palette(palette: dict) -> None:
    """Makes `palette` the one new widgets are created with."""
    global _palette
    _palette = palette
    globals().update({k: palette[k] for k in BG_ROLE + FG_ROLE})


def _system_is_dark(root: Tk) -> bool:
    try:
        return bool(int(root.tk.call("::tk::unsupported::MacWindowStyle", "isdark", root)))
    except Exception:
        return False  # not macOS, or a Tk too old to say — stay light


_use_palette(LIGHT_PALETTE)

INSTRUCTIONS_TEXT = """HOW TO COOK UP MENU SIGNS, STEP BY STEP

1. Pick Today's Special (.docx)…
   Choose the weekly lunch menu Word document (arrives Monday-ish each
   week). The document should have a "Monday" / "Tuesday" / etc. line
   before each day's items, with lines like:
       Breakfast: <item>
       Vegetarian Soup Du Jour: <item>
       Non-Vegetarian Soup Du Jour: <item>
       Main Entrée: <item>
       Veggie Entrée: <item>
   Wednesday can additionally have a standalone "Assorted Sushi" line.
   Not every day needs every line — a day can skip a soup, an entrée,
   etc., and that row is simply left off that day's sign. Friday usually
   has only ONE soup line (veg OR non-veg, not both, though it can also
   have none) — whichever is present is used and labeled to match; having
   BOTH on Friday is still treated as an error (that's ambiguous, not
   just sparse).
   Each day's heading should appear exactly once. The menu can be plain
   lines or laid out in a Word table — both are read. A day whose only
   text is a note like "Office Closed" gets a CLOSED sign; a day that has
   real menu lines is never treated as closed, even if it also has a
   note like "Cafe closed early at 1pm".

2. Starting Monday
   Confirm the date of that week's Monday (YYYY-MM-DD). Tuesday–Friday
   are set automatically to the following four days.

3. Flavor (Design variant)
   "House Special" is the maroon design used week-to-week. "Lighter
   Fare" is the inverted light version — only switch if you specifically
   need it.

4. Whip Up a Preview
   Reads the document and renders all five days on screen at reduced
   size so you can check the content and layout before generating the
   final files. Parsing only fails if a day ends up with nothing
   recognized at all (likely a formatting problem, not an intentionally
   sparse day), if Friday lists both soup lines at once, or if a day's
   heading appears twice — you'll get an error describing exactly what's
   wrong. If a re-parse fails, the previous preview (and what the export
   buttons act on) stays as it was. The buttons are greyed out while a
   preview, export, or update is cooking.

5. Push to Player…  (the weekly step)
   Plug in the orange ethernet cable, then click "Push to Player…".
   Check off which days should get this week's new image. Days whose
   new sign would replace one that hasn't aired yet start unchecked —
   e.g. push next week's menu on a Thursday and Thursday + Friday start
   unchecked, so this week's signs stay up. Push those days again once
   this week's have aired (after 4 pm, or over the weekend). The player's IP and password are
   filled in for you after the first push that works: the IP is
   remembered by the app, the password in this Mac's Keychain. "Clear
   IP" / "Clear password" forget them. Confirm, and the app sends the
   signs straight to the BrightSign player and restarts it — the sign
   goes blank for about 30 seconds — then shows a screenshot of what
   it's displaying. Days whose image hasn't changed are skipped, and if
   nothing changed the player isn't restarted at all. That's it — no
   brightAuthor:connected needed week to week.

   Double-check the Starting Monday date first — it defaults to the
   *upcoming* Monday, so pushing this week's menu mid-week needs it set
   back to this week. If any sign is dated for a different week than the
   one the player will show it in (e.g. a Thursday sign dated October 1
   pushed on Thursday September 24), the confirmation turns into a
   warning listing them, with "No" as the default.

   If any label or item text is too long and would wrap to a second
   line on the sign, or a day has so many rows that the bottom would be
   cut off, this gets sent back to the kitchen (blocked) with an error
   telling you which day and what's wrong — fix the source document and
   re-parse rather than shipping a half-baked layout. Nothing is sent to
   the player unless every checked day is ready to go, so you never end
   up with a half-updated week.

"Plate It Up (Export PNGs)…" lets you check off which days to export,
   then saves those PNGs to a folder of your choice, without touching
   the player or any presentation — useful if you just want the images.

────────────────────────────────────────────────────────────────
BRIGHTAUTHOR:CONNECTED — one-time setup, and the old way
────────────────────────────────────────────────────────────────

One-time setup (already done for the cafe's player — only needed again
if the player is replaced or reset):
   • The five "Cafe Menu <Day>.bpfx" presentations must be Published
     from brightAuthor:connected once. Push to Player swaps the images
     inside those published presentations, so they have to be on the
     player first.
   • Advanced → "Generate Schedule (.bpsx)… [one-time setup]" makes the
     schedule that shows each weekday's presentation. Every entry
     recurs forever, so this never needs running again. Open the saved
     file in brightAuthor:connected (File → Open, switch the file-type
     filter to Schedule), then Publish.

"Update This Week's Presentations…" — the old weekly way, before Push
   to Player. Check off the days, point it at the shared Brightsign
   folder (the one with the five "Cafe Menu <Day>.bpfx" files), and it
   rewrites each presentation to show the new signs. Then Publish from
   brightAuthor:connected.

   ⚠ Whenever you Publish from brightAuthor:connected for any reason,
   run "Update This Week's Presentations…" for the current week first.
   A Publish sends whatever images the .bpfx files point at — if the
   week's menu only went out by Push to Player, the .bpfx files still
   point at an older week, and a Publish would put those back on the
   sign.

The app never uses the internet — fonts and the rendering engine are
bundled inside it. The only network traffic is to the BrightSign player
on the local network, and only when you push to it or browse its files.
"""


def show_instructions(root: Tk):
    win = Toplevel(root, bg=BG)
    win.title("Chef's Instructions")
    win.geometry("620x560")

    text_frame = Frame(win, bg=BG)
    text_frame.pack(fill=BOTH, expand=True, padx=12, pady=12)
    scrollbar = Scrollbar(text_frame)
    scrollbar.pack(side=RIGHT, fill=Y)
    text = Text(
        text_frame, wrap=WORD, yscrollcommand=scrollbar.set, padx=8, pady=8,
        bg=PANEL_BG, fg=FG, insertbackground=FG, relief="flat",
    )
    text.insert("1.0", INSTRUCTIONS_TEXT)
    text.config(state="disabled")
    text.pack(fill=BOTH, expand=True)
    scrollbar.config(command=text.yview)

    Button(win, text="Close", command=win.destroy, bg=ACCENT, fg=ACCENT_FG,
           activebackground=ACCENT, activeforeground=ACCENT_FG, relief="flat").pack(pady=(0, 12))


BRIGHTSIGN_IMG_W = 640

# Each step: heading, body text, and an optional screenshot filename from
# brightsign_help/. Mirrors the walkthrough used to publish this cafe's
# BrightSign player, so it stays accurate to the real steps rather than a
# generic BrightSign tutorial. Updated for the "forever-recurring schedule +
# weekly presentation swap" method — the old drag-and-drop-every-week
# process (dragging PNGs into the Content tab, dragging presentations onto
# the Schedule calendar) is gone; the app does both of those now.
BRIGHTSIGN_STEPS = [
    # (heading, body, screenshot) — or (heading, None, None) for a section title.
    ("Every week", None, None),
    (
        "1. Get the ingredients ready",
        'Open "The Cafe Menu Sign Generator", pick this week\'s .docx, and '
        'Whip Up a Preview. Check every day looks right (see Chef\'s '
        "Instructions if you haven't yet).",
        None,
    ),
    (
        "2. Plug in",
        "Plug in the orange ethernet cable at James's desk — that's how the "
        "laptop reaches the player.",
        None,
    ),
    (
        "3. Push to Player — order up",
        'Click "Push to Player…" and check off which days should get this '
        "week's new image. The player's IP and password fill themselves in "
        "after the first push that works. Click Push and confirm: the sign "
        "goes blank for about 30 seconds while the player restarts, then "
        "the app shows a screenshot of what's on screen. Done.\n\n"
        "There's only one Friday presentation, shared by every week (the "
        "schedule can't tell \"this Friday\" from \"next Friday\"). If next "
        "week's menu shows up before this week's Friday has aired, the app "
        "starts Friday unchecked for you, so this week's Friday stays up. "
        "Push next week's Friday once this week's has actually played "
        "(after 4 pm Friday, or over the weekend).",
        None,
    ),
    ("brightAuthor:connected — one-time setup, and the old way", None, None),
    (
        "One-time setup (already done — only if the player is replaced or reset)",
        "Push to Player swaps the images inside the presentations already "
        "on the player, so those need to be published once first:\n\n"
        '• Publish the five "Cafe Menu <Day>.bpfx" presentations from '
        "brightAuthor:connected (see the Publish step below).\n"
        '• From the Advanced menu, "Generate Schedule (.bpsx)… [one-time '
        'setup]" (after a preview). Pick the days, one shared start/end '
        'time, and the shared Brightsign folder (the one with the five '
        '"Cafe Menu <Day>.bpfx" files in it), then save. In '
        "brightAuthor:connected: File → Open, switch the file-type filter "
        "to Schedule, open that file, then Publish. Each weekday's entry "
        "recurs every week, forever.",
        "03_schedule_empty.png",
    ),
    (
        "Before any Publish: update the presentations",
        'Click "Update This Week\'s Presentations…", check off the days, and '
        "point it at the shared Brightsign folder. This rewrites each "
        "day's presentation to show this week's signs.\n\n"
        "Always do this before publishing from brightAuthor:connected, for "
        "any reason — a Publish sends whatever images the presentations "
        "point at, and if this week only went out by Push to Player, they "
        "still point at an older week.",
        None,
    ),
    (
        "Open brightAuthor:connected",
        "On the MacBook Air, open brightAuthor:connected (the purple \"bA "
        "connected\" icon).",
        "01_open_baconnected.png",
    ),
    (
        "Publish",
        "With the orange ethernet cable plugged in: in the Destination "
        "panel, click the refresh icon above Networked Players, then check "
        'the box next to the player named "Cafe Menu-…" (it\'s the only one '
        "on the list). Click Publish (top right).",
        "05_publish.png",
    ),
]


def show_brightsign_instructions(root: Tk):
    win = Toplevel(root, bg=BG)
    win.title("Recipe (Instructions)")
    win.geometry("760x760")

    header = Label(
        win,
        text="Getting this week's signs from the kitchen to the screen",
        bg=BG, fg=FG, font=("", 14, "bold"), justify="left", wraplength=720,
    )
    header.pack(anchor="w", padx=16, pady=(14, 4))

    outer = Frame(win, bg=BG)
    outer.pack(fill=BOTH, expand=True, padx=12, pady=(0, 8))
    canvas = Canvas(outer, bg=BG, highlightthickness=0)
    scrollbar = Scrollbar(outer, orient="vertical", command=canvas.yview)
    content = Frame(canvas, bg=BG)
    content.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.create_window((0, 0), window=content, anchor=NW)
    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.pack(side="left", fill=BOTH, expand=True)
    scrollbar.pack(side="right", fill=Y)

    win._images = []  # keep PhotoImage refs alive for the life of the window

    for heading, body, img_name in BRIGHTSIGN_STEPS:
        if body is None:
            Label(
                content, text=heading, bg=BG, fg=MUTED_FG, font=("", 16, "bold"),
                anchor="w", justify="left", wraplength=700,
            ).pack(fill="x", padx=8, pady=(26, 0))
            Frame(content, bg=ACCENT, height=2).pack(fill="x", padx=8, pady=(4, 0))
            continue
        Label(
            content, text=heading, bg=BG, fg=FG, font=("", 13, "bold"),
            anchor="w", justify="left", wraplength=700,
        ).pack(fill="x", padx=8, pady=(16, 2))
        Label(
            content, text=body, bg=BG, fg=FG, anchor="w", justify="left", wraplength=700,
        ).pack(fill="x", padx=8, pady=(0, 6))

        if img_name:
            img_path = BRIGHTSIGN_HELP_DIR / img_name
            if img_path.exists():
                img = Image.open(img_path)
                scale = BRIGHTSIGN_IMG_W / img.width
                thumb = img.resize((BRIGHTSIGN_IMG_W, int(img.height * scale)), Image.LANCZOS)
                tk_img = ImageTk.PhotoImage(thumb)
                win._images.append(tk_img)
                Label(content, image=tk_img, bg=BG, relief="solid", borderwidth=1).pack(
                    padx=8, pady=(0, 4)
                )

    Button(win, text="Close", command=win.destroy, bg=ACCENT, fg=ACCENT_FG,
           activebackground=ACCENT, activeforeground=ACCENT_FG, relief="flat").pack(pady=(0, 12))


PLAYER_CONFIG_PATH = Path.home() / ".cafe_menu_brightsign_player.json"


def _load_player_config() -> dict:
    if PLAYER_CONFIG_PATH.exists():
        try:
            import json
            return json.loads(PLAYER_CONFIG_PATH.read_text())
        except Exception:
            return {}
    return {}


def _save_player_config(**fields: str) -> None:
    """Merges `fields` (any of ip, port, username, storage) into the saved
    config, keeping whatever else is already there. Deliberately never saves
    the password — this file isn't meant to be a credential store. IP, port,
    username, and storage are low-stakes convenience only."""
    import json
    cfg = _load_player_config()
    cfg.update(fields)
    PLAYER_CONFIG_PATH.write_text(json.dumps(cfg))


def show_player_browser(root: Tk):
    """Read-only file browser against a BrightSign player's Local DWS —
    a troubleshooting aid for "Push to Player". This panel only ever does
    GET requests; nothing here can change what's on the player or on screen.
    """
    cfg = _load_player_config()

    win = Toplevel(root, bg=BG)
    win.title("Browse Player Files (read-only)")
    win.geometry("700x560")

    Label(
        win,
        text="Look around the player's storage (for troubleshooting). This only "
             "reads — nothing here can change what's showing on the screen.",
        bg=BG, fg=MUTED_FG, wraplength=660, justify="left",
    ).pack(anchor="w", padx=16, pady=(14, 8))

    form = Frame(win, bg=BG)
    form.pack(fill="x", padx=16)

    Label(form, text="Player IP:", bg=BG, fg=FG).grid(row=0, column=0, sticky="w", pady=3)
    ip_var = StringVar(value=cfg.get("ip", ""))
    Entry(form, textvariable=ip_var, width=18, bg=PANEL_BG, fg=FG, insertbackground=FG, relief="flat").grid(
        row=0, column=1, sticky="w", padx=(6, 16)
    )

    Label(form, text="Port:", bg=BG, fg=FG).grid(row=0, column=2, sticky="w", pady=3)
    port_var = StringVar(value=cfg.get("port", str(brightsign_client.DEFAULT_PORT)))
    Entry(form, textvariable=port_var, width=8, bg=PANEL_BG, fg=FG, insertbackground=FG, relief="flat").grid(
        row=0, column=3, sticky="w", padx=(6, 16)
    )
    Label(form, text="(443 = HTTPS, which the cafe's player uses; 8080 is NOT the file API)",
          bg=BG, fg=MUTED_FG).grid(row=0, column=4, columnspan=2, sticky="w")

    Label(form, text="Username:", bg=BG, fg=FG).grid(row=1, column=0, sticky="w", pady=3)
    user_var = StringVar(value=cfg.get("username", "admin"))
    Entry(form, textvariable=user_var, width=12, bg=PANEL_BG, fg=FG, insertbackground=FG, relief="flat").grid(
        row=1, column=1, sticky="w", padx=(6, 16)
    )

    Label(form, text="Password:", bg=BG, fg=FG).grid(row=1, column=2, sticky="w", pady=3)
    pass_var = StringVar(value=credentials.load(cfg.get("ip", ""), cfg.get("username", "admin")))
    Entry(form, textvariable=pass_var, width=18, bg=PANEL_BG, fg=FG, insertbackground=FG, relief="flat", show="•").grid(
        row=1, column=3, sticky="w", padx=(6, 16)
    )
    Label(form, text="(remembered in this Mac's Keychain once it works)",
          bg=BG, fg=MUTED_FG).grid(row=1, column=4, columnspan=2, sticky="w")

    Label(form, text="Storage:", bg=BG, fg=FG).grid(row=2, column=0, sticky="w", pady=3)
    storage_var = StringVar(value=cfg.get("storage", "sd"))
    Entry(form, textvariable=storage_var, width=8, bg=PANEL_BG, fg=FG, insertbackground=FG, relief="flat").grid(
        row=2, column=1, sticky="w", padx=(6, 16)
    )

    Label(form, text="Path:", bg=BG, fg=FG).grid(row=2, column=2, sticky="w", pady=3)
    path_var = StringVar(value="")
    Entry(form, textvariable=path_var, width=30, bg=PANEL_BG, fg=FG, insertbackground=FG, relief="flat").grid(
        row=2, column=3, sticky="w", padx=(6, 0)
    )

    status_var = StringVar(value="")
    status_label = Label(win, textvariable=status_var, bg=BG, fg=MUTED_FG, anchor="w")
    status_label.pack(fill="x", padx=16, pady=(8, 0))

    text_frame = Frame(win, bg=BG)
    text_frame.pack(fill=BOTH, expand=True, padx=16, pady=(4, 8))
    scrollbar = Scrollbar(text_frame)
    scrollbar.pack(side=RIGHT, fill=Y)
    results = Text(text_frame, wrap=WORD, yscrollcommand=scrollbar.set, bg=PANEL_BG, fg=FG, relief="flat")
    results.pack(fill=BOTH, expand=True)
    scrollbar.config(command=results.yview)

    def do_list():
        ip, port_str, username, password, storage, path = (
            ip_var.get().strip(), port_var.get().strip(), user_var.get().strip(), pass_var.get(),
            storage_var.get().strip() or "sd", path_var.get().strip(),
        )
        if not ip or not username:
            messagebox.showwarning("Missing info", "Player IP and username are required.", parent=win)
            return
        try:
            port = int(port_str) if port_str else brightsign_client.DEFAULT_PORT
        except ValueError:
            messagebox.showerror("Bad port", "Port must be a number (e.g. 443).", parent=win)
            return
        status_var.set(f"Listing {storage}/{path or '(root)'} on port {port} …")
        win.update_idletasks()

        def worker():
            # Everything below is wrapped in one broad try/except — not just
            # for BrightSignError — so that if a firmware update ever changes
            # the response shape, the formatting code can't raise uncaught,
            # silently kill this thread, and leave the status stuck forever
            # on "Listing..." (which happened once, before the real shape was
            # known). Any failure shows the raw response instead.
            try:
                player = brightsign_client.Player(ip, port, username, password, storage=storage)
                files = player.list_files(path)
                _save_player_config(ip=ip, port=port_str, username=username, storage=storage)
                credentials.save(ip, username, password)
                lines = []
                # "._name" entries are macOS resource-fork litter on the SD card.
                files = [f for f in files if not f.get("name", "").startswith("._")]
                for f in sorted(files, key=lambda x: (x.get("type") != "dir", x.get("name", ""))):
                    kind = "DIR " if f.get("type") == "dir" else f.get("mime", "file")
                    size = "" if f.get("type") == "dir" else f.get("stat", {}).get("size", "")
                    lines.append(f"{kind:>24}  {size!s:>10}  {f.get('name', '')}")
                result_text = "\n".join(lines) if lines else "(empty)"
                status_text = f"{len(files)} item(s) at {storage}/{path or '(root)'}"
            except brightsign_client.BrightSignError as e:
                # Bind the message now — Python unbinds `e` when this except
                # block exits, so a lambda that referenced `e` directly would
                # raise NameError when Tk runs it later.
                msg = f"Failed: {e}"
                win.after(0, lambda: status_var.set(msg))
                return
            except Exception as e:
                # Unexpected shape from the real player — show it raw rather
                # than hang, so the actual response can be inspected.
                raw = brightsign_client.last_raw_response.get("text", "(no raw response captured)")
                result_text = f"Unexpected response shape ({e!r}).\n\nRaw response from player:\n{raw}"
                status_text = "Got a response, but couldn't parse it as expected — see below."
                win.after(0, lambda: (results.delete("1.0", "end"), results.insert("1.0", result_text)))
                win.after(0, lambda: status_var.set(status_text))
                return

            def show():
                results.delete("1.0", "end")
                results.insert("1.0", result_text)
                status_var.set(status_text)

            win.after(0, show)

        threading.Thread(target=worker, daemon=True).start()

    ttk.Button(form, text="List", command=do_list).grid(row=2, column=4, padx=(10, 0))

    Button(win, text="Close", command=win.destroy, bg=ACCENT, fg=ACCENT_FG,
           activebackground=ACCENT, activeforeground=ACCENT_FG, relief="flat").pack(pady=(0, 12))


def _next_monday(today: date) -> date:
    days_ahead = (7 - today.weekday()) % 7
    days_ahead = days_ahead or 7
    return today + timedelta(days=days_ahead) if today.weekday() != 0 else today


def _mismatch_line(day: str, sign: date, shown: date, today: date) -> str:
    return (f"• {day}'s sign says {format_month_day(sign)}, but the player will show it "
            f"{'today' if shown == today else 'next'} on {format_month_day(shown)}.")


def _recolor_tree(widget, old: dict, new: dict) -> None:
    """Swaps every palette color set on `widget` and its descendants (open
    dialogs included) from palette `old` to palette `new`, by role — see the
    note above LIGHT_PALETTE."""
    bg_map = {old[k].lower(): new[k] for k in BG_ROLE}
    fg_map = {old[k].lower(): new[k] for k in FG_ROLE}
    for options, mapping in ((BG_OPTIONS, bg_map), (FG_OPTIONS, fg_map)):
        for opt in options:
            try:
                value = str(widget.cget(opt)).lower()
            except Exception:
                continue  # ttk widgets and some natives don't have this option
            if value in mapping:
                try:
                    widget.configure(**{opt: mapping[value]})
                except Exception:
                    pass
    for child in widget.winfo_children():
        _recolor_tree(child, old, new)


class App:
    def __init__(self, root: Tk):
        self.root = root
        root.title("The Cafe — Menu Sign Generator")
        root.geometry("900x700")

        self._dark = _system_is_dark(root)
        _use_palette(DARK_PALETTE if self._dark else LIGHT_PALETTE)
        root.configure(bg=BG)
        self._setup_style()

        self.docx_path: str | None = None
        self.start_monday: date = _next_monday(date.today()) if date.today().weekday() != 0 else date.today()
        # Only ever set to a parse whose preview rendered successfully, so the
        # export/update buttons always act on what's actually shown on screen.
        self.days: list[DayMenu] | None = None
        self.variant = StringVar(value="main")
        self._busy = False

        self._build_menu()
        self._build_ui()
        self.root.after(2000, self._watch_appearance)

    def _setup_style(self):
        # 'clam' is a theme ttk fully draws itself (unlike 'aqua'), so our
        # explicit colors actually take effect instead of being overridden
        # by whatever the OS's light/dark appearance would otherwise force.
        # Safe to call again: re-running it is how the live light/dark
        # switch re-themes every ttk widget at once.
        pal = _palette
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("TFrame", background=BG)
        style.configure("TLabel", background=BG, foreground=FG)
        style.configure("TButton", background=ACCENT, foreground=ACCENT_FG, padding=6, relief="flat",
                        bordercolor=ACCENT, lightcolor=ACCENT, darkcolor=ACCENT)
        style.map("TButton",
                  background=[("disabled", pal["DISABLED_BG"]), ("active", pal["ACCENT_ACTIVE"])],
                  foreground=[("disabled", pal["DISABLED_FG"])],
                  bordercolor=[("disabled", pal["DISABLED_BG"])],
                  lightcolor=[("disabled", pal["DISABLED_BG"])],
                  darkcolor=[("disabled", pal["DISABLED_BG"])])
        for check_style in ("TRadiobutton", "TCheckbutton"):
            style.configure(check_style, background=BG, foreground=FG,
                            indicatorbackground=PANEL_BG, indicatorforeground=FG, upperbordercolor=MUTED_FG,
                            lowerbordercolor=MUTED_FG)
            style.map(check_style, background=[("active", BG)],
                      indicatorbackground=[("pressed", PANEL_BG), ("selected", PANEL_BG)])
        style.configure("TScrollbar", background=pal["SCROLL_THUMB"], troughcolor=BG, bordercolor=BG,
                        arrowcolor=MUTED_FG, lightcolor=pal["SCROLL_THUMB"], darkcolor=pal["SCROLL_THUMB"])

    def _watch_appearance(self):
        """Polls macOS's appearance and re-themes the whole app (every open
        window) when it flips between Light and Dark."""
        dark = _system_is_dark(self.root)
        if dark != self._dark:
            self._dark = dark
            old = _palette
            _use_palette(DARK_PALETTE if dark else LIGHT_PALETTE)
            self._setup_style()
            _recolor_tree(self.root, old, _palette)
        self.root.after(2000, self._watch_appearance)

    def _build_menu(self):
        menubar = Menu(self.root)

        advanced_menu = Menu(menubar, tearoff=False)
        advanced_menu.add_command(
            label="Generate Schedule (.bpsx)… [one-time setup]", command=self.generate_schedule, state="disabled"
        )
        menubar.add_cascade(label="Advanced", menu=advanced_menu)
        self.advanced_menu = advanced_menu

        help_menu = Menu(menubar, tearoff=False)
        help_menu.add_command(label="Chef's Instructions", command=lambda: show_instructions(self.root))
        help_menu.add_command(label="Recipe (Instructions)", command=lambda: show_brightsign_instructions(self.root))
        help_menu.add_command(label="Browse Player Files (read-only)", command=lambda: show_player_browser(self.root))
        menubar.add_cascade(label="Help", menu=help_menu)

        self.root.config(menu=menubar)

    def _build_ui(self):
        top = Frame(self.root, padx=16, pady=16, bg=BG)
        top.pack(fill="x")

        Label(
            top,
            text="Recipe: pick the weekly .docx  →  confirm the Monday date  →  "
                 "Whip Up a Preview  →  check it looks right  →  Push to Player. "
                 "(Help menu has the full Chef's Instructions.)",
            bg=BG, fg=MUTED_FG, wraplength=820, justify="left",
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))

        ttk.Button(top, text="Pick Today's Special (.docx)…", command=self.choose_file).grid(
            row=1, column=0, sticky="w"
        )
        self.file_label = Label(top, text="Nothing on the menu yet", bg=BG, fg=MUTED_FG)
        self.file_label.grid(row=1, column=1, sticky="w", padx=10)

        Label(top, text="Starting Monday:", bg=BG, fg=FG).grid(row=2, column=0, sticky="w", pady=(10, 0))
        date_frame = Frame(top, bg=BG)
        date_frame.grid(row=2, column=1, sticky="w", pady=(10, 0))
        self.date_var = StringVar(value=self.start_monday.isoformat())
        self.date_entry = Entry(date_frame, textvariable=self.date_var, width=12, bg=PANEL_BG, fg=FG,
                                 insertbackground=FG, relief="flat")
        self.date_entry.pack(side="left")
        Label(date_frame, text="(YYYY-MM-DD, must be a Monday)", bg=BG, fg=MUTED_FG).pack(side="left", padx=6)

        Label(top, text="Flavor (design):", bg=BG, fg=FG).grid(row=3, column=0, sticky="w", pady=(10, 0))
        variant_frame = Frame(top, bg=BG)
        variant_frame.grid(row=3, column=1, sticky="w", pady=(10, 0))
        ttk.Radiobutton(variant_frame, text="House Special (maroon)", variable=self.variant, value="main").pack(
            side="left"
        )
        ttk.Radiobutton(variant_frame, text="Lighter Fare (alt)", variable=self.variant, value="alt").pack(
            side="left", padx=10
        )

        self.preview_btn = ttk.Button(top, text="Whip Up a Preview", command=self.parse_and_preview)
        self.preview_btn.grid(row=4, column=0, sticky="w", pady=(14, 0))
        self.status_label = Label(top, text="", bg=BG, fg=MUTED_FG)
        self.status_label.grid(row=4, column=1, sticky="w", pady=(14, 0))

        # Scrollable preview area
        container = Frame(self.root, bg=BG)
        container.pack(fill="both", expand=True, padx=16)
        self.canvas = Canvas(container, bg=BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=self.canvas.yview)
        self.preview_frame = Frame(self.canvas, bg=BG)
        self.preview_frame.bind(
            "<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        self.canvas.create_window((0, 0), window=self.preview_frame, anchor=NW)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        bottom = Frame(self.root, padx=16, pady=12, bg=BG)
        bottom.pack(fill="x")
        self.update_presentations_btn = ttk.Button(
            bottom, text="Update This Week's Presentations…", command=self.update_presentations, state="disabled"
        )
        self.update_presentations_btn.pack(side="left")
        self.export_btn = ttk.Button(
            bottom, text="Plate It Up (Export PNGs)…", command=self.export, state="disabled"
        )
        self.export_btn.pack(side="left", padx=(10, 0))
        self.push_btn = ttk.Button(
            bottom, text="Push to Player…", command=self.push_to_player, state="disabled"
        )
        self.push_btn.pack(side="left", padx=(10, 0))
        ttk.Button(
            bottom, text="Recipe (Instructions)", command=lambda: show_brightsign_instructions(self.root)
        ).pack(side="left", padx=(10, 0))

        self._preview_images = []  # keep refs alive

    def choose_file(self):
        path = filedialog.askopenfilename(
            title="Pick today's special (.docx)", filetypes=[("Word Document", "*.docx")]
        )
        if path:
            self.docx_path = path
            self.file_label.config(text=Path(path).name, fg=FG)

    def parse_and_preview(self):
        if not self.docx_path:
            messagebox.showwarning("Order Up... Wait", "Pick a .docx menu file before we start cooking.")
            return
        try:
            start = date.fromisoformat(self.date_var.get().strip())
        except ValueError:
            messagebox.showerror("Date's Overcooked", "Starting Monday must be in YYYY-MM-DD format.")
            return
        if start.weekday() != 0:
            if not messagebox.askyesno(
                "Hold the Phone",
                f"{start.isoformat()} is a {start.strftime('%A')}, not a Monday. Cook with it anyway?",
            ):
                return

        # Parse into a local, not self.days: self.days only changes once the
        # preview for it has actually rendered, so a failed reparse/preview
        # leaves export/update acting on the preview still shown on screen.
        self.status_label.config(text="Prepping the ingredients…", fg=MUTED_FG)
        self._set_busy(True)
        self.root.update_idletasks()

        try:
            new_days = parse_menu_docx(self.docx_path, start)
        except MenuParseError as e:
            messagebox.showerror("Recipe Didn't Work Out", str(e))
            self.status_label.config(text="Parsing flopped.", fg=BAD_FG)
            self._set_busy(False)
            return
        except Exception as e:
            messagebox.showerror("Kitchen Nightmare", f"{e}\n\n{traceback.format_exc()}")
            self.status_label.config(text="Parsing flopped.", fg=BAD_FG)
            self._set_busy(False)
            return

        self.status_label.config(text="Plating the preview…", fg=MUTED_FG)
        self.root.update_idletasks()
        # Tk isn't thread-safe — read the variant here on the main thread
        # and hand it to the worker rather than calling .get() from there.
        threading.Thread(
            target=self._render_preview_thread, args=(new_days, self.variant.get()), daemon=True
        ).start()

    def _render_preview_thread(self, new_days: list[DayMenu], variant: str):
        try:
            previews = []
            for day in new_days:
                png_bytes = render_preview_png_bytes(day, variant=variant)
                previews.append((day, png_bytes))
            self.root.after(0, lambda: self._show_previews(new_days, previews))
        except Exception as e:
            err = f"{e}\n\n{traceback.format_exc()}"
            self.root.after(0, lambda: self._preview_failed(err))

    def _preview_failed(self, err: str):
        messagebox.showerror("Preview Burnt to a Crisp", err)
        self.status_label.config(text="Preview didn't make it out of the kitchen.", fg=BAD_FG)
        self._set_busy(False)

    def _set_busy(self, busy: bool):
        """Locks every action that starts background work (or reads
        self.days) while a preview, export, or update is running, so two
        jobs can't overlap or swap self.days out from under each other.
        When unlocking, export/update/schedule only come back if there's a
        successfully previewed self.days to act on."""
        self._busy = busy
        self.preview_btn.config(state="disabled" if busy else "normal")
        actions_state = "normal" if (not busy and self.days is not None) else "disabled"
        self.advanced_menu.entryconfig(0, state=actions_state)
        self.export_btn.config(state=actions_state)
        self.update_presentations_btn.config(state=actions_state)
        self.push_btn.config(state=actions_state)

    def _show_previews(self, new_days: list[DayMenu], previews: list[tuple[DayMenu, bytes]]):
        for widget in self.preview_frame.winfo_children():
            widget.destroy()
        self._preview_images.clear()

        for day, png_bytes in previews:
            img = Image.open(io.BytesIO(png_bytes))
            scale = PREVIEW_W / img.width
            thumb = img.resize((PREVIEW_W, int(img.height * scale)), Image.LANCZOS)
            tk_img = ImageTk.PhotoImage(thumb)
            self._preview_images.append(tk_img)

            row = Frame(self.preview_frame, pady=6, bg=BG)
            row.pack(fill="x")
            Label(
                row, text=f"{day.day_name} — {format_month_day(day.menu_date)}",
                anchor="w", bg=BG, fg=FG,
            ).pack(fill="x")
            Label(row, image=tk_img, bg=BG).pack()

        self.days = new_days
        self.status_label.config(text="Fresh off the grill — give it a taste-test before you plate it up.", fg=GOOD_FG)
        self._set_busy(False)

    def generate_schedule(self):
        if not self.days:
            return

        win = Toplevel(self.root, bg=BG)
        win.title("Generate Schedule")
        win.geometry("380x340")

        Label(
            win, text="Which days should this schedule cover?", bg=BG, fg=FG,
            font=("", 12, "bold"), anchor="w",
        ).pack(anchor="w", padx=16, pady=(16, 6))

        days = self.days  # snapshot; see update_presentations
        day_vars: dict[str, BooleanVar] = {}
        for day in days:
            var = BooleanVar(value=True)
            day_vars[day.day_name] = var
            ttk.Checkbutton(
                win, text=f"{day.day_name} — {format_month_day(day.menu_date)}", variable=var,
            ).pack(anchor="w", padx=24, pady=2)

        Label(
            win, text="What time should each day's presentation run?\n(same time every day)",
            bg=BG, fg=FG, font=("", 12, "bold"), anchor="w", justify="left",
        ).pack(anchor="w", padx=16, pady=(16, 6))

        time_frame = Frame(win, bg=BG)
        time_frame.pack(anchor="w", padx=24)
        Label(time_frame, text="Start:", bg=BG, fg=FG).grid(row=0, column=0, sticky="w")
        start_var = StringVar(value="06:00")
        Entry(time_frame, textvariable=start_var, width=8, bg=PANEL_BG, fg=FG, insertbackground=FG, relief="flat").grid(
            row=0, column=1, padx=(6, 20)
        )
        Label(time_frame, text="End:", bg=BG, fg=FG).grid(row=0, column=2, sticky="w")
        end_var = StringVar(value="16:00")
        Entry(time_frame, textvariable=end_var, width=8, bg=PANEL_BG, fg=FG, insertbackground=FG, relief="flat").grid(
            row=0, column=3, padx=(6, 0)
        )

        def do_generate():
            selected = [(day.day_name, day.menu_date) for day in days if day_vars[day.day_name].get()]
            if not selected:
                messagebox.showwarning("Missing info", "Pick at least one day.", parent=win)
                return
            try:
                start = datetime.strptime(start_var.get().strip(), "%H:%M").time()
                end = datetime.strptime(end_var.get().strip(), "%H:%M").time()
            except ValueError:
                messagebox.showerror("Bad time", "Start/End must be in 24-hour HH:MM format (e.g. 06:00).", parent=win)
                return

            bpfx_dir_str = filedialog.askdirectory(
                title="Pick the shared Brightsign folder (contains the Cafe Menu <Day>.bpfx files)"
            )
            if not bpfx_dir_str:
                return
            presentation_path = str(Path(bpfx_dir_str).resolve())
            if not presentation_path.endswith("/"):
                presentation_path += "/"

            try:
                schedule = bpsx_schedule.build_schedule(selected, start, end, presentation_path)
            except Exception as e:
                messagebox.showerror("Recipe Didn't Work Out", f"{e}\n\n{traceback.format_exc()}")
                return

            out_str = filedialog.asksaveasfilename(
                title="Save schedule as…",
                defaultextension=".bpsx",
                initialfile=f"Cafe Menu Schedule {selected[0][1].isoformat()}.bpsx",
                filetypes=[("BrightAuthor Schedule", "*.bpsx")],
            )
            if not out_str:
                return

            try:
                bpsx_schedule.write_schedule(schedule, Path(out_str))
            except Exception as e:
                messagebox.showerror("Kitchen Fire", f"{e}\n\n{traceback.format_exc()}")
                return

            win.destroy()
            messagebox.showinfo(
                "Order Up!",
                f"Schedule saved for {len(selected)} day(s).\n\nSaved: {out_str}\n\n"
                "In brightAuthor:connected: File → Open, switch the file-type filter "
                "to Schedule, and open this file. Then Publish as usual.",
            )

        ttk.Button(win, text="Generate", command=do_generate).pack(pady=(20, 12))

    def update_presentations(self):
        if not self.days:
            return

        win = Toplevel(self.root, bg=BG)
        win.title("Update This Week's Presentations")
        win.geometry("420x340")

        Label(
            win,
            text="Which days should get this week's new image?",
            bg=BG, fg=FG, font=("", 12, "bold"), anchor="w",
        ).pack(anchor="w", padx=16, pady=(16, 2))
        Label(
            win,
            text="Leave a day unchecked if it hasn't aired yet and shouldn't be "
                 "overwritten early — e.g. prepping next week's Monday–Thursday "
                 "while this week's Friday hasn't played yet.",
            bg=BG, fg=MUTED_FG, wraplength=380, justify="left",
        ).pack(anchor="w", padx=16, pady=(0, 10))

        # Snapshot the days this dialog's checkboxes describe, in case a new
        # preview replaces self.days while the dialog is still open.
        days = self.days
        day_vars: dict[str, BooleanVar] = {}
        for day in days:
            label = f"{day.day_name} — {format_month_day(day.menu_date)}"
            if day.closed:
                label += "  (Closed)"
            var = BooleanVar(value=True)
            day_vars[day.day_name] = var
            ttk.Checkbutton(win, text=label, variable=var).pack(anchor="w", padx=24, pady=2)

        def do_update():
            if self._busy:
                messagebox.showwarning("Still Cooking", "Wait for the current job to finish first.", parent=win)
                return
            selected_days = [day for day in days if day_vars[day.day_name].get()]
            if not selected_days:
                messagebox.showwarning("Missing info", "Pick at least one day.", parent=win)
                return

            bpfx_dir_str = filedialog.askdirectory(
                title="Pick the shared Brightsign folder (contains the Cafe Menu <Day>.bpfx files)"
            )
            if not bpfx_dir_str:
                return
            bpfx_dir = Path(bpfx_dir_str)

            win.destroy()
            self.status_label.config(text="Swapping in this week's specials…", fg=MUTED_FG)
            self._set_busy(True)
            self.root.update_idletasks()
            threading.Thread(
                target=self._update_presentations_thread,
                args=(bpfx_dir, selected_days, self.variant.get()), daemon=True,
            ).start()

        ttk.Button(win, text="Update", command=do_update).pack(pady=(16, 12))

    def _update_presentations_thread(self, bpfx_dir: Path, selected_days: list[DayMenu], variant: str):
        try:
            with tempfile.TemporaryDirectory() as tmp:
                results = render_days(selected_days, Path(tmp), variant=variant, strict=True)
                day_to_png = {r.day_name: r.png_path for r in results}
                written = bpfx_update.update_week(bpfx_dir, day_to_png)
            names = "\n".join(p.name for p in written)
            self.root.after(
                0,
                lambda: (
                    self.status_label.config(text="This week's presentations are updated.", fg=GOOD_FG),
                    self._set_busy(False),
                    messagebox.showinfo(
                        "Order Up!",
                        f"Updated {len(written)} presentation(s):\n{names}\n\n"
                        "In brightAuthor:connected: just hit Publish — no need to re-open "
                        "or re-schedule anything, as long as each day's schedule entry is "
                        "already set to recur forever.",
                    ),
                ),
            )
        except (RenderValidationError, bpfx_update.BpfxUpdateError) as e:
            msg = str(e)  # `e` is unbound once this block exits; see do_list
            self.root.after(
                0,
                lambda: (
                    messagebox.showerror("86'd — Update Didn't Take", msg),
                    self.status_label.config(text="Presentation update didn't make it out of the kitchen.", fg=BAD_FG),
                    self._set_busy(False),
                ),
            )
        except Exception as e:
            err = f"{e}\n\n{traceback.format_exc()}"
            self.root.after(
                0,
                lambda: (
                    messagebox.showerror("Kitchen Fire", err),
                    self.status_label.config(text="Presentation update didn't make it out of the kitchen.", fg=BAD_FG),
                    self._set_busy(False),
                ),
            )

    def export(self):
        if not self.days:
            return

        win = Toplevel(self.root, bg=BG)
        win.title("Plate It Up")
        win.geometry("380x340")

        Label(
            win, text="Which days should get a PNG?", bg=BG, fg=FG,
            font=("", 12, "bold"), anchor="w",
        ).pack(anchor="w", padx=16, pady=(16, 6))

        days = self.days  # snapshot; see update_presentations
        day_vars: dict[str, BooleanVar] = {}
        for day in days:
            label = f"{day.day_name} — {format_month_day(day.menu_date)}"
            if day.closed:
                label += "  (Closed)"
            var = BooleanVar(value=True)
            day_vars[day.day_name] = var
            ttk.Checkbutton(win, text=label, variable=var).pack(anchor="w", padx=24, pady=2)

        def do_export():
            if self._busy:
                messagebox.showwarning("Still Cooking", "Wait for the current job to finish first.", parent=win)
                return
            selected_days = [day for day in days if day_vars[day.day_name].get()]
            if not selected_days:
                messagebox.showwarning("Missing info", "Pick at least one day.", parent=win)
                return

            out_dir = filedialog.askdirectory(title="Choose a folder to plate the PNGs into")
            if not out_dir:
                return

            win.destroy()
            self.status_label.config(text="Plating the final dishes…", fg=MUTED_FG)
            self._set_busy(True)
            self.root.update_idletasks()
            threading.Thread(
                target=self._export_thread, args=(Path(out_dir), selected_days, self.variant.get()), daemon=True
            ).start()

        ttk.Button(win, text="Export", command=do_export).pack(pady=(16, 12))

    def _export_thread(self, out_dir: Path, selected_days: list[DayMenu], variant: str):
        try:
            results = render_days(selected_days, out_dir, variant=variant, strict=True)
            names = "\n".join(r.png_path.name for r in results)
            self.root.after(
                0,
                lambda: (
                    self.status_label.config(
                        text=f"Served! {len(results)} PNG(s) plated up in {out_dir}", fg=GOOD_FG
                    ),
                    self._set_busy(False),
                    messagebox.showinfo("Order Up!", f"Served:\n{names}"),
                ),
            )
        except RenderValidationError as e:
            msg = str(e)  # `e` is unbound once this block exits; see do_list
            self.root.after(
                0,
                lambda: (
                    messagebox.showerror("86'd — Layout Problem", msg),
                    self.status_label.config(text="Sent back to the kitchen: layout problem.", fg=BAD_FG),
                    self._set_busy(False),
                ),
            )
        except Exception as e:
            err = f"{e}\n\n{traceback.format_exc()}"
            self.root.after(
                0,
                lambda: (
                    messagebox.showerror("Kitchen Fire", err),
                    self.status_label.config(text="Export didn't make it out of the kitchen.", fg=BAD_FG),
                    self._set_busy(False),
                ),
            )

    def push_to_player(self):
        if not self.days:
            return
        cfg = _load_player_config()

        win = Toplevel(self.root, bg=BG)
        win.title("Push to Player")
        # No fixed size: the window fits its contents, so the note about
        # unchecked days below can never push the Push button out of view.

        Label(
            win, text="Which days should the player get this week's image for?",
            bg=BG, fg=FG, font=("", 12, "bold"), anchor="w", wraplength=420, justify="left",
        ).pack(anchor="w", padx=16, pady=(16, 2))
        Label(
            win,
            text="Sends the signs straight to the BrightSign player — no "
                 "brightAuthor:connected Publish needed. Leave a day unchecked if "
                 "it hasn't aired yet and shouldn't be overwritten early. The sign "
                 "goes blank for about 30 seconds while the player restarts.",
            bg=BG, fg=MUTED_FG, wraplength=420, justify="left",
        ).pack(anchor="w", padx=16, pady=(0, 10))

        days = self.days  # snapshot; see update_presentations
        # Days whose sign would air in the wrong week start unchecked — e.g.
        # pushing next week's menu on Thursday leaves Friday unchecked, so
        # this week's Friday sign stays on the player until it has aired.
        # Same rule as the warning in do_push (player_push.date_mismatches),
        # so days of this week that have already aired stay checked.
        today = date.today()
        unchecked = player_push.date_mismatches({d.day_name: d.menu_date for d in days}, today)
        held_back = {day for day, _, _ in unchecked}
        day_vars: dict[str, BooleanVar] = {}
        for day in days:
            label = f"{day.day_name} — {format_month_day(day.menu_date)}"
            if day.closed:
                label += "  (Closed)"
            var = BooleanVar(value=day.day_name not in held_back)
            day_vars[day.day_name] = var
            ttk.Checkbutton(win, text=label, variable=var).pack(anchor="w", padx=24, pady=2)
        if unchecked:
            Label(
                win,
                text="Left unchecked — these would replace a sign that hasn't aired yet, "
                     "or are dated for a different week:\n"
                     + "\n".join(_mismatch_line(d, sign, shown, today) for d, sign, shown in unchecked)
                     + "\nPush them after the current one has aired (or check the Starting "
                       "Monday date).",
                bg=BG, fg=MUTED_FG, wraplength=420, justify="left",
            ).pack(anchor="w", padx=24, pady=(6, 0))

        form = Frame(win, bg=BG)
        form.pack(anchor="w", padx=16, pady=(14, 0))
        saved_ip, saved_user = cfg.get("ip", ""), cfg.get("username") or "admin"
        fields = [
            ("Player IP:", StringVar(value=saved_ip), {}),
            ("Username:", StringVar(value=saved_user), {}),
            ("Password:", StringVar(value=credentials.load(saved_ip, saved_user)), {"show": "•"}),
        ]
        for row, (text, var, extra) in enumerate(fields):
            Label(form, text=text, bg=BG, fg=FG).grid(row=row, column=0, sticky="w", pady=3)
            Entry(form, textvariable=var, width=22, bg=PANEL_BG, fg=FG, insertbackground=FG,
                  relief="flat", **extra).grid(row=row, column=1, sticky="w", padx=(6, 0))
        ip_var, user_var, pass_var = (f[1] for f in fields)
        Label(
            form, text="The password is remembered in this Mac's Keychain (never in the "
                       "app's files) once a push with it works.",
            bg=BG, fg=MUTED_FG, wraplength=420, justify="left",
        ).grid(row=3, column=0, columnspan=3, sticky="w", pady=(4, 0))

        def clear_ip():
            ip_var.set("")
            _save_player_config(ip="")

        def clear_password():
            # Forget it for whichever player the dialog is pointed at, falling
            # back to the saved one if the IP field was already cleared.
            credentials.clear(ip_var.get().strip() or saved_ip, user_var.get().strip() or saved_user)
            pass_var.set("")

        ttk.Button(form, text="Clear IP", command=clear_ip).grid(row=0, column=2, sticky="w", padx=6)
        ttk.Button(form, text="Clear password", command=clear_password).grid(row=2, column=2, sticky="w", padx=6)

        def do_push():
            if self._busy:
                messagebox.showwarning("Still Cooking", "Wait for the current job to finish first.", parent=win)
                return
            selected_days = [day for day in days if day_vars[day.day_name].get()]
            if not selected_days:
                messagebox.showwarning("Missing info", "Pick at least one day.", parent=win)
                return
            ip, username, password = ip_var.get().strip(), user_var.get().strip(), pass_var.get()
            if not ip or not username:
                messagebox.showwarning("Missing info", "Player IP and username are required.", parent=win)
                return
            # Remember the IP as soon as it's entered, even if this push
            # fails (a wrong password shouldn't make you retype the IP).
            _save_player_config(ip=ip, username=username)
            names = ", ".join(d.day_name for d in selected_days)
            blank_note = "The sign will go blank for about 30 seconds while the player restarts."
            today = date.today()
            mismatches = player_push.date_mismatches({d.day_name: d.menu_date for d in selected_days}, today)
            if mismatches:
                lines = "\n".join(_mismatch_line(day, sign, shown, today) for day, sign, shown in mismatches)
                confirmed = messagebox.askyesno(
                    "Wrong Week on the Menu?",
                    f"These signs are dated for a different week than the one they'll be shown in:\n\n"
                    f"{lines}\n\nCheck the Starting Monday date, or uncheck days that haven't "
                    f"aired yet.\n\nPush {names} anyway? {blank_note}",
                    icon="warning", default="no", parent=win,
                )
            else:
                confirmed = messagebox.askyesno(
                    "Send It to the Pass?", f"Push {names} to the player at {ip}?\n\n{blank_note}", parent=win,
                )
            if not confirmed:
                return
            port = brightsign_client.DEFAULT_PORT
            win.destroy()
            self.status_label.config(text="Sending the specials to the player…", fg=MUTED_FG)
            self._set_busy(True)
            self.root.update_idletasks()
            player = brightsign_client.Player(ip, port, username, password)
            threading.Thread(
                target=self._push_thread,
                args=(player, selected_days, self.variant.get(),
                      lambda: credentials.save(ip, username, password)),
                daemon=True,
            ).start()

        ttk.Button(win, text="Push", command=do_push).pack(pady=(16, 12))

    def _push_thread(self, player, selected_days: list[DayMenu], variant: str, remember_password):
        def progress(msg: str):
            self.root.after(0, lambda: self.status_label.config(text=msg, fg=MUTED_FG))

        try:
            with tempfile.TemporaryDirectory() as tmp:
                progress("Rendering the signs…")
                results = render_days(selected_days, Path(tmp), variant=variant, strict=True)
                day_to_png = {r.day_name: r.png_path for r in results}
                changes, backup = player_push.push(player, day_to_png, progress=progress)
            # Only now — the player has accepted this password — is it worth
            # remembering. A typo never gets saved.
            remember_password()
            sent = [c.day_name for c in changes if not c.unchanged]
            same = [c.day_name for c in changes if c.unchanged]
            snapshot = None
            if sent:
                progress("Waiting for the sign to come back up…")
                time.sleep(30)  # let the presentation start before screenshotting
                try:
                    snapshot = player.snapshot()
                except brightsign_client.BrightSignError:
                    snapshot = None  # screenshot is a nice-to-have; the push itself worked
            lines = []
            if sent:
                lines.append(f"Pushed to the player: {', '.join(sent)}.")
            if same:
                lines.append(f"Already up to date (not re-sent): {', '.join(same)}.")
            lines.append(f"\nA copy of the player's previous content list was saved to:\n{backup}")
            summary = "\n".join(lines)
            self.root.after(0, lambda: self._push_done(summary, snapshot, bool(sent)))
        except (RenderValidationError, player_push.PlayerPushError, brightsign_client.BrightSignError) as e:
            msg = str(e)  # `e` is unbound once this block exits; see do_list
            self.root.after(
                0,
                lambda: (
                    messagebox.showerror("86'd — Push Didn't Go Out", msg),
                    self.status_label.config(text="Push didn't make it out of the kitchen.", fg=BAD_FG),
                    self._set_busy(False),
                ),
            )
        except Exception as e:
            err = f"{e}\n\n{traceback.format_exc()}"
            self.root.after(
                0,
                lambda: (
                    messagebox.showerror("Kitchen Fire", err),
                    self.status_label.config(text="Push didn't make it out of the kitchen.", fg=BAD_FG),
                    self._set_busy(False),
                ),
            )

    def _push_done(self, summary: str, snapshot: bytes | None, sent_any: bool):
        self.status_label.config(
            text="Order up — the player has this week's specials." if sent_any
            else "The player already had these signs — nothing needed sending.",
            fg=GOOD_FG,
        )
        self._set_busy(False)

        win = Toplevel(self.root, bg=BG)
        win.title("Order Up!")
        Label(win, text=summary, bg=BG, fg=FG, justify="left", anchor="w", wraplength=740).pack(
            anchor="w", padx=16, pady=(14, 8)
        )
        tk_img = None
        if snapshot:
            try:
                img = Image.open(io.BytesIO(snapshot))
                scale = PREVIEW_W / img.width
                tk_img = ImageTk.PhotoImage(img.resize((PREVIEW_W, int(img.height * scale)), Image.LANCZOS))
            except Exception:
                tk_img = None  # a garbled screenshot shouldn't hide that the push worked
        if tk_img:
            Label(win, text="What the sign is showing right now:", bg=BG, fg=MUTED_FG).pack(anchor="w", padx=16)
            win._image = tk_img  # keep the PhotoImage alive for the window's lifetime
            Label(win, image=tk_img, bg=BG, relief="solid", borderwidth=1).pack(padx=16, pady=(4, 8))
        Button(win, text="Close", command=win.destroy, bg=ACCENT, fg=ACCENT_FG,
               activebackground=ACCENT, activeforeground=ACCENT_FG, relief="flat").pack(pady=(0, 12))


def main():
    root = Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
