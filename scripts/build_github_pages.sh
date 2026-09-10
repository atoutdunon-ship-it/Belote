#!/usr/bin/env bash
# Produit les fichiers statiques que GitHub Pages doit servir a la racine du depot.
set -euo pipefail

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
ASSETS=(
  index.html
  app.js
  styles.css
  manifest.webmanifest
  service-worker.js
  runtime-config.js
  icon.svg
  icon-192.png
  icon-512.png
  apple-touch-icon.png
)

for asset in "${ASSETS[@]}"; do
  cp "$ROOT/web/$asset" "$ROOT/$asset"
done
: > "$ROOT/.nojekyll"
printf 'GitHub Pages files updated at %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
