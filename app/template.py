"""Builds a self-contained HTML string for one day's menu sign."""
from __future__ import annotations

import base64
import html
import sys
from datetime import date
from pathlib import Path

from decorations import decorations_html
from parser import DayMenu, format_month_day

if getattr(sys, "frozen", False):
    FONTS_DIR = Path(sys._MEIPASS) / "fonts"
else:
    FONTS_DIR = Path(__file__).parent / "fonts"

# (label_col_px, letter_spacing_label, item_font_normal, item_font_emphasis, emphasis_flex)
DAY_TYPE_SIZING = {
    "standard": dict(label_font=26, label_ls="0.11em", item_normal=42, item_emphasis=54, emphasis_flex=1.4),
    "friday": dict(label_font=26, label_ls="0.11em", item_normal=44, item_emphasis=56, emphasis_flex=1.5),
    "wednesday": dict(label_font=25, label_ls="0.10em", item_normal=36, item_emphasis=48, emphasis_flex=1.3),
}

_FRANKLIN = "'Libre Franklin', sans-serif"

# Colors and fonts per design variant. Holiday themes are just more entries
# here, plus (optionally) their own decorations in decorations.py.
THEMES = {
    "main": dict(
        bg="#6b2f20", brand_text="#a7bdc7", gold="#ffc72c", muted="#8b93a0",
        gold_text_shadow="",
        divider="rgba(241,239,232,0.14)", row_divider="rgba(241,239,232,0.12)",
        emphasis_bg="rgba(171,138,88,0.09)",
        subtitle="— Daily Menu —",
        display_font=_FRANKLIN, body_font=_FRANKLIN,
    ),
    "alt": dict(
        bg="#a7bdc7", brand_text="#6b2f20", gold="#f5be1f", muted="#8b93a0",
        gold_text_shadow="text-shadow: 1px 0 #3d1b12, -1px 0 #3d1b12, 0 1px #3d1b12, 0 -1px #3d1b12;",
        divider="rgba(61,27,18,0.14)", row_divider="rgba(61,27,18,0.12)",
        emphasis_bg="rgba(107,47,32,0.09)",
        subtitle="— Daily Menu —",
        display_font=_FRANKLIN, body_font=_FRANKLIN,
    ),
    # Night-sky purple, pumpkin orange and bone white, with Nosifer (letters
    # that drip blood) on everything. It's wide and all-caps, so the labels
    # and items are scaled down to fit without wrapping.
    "halloween": dict(
        bg="#17111f", brand_text="#efe3c8", gold="#ff7a1a", muted="#9a8fb0",
        gold_text_shadow="text-shadow: 0 0 18px rgba(255,122,26,0.45);",
        divider="rgba(255,122,26,0.22)", row_divider="rgba(239,227,200,0.10)",
        emphasis_bg="rgba(255,122,26,0.10)",
        subtitle="— Happy Halloween —",
        display_font="'Nosifer', cursive", body_font="'Nosifer', cursive",
        date_font="'Nosifer', cursive",
        extra_fonts=("Nosifer-Regular.ttf",),
        label_scale=0.8, item_scale=0.72, dot="#ff7a1a",
        # The logo, day name and CLOSED "bleed" in red.
        heading_font="'Nosifer', cursive", bleed="#d81b22",
        bleed_shadow="text-shadow: 0 0 16px rgba(216,27,34,0.35);",
    ),
    # Roasted-chestnut brown, harvest amber, cream and cranberry. Rye
    # (wood-type, county-fair poster) for the logo, day name and labels;
    # Bree Serif for menu items, a warm slab that stays easy to read.
    "thanksgiving": dict(
        bg="#2a1a11", brand_text="#f6e7cb", gold="#f2a33a", muted="#b49a7c",
        gold_text_shadow="",
        divider="rgba(242,163,58,0.22)", row_divider="rgba(246,231,203,0.10)",
        emphasis_bg="rgba(242,163,58,0.09)",
        subtitle="— Happy Thanksgiving —",
        display_font="'Rye', serif", body_font="'BreeSerif', serif",
        extra_fonts=("Rye-Regular.ttf", "BreeSerif-Regular.ttf"),
        dot="#c2412d", bleed="#e0662a",
    ),
    # Navy, white, brass and flag red. Stardos Stencil (military stencil
    # lettering) for the logo, day name, labels and CLOSED; menu items stay
    # in Libre Franklin so they're as easy to read as the everyday sign.
    "veterans": dict(
        bg="#13203a", brand_text="#f4f1ea", gold="#d9b45a", muted="#8f9ab0",
        gold_text_shadow="",
        divider="rgba(244,241,234,0.16)", row_divider="rgba(244,241,234,0.10)",
        emphasis_bg="rgba(217,180,90,0.09)",
        subtitle="— Honoring Our Veterans —",
        display_font="'StardosStencil', serif", body_font=_FRANKLIN,
        extra_fonts=("StardosStencil-Bold.ttf",),
        dot="#d63a43", bleed="#e04a52",
    ),
    # Evergreen, holly red, tinsel gold and snow white. Mountains of
    # Christmas (storybook lettering) for the logo, day name, labels and
    # CLOSED; Libre Franklin for the items, since it's too frilly for them.
    "christmas": dict(
        bg="#0f2a1d", brand_text="#f7f2e6", gold="#e6c15a", muted="#93ab9b",
        gold_text_shadow="",
        divider="rgba(230,193,90,0.22)", row_divider="rgba(247,242,230,0.10)",
        emphasis_bg="rgba(230,193,90,0.08)",
        subtitle="— Merry Christmas —",
        display_font="'MountainsofChristmas', cursive", body_font=_FRANKLIN,
        extra_fonts=("MountainsofChristmas-Bold.ttf",),
        label_scale=1.2, dot="#d8333a", bleed="#e0444a",
    ),
    # Midnight, champagne and gold, like a New Year's Eve party invite.
    # Limelight (1920s Art Deco) for the logo, day name, labels and CLOSED;
    # Libre Franklin for the items.
    "newyear": dict(
        bg="#0d0d17", brand_text="#f5ecd7", gold="#e8c766", muted="#9a96a8",
        gold_text_shadow="text-shadow: 0 0 14px rgba(232,199,102,0.35);",
        divider="rgba(232,199,102,0.25)", row_divider="rgba(245,236,215,0.10)",
        emphasis_bg="rgba(232,199,102,0.08)",
        subtitle="— Happy New Year —",
        display_font="'Limelight', serif", body_font=_FRANKLIN,
        extra_fonts=("Limelight-Regular.ttf",),
        dot="#e8c766",
    ),
    # The rest follow the same pattern: a display font for the logo, day
    # name, labels and CLOSED, and Libre Franklin for the items unless the
    # display font is easy enough to read at item size.
    # Deep blue, silver-blue and candle gold; Suez One's heavy serif.
    "hanukkah": dict(
        bg="#0f2350", brand_text="#f3f6fb", gold="#a9c8ff", muted="#8d9cc0",
        gold_text_shadow="",
        divider="rgba(169,200,255,0.22)", row_divider="rgba(243,246,251,0.10)",
        emphasis_bg="rgba(169,200,255,0.08)",
        subtitle="— Happy Hanukkah —",
        display_font="'SuezOne', serif", body_font=_FRANKLIN,
        extra_fonts=("SuezOne-Regular.ttf",), dot="#e9c46a",
    ),
    # Quiet and dignified: slate and warm gold, DM Serif Display, a sunrise.
    "mlk": dict(
        bg="#1b2130", brand_text="#f3efe6", gold="#d8b25c", muted="#8e97a8",
        gold_text_shadow="",
        divider="rgba(216,178,92,0.20)", row_divider="rgba(243,239,230,0.10)",
        emphasis_bg="rgba(216,178,92,0.08)",
        subtitle="— Honoring Dr. King —",
        display_font="'DMSerifDisplay', serif", body_font=_FRANKLIN,
        extra_fonts=("DMSerifDisplay-Regular.ttf",),
    ),
    # Lucky red and gold, Abril Fatface, lanterns and plum blossoms.
    "lunarnewyear": dict(
        bg="#7a1014", brand_text="#fbeed3", gold="#f2c14e", muted="#e0a39a",
        gold_text_shadow="",
        divider="rgba(242,193,78,0.28)", row_divider="rgba(251,238,211,0.14)",
        emphasis_bg="rgba(242,193,78,0.10)",
        subtitle="— Happy Lunar New Year —",
        display_font="'AbrilFatface', serif", body_font=_FRANKLIN,
        extra_fonts=("AbrilFatface-Regular.ttf",), dot="#f2c14e",
    ),
    # Purple, green and gold. Fascinate (carnival Art Deco) is too ornate
    # for the labels, so they're in Abril Fatface.
    "mardigras": dict(
        bg="#2a0f3d", brand_text="#f5ead2", gold="#f2c230", muted="#a891bf",
        gold_text_shadow="",
        divider="rgba(242,194,48,0.24)", row_divider="rgba(245,234,210,0.10)",
        emphasis_bg="rgba(76,194,106,0.10)",
        subtitle="— Happy Mardi Gras —",
        display_font="'AbrilFatface', serif", body_font=_FRANKLIN,
        extra_fonts=("Fascinate-Regular.ttf", "AbrilFatface-Regular.ttf"),
        heading_font="'Fascinate', cursive", dot="#4cc26a", bleed="#4cc26a",
    ),
    # Deep berry, pinks and cream. Pacifico script for the logo and day
    # name; DM Serif Display for the labels, since script caps are hard to read.
    "valentines": dict(
        bg="#3d0d1f", brand_text="#fbe7ec", gold="#f48fb1", muted="#c08a9a",
        gold_text_shadow="",
        divider="rgba(244,143,177,0.24)", row_divider="rgba(251,231,236,0.10)",
        emphasis_bg="rgba(244,143,177,0.09)",
        subtitle="— Happy Valentine's Day —",
        display_font="'DMSerifDisplay', serif", body_font=_FRANKLIN,
        extra_fonts=("Pacifico-Regular.ttf", "DMSerifDisplay-Regular.ttf"),
        heading_font="'Pacifico', cursive", dot="#e2365b", bleed="#ff5c7a",
    ),
    # Navy and parchment, IM Fell English SC (18th-century printing), an
    # arch of thirteen stars.
    "presidents": dict(
        bg="#1a2547", brand_text="#f2ead8", gold="#cfa94e", muted="#98a1bb",
        gold_text_shadow="",
        divider="rgba(207,169,78,0.22)", row_divider="rgba(242,234,216,0.10)",
        emphasis_bg="rgba(207,169,78,0.08)",
        subtitle="— Happy Presidents' Day —",
        display_font="'IMFellEnglishSC', serif", body_font=_FRANKLIN,
        extra_fonts=("IMFellEnglishSC-Regular.ttf",), dot="#b8323a",
    ),
    # Shamrock green and pot-of-gold yellow, Uncial Antiqua (Celtic).
    "stpatricks": dict(
        bg="#0c3a24", brand_text="#f3f0dc", gold="#f2c94c", muted="#8fb59c",
        gold_text_shadow="",
        divider="rgba(242,201,76,0.22)", row_divider="rgba(243,240,220,0.10)",
        emphasis_bg="rgba(63,191,106,0.10)",
        subtitle="— Happy St. Patrick's Day —",
        display_font="'UncialAntiqua', serif", body_font=_FRANKLIN,
        extra_fonts=("UncialAntiqua-Regular.ttf",), dot="#3fbf6a",
    ),
    # The one light design: lilac with plum text and raspberry labels,
    # Sniglet's rounded letters, pastel eggs.
    "easter": dict(
        bg="#f4eef8", brand_text="#3d2c5c", gold="#c2457f", muted="#8a7fa3",
        gold_text_shadow="",
        divider="rgba(61,44,92,0.14)", row_divider="rgba(61,44,92,0.10)",
        emphasis_bg="rgba(194,69,127,0.08)",
        subtitle="— Happy Easter —",
        display_font="'Sniglet', sans-serif", body_font=_FRANKLIN,
        extra_fonts=("Sniglet-ExtraBold.ttf",), dot="#7bbf8e",
    ),
    # Deep teal with bright papel picado colors, Lilita One.
    "cincodemayo": dict(
        bg="#123b3f", brand_text="#fff4e0", gold="#ffb627", muted="#8fb3b2",
        gold_text_shadow="",
        divider="rgba(255,182,39,0.24)", row_divider="rgba(255,244,224,0.10)",
        emphasis_bg="rgba(255,79,129,0.09)",
        subtitle="— ¡Feliz Cinco de Mayo! —",
        display_font="'LilitaOne', sans-serif", body_font=_FRANKLIN,
        extra_fonts=("LilitaOne-Regular.ttf",), dot="#ff4f81", bleed="#ff4f81",
    ),
    # Plum and blush, DM Serif Display italic for the logo and day name.
    "mothers": dict(
        bg="#3a1e30", brand_text="#fbeef0", gold="#f2a7b8", muted="#b893a6",
        gold_text_shadow="",
        divider="rgba(242,167,184,0.22)", row_divider="rgba(251,238,240,0.10)",
        emphasis_bg="rgba(242,167,184,0.08)",
        subtitle="— Happy Mother's Day —",
        display_font="'DMSerifDisplay', serif", body_font=_FRANKLIN,
        extra_fonts=("DMSerifDisplayItalic-Regular.ttf", "DMSerifDisplay-Regular.ttf"),
        heading_font="'DMSerifDisplayItalic', serif", dot="#9cc5a1",
    ),
    # Solemn: dark navy, DM Serif Display, three red poppies.
    "memorial": dict(
        bg="#151d2e", brand_text="#f1eee8", gold="#c9a75a", muted="#8b94a7",
        gold_text_shadow="",
        divider="rgba(241,238,232,0.16)", row_divider="rgba(241,238,232,0.10)",
        emphasis_bg="rgba(201,167,90,0.08)",
        subtitle="— We Remember —",
        display_font="'DMSerifDisplay', serif", body_font=_FRANKLIN,
        extra_fonts=("DMSerifDisplay-Regular.ttf",), dot="#c0283a",
    ),
    # Slate and tan, Alfa Slab One, neckties.
    "fathers": dict(
        bg="#1f2a33", brand_text="#f0e9dc", gold="#e3a857", muted="#8d9aa5",
        gold_text_shadow="",
        divider="rgba(227,168,87,0.22)", row_divider="rgba(240,233,220,0.10)",
        emphasis_bg="rgba(227,168,87,0.08)",
        subtitle="— Happy Father's Day —",
        display_font="'AlfaSlabOne', serif", body_font=_FRANKLIN,
        extra_fonts=("AlfaSlabOne-Regular.ttf",), dot="#5d8fb8",
    ),
    # The Juneteenth flag's colors and star, Abril Fatface.
    "juneteenth": dict(
        bg="#13224a", brand_text="#f6f2ea", gold="#e9b949", muted="#97a2bf",
        gold_text_shadow="",
        divider="rgba(246,242,234,0.16)", row_divider="rgba(246,242,234,0.10)",
        emphasis_bg="rgba(212,52,63,0.10)",
        subtitle="— Celebrating Freedom —",
        display_font="'AbrilFatface', serif", body_font=_FRANKLIN,
        extra_fonts=("AbrilFatface-Regular.ttf",), dot="#d4343f", bleed="#e0444f",
    ),
    # Navy, firework red and white, Bungee's bold block letters.
    "july4": dict(
        bg="#0f1d3d", brand_text="#f7f4ee", gold="#f1c24b", muted="#95a1bd",
        gold_text_shadow="",
        divider="rgba(247,244,238,0.16)", row_divider="rgba(247,244,238,0.10)",
        emphasis_bg="rgba(230,57,70,0.10)",
        subtitle="— Happy Fourth of July —",
        display_font="'Bungee', sans-serif", body_font=_FRANKLIN,
        extra_fonts=("Bungee-Regular.ttf",), dot="#e63946", bleed="#ff4d57",
    ),
    # Denim and safety yellow, Staatliches (condensed workwear lettering),
    # gears.
    "labor": dict(
        bg="#1e2b3a", brand_text="#f2efe8", gold="#f5b82e", muted="#8e9bab",
        gold_text_shadow="",
        divider="rgba(245,184,46,0.22)", row_divider="rgba(242,239,232,0.10)",
        emphasis_bg="rgba(245,184,46,0.08)",
        subtitle="— Happy Labor Day —",
        display_font="'Staatliches', sans-serif", body_font=_FRANKLIN,
        extra_fonts=("Staatliches-Regular.ttf",), label_scale=1.2, dot="#f5b82e",
    ),
}


