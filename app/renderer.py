"""Renders day HTML to final 3840x600 PNGs via headless Chromium + Lanczos downsample."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

from parser import DayMenu
from template import build_day_html

TARGET_W, TARGET_H = 3840, 600
SCALE = 4

# JS injected after render to detect any label/item that wrapped to 2+ lines.
WRAP_CHECK_JS = """
() => {
  const problems = [];
  document.querySelectorAll('.label, .item-cell').forEach(el => {
    const singleLineHeight = parseFloat(getComputedStyle(el).fontSize) * 1.3;
    if (el.offsetHeight > singleLineHeight * 1.6) {
      problems.push(el.textContent.trim());
    }
  });
  return problems;
}
"""


@dataclass
class RenderResult:
    day_name: str
    png_path: Path
    wrap_warnings: list[str]


class RenderValidationError(Exception):
    pass


def render_days(
    days: list[DayMenu],
    out_dir: Path,
    variant: str = "main",
    strict: bool = True,
) -> list[RenderResult]:
    out_dir.mkdir(parents=True, exist_ok=True)
    results: list[RenderResult] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            page = browser.new_page(
                viewport={"width": TARGET_W, "height": TARGET_H},
                device_scale_factor=SCALE,
            )
            for day in days:
                html_str = build_day_html(day, variant=variant)
                page.set_content(html_str, wait_until="load")
                page.evaluate("document.fonts.ready")

                wrap_problems = page.evaluate(WRAP_CHECK_JS)
                if wrap_problems and strict:
                    raise RenderValidationError(
                        f"{day.day_name}: text wrapped to multiple lines for: "
                        f"{', '.join(wrap_problems)}. Layout would ship broken — "
                        "widen the label column or shrink the font before exporting."
                    )

                date_tag = day.menu_date.strftime("%Y-%m-%d")
                png_path = out_dir / f"The_Cafe_Menu_{day.day_name}_{date_tag}.png"
                _screenshot_and_downsample(page, png_path)

                results.append(RenderResult(day.day_name, png_path, wrap_problems))
            page.close()
        finally:
            browser.close()

    return results


def _screenshot_and_downsample(page, out_path: Path) -> None:
    raw_bytes = page.screenshot()
    img = Image.open(__import__("io").BytesIO(raw_bytes))
    # Screenshot comes back at device_scale_factor * viewport size; crop/resize to exact target.
    resized = img.resize((TARGET_W, TARGET_H), Image.LANCZOS)
    resized.save(out_path, "PNG")


def render_preview_png_bytes(day: DayMenu, variant: str = "main") -> bytes:
    """Render a single day at 1x scale (no downsample) for on-screen preview only."""
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": TARGET_W, "height": TARGET_H})
            html_str = build_day_html(day, variant=variant)
            page.set_content(html_str, wait_until="load")
            page.evaluate("document.fonts.ready")
            png_bytes = page.screenshot()
        finally:
            browser.close()
    return png_bytes
