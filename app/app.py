"""The Cafe — Digital Menu Sign Generator. Offline Tkinter desktop app."""
from __future__ import annotations

import io
import os
import sys
import tempfile
import threading
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
    # bundled inside the app. sys._MEIPASS resolves to Contents/Frameworks
    # in a --windowed onedir .app on macOS (not Contents/Resources, despite
    # that being where PyInstaller's own --add-data assets also get mirrored) —
    # build_app.sh copies Chromium into Contents/Frameworks/ms-playwright
    # to match, instead of trying to download it at runtime, which would
    # require network access.
    bundle_root = Path(sys._MEIPASS)
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(bundle_root / "ms-playwright")
    app_dir = bundle_root
else:
    app_dir = Path(__file__).parent

sys.path.insert(0, str(app_dir))

BRIGHTSIGN_HELP_DIR = app_dir / "brightsign_help"

from parser import parse_menu_docx, MenuParseError, DayMenu, format_month_day
from renderer import render_days, render_preview_png_bytes, RenderValidationError
import brightsign_client
import bpsx_schedule
import bpfx_update

PREVIEW_W = 760

# Fixed light palette, applied regardless of macOS's system appearance.
# Tkinter's native (Aqua) widgets don't reliably re-theme for dark mode —
# labels/status text were rendering as dark-on-dark. Forcing a 'clam' ttk
# theme with explicit colors, plus explicit colors on the plain tk widgets,
# keeps contrast readable no matter what the OS is set to.
BG = "#faf7f2"
PANEL_BG = "#f1ece2"
FG = "#2b1d16"
MUTED_FG = "#6b5c50"
GOOD_FG = "#2f7a3d"
BAD_FG = "#b3392c"
ACCENT = "#6b2f20"
ACCENT_FG = "#faf7f2"

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
   sparse day) or if Friday lists both soup lines at once — you'll get
   an error describing exactly what's wrong.

5. Update This Week's Presentations…
   Check off which days should get this week's new image (all 5 checked
   by default — uncheck a day if it hasn't aired yet and shouldn't be
   overwritten early, e.g. Friday, if next week's menu showed up before
   this week's Friday has played), then point this at the shared
   Brightsign folder (the one with the five "Cafe Menu <Day>.bpfx" files
   in it). This renders the checked days' 3840×600px signs and rewrites
   each one's brightAuthor:connected presentation to show them — no
   manual drag-and-drop needed. Then in brightAuthor:connected, just hit
   Publish.

   If any label or item text is too long and would wrap to a second
   line on the sign, this gets sent back to the kitchen (blocked) with
   an error telling you which day and which text — fix the source
   document and re-parse rather than shipping a half-baked layout.

   See "Recipe (Instructions)" in the Help menu for the full weekly
   walkthrough, including the one-time schedule setup.

Advanced menu (rarely needed):
   "Plate It Up (Export 5 PNGs)…" exports the five PNGs to a folder of
   your choice, without touching any presentation — useful if you just
   want the images themselves. "Generate Schedule (.bpsx)…" is a
   one-time setup step; once each weekday's schedule entry is created
   to recur forever, you never need to run it again.