def _day_type(day_name: str) -> str:
    if day_name == "Friday":
        return "friday"
    if day_name == "Wednesday":
        return "wednesday"
    return "standard"


# The panel shows each day's image for a whole day, so the fixed lines
# (brand divider, row dividers, label column) would otherwise sit on the
# same pixels day after day and risk LCD image retention. Nudge the brand
# and menu columns a few pixels per sign, cycling by date so a weekday also
# lands somewhere different from one week to the next. Too small to notice
# on the sign; the padding absorbs it. Decorations don't move, so the ones
# anchored to the panel edge stay flush with it.
_RETENTION_SHIFTS = ((0, 0), (6, 4), (-6, 4), (-6, -4), (6, -4))


def _retention_shift(menu_date: date) -> tuple[int, int]:
    return _RETENTION_SHIFTS[menu_date.toordinal() % len(_RETENTION_SHIFTS)]


def _font_face_css(extra_fonts: tuple[str, ...] = ()) -> str:
    def b64(fname: str) -> str:
        return base64.b64encode((FONTS_DIR / fname).read_bytes()).decode("ascii")

    roman = b64("LibreFranklin[wght].ttf")
    italic = b64("LibreFranklin-Italic[wght].ttf")
    # Static single-weight fonts; the family name is the file name's prefix.
    extra = "".join(f"""
@font-face {{
  font-family: '{fname.split("-")[0]}';
  src: url(data:font/ttf;base64,{b64(fname)}) format('truetype');
  font-display: block;
}}""" for fname in extra_fonts)
    return f"""
@font-face {{
  font-family: 'Libre Franklin';
  src: url(data:font/ttf;base64,{roman}) format('truetype-variations');
  font-weight: 100 900;
  font-style: normal;
  font-display: block;
}}
@font-face {{
  font-family: 'Libre Franklin';
  src: url(data:font/ttf;base64,{italic}) format('truetype-variations');
  font-weight: 100 900;
  font-style: italic;
  font-display: block;
}}{extra}
"""


