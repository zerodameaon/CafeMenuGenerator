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
# Chromium goes in Contents/Resources, not Contents/Frameworks. codesign
# treats everything under Frameworks as code that must itself be signed,
# and Chromium's folder also holds plain files (e.g. .js resources), so a
# bundle with Chromium under Frameworks can't be re-signed at all. Under
# Resources its files are simply hashed into the outer app's seal.
# app.py's PLAYWRIGHT_BROWSERS_PATH bootstrap looks for it here.
RESOURCES="$APP/Contents/Resources"

mkdir -p "$RESOURCES/ms-playwright"
cp -R "$CHROMIUM_DIR"/. "$RESOURCES/ms-playwright/"

# Playwright's internal ".links" bookkeeping dir under ms-playwright isn't
# needed at runtime (only used by Playwright's own browser-download dedup).
find "$RESOURCES/ms-playwright" -name ".links" -type d -exec rm -rf {} + 2>/dev/null || true

# Re-seal the app AFTER adding Chromium. PyInstaller ad-hoc signs the app
# during the build above, and copying anything in afterwards invalidates
# that signature — which a downloaded (quarantined) copy then reports as
# "is damaged and can't be opened", with no way past it but Terminal.
# A shallow (non --deep) ad-hoc re-sign seals the new files without trying
# to re-sign Chromium's own nested bundles (which --deep chokes on).
# Note: Playwright's Chromium builds are only ad-hoc (linker) signed, not
# Google-signed — app.py clears the quarantine flag on them at startup.
codesign --force --sign - "$APP"
if ! codesign --verify --deep --strict "$APP"; then
  echo "Signature check failed — a downloaded copy would show as 'damaged'. Not shipping this build." >&2
  exit 1
fi

xattr -cr "$APP"

echo ""
echo "Built: $APP (signature verified)"
echo "This bundle includes Libre Franklin fonts and Chromium — it doesn't need the internet."
echo "On another Mac, after unzipping, either run once in Terminal:"
echo "  xattr -cr \"/path/to/The Cafe Menu Sign Generator.app\""
echo "or open it, then System Settings > Privacy & Security > Open Anyway."