This app makes no network connections — everything (fonts, rendering
engine) is bundled inside the app. Fully homemade, nothing delivered.
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
    (
        "One-time setup — only needed once, ever",
        "Skip this if the schedule's already set up. From the Advanced "
        'menu: "Generate Schedule (.bpsx)… [one-time setup]" (after a '
        "preview). Pick the days, one shared start/end time, and the "
        "shared Brightsign folder (the one with the five "
        '"Cafe Menu <Day>.bpfx" files in it), then save the file. In '
        "brightAuthor:connected: File → Open, switch the file-type "
        "filter to Schedule, open that file, then Publish.\n\n"
        "Each weekday's schedule entry recurs every week, forever — you "
        "will not need to touch scheduling again after this.",
        "03_schedule_empty.png",
    ),
    (
        "1. Get the ingredients ready",
        'Open "The Cafe Menu Sign Generator", pick this week\'s .docx, and '
        'Whip Up a Preview (see Chef\'s Instructions if you haven\'t yet).',
        None,
    ),
    (
        "2. Update this week's presentations",
        'Click "Update This Week\'s Presentations…", check off which days '
        "should get this week's new image, and point it at the shared "
        'Brightsign folder (the one with the five "Cafe Menu <Day>.bpfx" '
        "files in it). This renders those days' signs and rewrites each "
        "one's presentation to show them — no dragging PNGs around by "
        "hand.\n\n"
        "There's still only one Friday presentation, shared by every week "
        "(the schedule can't tell \"this Friday\" from \"next Friday\" — "
        "it's the same recurring block). If next week's menu shows up "
        "before this week's Friday has aired, leave Friday unchecked for "
        "now and update it once this week's Friday has actually played — "
        "otherwise you'd overwrite it early.",
        None,
    ),
    (
        "3. Preheat brightAuthor:connected",
        "On the MacBook Air, open brightAuthor:connected (the purple \"bA "
        "connected\" icon). This is the oven the signs actually get baked "
        "into.",
        "01_open_baconnected.png",
    ),
    (
        "4. Fire it and send it out",
        "Plug in the orange ethernet cable at James's desk. In the "
        "Destination panel, click the refresh icon above Networked "
        'Players, then check the box next to the player named "Cafe '
        'Menu-…" (it\'s the only one on the list). Click Publish (top '
        "right) — order up, it's on the screen.",
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
        if heading:
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


def _save_player_config(ip: str, port: str, username: str, storage: str) -> None:
    # Deliberately never saves the password — it's the player's serial
    # number and this file isn't meant to be a credential store. IP, port,
    # username, and storage are low-stakes convenience only.
    import json
    PLAYER_CONFIG_PATH.write_text(json.dumps({"ip": ip, "port": port, "username": username, "storage": storage}))


def show_player_browser(root: Tk):
    """Read-only file browser against a BrightSign player's Local DWS.

    This exists to answer one open question before any direct-upload
    feature gets built: does a presentation's zone read its image from a
    fixed, predictable filename on the player (which a future "push this
    week's PNGs directly to the player" button could safely overwrite), or
    does brightAuthor:connected rename/rehash the asset on every Publish
    (which would make a blind overwrite silently do nothing, or worse,
    clobber the wrong file)? This panel only ever does GET requests —
    nothing here can change what's on the player or what's on screen.
    """
    cfg = _load_player_config()

    win = Toplevel(root, bg=BG)
    win.title("Browse Player Files (read-only)")
    win.geometry("700x560")

    Label(
        win,
        text="Look around the player's storage to find the exact file each day's "
             "menu zone reads from. This only reads — nothing here can change "
             "what's showing on the screen.",
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
    port_var = StringVar(value=cfg.get("port", "8080"))
    Entry(form, textvariable=port_var, width=8, bg=PANEL_BG, fg=FG, insertbackground=FG, relief="flat").grid(
        row=0, column=3, sticky="w", padx=(6, 16)
    )
    Label(form, text="(not always 80 — check by loading http://<ip>:<port> in a browser first)",
          bg=BG, fg=MUTED_FG).grid(row=0, column=4, columnspan=2, sticky="w")

    Label(form, text="Username:", bg=BG, fg=FG).grid(row=1, column=0, sticky="w", pady=3)
    user_var = StringVar(value=cfg.get("username", "admin"))
    Entry(form, textvariable=user_var, width=12, bg=PANEL_BG, fg=FG, insertbackground=FG, relief="flat").grid(
        row=1, column=1, sticky="w", padx=(6, 16)
    )

    Label(form, text="Password:", bg=BG, fg=FG).grid(row=1, column=2, sticky="w", pady=3)
    pass_var = StringVar(value="")
    Entry(form, textvariable=pass_var, width=18, bg=PANEL_BG, fg=FG, insertbackground=FG, relief="flat", show="•").grid(
        row=1, column=3, sticky="w", padx=(6, 16)
    )
    Label(form, text="(not saved between sessions — try blank first, or the serial number)",
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
            messagebox.showwarning("Missing info", "Player IP and username are required.")
            return
        try:
            port = int(port_str) if port_str else 80
        except ValueError:
            messagebox.showerror("Bad port", "Port must be a number (e.g. 80 or 8080).")
            return
        status_var.set(f"Listing {storage}/{path or '(root)'} on port {port} …")
        win.update_idletasks()

        def worker():
            # Everything below is wrapped in one broad try/except — not just
            # for BrightSignError — because the real player's JSON response
            # shape is only inferred from reading a reference CLI's source,
            # never actually tested against real hardware until the user
            # tries it. If that shape assumption is wrong (different key
            # names, files as strings instead of dicts, etc.), formatting
            # code below would raise an exception that, uncaught, silently
            # kills this background thread and leaves the GUI's status text
            # stuck forever on "Listing..." — which is exactly what happened
            # once already. Showing the raw response on any failure here
            # turns a silent hang into an actionable error and a way to see
            # the real shape so this code can be corrected to match it.
            try:
                files = brightsign_client.list_files(ip, port, username, password, path=path, storage=storage)
                _save_player_config(ip, port_str, username, storage)
                lines = []
                for f in sorted(files, key=lambda x: (x.get("mime") != "directory", x.get("name", ""))):
                    kind = "DIR " if f.get("mime") == "directory" else f.get("mime", "file")
                    size = f.get("size", "")
                    lines.append(f"{kind:>18}  {size!s:>10}  {f.get('name', '')}")
                result_text = "\n".join(lines) if lines else "(empty)"
                status_text = f"{len(files)} item(s) at {storage}/{path or '(root)'}"
            except brightsign_client.BrightSignError as e:
                win.after(0, lambda: status_var.set(f"Failed: {e}"))
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


class App:
    def __init__(self, root: Tk):
        self.root = root
        root.title("The Cafe — Menu Sign Generator")
        root.geometry("900x700")
        root.configure(bg=BG)

        self._setup_style()

        self.docx_path: str | None = None
        self.start_monday: date = _next_monday(date.today()) if date.today().weekday() != 0 else date.today()
        self.days: list[DayMenu] | None = None
        self.variant = StringVar(value="main")

        self._build_menu()
        self._build_ui()

    def _setup_style(self):
        # 'clam' is a theme ttk fully draws itself (unlike 'aqua'), so our
        # explicit colors actually take effect instead of being overridden
        # by whatever the OS's light/dark appearance would otherwise force.
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("TFrame", background=BG)
        style.configure("TLabel", background=BG, foreground=FG)
        style.configure("TButton", background=ACCENT, foreground=ACCENT_FG, padding=6, relief="flat")
        style.map("TButton", background=[("active", "#82412e"), ("disabled", "#b8aca3")])
        style.configure("TRadiobutton", background=BG, foreground=FG)
        style.map("TRadiobutton", background=[("active", BG)])
        style.configure("TScrollbar", background=PANEL_BG)

    def _build_menu(self):
        menubar = Menu(self.root)

        advanced_menu = Menu(menubar, tearoff=False)
        advanced_menu.add_command(
            label="Plate It Up (Export 5 PNGs)…", command=self.export, state="disabled"
        )
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
                 "Whip Up a Preview  →  check for wrapping  →  Update This Week's "
                 "Presentations. (Help menu has the full Chef's Instructions.)",
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

        ttk.Button(top, text="Whip Up a Preview", command=self.parse_and_preview).grid(
            row=4, column=0, sticky="w", pady=(14, 0)
        )
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

        self.status_label.config(text="Prepping the ingredients…", fg=MUTED_FG)
        self.advanced_menu.entryconfig(0, state="disabled")
        self.root.update_idletasks()

        try:
            self.days = parse_menu_docx(self.docx_path, start)
        except MenuParseError as e:
            messagebox.showerror("Recipe Didn't Work Out", str(e))
            self.status_label.config(text="Parsing flopped.", fg=BAD_FG)
            return
        except Exception as e:
            messagebox.showerror("Kitchen Nightmare", f"{e}\n\n{traceback.format_exc()}")
            self.status_label.config(text="Parsing flopped.", fg=BAD_FG)
            return

        self.status_label.config(text="Plating the preview…", fg=MUTED_FG)
        self.root.update_idletasks()
        threading.Thread(target=self._render_preview_thread, daemon=True).start()

    def _render_preview_thread(self):
        try:
            variant = self.variant.get()
            previews = []
            for day in self.days:
                png_bytes = render_preview_png_bytes(day, variant=variant)
                previews.append((day, png_bytes))
            self.root.after(0, lambda: self._show_previews(previews))
        except Exception as e:
            err = f"{e}\n\n{traceback.format_exc()}"
            self.root.after(0, lambda: self._preview_failed(err))

    def _preview_failed(self, err: str):
        messagebox.showerror("Preview Burnt to a Crisp", err)
        self.status_label.config(text="Preview didn't make it out of the kitchen.", fg=BAD_FG)

    def _show_previews(self, previews: list[tuple[DayMenu, bytes]]):
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

        self.status_label.config(text="Fresh off the grill — give it a taste-test before you plate it up.", fg=GOOD_FG)
        self.advanced_menu.entryconfig(0, state="normal")
        self.advanced_menu.entryconfig(1, state="normal")
        self.update_presentations_btn.config(state="normal")

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

        day_vars: dict[str, BooleanVar] = {}
        for day in self.days:
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
            selected = [(day.day_name, day.menu_date) for day in self.days if day_vars[day.day_name].get()]
            if not selected:
                messagebox.showwarning("Missing info", "Pick at least one day.")
                return
            try:
                start = datetime.strptime(start_var.get().strip(), "%H:%M").time()
                end = datetime.strptime(end_var.get().strip(), "%H:%M").time()
            except ValueError:
                messagebox.showerror("Bad time", "Start/End must be in 24-hour HH:MM format (e.g. 06:00).")
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
        win.geometry("420x300")

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

        day_vars: dict[str, BooleanVar] = {}
        for day in self.days:
            var = BooleanVar(value=True)
            day_vars[day.day_name] = var
            ttk.Checkbutton(
                win, text=f"{day.day_name} — {format_month_day(day.menu_date)}", variable=var,
            ).pack(anchor="w", padx=24, pady=2)

        def do_update():
            selected_days = [day for day in self.days if day_vars[day.day_name].get()]
            if not selected_days:
                messagebox.showwarning("Missing info", "Pick at least one day.")
                return

            bpfx_dir_str = filedialog.askdirectory(
                title="Pick the shared Brightsign folder (contains the Cafe Menu <Day>.bpfx files)"
            )
            if not bpfx_dir_str:
                return
            bpfx_dir = Path(bpfx_dir_str)

            win.destroy()
            self.status_label.config(text="Swapping in this week's specials…", fg=MUTED_FG)
            self.update_presentations_btn.config(state="disabled")
            self.root.update_idletasks()
            threading.Thread(
                target=self._update_presentations_thread, args=(bpfx_dir, selected_days), daemon=True
            ).start()

        ttk.Button(win, text="Update", command=do_update).pack(pady=(16, 12))

    def _update_presentations_thread(self, bpfx_dir: Path, selected_days: list[DayMenu]):
        try:
            with tempfile.TemporaryDirectory() as tmp:
                results = render_days(selected_days, Path(tmp), variant=self.variant.get(), strict=True)
                day_to_png = {r.day_name: r.png_path for r in results}
                written = bpfx_update.update_week(bpfx_dir, day_to_png)
            names = "\n".join(p.name for p in written)
            self.root.after(
                0,
                lambda: (
                    self.status_label.config(text="This week's presentations are updated.", fg=GOOD_FG),
                    self.update_presentations_btn.config(state="normal"),
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
            self.root.after(
                0,
                lambda: (
                    messagebox.showerror("86'd — Update Didn't Take", str(e)),
                    self.status_label.config(text="Presentation update didn't make it out of the kitchen.", fg=BAD_FG),
                    self.update_presentations_btn.config(state="normal"),
                ),
            )
        except Exception as e:
            err = f"{e}\n\n{traceback.format_exc()}"
            self.root.after(
                0,
                lambda: (
                    messagebox.showerror("Kitchen Fire", err),
                    self.status_label.config(text="Presentation update didn't make it out of the kitchen.", fg=BAD_FG),
                    self.update_presentations_btn.config(state="normal"),
                ),
            )

    def export(self):
        if not self.days:
            return
        out_dir = filedialog.askdirectory(title="Choose a folder to plate the PNGs into")
        if not out_dir:
            return
        self.status_label.config(text="Plating the final dishes…", fg=MUTED_FG)
        self.advanced_menu.entryconfig(0, state="disabled")
        self.root.update_idletasks()
        threading.Thread(target=self._export_thread, args=(Path(out_dir),), daemon=True).start()

    def _export_thread(self, out_dir: Path):
        try:
            results = render_days(self.days, out_dir, variant=self.variant.get(), strict=True)
            names = "\n".join(r.png_path.name for r in results)
            self.root.after(
                0,
                lambda: (
                    self.status_label.config(text=f"Served! 5 PNGs plated up in {out_dir}", fg=GOOD_FG),
                    self.advanced_menu.entryconfig(0, state="normal"),
                    messagebox.showinfo("Order Up!", f"Served:\n{names}"),
                ),
            )
        except RenderValidationError as e:
            self.root.after(
                0,
                lambda: (
                    messagebox.showerror("86'd — Layout Problem", str(e)),
                    self.status_label.config(text="Sent back to the kitchen: text wrapped.", fg=BAD_FG),
                    self.advanced_menu.entryconfig(0, state="normal"),
                ),
            )
        except Exception as e:
            err = f"{e}\n\n{traceback.format_exc()}"
            self.root.after(
                0,
                lambda: (
                    messagebox.showerror("Kitchen Fire", err),
                    self.status_label.config(text="Export didn't make it out of the kitchen.", fg=BAD_FG),
                    self.advanced_menu.entryconfig(0, state="normal"),
                ),
            )


def main():
    root = Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
