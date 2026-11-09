#!/usr/bin/env python3
"""
mega-plano: transforma a análise em um plano de ação pronto para aplicar.

Entrada: plano.json (formato em ../SKILL.md e ../exemplo/plano.json)
Saída (pasta --saida):
  plano-de-acao.pdf    plano completo, reclassificado por prioridade, para aplicar
  plano-para-ia.md     o mesmo plano + instruções, para colar em qualquer IA e aplicar/corrigir
  plano.json           versão normalizada com as notas calculadas (edite e gere de novo)
  checklist.csv        ações para importar em Trello, Notion, Sheets ou ClickUp
  plano-de-acao.html   só se o reportlab não estiver instalado (abra e imprima em PDF)

Uso:
  python3 gerar.py plano.json --saida plano-final
  python3 gerar.py plano.json --validar          # só confere o JSON
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import re
import sys
from datetime import date
from pathlib import Path

CONFIANCA = {"TESTADO": 9, "EVIDENCIA": 7, "EVIDÊNCIA": 7, "HIPOTESE": 4, "HIPÓTESE": 4}
QUADRANTES = [
    ("FAÇA AGORA", "Alto impacto, pouco esforço. Comece por aqui."),
    ("PROJETO", "Alto impacto, muito esforço. Planeje e quebre em partes."),
    ("RÁPIDO", "Baixo impacto, pouco esforço. Faça nos intervalos."),
    ("REPENSAR", "Baixo impacto, muito esforço. Corte ou adie."),
]
ETAPAS = ["tecnico", "oferta", "site", "aquisicao", "vendas", "identidade", "instagram", "conteudo", "produto", "outro"]
NOMES_ETAPA = {"tecnico": "Técnico", "oferta": "Oferta", "site": "Site", "aquisicao": "Aquisição", "vendas": "Vendas",
               "identidade": "Identidade visual", "instagram": "Redes sociais", "conteudo": "Conteúdo",
               "produto": "Produto", "outro": "Outro"}


# --------------------------------------------------------------------------
# Validação e reclassificação
# --------------------------------------------------------------------------

def validar(p: dict) -> list[str]:
    erros = []
    proj = p.get("projeto")
    if not isinstance(proj, dict):
        return ["Falta o bloco 'projeto'."]
    for k in ("nome", "veredito", "estrategia_unica"):
        if not proj.get(k):
            erros.append(f"projeto.{k} está vazio.")
    acoes = p.get("acoes")
    if not isinstance(acoes, list) or not acoes:
        erros.append("Falta a lista 'acoes' (pelo menos 1 ação).")
        return erros
    for i, a in enumerate(acoes, 1):
        rot = f"acoes[{i}] ({a.get('titulo', 'sem título')})"
        for k in ("titulo", "porque", "metrica"):
            if not a.get(k):
                erros.append(f"{rot}: campo '{k}' vazio.")
        for k in ("impacto", "facilidade"):
            v = a.get(k)
            if not isinstance(v, (int, float)) or not 1 <= v <= 10:
                erros.append(f"{rot}: '{k}' precisa ser número de 1 a 10.")
        ev = str(a.get("evidencia", "")).upper()
        if ev not in CONFIANCA:
            erros.append(f"{rot}: 'evidencia' precisa ser TESTADO, EVIDENCIA ou HIPOTESE.")
        if not isinstance(a.get("passos", []), list):
            erros.append(f"{rot}: 'passos' precisa ser lista.")
        if a.get("etapa") and a["etapa"] not in ETAPAS:
            erros.append(f"{rot}: etapa '{a['etapa']}' inválida. Use uma de: {', '.join(ETAPAS)}.")
    for c in p.get("paleta", []):
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", str(c.get("hex", ""))):
            erros.append(f"paleta: '{c.get('hex')}' não é hex de 6 dígitos (#rrggbb).")
    return erros


def reclassificar(p: dict) -> dict:
    """Calcula ICE (impacto × confiança × facilidade) e o quadrante de cada ação."""
    for i, a in enumerate(p["acoes"], 1):
        a.setdefault("id", f"A{i:02d}")
        a.setdefault("etapa", "outro")
        a.setdefault("semana", 1)
        a.setdefault("dono", "—")
        a.setdefault("passos", [])
        a["evidencia"] = a["evidencia"].upper().replace("Ê", "E").replace("Ó", "O")
        conf = CONFIANCA[a["evidencia"]]
        a["confianca"] = conf
        a["ice"] = round(a["impacto"] * conf * a["facilidade"] / 10)
        alto_imp, facil = a["impacto"] >= 6, a["facilidade"] >= 6
        a["quadrante"] = ("FAÇA AGORA" if alto_imp and facil else "PROJETO" if alto_imp
                          else "RÁPIDO" if facil else "REPENSAR")
        if not a.get("prompt_ia"):
            a["prompt_ia"] = prompt_padrao(p["projeto"], a)
    ordem_q = {q: i for i, (q, _) in enumerate(QUADRANTES)}
    p["acoes"].sort(key=lambda a: (ordem_q[a["quadrante"]], -a["ice"]))
    p["projeto"].setdefault("data", date.today().isoformat())
    return p


def prompt_padrao(proj: dict, a: dict) -> str:
    base = f"\n\nPonto de partida já escrito:\n{a['entregavel']}" if a.get("entregavel") else ""
    passos = "\n".join(f"- {x}" for x in a.get("passos", []))
    return (
        f"Você vai executar uma ação do plano de {proj['nome']}"
        f"{' (' + proj['url'] + ')' if proj.get('url') else ''}.\n"
        f"Estratégia: {proj['estrategia_unica']}\n\n"
        f"Ação: {a['titulo']}\nPor quê: {a['porque']}\n"
        f"{('Passos:' + chr(10) + passos) if passos else ''}{base}\n\n"
        f"Entregue a versão final pronta para usar (texto, lista ou instrução exata). "
        f"Nada genérico: se a frase serviria para qualquer concorrente, reescreva com detalhe deste negócio. "
        f"Diga como medir: {a['metrica']}."
    )


# --------------------------------------------------------------------------
# Saídas de texto
# --------------------------------------------------------------------------

def para_markdown_ia(p: dict) -> str:
    proj = p["projeto"]
    L = [
        "# INSTRUÇÕES PARA A IA",
        "",
        "Você é o executor deste plano estratégico. Regras:",
        "1. Siga a ordem das ações (já está reclassificada por prioridade: FAÇA AGORA → PROJETO → RÁPIDO → REPENSAR).",
        "2. Quando eu disser \"aplique A01\" (ou outro código), entregue a versão final pronta daquela ação.",
        "3. Quando eu disser \"corrija o plano\" e der um dado novo, ajuste as ações afetadas, diga o que mudou e "
        "devolva o JSON atualizado no mesmo formato do bloco no fim deste arquivo.",
        "4. Nada genérico. Toda afirmação tem marcação [TESTADO], [EVIDENCIA] ou [HIPOTESE]. Hipótese nunca vira fato.",
        "5. Se faltar informação para executar, pergunte uma coisa só, a mais importante.",
        "",
        f"# PLANO: {proj['nome']}",
        f"{proj.get('url', '')} · {proj['data']}",
        "",
        f"**Veredito:** {proj['veredito']}",
        f"**Estratégia única:** {proj['estrategia_unica']}",
    ]
    for k, rot in (("publico", "Público"), ("meta_90_dias", "Meta de 90 dias"), ("resumo", "Resumo")):
        if proj.get(k):
            L.append(f"**{rot}:** {proj[k]}")
    L += ["", "## Ações (por prioridade)", ""]
    for a in p["acoes"]:
        L.append(f"### {a['id']} · {a['titulo']}  [{a['quadrante']} · ICE {a['ice']} · {a['evidencia']}]")
        L.append(f"Etapa: {NOMES_ETAPA.get(a['etapa'], a['etapa'])} · Semana {a['semana']} · Dono: {a['dono']}")
        L.append(f"Por quê: {a['porque']}")
        if a["passos"]:
            L += [f"- [ ] {x}" for x in a["passos"]]
        if a.get("entregavel"):
            L += ["Entregável pronto:", "```", a["entregavel"], "```"]
        L.append(f"Métrica: {a['metrica']}" + (f" · Meta: {a['meta']}" if a.get("meta") else ""))
        L.append("")
    if p.get("ofertas"):
        L.append("## Ofertas")
        for o in p["ofertas"]:
            L.append(f"### {o.get('nome')}")
            L += [f"- {k}: {v}" for k, v in o.items() if k != "nome" and v]
        L.append("")
    if p.get("ativos"):
        L.append("## Ativos prontos")
        for at in p["ativos"]:
            L += [f"### {at.get('titulo')} ({at.get('tipo', '')})", "```", at.get("texto", ""), "```"]
        L.append("")
    if p.get("paleta"):
        L.append("## Paleta")
        L += [f"- {c['hex']} {c.get('nome', '')}: {c.get('uso', '')}" for c in p["paleta"]]
        L.append("")
    if p.get("conteudo"):
        L.append("## Ideias de conteúdo (com sinal real)")
        L += [f"- [{c.get('funil', '')}] {c.get('gancho')} ({c.get('formato', '')}). Sinal: {c.get('sinal')}"
              for c in p["conteudo"]]
        L.append("")
    if p.get("metricas"):
        L.append("## Métricas")
        L += [f"- {m.get('nome')}: atual {m.get('atual', '?')} → meta {m.get('meta', '?')} ({m.get('quando', '')})"
              for m in p["metricas"]]
        L.append("")
    if p.get("suposicoes"):
        L.append("## Suposições a validar")
        L += [f"- {s}" for s in p["suposicoes"]]
        L.append("")
    L += ["## JSON do plano (para correções)", "```json", json.dumps(p, ensure_ascii=False, indent=1), "```"]
    return "\n".join(L) + "\n"


def salvar_csv(p: dict, arq: Path):
    with arq.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["ID", "Ação", "Quadrante", "ICE", "Evidência", "Etapa", "Semana", "Dono", "Métrica", "Meta", "Passos", "Feito"])
        for a in p["acoes"]:
            w.writerow([a["id"], a["titulo"], a["quadrante"], a["ice"], a["evidencia"],
                        NOMES_ETAPA.get(a["etapa"], a["etapa"]), a["semana"], a["dono"], a["metrica"],
                        a.get("meta", ""), " | ".join(a["passos"]), ""])


# --------------------------------------------------------------------------
# PDF (reportlab)
# --------------------------------------------------------------------------

TROCAS = {"✓": "OK", "✔": "OK", "✖": "X", "→": "->", "←": "<-", "↓": "v", "↗": "->", "×": "x", "≥": ">=",
          "≤": "<=", "★": "*", "☐": "[ ]", "🔦": "", "🧾": "", "⚠": "!"}


def seguro(t) -> str:
    """Escapa para Paragraph e troca símbolos que a fonte padrão não tem."""
    t = str(t if t is not None else "")
    for a, b in TROCAS.items():
        t = t.replace(a, b)
    t = "".join(ch for ch in t if ch == "\n" or ord(ch) < 0x2000 or ch in "–—‘’“”•…€™")
    t = "".join(ch if ord(ch) < 0x10000 else "" for ch in t)
    return html.escape(t).replace("\n", "<br/>")


def gerar_pdf(p: dict, arq: Path):
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
                                    TableStyle)

    proj = p["projeto"]
    tinta = colors.HexColor("#1f2a2e")
    cinza = colors.HexColor("#5b6670")
    linha = colors.HexColor("#d9dee2")
    fundo = colors.HexColor("#f4f6f7")
    acento = colors.HexColor(next((c["hex"] for c in p.get("paleta", []) if c.get("destaque")), "#2f6f62"))
    cores_q = {"FAÇA AGORA": colors.HexColor("#2f6f62"), "PROJETO": colors.HexColor("#3c5a99"),
               "RÁPIDO": colors.HexColor("#8a6d1f"), "REPENSAR": colors.HexColor("#8c3b3b")}

    ss = getSampleStyleSheet()
    S = {
        "capa": ParagraphStyle("capa", parent=ss["Title"], fontSize=28, leading=33, textColor=tinta, alignment=TA_LEFT),
        "sub": ParagraphStyle("sub", parent=ss["Normal"], fontSize=12, leading=16, textColor=cinza),
        "h1": ParagraphStyle("h1", parent=ss["Heading1"], fontSize=18, leading=22, textColor=tinta, spaceBefore=4, spaceAfter=8),
        "h2": ParagraphStyle("h2", parent=ss["Heading2"], fontSize=12.5, leading=16, textColor=tinta, spaceBefore=8, spaceAfter=4),
        "txt": ParagraphStyle("txt", parent=ss["Normal"], fontSize=9.6, leading=13.5, textColor=tinta),
        "peq": ParagraphStyle("peq", parent=ss["Normal"], fontSize=8.4, leading=11, textColor=cinza),
        "cel": ParagraphStyle("cel", parent=ss["Normal"], fontSize=8.4, leading=10.8, textColor=tinta),
        "celb": ParagraphStyle("celb", parent=ss["Normal"], fontSize=8.4, leading=10.8, textColor=tinta, fontName="Helvetica-Bold"),
        "copy": ParagraphStyle("copy", parent=ss["Normal"], fontSize=9.2, leading=13, textColor=tinta, fontName="Courier"),
        "dest": ParagraphStyle("dest", parent=ss["Normal"], fontSize=11, leading=15.5, textColor=tinta),
    }
    P = lambda t, s="txt": Paragraph(seguro(t), S[s])  # noqa: E731
    Pb = lambda t, s="txt": Paragraph(t, S[s])  # já formatado  # noqa: E731
    largura = A4[0] - 36 * mm

    def caixa(conteudo, cor_borda=linha, cor_fundo=fundo, pad=8):
        t = Table([[conteudo]], colWidths=[largura])
        t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.6, cor_borda), ("BACKGROUND", (0, 0), (-1, -1), cor_fundo),
                               ("LEFTPADDING", (0, 0), (-1, -1), pad), ("RIGHTPADDING", (0, 0), (-1, -1), pad),
                               ("TOPPADDING", (0, 0), (-1, -1), pad), ("BOTTOMPADDING", (0, 0), (-1, -1), pad)]))
        return t

    def tabela(linhas, larguras, cabecalho=True):
        dados = [[c if not isinstance(c, str) else P(c, "celb" if (cabecalho and i == 0) else "cel") for c in row]
                 for i, row in enumerate(linhas)]
        t = Table(dados, colWidths=larguras, repeatRows=1 if cabecalho else 0)
        estilo = [("GRID", (0, 0), (-1, -1), 0.4, linha), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                  ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                  ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]
        if cabecalho:
            estilo.append(("BACKGROUND", (0, 0), (-1, 0), fundo))
        t.setStyle(TableStyle(estilo))
        return t

    def rodape(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(cinza)
        canvas.drawString(18 * mm, 10 * mm, seguro(f"{proj['nome']} · Plano de ação · {proj['data']}").replace("&amp;", "&"))
        canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"{doc.page}")
        canvas.setStrokeColor(acento)
        canvas.setLineWidth(2)
        canvas.line(18 * mm, A4[1] - 12 * mm, A4[0] - 18 * mm, A4[1] - 12 * mm)
        canvas.restoreState()

    st = []
    # ---- capa
    st += [Spacer(1, 40 * mm), P("PLANO DE AÇÃO", "sub"), Spacer(1, 4), P(proj["nome"], "capa")]
    if proj.get("url"):
        st.append(P(proj["url"], "sub"))
    st += [Spacer(1, 10 * mm), caixa(Pb(f"<b>Veredito.</b> {seguro(proj['veredito'])}", "dest"), acento),
           Spacer(1, 6), caixa(Pb(f"<b>Estratégia única.</b> {seguro(proj['estrategia_unica'])}", "dest"))]
    extras = [(k, r) for k, r in (("publico", "Público"), ("meta_90_dias", "Meta de 90 dias")) if proj.get(k)]
    for k, r in extras:
        st += [Spacer(1, 6), caixa(Pb(f"<b>{r}.</b> {seguro(proj[k])}", "txt"))]
    cont = {q: sum(1 for a in p["acoes"] if a["quadrante"] == q) for q, _ in QUADRANTES}
    st += [Spacer(1, 10 * mm), P(f"{len(p['acoes'])} ações · " + " · ".join(f"{q}: {n}" for q, n in cont.items()), "peq"),
           P(f"Gerado em {proj['data']} pelo mega-plano (Ultra Skills).", "peq"), PageBreak()]

    # ---- como usar
    st += [P("Como usar este plano", "h1"),
           P("1. Aplique na ordem. As ações já estão reclassificadas por prioridade (impacto × confiança × facilidade). "
             "Comece pelo quadrante FAÇA AGORA."),
           Spacer(1, 4),
           P("2. Use com IA. Abra o arquivo plano-para-ia.md, cole inteiro no ChatGPT, Claude, Gemini ou outra IA e diga "
             "\"aplique A01\" para receber a ação pronta, ou \"corrija o plano: [dado novo]\" para ajustar."),
           Spacer(1, 4),
           P("3. Corrija e gere de novo. Edite o plano.json (ou peça a IA para editar) e rode gerar.py outra vez. "
             "As prioridades se recalculam sozinhas."),
           Spacer(1, 4),
           P("4. Acompanhe. Importe o checklist.csv no Trello, Notion, Sheets ou ClickUp."),
           Spacer(1, 8),
           P("Marcações: TESTADO = verificado; EVIDENCIA = fonte externa; HIPOTESE = opinião a validar. "
             "A confiança da marcação entra na nota (9, 7 e 4).", "peq")]
    if proj.get("resumo"):
        st += [P("Resumo", "h2"), P(proj["resumo"])]

    # ---- matriz
    st += [PageBreak(), P("Matriz de prioridade", "h1")]
    celulas = []
    for q, desc in QUADRANTES:
        itens = [a for a in p["acoes"] if a["quadrante"] == q]
        corpo = f"<font color='{cores_q[q].hexval().replace('0x', '#')}'><b>{q}</b></font><br/><font size=7.5>{seguro(desc)}</font><br/><br/>"
        corpo += "<br/>".join(f"<b>{a['id']}</b> {seguro(a['titulo'])} <font color='#5b6670'>(ICE {a['ice']})</font>"
                              for a in itens) or "<font color='#5b6670'>nenhuma</font>"
        celulas.append(Paragraph(corpo, S["cel"]))
    mt = Table([[celulas[0], celulas[1]], [celulas[2], celulas[3]]], colWidths=[largura / 2] * 2)
    mt.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.6, linha), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                            ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 9)]))
    st += [P("Eixo vertical: impacto (alto em cima). Eixo horizontal: facilidade (fácil à esquerda).", "peq"), Spacer(1, 4), mt]

    # ---- roadmap
    st += [Spacer(1, 10), P("Roteiro semana a semana", "h1")]
    linhas = [["Semana", "Ação", "Etapa", "Dono", "Métrica / meta"]]
    for a in sorted(p["acoes"], key=lambda a: (a["semana"] if isinstance(a["semana"], (int, float)) else 99, -a["ice"])):
        linhas.append([str(a["semana"]), f"{a['id']} · {a['titulo']}", NOMES_ETAPA.get(a["etapa"], a["etapa"]),
                       a["dono"], a["metrica"] + (f" → {a['meta']}" if a.get("meta") else "")])
    st.append(tabela(linhas, [16 * mm, 70 * mm, 26 * mm, 22 * mm, largura - 134 * mm]))

    # ---- ações detalhadas
    st += [PageBreak(), P("As ações, prontas para aplicar", "h1")]
    for a in p["acoes"]:
        cq = cores_q[a["quadrante"]].hexval().replace("0x", "#")
        bloco = [Pb(f"<font color='{cq}'><b>{a['quadrante']}</b></font> · ICE {a['ice']} · {a['evidencia']} · "
                    f"{seguro(NOMES_ETAPA.get(a['etapa'], a['etapa']))} · semana {seguro(a['semana'])} · dono: {seguro(a['dono'])}", "peq"),
                 Pb(f"<b>{a['id']} · {seguro(a['titulo'])}</b>", "h2"),
                 Pb(f"<b>Por quê:</b> {seguro(a['porque'])}", "txt")]
        if a["passos"]:
            bloco.append(Spacer(1, 3))
            bloco += [Pb(f"[&nbsp;&nbsp;] {seguro(x)}", "txt") for x in a["passos"]]
        if a.get("entregavel"):
            bloco += [Spacer(1, 4), P("Entregável pronto:", "peq"), caixa(P(a["entregavel"], "copy"))]
        bloco += [Spacer(1, 3), Pb(f"<b>Métrica:</b> {seguro(a['metrica'])}" + (f" · <b>Meta:</b> {seguro(a['meta'])}" if a.get("meta") else ""), "txt"),
                  Spacer(1, 3), P(f"Na IA: \"aplique {a['id']}\" (o prompt completo está no plano-para-ia.md).", "peq"),
                  Spacer(1, 10)]
        st.append(KeepTogether(bloco))

    # ---- ofertas
    if p.get("ofertas"):
        st += [PageBreak(), P("Ofertas", "h1")]
        chaves = [("publico", "Público"), ("dor", "Dor"), ("promessa", "Promessa"), ("inclui", "Inclui"), ("preco", "Preço"),
                  ("garantia", "Garantia"), ("urgencia", "Urgência"), ("canal", "Canal"), ("headline", "Headline")]
        for o in p["ofertas"]:
            linhas = [[r, o[k]] for k, r in chaves if o.get(k)]
            st += [KeepTogether([P(o.get("nome", "Oferta"), "h2"), tabela(linhas, [28 * mm, largura - 28 * mm], cabecalho=False)]),
                   Spacer(1, 6)]

    # ---- ativos
    if p.get("ativos"):
        st += [PageBreak(), P("Ativos prontos para copiar", "h1")]
        for at in p["ativos"]:
            st += [KeepTogether([P(f"{at.get('titulo', '')}  ({at.get('tipo', '')})", "h2"), caixa(P(at.get("texto", ""), "copy"))]),
                   Spacer(1, 6)]

    # ---- paleta
    if p.get("paleta"):
        linhas, estilos = [], []
        for i, c in enumerate(p["paleta"]):
            linhas.append(["", P(f"{c['hex']}  {c.get('nome', '')}", "celb"), P(c.get("uso", ""), "cel")])
            estilos.append(("BACKGROUND", (0, i), (0, i), colors.HexColor(c["hex"])))
        t = Table(linhas, colWidths=[16 * mm, 50 * mm, largura - 66 * mm], rowHeights=[12 * mm] * len(linhas))
        t.setStyle(TableStyle(estilos + [("GRID", (0, 0), (-1, -1), 0.4, linha), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
        st += [Spacer(1, 6), KeepTogether([P("Paleta", "h1"), t])]

    # ---- conteúdo
    if p.get("conteudo"):
        st += [PageBreak(), P("Conteúdo: ideias com sinal real", "h1")]
        linhas = [["#", "Gancho", "Formato", "Funil", "Sinal real"]]
        for i, c in enumerate(p["conteudo"], 1):
            linhas.append([str(i), c.get("gancho", ""), c.get("formato", ""), c.get("funil", ""), c.get("sinal", "")])
        st.append(tabela(linhas, [8 * mm, 68 * mm, 22 * mm, 16 * mm, largura - 114 * mm]))

    # ---- métricas e suposições
    if p.get("metricas"):
        st += [Spacer(1, 10), P("Métricas", "h1")]
        linhas = [["Métrica", "Hoje", "Meta", "Quando"]] + [[m.get("nome", ""), m.get("atual", "?"), m.get("meta", ""), m.get("quando", "")]
                                                         for m in p["metricas"]]
        st.append(tabela(linhas, [70 * mm, 30 * mm, 40 * mm, largura - 140 * mm]))
    if p.get("suposicoes"):
        st += [Spacer(1, 10), P("Suposições a validar", "h1")]
        st += [Pb(f"[&nbsp;&nbsp;] {seguro(s)}", "txt") for s in p["suposicoes"]]

    # ---- checklist final
    st += [PageBreak(), P("Checklist", "h1")]
    linhas = [["Feito", "ID", "Ação", "Quadrante", "Semana"]] + [["[   ]", a["id"], a["titulo"], a["quadrante"], str(a["semana"])]
                                                                  for a in p["acoes"]]
    st.append(tabela(linhas, [14 * mm, 14 * mm, 100 * mm, 26 * mm, largura - 154 * mm]))
    if p.get("fontes"):
        st += [Spacer(1, 10), P("Fontes", "h2")] + [P(f"• {f}", "peq") for f in p["fontes"]]

    doc = SimpleDocTemplate(str(arq), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=18 * mm,
                            bottomMargin=16 * mm, title=f"Plano de ação: {proj['nome']}", author="Ultra Skills · mega-plano")
    doc.build(st, onFirstPage=rodape, onLaterPages=rodape)


def gerar_html(p: dict, arq: Path):
    """Alternativa sem reportlab: HTML pronto para imprimir em PDF pelo navegador."""
    import markdown as md  # type: ignore
    corpo = md.markdown(para_markdown_ia(p).split("## JSON do plano")[0].split("# PLANO:", 1)[-1], extensions=["fenced_code"])
    arq.write_text(f"""<!doctype html><html lang="pt-BR"><meta charset="utf-8"><title>Plano: {html.escape(p['projeto']['nome'])}</title>
