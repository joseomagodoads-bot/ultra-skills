#!/usr/bin/env python3
"""
Instala as Ultra Skills no Claude Code e/ou no Codex. Funciona em Windows, macOS e Linux.

  python install.py            Claude Code (~/.claude/skills) + Codex (~/.codex/skills)
  python install.py --claude   só Claude Code
  python install.py --codex    só Codex
  python install.py --projeto  só no projeto atual (./.claude/skills e ./.codex/skills)

No Windows, se "python" não funcionar, use "py install.py".
"""

import shutil
import sys
from pathlib import Path


def main():
    for fluxo in (sys.stdout, sys.stderr):
        try:
            fluxo.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    origem = Path(__file__).resolve().parent / "skills"
    casa = Path.home()
    opcao = sys.argv[1] if len(sys.argv) > 1 else ""
    alvos = {
        "": [casa / ".claude" / "skills", casa / ".codex" / "skills"],
        "--claude": [casa / ".claude" / "skills"],
        "--codex": [casa / ".codex" / "skills"],
        "--projeto": [Path.cwd() / ".claude" / "skills", Path.cwd() / ".codex" / "skills"],
    }.get(opcao)
    if alvos is None:
        sys.exit(f"Opção desconhecida: {opcao}. Use --claude, --codex ou --projeto.")
    if sys.version_info < (3, 8):
        sys.exit("Precisa de Python 3.8 ou mais novo.")

    for alvo in alvos:
        alvo.mkdir(parents=True, exist_ok=True)
        for skill in sorted(p for p in origem.iterdir() if p.is_dir()):
            destino = alvo / skill.name
            if destino.exists():
                shutil.rmtree(destino)
            shutil.copytree(skill, destino, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        print(f"OK: skills instaladas em {alvo}")

    faltando = []
    for mod, uso in (("reportlab", "PDF do mega-plano (sem ele sai HTML)"),
                     ("playwright", "ler sites em JavaScript (sem ele usa o Chrome/Edge do computador)"),
                     ("certifi", "certificados no macOS")):
        try:
            __import__(mod)
        except ImportError:
            faltando.append(f"  pip install {mod:<10}  # {uso}")
    if faltando:
        print("\nOpcionais (nada é obrigatório):")
        print("\n".join(faltando))
    print("\nPronto. Peça para a IA: \"faz uma análise ultra do https://seusite.com\"")


if __name__ == "__main__":
    main()
