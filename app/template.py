"""Builds a self-contained HTML string for one day's menu sign."""
from __future__ import annotations

import base64
import html
import sys
from pathlib import Path

from parser import DayMenu

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


def _day_type(day_name: str) -> str:
    if day_name == "Friday":
        return "friday"
    if day_name == "Wednesday":
        return "wednesday"
    return "standard"


def _font_face_css() -> str:
    def b64(fname: str) -> str:
        return base64.b64encode((FONTS_DIR / fname).read_bytes()).decode("ascii")

    roman = b64("LibreFranklin[wght].ttf")
    italic = b64("LibreFranklin-Italic[wght].ttf")
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
}}
"""


def build_day_html(day: DayMenu, variant: str = "main") -> str:
    sizing = DAY_TYPE_SIZING[_day_type(day.day_name)]

    if variant == "alt":
        bg = "#a7bdc7"
        brand_text = "#6b2f20"
        gold = "#f5be1f"
        muted = "#8b93a0"
        gold_text_shadow = "text-shadow: 1px 0 #3d1b12, -1px 0 #3d1b12, 0 1px #3d1b12, 0 -1px #3d1b12;"
        divider = "rgba(61,27,18,0.14)"
        row_divider = "rgba(61,27,18,0.12)"
        emphasis_bg = "rgba(107,47,32,0.09)"
    else:
        bg = "#6b2f20"
        brand_text = "#a7bdc7"
        gold = "#ffc72c"
        muted = "#8b93a0"
        gold_text_shadow = ""
        divider = "rgba(241,239,232,0.14)"
        row_divider = "rgba(241,239,232,0.12)"
        emphasis_bg = "rgba(171,138,88,0.09)"

    date_str = day.menu_date.strftime("%B %-d, %Y").upper()

    rows_html = []
    for row in day.rows:
        label_color = muted if row.muted else gold
        item_font = sizing["item_emphasis"] if row.emphasis else sizing["item_normal"]
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
{_font_face_css()}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
html, body {{
  width: 3840px; height: 600px;
  background: {bg};
  font-family: 'Libre Franklin', sans-serif;
  overflow: hidden;
}}
.canvas {{ display: flex; width: 3840px; height: 600px; }}
.brand {{
  width: 660px; flex-shrink: 0;
  padding: 40px 0 32px 56px;
  border-right: 1px solid {divider};
  display: flex; flex-direction: column;
}}
.logo {{
  font-weight: 600; font-size: 92px; line-height: 0.95; letter-spacing: -0.01em;
}}
.logo .the {{ color: {brand_text}; }}
.logo .cafe {{ color: {gold}; {gold_text_shadow} }}
.subtitle {{
  font-style: italic; font-weight: 600; font-size: 36px; color: {muted};
  letter-spacing: 0.04em; margin-top: 10px;
}}
.spacer {{ flex: 1; }}
.day-name {{ font-weight: 600; font-size: 56px; color: {brand_text}; line-height: 1; }}
.date {{
  font-weight: 600; font-size: 29px; color: {gold}; letter-spacing: 0.11em;
  text-transform: uppercase; margin-top: 8px; {gold_text_shadow}
}}
.menu {{
  flex: 1;
  padding: 40px 64px 32px 64px;
  display: flex; flex-direction: column;
}}
.row {{ display: flex; align-items: stretch; }}
.row-inner {{
  display: grid; grid-template-columns: 360px 1fr; gap: 32px; align-items: center;
  width: 100%;
  border-top: 1px solid {row_divider};
}}
.row:first-child .row-inner {{ border-top: none; }}
.row.emphasis .row-inner {{
  background: {emphasis_bg};
  margin: 0 -32px; padding: 0 32px; width: calc(100% + 64px);
}}
.label-cell {{ display: flex; align-items: center; }}
.dot {{
  width: 14px; height: 14px; border-radius: 50%; background: {brand_text};
  margin-right: 14px; flex-shrink: 0;
}}
.label {{ font-size: {sizing["label_font"]}px; letter-spacing: {sizing["label_ls"]}; font-weight: 600; text-transform: uppercase; }}
.item-cell {{ color: {brand_text}; text-align: center; }}
</style>
</head>
<body>
<div class="canvas">
  <div class="brand">
    <div class="logo"><span class="the">THE </span><span class="cafe">CAFE</span></div>
    <div class="subtitle">— Daily Menu —</div>
    <div class="spacer"></div>
    <div class="day-name">{html.escape(day.day_name)}</div>
    <div class="date">{date_str}</div>
  </div>
  <div class="menu">
    {"".join(rows_html)}
  </div>
</div>
</body>
</html>"""
