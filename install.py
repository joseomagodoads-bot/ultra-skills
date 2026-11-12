#!/usr/bin/env python3
"""
Instala as Ultra Skills: o motor, as skills e os 24 agentes. Funciona em Windows, macOS e Linux.

  python install.py            Claude Code + Codex
  python install.py --claude   só Claude Code
  python install.py --codex    só Codex
  python install.py --projeto  skills e agentes só no projeto atual (./.claude e ./.codex)

O que vai para onde:
  motor e parâmetros  ~/.ultra-skills/        (ultra.py, params/, scripts/)
  skills              ~/.claude/skills/  ~/.codex/skills/  ~/.agents/skills/
  agentes             ~/.claude/agents/*.md  ~/.codex/agents/*.toml

No Windows, se "python" não funcionar, use "py install.py".
Reinstalar sobrescreve só os arquivos das Ultra Skills; o resto fica como está.
"""

import shutil
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
IGNORAR = shutil.ignore_patterns("__pycache__", "*.pyc")


def copiar_pasta(origem: Path, destino: Path):
    if destino.exists():
        shutil.rmtree(destino)
    shutil.copytree(origem, destino, ignore=IGNORAR)


def instalar_motor(casa: Path) -> Path:
    motor = casa / ".ultra-skills"
    motor.mkdir(parents=True, exist_ok=True)
    shutil.copy2(RAIZ / "nucleo" / "ultra.py", motor / "ultra.py")
    copiar_pasta(RAIZ / "nucleo" / "params", motor / "params")
    scripts = motor / "scripts"
    scripts.mkdir(exist_ok=True)
    for s in RAIZ.glob("skills/*/scripts/*.py"):
        if s.name != "pipeline.py":
            shutil.copy2(s, scripts / s.name)
    print(f"OK: motor e parâmetros em {motor}")
    return motor


def instalar_skills(alvos):
    for alvo in alvos:
        alvo.mkdir(parents=True, exist_ok=True)
        for skill in sorted(p for p in (RAIZ / "skills").iterdir() if p.is_dir()):
            copiar_pasta(skill, alvo / skill.name)
        print(f"OK: skills em {alvo}")


def instalar_agentes(origem: Path, destino: Path, padrao: str):
    destino.mkdir(parents=True, exist_ok=True)
    n = 0
    for f in sorted(origem.glob(padrao)):
        if f.stem.upper().startswith("LEIA"):
            continue
        shutil.copy2(f, destino / f.name)
        n += 1
    print(f"OK: {n} agentes em {destino}")


def main():
    for fluxo in (sys.stdout, sys.stderr):
        try:
            fluxo.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    if sys.version_info < (3, 8):
        sys.exit("Precisa de Python 3.8 ou mais novo.")

    opcao = sys.argv[1] if len(sys.argv) > 1 else ""
    if opcao in ("-h", "--help"):
        print(__doc__)
        return
    if opcao not in ("", "--claude", "--codex", "--projeto"):
        sys.exit(f"Opção desconhecida: {opcao}. Use --claude, --codex ou --projeto.")

    casa = Path.home()
    base = Path.cwd() if opcao == "--projeto" else casa
    claude = opcao in ("", "--claude", "--projeto")
    codex = opcao in ("", "--codex", "--projeto")

    # Gera os agentes se a pasta não vier pronta (ex.: clone parcial).
    if not any((RAIZ / "agents" / "claude").glob("*.md")):
        import subprocess
        subprocess.check_call([sys.executable, str(RAIZ / "nucleo" / "ultra.py"), "build"])

    instalar_motor(casa)

    skills = []
    if claude:
        skills.append(base / ".claude" / "skills")
    if codex:
        skills += [base / ".codex" / "skills", base / ".agents" / "skills"]
    instalar_skills(skills)

    if claude:
        instalar_agentes(RAIZ / "agents" / "claude", base / ".claude" / "agents", "*.md")
    if codex:
        instalar_agentes(RAIZ / "agents" / "codex", base / ".codex" / "agents", "*.toml")

    faltando = []
    for mod, uso in (("reportlab", "PDF do plano (sem ele sai HTML)"),
                     ("PIL", "folha de teste do logo (pip install pillow)"),
                     ("playwright", "sites em JavaScript (sem ele usa o Chrome/Edge do computador)"),
                     ("certifi", "certificados no macOS")):
        try:
            __import__(mod)
        except ImportError:
            nome = "pillow" if mod == "PIL" else mod
            faltando.append(f"  pip install {nome:<10}  # {uso}")
    if faltando:
        print("\nOpcionais (nada é obrigatório):")
        print("\n".join(faltando))

    cmd = "py %USERPROFILE%\\.ultra-skills\\ultra.py" if sys.platform.startswith("win") else "python3 ~/.ultra-skills/ultra.py"
    print("\nPronto. Reinicie o Claude Code ou o Codex e peça:")
    print('  "faz uma análise ultra do https://seusite.com"')
    print(f"Para ver os agentes: {cmd} listar")
    if codex:
        print("No Codex, peça os agentes pelo nome (ele só chama agentes quando você pede).")


if __name__ == "__main__":
    main()
