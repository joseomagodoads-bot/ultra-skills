#!/usr/bin/env python3
"""
paleta.py: prova que uma paleta não é genérica e que dá para ler.

Compara as cores propostas com as cores de destaque dos concorrentes (do
comparativo.json do scan-ultra ou passadas à mão), mede a distância visual
(Delta E, CIE76) e o contraste WCAG entre cada par de cores.

Uso:
  python3 paleta.py --cores "#0f3d2e,#f2b705,#faf7f0" --comparativo scan-ultra-saida/comparativo.json
  python3 paleta.py --cores "#0f3d2e,#f2b705" --concorrentes "ifood.com=#ea1d2c,saipos.com=#2b6cb0"
"""

from __future__ import annotations

import argparse
import colorsys
import json
import math
import sys
from collections import Counter
from pathlib import Path


def hex_rgb(h: str) -> tuple[int, int, int]:
    h = h.strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def luminancia(rgb) -> float:
    def canal(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (canal(x) for x in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contraste(a, b) -> float:
    la, lb = sorted((luminancia(hex_rgb(a)), luminancia(hex_rgb(b))), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def lab(hexcor: str):
    def lin(c):
        c /= 255
        return ((c + 0.055) / 1.055) ** 2.4 if c > 0.04045 else c / 12.92
    r, g, b = (lin(x) for x in hex_rgb(hexcor))
    x = (r * 0.4124 + g * 0.3576 + b * 0.1805) / 0.95047
    y = (r * 0.2126 + g * 0.7152 + b * 0.0722)
    z = (r * 0.0193 + g * 0.1192 + b * 0.9505) / 1.08883

    def f(t):
        return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116
    fx, fy, fz = f(x), f(y), f(z)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def delta_e(a: str, b: str) -> float:
    return math.dist(lab(a), lab(b))


def familia(hexcor: str) -> str:
    ri, gi, bi = hex_rgb(hexcor)
    if max(ri, gi, bi) - min(ri, gi, bi) < 26:  # croma baixo: papel, creme, grafite, preto-azulado
        return "neutro"
    h, l, s = colorsys.rgb_to_hls(ri / 255, gi / 255, bi / 255)
    if l < 0.08 or l > 0.97:
        return "neutro"
    graus = h * 360
    for limite, nome in ((15, "vermelho"), (40, "laranja"), (65, "amarelo"), (170, "verde"),
                         (195, "ciano"), (255, "azul"), (290, "roxo"), (335, "rosa"), (361, "vermelho")):
        if graus < limite:
            return nome
    return "vermelho"


def ler_concorrentes(args) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    if args.comparativo:
        for m in json.loads(Path(args.comparativo).read_text(encoding="utf-8")):
            nome = m.get("url_final", "?").split("//")[-1].split("/")[0]
            out[nome] = m.get("identidade_visual", {}).get("cores_de_destaque", [])[:4]
    if args.concorrentes:
        for par in args.concorrentes.split(","):
            if "=" in par:
                nome, cor = par.split("=", 1)
                out.setdefault(nome.strip(), []).append(cor.strip())
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--cores", required=True, help="cores propostas, separadas por vírgula")
    ap.add_argument("--comparativo", help="comparativo.json do scan-ultra")
    ap.add_argument("--concorrentes", help="nome=#hex,nome=#hex")
    ap.add_argument("--limite", type=float, default=15.0, help="Delta E abaixo disso = parecida demais")
    a = ap.parse_args(argv)

    cores = [c.strip() if c.strip().startswith("#") else "#" + c.strip() for c in a.cores.split(",") if c.strip()]
    conc = ler_concorrentes(a)
    L = ["# Prova da paleta", ""]

    L.append("## 1. Distância dos concorrentes (Delta E: <15 parece igual, 15–30 parecida, >30 distinta)")
    if not conc:
        L.append("Sem cores de concorrentes. Rode o scan-ultra nos concorrentes e passe --comparativo.")
    problemas = 0
    for c in cores:
        if familia(c) == "neutro":
            L.append(f"- {c} (neutro): não entra na disputa de identidade")
            continue
        perto = sorted(((delta_e(c, x), nome, x) for nome, xs in conc.items() for x in xs
                        if familia(x) != "neutro"), key=lambda t: t[0])
        if not perto:
            L.append(f"- {c} ({familia(c)}): sem cor de destaque concorrente para comparar")
            continue
        d, nome, x = perto[0]
        selo = "PARECE IGUAL" if d < a.limite else ("parecida" if d < 30 else "distinta")
        problemas += d < a.limite
        L.append(f"- {c} ({familia(c)}): mais perto de {x} ({nome}), Delta E {d:.1f} → {selo}")

    fam = Counter(familia(x) for xs in conc.values() for x in xs[:2] if familia(x) != "neutro")
    if fam:
        L.append("\n## 2. Cores que o mercado já usa (2 primeiras de destaque de cada concorrente)")
        L.append(", ".join(f"{k}: {v}" for k, v in fam.most_common()))
        livres = [f for f in ("vermelho", "laranja", "amarelo", "verde", "ciano", "azul", "roxo", "rosa") if f not in fam]
        L.append(f"Famílias que ninguém usa: {', '.join(livres) or 'nenhuma'}")

    L.append("\n## 3. Contraste entre as cores propostas (WCAG: texto normal ≥4.5, texto grande e botões ≥3)")
    for i, x in enumerate(cores):
        for y in cores[i + 1:]:
            r = contraste(x, y)
            uso = "texto normal ok" if r >= 4.5 else ("só texto grande/ícone" if r >= 3 else "NÃO usar como texto/fundo")
            L.append(f"- {x} × {y}: {r:.2f} → {uso}")
    for c in cores:
        rb, rp = contraste(c, "#ffffff"), contraste(c, "#000000")
        L.append(f"- {c} sobre branco {rb:.2f}, sobre preto {rp:.2f}")

    L.append(f"\n**Resultado:** {problemas} cor(es) parecida(s) demais com concorrente." if conc else "")
    print("\n".join(L))
    return 1 if problemas else 0


if __name__ == "__main__":
    sys.exit(main())
