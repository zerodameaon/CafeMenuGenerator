#!/bin/bash
# Builds "The Cafe Menu Sign Generator.app" as a fully offline, double-clickable
# macOS app: bundles the Libre Franklin fonts and the Playwright Chromium binary
# inside the app so no network access is needed at runtime.
set -euo pipefail
cd "$(dirname "$0")"

source venv/bin/activate

CHROMIUM_DIR=$(python3 -c "
import playwright, os
from pathlib import Path
cache = Path.home() / 'Library' / 'Caches' / 'ms-playwright'
print(cache)
")

if [ ! -d "$CHROMIUM_DIR" ]; then
  echo "Playwright browsers not found at $CHROMIUM_DIR — run 'playwright install chromium' first." >&2
  exit 1
fi

if [ ! -f "app/AppIcon.icns" ]; then
  echo "app/AppIcon.icns not found — run 'python3 app/icon_src/make_icon.py' first." >&2
  exit 1
fi

rm -rf build dist

# Chromium is a nested .app bundle; PyInstaller's --add-data tries to
# re-codesign every Mach-O binary it collects, which fails on nested .app
# bundles. So we build without it and copy it in as a plain post-build step.
pyinstaller \
  --name "The Cafe Menu Sign Generator" \
  --windowed \
  --noconfirm \
  --icon "app/AppIcon.icns" \
  --add-data "app/fonts:fonts" \
  --add-data "app/brightsign_help:brightsign_help" \
  --hidden-import PIL._tkinter_finder \
  --hidden-import requests \
  app/app.py

APP="dist/The Cafe Menu Sign Generator.app"
# sys._MEIPASS resolves to Contents/Frameworks in a --windowed onedir .app
# bundle on macOS, not Contents/Resources — Chromium must land there for
# app.py's PLAYWRIGHT_BROWSERS_PATH bootstrap to find it.
FRAMEWORKS="$APP/Contents/Frameworks"

mkdir -p "$FRAMEWORKS/ms-playwright"
cp -R "$CHROMIUM_DIR"/. "$FRAMEWORKS/ms-playwright/"

# Playwright's internal ".links" bookkeeping dir under ms-playwright isn't
# a valid bundle/binary (only used by Playwright's own browser-download
# dedup, not needed at runtime here) — drop it so it can't confuse codesign.
find "$FRAMEWORKS/ms-playwright" -name ".links" -type d -exec rm -rf {} + 2>/dev/null || true

# Re-signing the whole tree (with or without --deep) reliably breaks on the
# nested Chromium.app + ffmpeg bundles inside ms-playwright, for reasons
# that vary by macOS/codesign version. Skip re-signing entirely: the
# downloaded Chromium already carries a valid Google signature, and the
# outer PyInstaller-built app was already ad-hoc signed by PyInstaller
# itself during the build above. Clearing the quarantine flag (below, or
# via the note printed at the end) is what actually lets it launch locally.
xattr -cr "$APP"

echo ""
echo "Built: $APP"
echo "This bundle includes Libre Franklin fonts and Chromium — it should run fully offline."
echo "Quarantine flag cleared for this build machine. If you copy the .app to another"
echo "Mac, run on that Mac: xattr -cr \"$APP\"  (or right-click > Open the first time)."
