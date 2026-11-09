#!/usr/bin/env python3
"""
pipeline.py: roda a sequência Ultra e guarda o estado em uma pasta.

  1. scan-ultra                       → 01-scan/ (mapas + comparativo)   [automático]
  2. pare-de-pensar-como-ia           → 02-pessoas.md
  3. teu-saas-e-uma-merda             → 03-fundadores.md
  4. tu-e-doido-isso-que-e-marketing  → 04-plano-estrategico.md
  5. mega-plano                       → 05-plano/ (PDF + arquivo para IA + checklist)

Uso:
  python3 pipeline.py iniciar https://site.com --concorrentes https://a.com https://b.com [--print]
  python3 pipeline.py status   [--pasta ultra-run-site.com]
  python3 pipeline.py proximo  [--pasta ultra-run-site.com]

Cada etapa só é considerada feita quando o arquivo de saída dela existe.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

AQUI = Path(__file__).resolve()
SKILLS = AQUI.parents[2]  # .../skills/
SCAN = SKILLS / "scan-ultra" / "scripts" / "scan.py"

ETAPAS = [
    {"id": "01-scan", "skill": "scan-ultra", "saida": "01-scan/CONFERENCIA.md",
     "faz": "Ler o mapa do site e dos concorrentes e escrever a conferência do mapeamento (Passo 2 da skill)."},
    {"id": "02-pessoas", "skill": "pare-de-pensar-como-ia", "saida": "02-pessoas.md",
     "faz": "Rodar as 5 pessoas usando o mapa como prova. Tudo que veio do scan é [TESTADO]."},
    {"id": "03-fundadores", "skill": "teu-saas-e-uma-merda", "saida": "03-fundadores.md",
     "faz": "Jobs, Wozniak, Huang e Bezos atacam o produto com as provas das etapas 1 e 2."},
    {"id": "04-marketing", "skill": "tu-e-doido-isso-que-e-marketing", "saida": "04-plano-estrategico.md",
     "faz": "Os 10 mestres montam o plano estratégico a partir de tudo que foi provado."},
    {"id": "05-mega-plano", "skill": "mega-plano", "saida": "05-plano/plano-para-ia.md",
     "faz": "Escrever 05-plano/plano.json e rodar mega-plano/scripts/gerar.py plano.json --saida 05-plano "
            "(gera o PDF do plano de ação, o arquivo para IA e o checklist)."},
]


def pasta_padrao(url: str) -> Path:
    host = urlparse(url if "://" in url else "https://" + url).netloc or "site"
    return Path("ultra-run-" + "".join(c if c.isalnum() or c in ".-" else "_" for c in host))


def achar_pasta(arg: str | None) -> Path:
    if arg:
        return Path(arg)
    runs = sorted(Path(".").glob("ultra-run-*/estado.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not runs:
        sys.exit("Nenhuma pasta ultra-run-* aqui. Rode: pipeline.py iniciar URL")
    return runs[0].parent


def iniciar(a):
    pasta = Path(a.pasta) if a.pasta else pasta_padrao(a.url)
    (pasta / "01-scan").mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, str(SCAN), a.url, *a.concorrentes, "--saida", str(pasta / "01-scan"), "--links"]
    if a.print:
        cmd.append("--print")
    elif a.render:
        cmd.append("--render")
    print("→", " ".join(cmd), flush=True)
    t0 = time.perf_counter()
    rc = subprocess.call(cmd)
    estado = {"url": a.url, "concorrentes": a.concorrentes, "criado": time.strftime("%Y-%m-%d %H:%M"),
              "scan_rc": rc, "scan_s": round(time.perf_counter() - t0, 2)}
    (pasta / "estado.json").write_text(json.dumps(estado, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nPasta da análise: {pasta}")
    falhas = []
    for j in (pasta / "01-scan").glob("*.json"):
        if j.name.startswith("comparativo"):
            continue
        m = json.loads(j.read_text(encoding="utf-8"))
        if m["http"].get("status") is None or m["verificacao"]["confianca"] == "baixa":
            falhas.append(f"{m['url']}: {m['http'].get('erro') or 'confiança baixa (provável JavaScript)'}")
    if falhas:
        print("\n⚠ O scan não conseguiu ler direito:")
        for f in falhas:
            print("   -", f)
        print("   Antes de analisar: rode de novo com --render (sites em JavaScript), verifique a rede,")
        print("   ou monte o mapa com a ferramenta de leitura de páginas (seção 'Quando o script não pode rodar'")
        print("   do scan-ultra) e marque a análise como sem conferência automática.")
    proximo(argparse.Namespace(pasta=str(pasta)))


def status(a):
    pasta = achar_pasta(a.pasta)
    est = json.loads((pasta / "estado.json").read_text(encoding="utf-8"))
    print(f"Análise de {est['url']} ({len(est['concorrentes'])} concorrentes) em {pasta}")
    for e in ETAPAS:
        feito = (pasta / e["saida"]).exists()
        print(f"  [{'x' if feito else ' '}] {e['id']}  {e['skill']:<34} → {e['saida']}")


def proximo(a):
    pasta = achar_pasta(a.pasta)
    for i, e in enumerate(ETAPAS):
        if not (pasta / e["saida"]).exists():
            break
    else:
        print("Todas as etapas feitas. Entregue 05-plano/plano-de-acao.pdf, plano-para-ia.md e checklist.csv.")
        return
    anteriores = [str(pasta / x["saida"]) for x in ETAPAS[:i]]
    mapas = sorted(str(p) for p in (pasta / "01-scan").glob("*.md") if p.name != "CONFERENCIA.md")
    print(f"\nPRÓXIMA ETAPA: {e['id']}")
    print(f"  Skill: {e['skill']} (carregue o SKILL.md dela)")
    print(f"  O que fazer: {e['faz']}")
    print("  Leia:")
    for m in mapas:
        print(f"    - {m}")
    for x in anteriores:
        print(f"    - {x}")
    print(f"  Escreva o resultado em: {pasta / e['saida']}")
    print(f"  Depois rode: python3 {AQUI} proximo --pasta {pasta}")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Pipeline Ultra")
    sub = ap.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("iniciar")
    i.add_argument("url")
    i.add_argument("--concorrentes", nargs="*", default=[])
    i.add_argument("--pasta")
    i.add_argument("--render", action="store_true")
    i.add_argument("--print", action="store_true")
    i.set_defaults(f=iniciar)
    for nome, f in (("status", status), ("proximo", proximo)):
        p = sub.add_parser(nome)
        p.add_argument("--pasta")
        p.set_defaults(f=f)
    a = ap.parse_args(argv)
    a.f(a)


if __name__ == "__main__":
    main()