def _base_css(t: dict, day: DayMenu) -> str:
    """Page + brand column CSS shared by the menu and CLOSED layouts."""
    dx, dy = _retention_shift(day.menu_date)
    return f"""
{_font_face_css(t.get("extra_fonts", ()))}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
html, body {{
  width: 3840px; height: 600px;
  background: {t["bg"]};
  font-family: {t["body_font"]};
  overflow: hidden;
  font-synthesis: none;
}}
.canvas {{ display: flex; width: 3840px; height: 600px; }}
.brand {{
  width: 660px; flex-shrink: 0;
  padding: 40px 0 32px 56px;
  border-right: 1px solid {t["divider"]};
  display: flex; flex-direction: column;
}}
.logo {{
  font-family: {t.get("heading_font", t["display_font"])};
  font-weight: 600; font-size: 92px; line-height: 0.95; letter-spacing: -0.01em;
}}
.logo .the {{ color: {t["brand_text"]}; }}
.logo .cafe {{ color: {t.get("bleed", t["gold"])}; {t.get("bleed_shadow", t["gold_text_shadow"])} }}
.subtitle {{
  font-style: italic; font-weight: 600; font-size: 36px; color: {t["muted"]};
  letter-spacing: 0.04em; margin-top: 10px;
}}
.brand, .menu {{ transform: translate({dx}px, {dy}px); }}
.spacer {{ flex: 1; }}
.day-name {{
  font-family: {t.get("heading_font", t["display_font"])};
  font-weight: 600; font-size: 56px; color: {t.get("bleed", t["brand_text"])}; line-height: 1;
  {t.get("bleed_shadow", "")}
}}
.date {{
  font-family: {t.get("date_font", _FRANKLIN)};
  font-weight: 600; font-size: 29px; color: {t["gold"]}; letter-spacing: 0.11em;
  text-transform: uppercase; margin-top: 8px; {t["gold_text_shadow"]}
}}
"""


