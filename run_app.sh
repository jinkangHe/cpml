#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"
PYTHON_BIN="$VENV_DIR/bin/python"
PLUGIN_PATH="$VENV_DIR/lib/python3.12/site-packages/PyQt5/Qt5/plugins"
export QT_QPA_PLATFORM_PLUGIN_PATH="$PLUGIN_PATH"
exec "$PYTHON_BIN" "$SCRIPT_DIR/app.py"