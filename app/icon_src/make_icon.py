"""Renders a square app-icon PNG (burger + sushi roll on maroon, rounded)
and writes it out as app/AppIcon.icns. This is the Finder/Dock icon for the
packaged app only — the menu signs themselves have no logo on them."""
import subprocess
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

GOLD = "#ffc72c"
MAROON = "#6b2f20"

SVG_ICON = f"""
<svg width="1024" height="1024" viewBox="0 0 300 300" xmlns="http://www.w3.org/2000/svg">
  <rect width="300" height="300" rx="56" fill="{MAROON}"/>
  <g fill="none" stroke="{GOLD}" stroke-width="6" stroke-linecap="round" stroke-linejoin="round">
    <!-- burger, top half -->
    <path d="M70 100 Q70 40 150 40 Q230 40 230 100"/>
    <circle cx="112" cy="88" r="4.5" fill="{GOLD}" stroke="none"/>
    <circle cx="150" cy="78" r="4.5" fill="{GOLD}" stroke="none"/>
    <circle cx="188" cy="88" r="4.5" fill="{GOLD}" stroke="none"/>
    <path d="M65 118 Q95 103 125 118 T185 118 T245 118"/>
    <path d="M65 138 Q95 123 125 138 T185 138 T245 138"/>
    <path d="M62 155 L238 155"/>
    <path d="M62 155 Q62 178 90 178 L210 178 Q238 178 238 155"/>
    <!-- sushi roll, bottom half -->
    <circle cx="150" cy="240" r="55"/>
    <circle cx="150" cy="240" r="19" fill="{GOLD}" stroke="none"/>
    <circle cx="188" cy="240" r="4.5" fill="{GOLD}" stroke="none"/>
    <circle cx="177" cy="267" r="4.5" fill="{GOLD}" stroke="none"/>
    <circle cx="150" cy="278" r="4.5" fill="{GOLD}" stroke="none"/>
    <circle cx="123" cy="267" r="4.5" fill="{GOLD}" stroke="none"/>
    <circle cx="112" cy="240" r="4.5" fill="{GOLD}" stroke="none"/>
    <circle cx="123" cy="213" r="4.5" fill="{GOLD}" stroke="none"/>
    <circle cx="150" cy="202" r="4.5" fill="{GOLD}" stroke="none"/>
    <circle cx="177" cy="213" r="4.5" fill="{GOLD}" stroke="none"/>
  </g>
</svg>
"""

HTML = f"""<!DOCTYPE html>
<html><head><style>
html,body {{ margin:0; padding:0; width:1024px; height:1024px; background:transparent; }}
</style></head>
<body>{SVG_ICON}</body></html>"""


def main():
    out_dir = Path(__file__).parent
    png_path = out_dir / "icon_1024.png"

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1024, "height": 1024}, device_scale_factor=1)
        page.set_content(HTML, wait_until="load")
        page.screenshot(path=str(png_path), omit_background=True)
        browser.close()

    iconset_dir = out_dir / "AppIcon.iconset"
    iconset_dir.mkdir(exist_ok=True)

    sizes = [16, 32, 64, 128, 256, 512, 1024]
    for size in sizes:
        subprocess.run(
            ["sips", "-z", str(size), str(size), str(png_path),
             "--out", str(iconset_dir / f"icon_{size}x{size}.png")],
            check=True, capture_output=True,
        )
        if size <= 512:
            subprocess.run(
                ["sips", "-z", str(size * 2), str(size * 2), str(png_path),
                 "--out", str(iconset_dir / f"icon_{size}x{size}@2x.png")],
                check=True, capture_output=True,
            )

    icns_path = out_dir.parent / "AppIcon.icns"
    subprocess.run(
        ["iconutil", "-c", "icns", str(iconset_dir), "-o", str(icns_path)],
        check=True,
    )
    print(f"Wrote {icns_path}")


if __name__ == "__main__":
    main()