<style>body{{font:15px/1.55 system-ui,sans-serif;max-width:820px;margin:40px auto;padding:0 20px;color:#1f2a2e}}
h1,h2,h3{{line-height:1.2}} pre{{background:#f4f6f7;padding:12px;white-space:pre-wrap;border:1px solid #d9dee2}}
@media print{{h3{{break-after:avoid}} pre{{break-inside:avoid}}}}</style>
<h1>Plano: {corpo}</html>""", encoding="utf-8")


# --------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(description="mega-plano: plano de ação em PDF + arquivo para IA")
    ap.add_argument("json", help="plano.json")
    ap.add_argument("--saida", default="plano-final")
    ap.add_argument("--validar", action="store_true", help="só valida o JSON")
    a = ap.parse_args(argv)

    try:
        plano = json.loads(Path(a.json).read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        sys.exit(f"JSON inválido: {e}")
    erros = validar(plano)
    if erros:
        print("O plano.json tem problemas. Corrija e rode de novo:")
        print("\n".join(f"  - {e}" for e in erros))
        return 1
    if a.validar:
        print(f"plano.json válido: {len(plano['acoes'])} ações.")
        return 0

    plano = reclassificar(plano)
    pasta = Path(a.saida)
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / "plano.json").write_text(json.dumps(plano, ensure_ascii=False, indent=1), encoding="utf-8")
    (pasta / "plano-para-ia.md").write_text(para_markdown_ia(plano), encoding="utf-8")
    salvar_csv(plano, pasta / "checklist.csv")
    try:
        gerar_pdf(plano, pasta / "plano-de-acao.pdf")
        principal = pasta / "plano-de-acao.pdf"
    except ImportError:
        gerar_html(plano, pasta / "plano-de-acao.html")
        principal = pasta / "plano-de-acao.html"
        print("reportlab não instalado: gerei HTML. Abra e use Imprimir → Salvar como PDF. "
              "Para PDF direto: pip install reportlab")

    cont = {}
    for x in plano["acoes"]:
        cont[x["quadrante"]] = cont.get(x["quadrante"], 0) + 1
    print(f"{len(plano['acoes'])} ações reclassificadas: " + ", ".join(f"{k} {v}" for k, v in cont.items()))
    print("Top 3:", " | ".join(f"{x['id']} {x['titulo']} (ICE {x['ice']})" for x in plano["acoes"][:3]))
    for nome in (principal.name, "plano-para-ia.md", "plano.json", "checklist.csv"):
        print(f"  → {pasta / nome}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
