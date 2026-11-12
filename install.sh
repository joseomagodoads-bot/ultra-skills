#!/usr/bin/env bash
# Instala as Ultra Skills (motor, skills e agentes) no Claude Code e/ou no Codex.
#
#   bash install.sh            Claude Code + Codex
#   bash install.sh --claude   só Claude Code
#   bash install.sh --codex    só Codex
#   bash install.sh --projeto  só neste projeto
#
# Este script só chama o install.py, que faz o trabalho em qualquer sistema.
set -euo pipefail
AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if command -v python3 >/dev/null 2>&1; then PY=python3
elif command -v python >/dev/null 2>&1; then PY=python
else echo "Precisa de Python 3.8+: https://www.python.org/downloads/"; exit 1; fi
exec "$PY" "$AQUI/install.py" "$@"
