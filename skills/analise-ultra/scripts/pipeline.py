#!/usr/bin/env python3
"""
pipeline.py: atalho para o motor ultra.py (mantido por compatibilidade).

  python3 pipeline.py iniciar URL --concorrentes A B [--print]
  python3 pipeline.py proximo [--pasta P] [--json]
  python3 pipeline.py status [--pasta P]
"""

import subprocess
import sys
from pathlib import Path

AQUI = Path(__file__).resolve()
CANDIDATOS = [
    AQUI.parents[3] / "nucleo" / "ultra.py",
    AQUI.parent.parent / "ultra.py",
    Path.home() / ".ultra-skills" / "ultra.py",
]


def main():
    ultra = next((c for c in CANDIDATOS if c.exists()), None)
    if not ultra:
        sys.exit("ultra.py não encontrado. Rode o install.py do repositório Ultra Skills.")
    sys.exit(subprocess.call([sys.executable, str(ultra), *sys.argv[1:]]))


if __name__ == "__main__":
    main()
