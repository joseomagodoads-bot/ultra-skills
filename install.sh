#!/usr/bin/env bash
# Instala as skills Ultra no Claude Code e/ou no Codex.
#
#   bash install.sh            instala no Claude Code (~/.claude/skills) e no Codex (~/.codex/skills)
#   bash install.sh --claude   só Claude Code
#   bash install.sh --codex    só Codex
#   bash install.sh --projeto  só neste projeto (./.claude/skills e ./.codex/skills)
#
# Reinstalar sobrescreve as versões antigas destas skills e não mexe em outras.
set -euo pipefail

ORIGEM="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/skills"
ALVOS=()

case "${1:-}" in
  --claude)  ALVOS=("$HOME/.claude/skills") ;;
  --codex)   ALVOS=("$HOME/.codex/skills") ;;
  --projeto) ALVOS=("$PWD/.claude/skills" "$PWD/.codex/skills") ;;
  "")        ALVOS=("$HOME/.claude/skills" "$HOME/.codex/skills") ;;
  *) echo "Opção desconhecida: $1"; exit 1 ;;
esac

for alvo in "${ALVOS[@]}"; do
  mkdir -p "$alvo"
  for skill in "$ORIGEM"/*/; do
    nome="$(basename "$skill")"
    rm -rf "${alvo:?}/$nome"
    cp -R "$skill" "$alvo/$nome"
    chmod +x "$alvo/$nome"/scripts/*.py 2>/dev/null || true
  done
  echo "✔ skills instaladas em $alvo"
done

if ! command -v python3 >/dev/null 2>&1; then
  echo "⚠ python3 não encontrado: o scan-ultra precisa dele."
fi
if ! python3 -c "import playwright" >/dev/null 2>&1; then
  echo "ℹ Opcional, para sites em JavaScript e prints: pip install playwright && playwright install chromium"
fi
