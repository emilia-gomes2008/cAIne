#!/usr/bin/env bash
# Builds a standalone Linux binary for the CAINE GUI.
# Run this ON Linux — PyInstaller does not cross-compile.
set -e
cd "$(dirname "$0")/.."

pip install -r requirements.txt -r requirements-build.txt

pyinstaller --name CAINE --onefile --windowed --noconfirm \
    --add-data "assets/caine_avatar.png:assets" \
    app/gui.py

echo
echo "Done: dist/CAINE"
echo "Ollama must still be installed and running separately — this binary"
echo "only bundles the Python app, not Ollama or the model weights."