def _brand_html(day: DayMenu, t: dict) -> str:
    date_str = format_month_day(day.menu_date).upper()
    return f"""
  <div class="brand">
    <div class="logo"><span class="the">THE </span><span class="cafe">CAFE</span></div>
    <div class="subtitle">{html.escape(t["subtitle"])}</div>
    <div class="spacer"></div>
    <div class="day-name">{html.escape(day.day_name)}</div>
    <div class="date">{date_str}</div>
  </div>"""


def build_day_html(day: DayMenu, variant: str = "main") -> str:
    sizing = DAY_TYPE_SIZING[_day_type(day.day_name)]
    t = THEMES.get(variant, THEMES["main"])
    gold = t["gold"]
    gold_text_shadow = t["gold_text_shadow"]
    deco_css, deco_html = decorations_html(variant, t)

    if day.closed:
        closed_html = f"""
    <div class="closed">
      <div class="closed-label" style="color:{t.get("bleed", gold)};{t.get("bleed_shadow", gold_text_shadow)}">CLOSED</div>
      <div class="closed-reason" style="color:{t["brand_text"]}">{html.escape(day.closed_reason)}</div>
    </div>"""
        return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
{_base_css(t, day)}
.menu {{
  flex: 1;
  padding: 40px 64px 32px 64px;
  display: flex; flex-direction: column;
  align-items: center; justify-content: center;
}}
.closed {{ text-align: center; }}
.closed-label {{ font-family: {t.get("heading_font", t["display_font"])}; font-weight: 600; font-size: 88px; letter-spacing: 0.11em; }}
.closed-reason {{ font-style: italic; font-weight: 600; font-size: 38px; margin-top: 16px; }}
{deco_css}
</style>
</head>
<body>
<div class="canvas">
  {deco_html}
  {_brand_html(day, t)}
  <div class="menu">
    {closed_html}
  </div>
