#!/usr/bin/env bash
# Build the static preview site from the real dashboard, injecting the preview
# shim so /api/* calls are served from bundled sample data (no backend).
set -euo pipefail
cd "$(dirname "$0")"

SRC=../hub/dashboard
OUT=public

mkdir -p "$OUT/placeholders"
# Carry over the real dashboard assets verbatim.
cp "$SRC"/index.html "$SRC"/storyboard.html "$SRC"/styles.css "$SRC"/storyboard.css \
   "$SRC"/app.js "$SRC"/storyboard.js "$OUT"/
cp preview-shim.js "$OUT"/

# Inject the shim before the page scripts so it patches fetch first.
sed -i 's#<script src="app.js"></script>#<script src="preview-shim.js"></script>\n  <script src="app.js"></script>#' "$OUT/index.html"
sed -i 's#<script src="storyboard.js"></script>#<script src="preview-shim.js"></script>\n  <script src="storyboard.js"></script>#' "$OUT/storyboard.html"

echo "built $OUT/ from $SRC (shim injected)"
ls "$OUT"
