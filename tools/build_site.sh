#!/usr/bin/env bash
# Assemble the static site into _site/. Used by both the Pages deploy and the
# weekly sweep, so the two cannot drift apart.
set -euo pipefail
cd "$(dirname "$0")/.."
rm -rf _site
mkdir -p _site
cp index.html app.js style.css _site/
cp -r data _site/data
python3 tools/build_sqlite.py --out _site/directory.db
echo "assembled:"
ls -la _site