</div>
</body>
</html>"""

    rows_html = []
    for row in day.rows:
        label_color = t["muted"] if row.muted else gold
        item_font = round((sizing["item_emphasis"] if row.emphasis else sizing["item_normal"])
                          * t.get("item_scale", 1))
        flex = sizing["emphasis_flex"] if row.emphasis else 1
        row_class = "row emphasis" if row.emphasis else "row"
        label_style = f"color:{label_color};{gold_text_shadow if not row.muted else ''}"
        rows_html.append(f"""
        <div class="{row_class}" style="flex:{flex};">
          <div class="row-inner">
            <div class="label-cell">
              <span class="dot"></span>
              <span class="label" style="{label_style}">{html.escape(row.label).upper()}</span>
            </div>
            <div class="item-cell" style="font-size:{item_font}px; font-weight:{600 if row.emphasis else 400};">
              {html.escape(row.item)}
            </div>
          </div>
        </div>""")

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
{_base_css(t, day)}
.menu {{
  flex: 1;
  padding: 40px 64px 32px 64px;
  display: flex; flex-direction: column;
}}
.row {{ display: flex; align-items: stretch; }}
.row-inner {{
  display: grid; grid-template-columns: 360px 1fr; gap: 32px; align-items: center;
  width: 100%;
  border-top: 1px solid {t["row_divider"]};
}}
.row:first-child .row-inner {{ border-top: none; }}
.row.emphasis .row-inner {{
  background: {t["emphasis_bg"]};
  margin: 0 -32px; padding: 0 32px; width: calc(100% + 64px);
}}
.label-cell {{ display: flex; align-items: center; }}
.dot {{
  width: 14px; height: 14px; border-radius: 50%; background: {t.get("dot", t["brand_text"])};
  margin-right: 14px; flex-shrink: 0;
}}
.label {{
  font-family: {t["display_font"]};
  font-size: {round(sizing["label_font"] * t.get("label_scale", 1))}px; letter-spacing: {sizing["label_ls"]}; font-weight: 600; text-transform: uppercase;
}}
.item-cell {{ color: {t["brand_text"]}; text-align: center; }}
{deco_css}
</style>
</head>
<body>
<div class="canvas">
  {deco_html}
  {_brand_html(day, t)}
  <div class="menu">
    {"".join(rows_html)}
  </div>
</div>
</body>
</html>"""
