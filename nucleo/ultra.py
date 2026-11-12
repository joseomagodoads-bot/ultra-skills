#!/usr/bin/env python3
"""
ultra.py: o motor de parâmetros do sistema Ultra.

Os agentes (Jobs, Bezos, Hormozi, João, Fernando...) não leem texto corrido: leem
PARÂMETROS (critérios com peso e régua de 0 a 10, testes, alertas, números com fonte)
e devolvem um JSON padronizado. Este motor valida, consolida, acha discordâncias,
faz o duelo de ofertas e monta o plano, em milissegundos.

  ultra.py listar                          agentes e conselhos
  ultra.py params ultra-jobs [--compacto]  parâmetros expandidos de um agente
  ultra.py iniciar URL --concorrentes A B  cria a pasta da análise e roda o scan
  ultra.py proximo [--pasta P] [--json]    próxima rodada: tarefa pronta para cada agente
  ultra.py status [--pasta P]              o que já foi feito
  ultra.py validar ARQUIVO_OU_PASTA        confere a saída de um agente
  ultra.py consolidar PASTA [--rodada N]   junta um conselho: notas, divergências, ações
  ultra.py duelo PASTA_VENDAS              ranking das ofertas do conselho de vendas
  ultra.py logo-teste IMAGEM [--saida P]   folha de teste do logo (16/32/110 px, uma cor, invertido)
  ultra.py plano PASTA [--pdf]             plano.json para o mega-plano (e o PDF)
  ultra.py build [--saida DIR]             gera os agentes para Claude Code, Codex e ChatGPT

Só biblioteca padrão do Python 3.8+ (logo-teste usa Pillow, se houver).
"""

from __future__ import annotations

import argparse
import difflib
import glob
import json
import re
import subprocess
import sys
import time
import unicodedata
from pathlib import Path
from urllib.parse import urlparse

AQUI = Path(__file__).resolve().parent
PARAMS = AQUI / "params"
VERSAO = "3.0.0"
MARCAS = ("TESTADO", "EVIDENCIA", "HIPOTESE")
CONFIANCA = {"TESTADO": 9, "EVIDENCIA": 7, "HIPOTESE": 4}
ETAPAS = ["tecnico", "oferta", "site", "aquisicao", "vendas", "identidade", "instagram", "conteudo", "produto", "outro"]


# ---------------------------------------------------------------- utilidades

def utf8():
    for f in (sys.stdout, sys.stderr):
        try:
            f.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def ler_json(p) -> object:
    return json.loads(Path(p).read_text(encoding="utf-8"))


def salvar_json(p, dado):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(json.dumps(dado, ensure_ascii=False, indent=1), encoding="utf-8")


def norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", str(t).lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9 ]+", " ", t).strip()


PARADAS = {"a", "o", "as", "os", "de", "da", "do", "das", "dos", "e", "em", "no", "na", "nos", "nas", "para", "com", "por", "um", "uma", "que", "the", "of", "to"}


def parecido(a: str, b: str) -> float:
    """Junta só o que é o MESMO ponto: texto parecido E as mesmas palavras de conteúdo."""
    na, nb = norm(a), norm(b)
    wa, wb = set(na.split()) - PARADAS, set(nb.split()) - PARADAS
    jac = len(wa & wb) / len(wa | wb) if (wa | wb) else 1.0
    return min(difflib.SequenceMatcher(None, na, nb).ratio(), jac + 0.25)


def curto(agente_id: str) -> str:
    return agente_id.removeprefix("ultra-")


def achar_script(nome: str) -> Path | None:
    for c in [AQUI / "scripts" / nome, *AQUI.parent.glob(f"skills/*/scripts/{nome}")]:
        if Path(c).exists():
            return Path(c)
    return None


def py() -> str:
    return sys.executable or "python3"


# ---------------------------------------------------------------- parâmetros

_CACHE: dict = {}


def bibliotecas() -> dict:
    if "bib" not in _CACHE:
        _CACHE["bib"] = {d["id"]: d for d in (ler_json(f) for f in sorted(PARAMS.glob("criterios/*.json")))}
    return _CACHE["bib"]


def agentes() -> dict:
    if "ag" not in _CACHE:
        lista = []
        for f in sorted(PARAMS.glob("agentes/*.json")):
            lista += ler_json(f)
        _CACHE["ag"] = {a["id"]: a for a in lista}
    return _CACHE["ag"]


def conselhos() -> dict:
    if "co" not in _CACHE:
        _CACHE["co"] = ler_json(PARAMS / "conselhos.json")
    return _CACHE["co"]


def regras() -> dict:
    if "re" not in _CACHE:
        _CACHE["re"] = ler_json(PARAMS / "regras.json")
    return _CACHE["re"]


def criterio_global(cid: str) -> dict | None:
    """'oferta.garantia' -> critério da biblioteca; 'jobs.corte' -> critério próprio do agente."""
    lib, _, nome = cid.partition(".")
    b = bibliotecas().get(lib)
    if b:
        return next((dict(c, id=cid) for c in b["criterios"] if c["id"] == nome), None)
    ag = agentes().get("ultra-" + lib)
    if ag:
        return next((dict(c, id=cid) for c in ag.get("criterios", []) if c.get("id") == nome), None)
    return None


def expandir(agente_id: str) -> dict:
    """Parâmetros prontos para o agente: critérios resolvidos com id global, peso e escala."""
    a = agentes().get(agente_id)
    if not a:
        sys.exit(f"Agente desconhecido: {agente_id}. Rode: ultra.py listar")
    out = {k: v for k, v in a.items() if k != "criterios"}
    crits, libs_usadas = [], []
    for c in a.get("criterios", []):
        if "ref" in c:
            g = criterio_global(c["ref"])
            lib = c["ref"].split(".")[0]
            if lib not in libs_usadas:
                libs_usadas.append(lib)
        else:
            g = dict(c, id=f"{curto(agente_id)}.{c['id']}")
        crits.append(g)
    out["criterios"] = crits
    out["peso_total"] = sum(c["peso"] for c in crits)
    extras = {}
    for lib in libs_usadas:
        b = bibliotecas()[lib]
        e = {k: b[k] for k in ("como_avaliar", "numeros_de_bolso", "regras_de_bolso", "formato_oferta", "proibidos", "testes", "alertas") if k in b}
        if e:
            extras[lib] = e
    if agente_id in conselhos()["conselhos"]["vendas"]["membros"]:
        extras.setdefault("oferta", {})["formato_oferta"] = bibliotecas()["oferta"]["formato_oferta"]
    out["bibliotecas"] = extras
    return out


def pesos() -> dict:
    """id global do critério -> peso (inclui critérios próprios de todos os agentes)."""
    if "pe" not in _CACHE:
        p = {f"{b['id']}.{c['id']}": c["peso"] for b in bibliotecas().values() for c in b["criterios"]}
        for aid, a in agentes().items():
            for c in a.get("criterios", []):
                if "id" in c:
                    p[f"{curto(aid)}.{c['id']}"] = c["peso"]
        _CACHE["pe"] = p
    return _CACHE["pe"]


def dimensao(cid: str) -> str:
    c = criterio_global(cid)
    return c.get("dimensao", "outro") if c else "outro"


# ---------------------------------------------------------------- validação

def validar_saida(d: dict, caminho: str = "") -> list[str]:
    e = []
    for k in ("agente", "rodada", "veredito", "notas", "achados", "acoes"):
        if k not in d:
            e.append(f"falta o campo '{k}'")
    if e:
        return e
    ag = agentes().get(d["agente"])
    if not ag:
        return [f"agente '{d['agente']}' não existe"]
    v = d["veredito"]
    if not isinstance(v, dict) or "resumo" not in v or "nota_geral" not in v:
        e.append("veredito precisa de 'resumo' e 'nota_geral'")
    elif v["nota_geral"] is not None and not (isinstance(v["nota_geral"], (int, float)) and 0 <= v["nota_geral"] <= 10):
        e.append("veredito.nota_geral precisa ser 0 a 10 ou null")
    esperados = {c["id"] for c in expandir(d["agente"])["criterios"]}
    vistos = set()
    for i, n in enumerate(d["notas"], 1):
        cid = n.get("criterio", "")
        if cid not in esperados:
            e.append(f"notas[{i}]: critério '{cid}' não é deste agente")
        vistos.add(cid)
        nota = n.get("nota")
        if nota is not None and not (isinstance(nota, (int, float)) and 0 <= nota <= 10):
            e.append(f"notas[{i}] ({cid}): nota precisa ser 0 a 10 ou null")
        if not str(n.get("evidencia", "")).strip():
            e.append(f"notas[{i}] ({cid}): nota sem evidência é inválida")
        if n.get("marca") not in MARCAS:
            e.append(f"notas[{i}] ({cid}): marca precisa ser TESTADO, EVIDENCIA ou HIPOTESE")
    faltam = esperados - vistos
    if faltam and d.get("rodada", 1) == 1 and not ag.get("tipo") == "executor":
        e.append(f"faltam notas para: {', '.join(sorted(faltam))}")
    for i, a in enumerate(d["achados"], 1):
        for k in ("tipo", "texto", "prova", "marca"):
            if not a.get(k):
                e.append(f"achados[{i}]: falta '{k}'")
        if a.get("marca") and a["marca"] not in MARCAS:
            e.append(f"achados[{i}]: marca inválida")
    for i, a in enumerate(d["acoes"], 1):
        for k in ("titulo", "porque", "metrica"):
            if not str(a.get(k, "")).strip():
                e.append(f"acoes[{i}]: falta '{k}'")
        for k in ("impacto", "facilidade"):
            if not isinstance(a.get(k), (int, float)) or not 1 <= a[k] <= 10:
                e.append(f"acoes[{i}]: '{k}' precisa ser 1 a 10")
        if a.get("evidencia") not in MARCAS:
            e.append(f"acoes[{i}]: evidencia precisa ser TESTADO, EVIDENCIA ou HIPOTESE")
        if a.get("etapa") and a["etapa"] not in ETAPAS:
            e.append(f"acoes[{i}]: etapa '{a['etapa']}' inválida ({', '.join(ETAPAS)})")
    for i, o in enumerate(d.get("ofertas", []), 1):
        for k in ("id", "nome", "promessa", "preco"):
            if k not in o:
                e.append(f"ofertas[{i}]: falta '{k}'")
    for i, vt in enumerate(d.get("votos", []), 1):
        if "oferta_id" not in vt or not isinstance(vt.get("notas"), dict):
            e.append(f"votos[{i}]: precisa de 'oferta_id' e 'notas' (objeto criterio -> nota)")
        else:
            for cid, n in vt["notas"].items():
                if not (cid.startswith(("oferta.", "preco.")) and isinstance(n, (int, float)) and 0 <= n <= 10):
                    e.append(f"votos[{i}]: '{cid}': {n} inválido (use critérios oferta.* ou preco.* com nota 0 a 10)")
    return e


def cmd_validar(a):
    alvos = sorted(Path(a.alvo).glob("**/*.json")) if Path(a.alvo).is_dir() else [Path(a.alvo)]
    ruins = 0
    for p in alvos:
        if p.name.startswith(("consolidado", "duelo", "estado", "plano")):
            continue
        try:
            d = ler_json(p)
        except json.JSONDecodeError as ex:
            print(f"✖ {p}: JSON inválido ({ex})")
            ruins += 1
            continue
        if not isinstance(d, dict) or "agente" not in d:
            continue
        e = validar_saida(d, str(p))
        if e:
            ruins += 1
            print(f"✖ {p}")
            print("\n".join(f"   - {x}" for x in e))
        else:
            print(f"✔ {p}  ({d['agente']}, {len(d['notas'])} notas, {len(d['acoes'])} ações)")
    return 1 if ruins else 0


# ---------------------------------------------------------------- consolidação

def nota_ponderada(d: dict) -> float | None:
    p = pesos()
    num = den = 0.0
    for n in d["notas"]:
        if n.get("nota") is None:
            continue
        w = p.get(n["criterio"], 1)
        num += n["nota"] * w
        den += w
    return round(num / den, 1) if den else None


def ice(acao: dict) -> int:
    return round(acao["impacto"] * CONFIANCA.get(acao.get("evidencia", "HIPOTESE"), 4) * acao["facilidade"] / 10)


def juntar_parecidos(itens: list[dict], chave: str, limiar: float) -> list[dict]:
    grupos: list[dict] = []
    for it in itens:
        alvo = next((g for g in grupos if parecido(g[chave], it[chave]) >= limiar), None)
        if alvo:
            alvo["autores"] = sorted(set(alvo["autores"]) | set(it["autores"]))
            alvo["variacoes"].append(it[chave])
            for k in ("impacto", "facilidade"):
                if k in it:
                    alvo[k] = max(alvo[k], it[k]) if k == "impacto" else round((alvo[k] + it[k]) / 2)
            if "evidencia" in it and MARCAS.index(it["evidencia"]) < MARCAS.index(alvo["evidencia"]):
                alvo["evidencia"] = it["evidencia"]
            if not alvo.get("entregavel") and it.get("entregavel"):
                alvo["entregavel"] = it["entregavel"]
        else:
            g = dict(it)
            g["variacoes"] = []
            grupos.append(g)
    return grupos


def carregar_saidas(pasta: Path) -> tuple[list[dict], list[str]]:
    saidas, avisos = [], []
    for p in sorted(pasta.glob("*.json")):
        try:
            d = ler_json(p)
        except json.JSONDecodeError:
            avisos.append(f"{p.name}: JSON inválido, ignorado")
            continue
        if not isinstance(d, dict) or "agente" not in d:
            continue
        e = validar_saida(d)
        if e:
            avisos.append(f"{p.name}: {len(e)} problema(s) ({e[0]}). Rode 'ultra.py validar {p}'")
            if any("falta o campo" in x or "não existe" in x for x in e):
                continue
        d["_arquivo"] = str(p)
        saidas.append(d)
    return saidas, avisos


def consolidar(pasta: Path, rodada: int | None = None) -> dict:
    if rodada is None:
        rs = sorted(int(p.name[1:]) for p in pasta.glob("r[0-9]*") if p.is_dir() and any(p.glob("*.json")))
        rodada = rs[-1] if rs else None
    base = pasta / f"r{rodada}" if rodada else pasta
    saidas, avisos = carregar_saidas(base)
    if not saidas:
        sys.exit(f"Nenhuma saída de agente em {base}")
    cfg = conselhos()

    tabela, dims, por_criterio, votos_vende = [], {}, {}, {}
    placar = {m: 0 for m in MARCAS}
    for d in saidas:
        ag = d["agente"]
        pond = nota_ponderada(d)
        tabela.append({"agente": ag, "nome": agentes()[ag]["nome"], "nota_geral": d["veredito"].get("nota_geral"),
                       "nota_ponderada": pond, "vende": d["veredito"].get("vende", ""), "resumo": d["veredito"].get("resumo", ""),
                       "confianca": d["veredito"].get("confianca", "")})
        votos_vende[d["veredito"].get("vende", "?")] = votos_vende.get(d["veredito"].get("vende", "?"), 0) + 1
        for n in d["notas"]:
            placar[n["marca"]] = placar.get(n["marca"], 0) + 1
            if n.get("nota") is None:
                continue
            dims.setdefault(dimensao(n["criterio"]), {}).setdefault(ag, []).append(n["nota"])
            por_criterio.setdefault(n["criterio"], []).append({"agente": ag, "nota": n["nota"], "evidencia": n["evidencia"], "marca": n["marca"]})
        for x in d["achados"] + d["acoes"]:
            m = x.get("marca") or x.get("evidencia")
            if m in placar:
                placar[m] += 1

    matriz = {dim: {ag: round(sum(v) / len(v), 1) for ag, v in ags.items()} for dim, ags in dims.items()}
    divergencias = []
    lim = cfg.get("divergencia_minima", 4)
    for dim, ags in matriz.items():
        if len(ags) >= 2:
            alto = max(ags, key=ags.get)
            baixo = min(ags, key=ags.get)
            if ags[alto] - ags[baixo] >= lim:
                divergencias.append({"tipo": "dimensao", "sobre": dim, "alto": [alto, ags[alto]], "baixo": [baixo, ags[baixo]],
                                     "diferenca": round(ags[alto] - ags[baixo], 1)})
    for cid, ns in por_criterio.items():
        if len(ns) >= 2:
            alto = max(ns, key=lambda x: x["nota"])
            baixo = min(ns, key=lambda x: x["nota"])
            if alto["nota"] - baixo["nota"] >= lim:
                divergencias.append({"tipo": "criterio", "sobre": cid, "alto": [alto["agente"], alto["nota"], alto["evidencia"]],
                                     "baixo": [baixo["agente"], baixo["nota"], baixo["evidencia"]], "diferenca": alto["nota"] - baixo["nota"]})
    divergencias.sort(key=lambda x: -x["diferenca"])
    consensos = [{"criterio": cid, "media": round(sum(x["nota"] for x in ns) / len(ns), 1), "agentes": [x["agente"] for x in ns]}
                 for cid, ns in por_criterio.items() if len(ns) >= 2 and max(x["nota"] for x in ns) - min(x["nota"] for x in ns) <= cfg.get("consenso_maximo", 1.5)]

    achados = juntar_parecidos([dict(x, autores=[d["agente"]]) for d in saidas for x in d["achados"]], "texto", 0.75)
    ordem_g = {"alta": 0, "media": 1, "baixa": 2, None: 3}
    achados.sort(key=lambda x: (-len(x["autores"]), ordem_g.get(x.get("gravidade")), MARCAS.index(x["marca"]) if x.get("marca") in MARCAS else 3))
    acoes = juntar_parecidos([dict(x, autores=[d["agente"]]) for d in saidas for x in d["acoes"]], "titulo", 0.8)
    for x in acoes:
        x["ice"] = ice(x)
    acoes.sort(key=lambda x: (-x["ice"], -len(x["autores"])))
    perguntas = [{"de": d["agente"], **q} for d in saidas for q in d.get("perguntas", [])]
    discordancias = [{"de": d["agente"], **q} for d in saidas for q in d.get("discorda_de", [])]
    total = sum(placar.values()) or 1
    out = {
        "conselho": pasta.name, "rodada": rodada, "gerado": time.strftime("%Y-%m-%d %H:%M"), "agentes": len(saidas),
        "tabela": sorted(tabela, key=lambda x: -(x["nota_ponderada"] or 0)),
        "votos_vende": votos_vende, "placar": placar,
        "alerta_hipotese": placar["HIPOTESE"] / total > 0.5,
        "matriz_dimensoes": matriz, "divergencias": divergencias, "consensos": consensos,
        "achados": achados, "acoes": acoes, "perguntas": perguntas, "discordancias": discordancias,
        "avisos": avisos,
        "temas": {d["agente"]: d["temas"] for d in saidas if d.get("temas")},
        "entregas": [dict(e, autor=d["agente"]) for d in saidas for e in d.get("entregas", [])],
        "nao_testei": sorted({x for d in saidas for x in d.get("nao_testei", [])}),
    }
    nome = f"consolidado-r{rodada}" if rodada else "consolidado"
    salvar_json(pasta / f"{nome}.json", out)
    (pasta / f"{nome}.md").write_text(consolidado_md(out), encoding="utf-8")
    return out


def consolidado_md(c: dict) -> str:
    nomes = {k: v["nome"] for k, v in agentes().items()}
    L = [f"# Consolidado: {c['conselho']}, rodada {c['rodada']}", f"{c['agentes']} agentes · {c['gerado']}", ""]
    if c["avisos"]:
        L += ["**Avisos:**"] + [f"- {x}" for x in c["avisos"]] + [""]
    tot = sum(c["placar"].values()) or 1
    L.append(f"**Placar de evidência:** TESTADO {c['placar']['TESTADO']} · EVIDENCIA {c['placar']['EVIDENCIA']} · "
             f"HIPOTESE {c['placar']['HIPOTESE']} ({round(100 * c['placar']['HIPOTESE'] / tot)}% hipótese)"
             + ("  ⚠ mais da metade é hipótese" if c["alerta_hipotese"] else ""))
    L.append(f"**Vende?** " + ", ".join(f"{k}: {v}" for k, v in c["votos_vende"].items()))
    L += ["", "## Notas por agente", "| Agente | Nota geral | Ponderada pelos critérios | Vende | Resumo |", "|---|---|---|---|---|"]
    for t in c["tabela"]:
        L.append(f"| {t['nome']} | {t['nota_geral']} | {t['nota_ponderada']} | {t['vende']} | {t['resumo']} |")
    dims = sorted(c["matriz_dimensoes"])
    ags = sorted({a for d in c["matriz_dimensoes"].values() for a in d})
    if dims and ags:
        L += ["", "## Matriz: dimensão × agente (média das notas)", "| Dimensão | " + " | ".join(nomes.get(a, a) for a in ags) + " |",
              "|" + "---|" * (len(ags) + 1)]
        for dm in dims:
            L.append(f"| {dm} | " + " | ".join(str(c["matriz_dimensoes"][dm].get(a, "")) for a in ags) + " |")
    L += ["", f"## Divergências (diferença ≥ {conselhos().get('divergencia_minima', 4)}): o que vai para debate"]
    if not c["divergencias"]:
        L.append("- nenhuma: se todos concordam em tudo, desconfie (regra do André)")
    for d in c["divergencias"]:
        if d["tipo"] == "criterio":
            L.append(f"- **{d['sobre']}**: {nomes.get(d['alto'][0])} deu {d['alto'][1]} ({d['alto'][2][:120]}) × "
                     f"{nomes.get(d['baixo'][0])} deu {d['baixo'][1]} ({d['baixo'][2][:120]})")
        else:
            L.append(f"- **{d['sobre']}** (dimensão): {nomes.get(d['alto'][0])} {d['alto'][1]} × {nomes.get(d['baixo'][0])} {d['baixo'][1]}")
    if c["consensos"]:
        L += ["", "## Consensos (mesmo critério, notas próximas)"] + [
            f"- {x['criterio']}: {x['media']} ({', '.join(nomes.get(a, a) for a in x['agentes'])})" for x in c["consensos"]]
    L += ["", "## Achados (repetidos contam uma vez, com todos os autores)"]
    for x in c["achados"][:25]:
        L.append(f"- [{x.get('marca')}] {x['texto']} — prova: {x['prova'][:160]} ({', '.join(nomes.get(a, a) for a in x['autores'])})")
    L += ["", "## Ações por prioridade (ICE = impacto × confiança × facilidade ÷ 10)", "| ICE | Ação | Evidência | Autores |", "|---|---|---|---|"]
    for x in c["acoes"][:25]:
        L.append(f"| {x['ice']} | {x['titulo']} | {x['evidencia']} | {', '.join(nomes.get(a, a) for a in x['autores'])} |")
    if c["perguntas"]:
        L += ["", "## Perguntas entre agentes"] + [f"- {nomes.get(p['de'])} → {nomes.get(p['para'], p['para'])}: {p['pergunta']}" for p in c["perguntas"]]
    if c["discordancias"]:
        L += ["", "## Discordâncias declaradas"] + [f"- {nomes.get(p['de'])} discorda de {nomes.get(p.get('agente'), p.get('agente'))}: {p.get('ponto')} ({p.get('porque')})" for p in c["discordancias"]]
    if c["temas"]:
        L += ["", "## Temas"]
        for ag, t in c["temas"].items():
            L.append(f"**{nomes.get(ag)}**")
            L += [f"- {k}: {v}" for k, v in t.items()]
    if c["nao_testei"]:
        L += ["", "## Não testado"] + [f"- {x}" for x in c["nao_testei"]]
    return "\n".join(L) + "\n"


def cmd_consolidar(a):
    c = consolidar(Path(a.pasta), a.rodada)
    print(f"{c['agentes']} agentes · {len(c['divergencias'])} divergências · {len(c['acoes'])} ações únicas · "
          f"placar T{c['placar']['TESTADO']}/E{c['placar']['EVIDENCIA']}/H{c['placar']['HIPOTESE']}")
    for d in c["divergencias"][:5]:
        print(f"  ! {d['sobre']}: {d['alto'][0]} {d['alto'][1]} x {d['baixo'][0]} {d['baixo'][1]}")
    for av in c["avisos"]:
        print(f"  aviso: {av}")
    print(f"-> {Path(a.pasta) / ('consolidado-r' + str(c['rodada']) if c['rodada'] else 'consolidado')}.md")


# ---------------------------------------------------------------- duelo de ofertas

def duelo(pasta: Path) -> dict:
    ofertas, autores = {}, {}
    for d, _ in [(x, 0) for x in carregar_saidas(pasta / "r1")[0]]:
        for o in d.get("ofertas", []):
            ofertas[o["id"]] = o
            autores[o["id"]] = d["agente"]
    if not ofertas:
        sys.exit(f"Nenhuma oferta em {pasta / 'r1'}")
    votos, _ = carregar_saidas(pasta / "r2")
    p = pesos()
    matriz = {oid: {} for oid in ofertas}          # oferta -> votante -> nota ponderada
    por_crit = {oid: {} for oid in ofertas}        # oferta -> criterio -> [notas de outros]
    for d in votos:
        for vt in d.get("votos", []):
            oid = vt["oferta_id"]
            if oid not in ofertas:
                continue
            num = sum(n * p.get(c, 1) for c, n in vt["notas"].items())
            den = sum(p.get(c, 1) for c in vt["notas"])
            matriz[oid][d["agente"]] = round(num / den, 2) if den else None
            if d["agente"] != autores[oid]:
                for c, n in vt["notas"].items():
                    por_crit[oid].setdefault(c, []).append(n)
    ranking = []
    for oid in ofertas:
        outros = [v for ag, v in matriz[oid].items() if ag != autores[oid] and v is not None]
        todos = [v for v in matriz[oid].values() if v is not None]
        ranking.append({"oferta_id": oid, "autor": autores[oid], "nome": ofertas[oid].get("nome"),
                        "nota_dos_outros": round(sum(outros) / len(outros), 2) if outros else None,
                        "nota_com_propria": round(sum(todos) / len(todos), 2) if todos else None,
                        "autovoto": matriz[oid].get(autores[oid]), "votos": matriz[oid]})
    ranking.sort(key=lambda x: -(x["nota_dos_outros"] or 0))
    criterios = sorted({c for o in por_crit.values() for c in o})
    melhores = {}
    for c in criterios:
        medias = {oid: sum(v) / len(v) for oid, crs in por_crit.items() for cc, v in crs.items() if cc == c and v}
        if medias:
            oid = max(medias, key=medias.get)
            melhores[c] = {"oferta_id": oid, "autor": autores[oid], "media": round(medias[oid], 1)}
    roubos = [{"de": d["agente"], "oferta_id": vt["oferta_id"], "roubaria": vt["roubaria"]}
              for d in votos for vt in d.get("votos", []) if vt.get("roubaria")]
    out = {"gerado": time.strftime("%Y-%m-%d %H:%M"), "ranking": ranking, "vencedora": ranking[0] if ranking else None,
           "melhor_componente_por_criterio": melhores, "roubos": roubos, "ofertas": ofertas,
           "votantes": [d["agente"] for d in votos]}
    salvar_json(pasta / "duelo.json", out)
    (pasta / "duelo.md").write_text(duelo_md(out), encoding="utf-8")
    return out


def duelo_md(d: dict) -> str:
    nomes = {k: v["nome"] for k, v in agentes().items()}
    L = ["# Duelo de ofertas", f"Votantes: {', '.join(nomes.get(v, v) for v in d['votantes'])} · {d['gerado']}", "",
         "A nota que decide é a dos OUTROS (autovoto não conta), ponderada pelos pesos dos critérios de oferta e preço.", "",
         "| # | Oferta | Autor | Nota dos outros | Autovoto | Preço |", "|---|---|---|---|---|---|"]
    for i, r in enumerate(d["ranking"], 1):
        pr = d["ofertas"][r["oferta_id"]].get("preco", {})
        preco = f"{pr.get('moeda', '')} {pr.get('principal', '')}".strip() if isinstance(pr, dict) else pr
        L.append(f"| {i} | {r['nome']} | {nomes.get(r['autor'])} | {r['nota_dos_outros']} | {r['autovoto']} | {preco} |")
    if d["vencedora"]:
        L += ["", f"**Vencedora:** {d['vencedora']['nome']} ({nomes.get(d['vencedora']['autor'])}). "
                  f"O autor monta a OFERTA CAMPEÃ juntando os melhores componentes abaixo."]
    L += ["", "## Melhor componente por critério (média dos outros)", "| Critério | Melhor oferta | Autor | Média |", "|---|---|---|---|"]
    for c, m in sorted(d["melhor_componente_por_criterio"].items()):
        L.append(f"| {c} | {d['ofertas'][m['oferta_id']].get('nome')} | {nomes.get(m['autor'])} | {m['media']} |")
    if d["roubos"]:
        L += ["", "## O que cada um roubaria"] + [f"- {nomes.get(r['de'])} roubaria de {r['oferta_id']}: {r['roubaria']}" for r in d["roubos"]]
    L += ["", "## As ofertas"]
    for oid, o in d["ofertas"].items():
        L.append(f"### {o.get('nome')} ({oid})")
        for k in ("publico", "promessa", "mecanismo", "headline", "por_que_vence"):
            if o.get(k):
                L.append(f"- {k}: {o[k]}")
        if o.get("garantia"):
            L.append(f"- garantia: {o['garantia']}")
        if o.get("niveis"):
            L.append("- níveis: " + "; ".join(f"{n.get('nome')} {n.get('preco')}" for n in o["niveis"]))
    return "\n".join(L) + "\n"


def cmd_duelo(a):
    d = duelo(Path(a.pasta))
    for i, r in enumerate(d["ranking"], 1):
        print(f"{i}. {r['nome']} ({r['autor']}): {r['nota_dos_outros']} dos outros · autovoto {r['autovoto']}")
    print(f"-> {Path(a.pasta) / 'duelo.md'}")


# ---------------------------------------------------------------- logo

def logo_teste(img: Path, saida: Path | None = None, fundo: str = "#111111") -> Path:
    try:
        from PIL import Image, ImageDraw, ImageFont, ImageOps
    except ImportError:
        sys.exit("logo-teste precisa do Pillow: pip install pillow")
    if img.suffix.lower() == ".svg":
        sys.exit("SVG não é lido sem conversor. Exporte um PNG do logo (ou abra o SVG no navegador e tire print).")
    im = Image.open(img)
    if getattr(im, "n_frames", 1) > 1 and img.suffix.lower() == ".ico":
        im.seek(max(range(im.n_frames), key=lambda i: (im.seek(i), im.size[0])[1]))
    im = im.convert("RGBA")
    bbox = im.getbbox()
    if bbox:
        im = im.crop(bbox)
    alpha = im.split()[3]
    tem_alpha = alpha.getextrema()[0] < 250
    cinza = ImageOps.grayscale(im)
    if not tem_alpha:  # fundo sólido: o que difere do fundo é logo
        alpha = cinza.point(lambda v: 255 if v < 235 else 0)
    # uma cor: dentro da área opaca, o que é escuro vira tinta e o que é claro vira "furo"
    dados = lambda i: list(i.get_flattened_data()) if hasattr(i, "get_flattened_data") else list(i.getdata())  # noqa: E731
    px = [c for c, a_ in zip(dados(cinza), dados(alpha)) if a_ > 128]
    limiar = (sum(px) / len(px)) if px else 128
    mascara = Image.new("L", im.size, 0)
    mascara.putdata([255 if (a_ > 128 and c <= limiar) else 0 for c, a_ in zip(dados(cinza), dados(alpha))])
    preto = Image.new("RGBA", im.size, (0, 0, 0, 255))
    preto.putalpha(mascara)
    branco = Image.new("RGBA", im.size, (255, 255, 255, 255))
    branco.putalpha(mascara)
    fonte = None
    for nome in ("DejaVuSans.ttf", "Arial.ttf", "arial.ttf", "Helvetica.ttc", "segoeui.ttf"):
        try:
            fonte = ImageFont.truetype(nome, 13)
            break
        except OSError:
            continue
    if fonte is None:
        try:
            fonte = ImageFont.load_default(size=13)
        except TypeError:
            fonte = ImageFont.load_default()
    versoes = [("original / claro", im, (255, 255, 255)), ("original / escuro", im, tuple(int(fundo[i:i + 2], 16) for i in (1, 3, 5))),
               ("uma cor", preto, (255, 255, 255)), ("invertido", branco, (17, 17, 17))]
    tamanhos = [16, 32, 64, 110]
    cel, margem, topo = 130, 20, 34
    W = margem * 2 + 150 + cel * len(tamanhos) + 150
    H = topo + margem + (cel + 10) * len(versoes) + 40
    folha = Image.new("RGB", (W, H), (245, 245, 245))
    d = ImageDraw.Draw(folha)
    d.text((margem, 10), font=fonte, text=f"Folha de teste do logo: {img.name}  ({im.size[0]}x{im.size[1]} px; transparência: {'sim' if tem_alpha else 'não'})", fill=(20, 20, 20))
    for j, t in enumerate(tamanhos):
        d.text((margem + 150 + j * cel + 4, topo), f"{t}px" + (" (aba)" if t == 16 else ""), fill=(80, 80, 80), font=fonte)
    d.text((margem + 150 + len(tamanhos) * cel + 4, topo), "16px ampliado", fill=(80, 80, 80), font=fonte)
    for i, (rotulo, v, cor) in enumerate(versoes):
        y = topo + 16 + i * (cel + 10)
        d.text((margem, y + cel // 2 - 6), rotulo, fill=(20, 20, 20), font=fonte)
        for j, t in enumerate(tamanhos + [16]):
            x = margem + 150 + j * cel
            d.rectangle([x, y, x + cel - 10, y + cel - 10], fill=cor)
            esc = t / max(v.size)
            mini = v.resize((max(1, round(v.size[0] * esc)), max(1, round(v.size[1] * esc))), Image.LANCZOS)
            if j == len(tamanhos):  # 16 px ampliado: mostra o que sobra de verdade
                f = 6
                mini = mini.resize((mini.size[0] * f, mini.size[1] * f), Image.NEAREST)
            px = x + (cel - 10 - mini.size[0]) // 2
            py_ = y + (cel - 10 - mini.size[1]) // 2
            folha.paste(mini, (px, py_), mini)
    d.text((margem, H - 26), "Régua: logo.pequeno (16/32 px), logo.uma_cor, logo.invertido, logo.simplicidade. Nota null se não deu para ver.", fill=(90, 90, 90), font=fonte)
    destino = saida or img.with_name(img.stem + "-folha-teste.png")
    if destino.is_dir():
        destino = destino / (img.stem + "-folha-teste.png")
    folha.save(destino)
    return destino


def cmd_logo(a):
    p = logo_teste(Path(a.imagem), Path(a.saida) if a.saida else None, a.fundo)
    print(f"folha de teste -> {p}")


# ---------------------------------------------------------------- pipeline

def pasta_run(arg: str | None) -> Path:
    if arg:
        return Path(arg)
    runs = sorted(Path(".").glob("ultra-run-*/estado.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not runs:
        sys.exit("Nenhuma pasta ultra-run-* aqui. Comece com: ultra.py iniciar URL")
    return runs[0].parent


def cmd_iniciar(a):
    url = a.url if "://" in a.url else "https://" + a.url
    host = urlparse(url).netloc
    pasta = Path(a.pasta) if a.pasta else Path("ultra-run-" + "".join(c if c.isalnum() or c in ".-" else "_" for c in host))
    (pasta / "01-scan").mkdir(parents=True, exist_ok=True)
    scan = achar_script("scan.py")
    if not scan:
        sys.exit("scan.py não encontrado. Reinstale com install.py.")
    cmd = [py(), str(scan), url, *a.concorrentes, "--saida", str(pasta / "01-scan"), "--links"]
    if a.print:
        cmd.append("--print")
    print("->", " ".join(cmd), flush=True)
    t0 = time.perf_counter()
    rc = subprocess.call(cmd)
    folhas = []
    for logo in sorted((pasta / "01-scan").glob("*-logo-*")):
        if "folha-teste" in logo.name or logo.suffix.lower() == ".svg":
            continue
        try:
            folhas.append(str(logo_teste(logo)))
        except SystemExit as e:
            print(f"   logo {logo.name}: {e}")
        except Exception as e:  # noqa: BLE001
            print(f"   logo {logo.name}: não deu para gerar a folha ({e})")
    salvar_json(pasta / "estado.json", {"url": url, "concorrentes": a.concorrentes, "criado": time.strftime("%Y-%m-%d %H:%M"),
                                        "scan_rc": rc, "scan_s": round(time.perf_counter() - t0, 1), "folhas_logo": folhas})
    if folhas:
        print("folhas de teste do logo:", *folhas, sep="\n  ")
    print(f"\nPasta da análise: {pasta}")
    cmd_proximo(argparse.Namespace(pasta=str(pasta), json=False))


def arquivos_de_entrada(pasta: Path, conselho: str, n: int) -> list[str]:
    scan = sorted(str(p) for p in (pasta / "01-scan").glob("*.md"))
    folhas = sorted(str(p) for p in (pasta / "01-scan").glob("*folha-teste*.png"))
    prints = sorted(str(p) for p in (pasta / "01-scan").glob("*-desktop.png")) + sorted(str(p) for p in (pasta / "01-scan").glob("*-mobile.png"))
    cons = lambda c: sorted(str(p) for p in (pasta / conselhos()["conselhos"][c]["pasta"]).glob("consolidado-r*.md"))  # noqa: E731
    ent = list(scan)
    if conselho in ("pessoas", "fundadores", "marketing"):
        ent += prints + folhas
    if conselho == "pessoas" and n == 2:
        ent += sorted(str(p) for p in (pasta / "02-pessoas" / "r1").glob("*.json")) + cons("pessoas")
    if conselho in ("fundadores", "vendas", "marketing", "plano"):
        ent += cons("pessoas") + sorted(str(p) for p in (pasta / "02-pessoas" / "r2").glob("*.json"))
    if conselho == "fundadores" and n == 2:
        ent += cons("fundadores")
    if conselho in ("vendas", "marketing", "plano"):
        ent += cons("fundadores")
    if conselho == "vendas" and n == 2:
        ent += sorted(str(p) for p in (pasta / "04-vendas" / "r1").glob("*.json"))
    if conselho in ("marketing", "plano"):
        ent += [str(p) for p in [pasta / "04-vendas" / "duelo.md", pasta / "04-vendas" / "r3" / "oferta-campea.json"] if p.exists()]
    if conselho == "plano":
        ent += cons("marketing") + [str(p) for p in (pasta / "06-plano").glob("*.md")]
    return list(dict.fromkeys(ent))


def rodada_feita(pasta: Path, r: dict) -> bool:
    saida = r["saida"]
    if "{agente}" in saida:
        return all((pasta / saida.format(agente=ag)).exists() for ag in r["quem"])
    if saida.endswith("duelo.md"):
        return (pasta / saida).exists() and (pasta / "04-vendas" / "r3" / "oferta-campea.json").exists()
    return (pasta / saida).exists()


def auto_consolidar(pasta: Path):
    """Consolida sozinho rodadas completas que ainda não têm consolidado (é instantâneo)."""
    for nome, c in conselhos()["conselhos"].items():
        for r in c["rodadas"]:
            if "{agente}" not in r["saida"] or not rodada_feita(pasta, r):
                continue
            alvo = pasta / c["pasta"] / f"consolidado-r{r['n']}.json"
            if not alvo.exists():
                try:
                    consolidar(pasta / c["pasta"], r["n"])
                except SystemExit:
                    pass
        if nome == "vendas" and rodada_feita(pasta, c["rodadas"][1]) and not (pasta / "04-vendas" / "duelo.json").exists():
            try:
                duelo(pasta / "04-vendas")
            except SystemExit:
                pass


def proxima(pasta: Path) -> tuple[str, dict, dict] | None:
    for nome in conselhos()["pipeline"]:
        c = conselhos()["conselhos"][nome]
        for r in c["rodadas"]:
            if rodada_feita(pasta, r):
                continue
            if r.get("so_se") and nome == "fundadores":
                cons = pasta / c["pasta"] / "consolidado-r1.json"
                if cons.exists() and not ler_json(cons)["divergencias"]:
                    continue
            return nome, c, r
    return None


def cmd_proximo(a):
    pasta = pasta_run(a.pasta)
    auto_consolidar(pasta)
    p = proxima(pasta)
    if not p:
        msg = {"feito": True, "entregar": [str(x) for x in (pasta / "06-plano").glob("plano-de-acao.*")]}
        print(json.dumps(msg, ensure_ascii=False) if a.json else "Tudo feito. Entregue 06-plano/plano-de-acao.pdf, plano-para-ia.md e checklist.csv.")
        return
    nome, c, r = p
    entradas = arquivos_de_entrada(pasta, nome, r["n"])
    tarefas = []
    for ag in r["quem"]:
        saida = (pasta / r["saida"].format(agente=ag)).resolve()
        tarefas.append({"agente": ag, "salvar_em": str(saida), "ler": [str(Path(x).resolve()) for x in entradas],
                        "tarefa": r["tarefa"], "rodada": r["n"], "conselho": nome})
    if a.json:
        print(json.dumps({"conselho": nome, "rodada": r["n"], "paralelo": r.get("paralelo", False), "tarefas": tarefas}, ensure_ascii=False, indent=1))
        return
    print(f"\nPRÓXIMO: conselho '{c['nome']}', rodada {r['n']} " + ("(chame os agentes EM PARALELO)" if r.get("paralelo") else ""))
    for t in tarefas:
        print(f"\n--- {t['agente']} ---")
        print(f"Tarefa: {t['tarefa']}")
        print(f"Rodada: {t['rodada']}. Salve em: {t['salvar_em']}")
        print("Leia:")
        for x in t["ler"]:
            print(f"  - {x}")
    print(f"\nDepois: \"{py()}\" \"{Path(__file__).resolve()}\" proximo --pasta {pasta}  (consolida sozinho e mostra a rodada seguinte)")


def cmd_status(a):
    pasta = pasta_run(a.pasta)
    est = ler_json(pasta / "estado.json") if (pasta / "estado.json").exists() else {}
    print(f"Análise de {est.get('url', '?')} em {pasta}")
    for nome in conselhos()["pipeline"]:
        c = conselhos()["conselhos"][nome]
        for r in c["rodadas"]:
            print(f"  [{'x' if rodada_feita(pasta, r) else ' '}] {c['nome']} · rodada {r['n']} · {', '.join(curto(x) for x in r['quem'])}")


# ---------------------------------------------------------------- plano

def cmd_plano(a):
    pasta = Path(a.pasta)
    est = ler_json(pasta / "estado.json") if (pasta / "estado.json").exists() else {}
    url = est.get("url", "")
    todas, entregas, vende, notas = [], [], {}, []
    for nome in ("pessoas", "fundadores", "vendas", "marketing"):
        cpasta = pasta / conselhos()["conselhos"][nome]["pasta"]
        cons = sorted(cpasta.glob("consolidado-r*.json"))
        if not cons:
            continue
        c = ler_json(cons[-1])
        todas += [dict(x, conselho=nome) for x in c["acoes"]]
        entregas += c.get("entregas", [])
        for k, v in c["votos_vende"].items():
            vende[k] = vende.get(k, 0) + v
        notas += [t["nota_ponderada"] for t in c["tabela"] if t["nota_ponderada"] is not None]
    if not todas:
        sys.exit("Nenhum consolidado encontrado. Rode os conselhos antes.")
    acoes = juntar_parecidos([dict(x, autores=x.get("autores", [])) for x in todas], "titulo", 0.8)
    for x in acoes:
        x["ice"] = ice(x)
    acoes.sort(key=lambda x: -x["ice"])
    nomes = {k: v["nome"] for k, v in agentes().items()}
    veredito_md = pasta / "06-plano" / "VEREDITO.md"
    veredito = ""
    if veredito_md.exists():
        linhas = [l.strip("# ").strip() for l in veredito_md.read_text(encoding="utf-8").splitlines() if l.strip()]
        veredito = next((l for l in linhas if len(l) > 30), linhas[0] if linhas else "")
    if not veredito:
        maioria = max(vende, key=vende.get) if vende else "?"
        veredito = f"{maioria.capitalize()} (maioria dos agentes; nota média {round(sum(notas) / len(notas), 1) if notas else '?'}/10)."
    estrategia = next((e.get("texto") for e in entregas if e.get("tipo") == "posicionamento" and e.get("texto")), "")
    plano = {"projeto": {"nome": urlparse(url).netloc or pasta.name, "url": url, "veredito": veredito,
                         "estrategia_unica": estrategia or "(preencher com a entrega de posicionamento do conselho de marketing)",
                         "resumo": f"Plano gerado a partir de {len(todas)} ações de {len({a for x in todas for a in x.get('autores', [])})} agentes Ultra, "
                                   f"deduplicadas em {len(acoes)} e ordenadas por ICE."},
             "acoes": [], "ofertas": [], "ativos": [], "paleta": [], "conteudo": [], "metricas": [], "suposicoes": [], "fontes": []}
    for x in acoes[: a.max]:
        plano["acoes"].append({"titulo": x["titulo"], "etapa": x.get("etapa") if x.get("etapa") in ETAPAS else "outro",
                               "semana": x.get("semana", 1), "dono": x.get("dono", "—"),
                               "impacto": x["impacto"], "facilidade": x["facilidade"], "evidencia": x["evidencia"],
                               "porque": x["porque"] + f" (agentes: {', '.join(nomes.get(a, a) for a in x.get('autores', []))})",
                               "passos": x.get("passos", []), "entregavel": x.get("entregavel", ""), "metrica": x["metrica"],
                               "meta": x.get("meta", "")})
    campea = pasta / "04-vendas" / "r3" / "oferta-campea.json"
    fontes_ofertas = []
    if campea.exists():
        oc = ler_json(campea)
        fontes_ofertas = oc.get("ofertas") or ([oc] if isinstance(oc, dict) else oc)
    elif (pasta / "04-vendas" / "duelo.json").exists():
        dd = ler_json(pasta / "04-vendas" / "duelo.json")
        fontes_ofertas = [dd["ofertas"][r["oferta_id"]] for r in dd["ranking"]]
    for o in fontes_ofertas:
        pr = o.get("preco", {})
        plano["ofertas"].append({k: v for k, v in {
            "nome": o.get("nome"), "publico": o.get("publico"), "dor": o.get("dor", ""), "promessa": o.get("promessa"),
            "inclui": "; ".join(c.get("item", "") for c in o.get("componentes", [])) if isinstance(o.get("componentes"), list) else o.get("inclui", ""),
            "preco": (f"{pr.get('moeda', '')} {pr.get('principal', '')}" + (f" ({pr.get('parcelas')})" if pr.get("parcelas") else "")).strip() if isinstance(pr, dict) else pr,
            "garantia": (f"{o['garantia'].get('tipo', '')} {o['garantia'].get('prazo_dias', '')} dias. {o['garantia'].get('como_pedir', '')}".strip() if isinstance(o.get("garantia"), dict) else o.get("garantia", "")),
            "urgencia": (o["urgencia"].get("motivo_real", "") if isinstance(o.get("urgencia"), dict) else o.get("urgencia", "")),
            "canal": o.get("canal", ""), "headline": o.get("headline", "")}.items() if v})
    for e in entregas:
        if e.get("tipo") == "paleta" and e.get("cores"):
            for i, c in enumerate(e["cores"]):
                if re.fullmatch(r"#[0-9a-fA-F]{6}", str(c.get("hex", ""))) and not any(p["hex"] == c["hex"] for p in plano["paleta"]):
                    plano["paleta"].append({"hex": c["hex"], "nome": c.get("nome", ""), "uso": c.get("uso", ""), **({"destaque": True} if c.get("destaque") else {})})
        elif e.get("tipo") == "ideias_conteudo" and e.get("itens"):
            plano["conteudo"] += [i for i in e["itens"] if isinstance(i, dict)]
        elif e.get("texto"):
            plano["ativos"].append({"tipo": e.get("tipo", ""), "titulo": f"{e.get('titulo', '')} ({nomes.get(e.get('autor'), e.get('autor'))})", "texto": e["texto"]})
    plano["metricas"] = [{"nome": x["metrica"], "atual": "?", "meta": x.get("meta", ""), "quando": f"semana {x.get('semana', '?')}"} for x in acoes[:5]]
    plano["suposicoes"] = [x["titulo"] + ": " + x["porque"][:120] for x in acoes if x["evidencia"] == "HIPOTESE"][:8]
    plano["fontes"] = [f"Scan de {url} e concorrentes {', '.join(est.get('concorrentes', []))}".strip(), "Saídas dos agentes em 02 a 05 (consolidado-r*.md)"]
    destino = pasta / "06-plano" / "plano.json"
    salvar_json(destino, plano)
    print(f"{len(plano['acoes'])} ações · {len(plano['ofertas'])} ofertas · {len(plano['ativos'])} ativos · {len(plano['paleta'])} cores · {len(plano['conteudo'])} ideias")
    print(f"-> {destino}")
    if a.pdf:
        g = achar_script("gerar.py")
        if not g:
            sys.exit("gerar.py (mega-plano) não encontrado")
        subprocess.call([py(), str(g), str(destino), "--saida", str(destino.parent)])


# ---------------------------------------------------------------- build dos agentes

def esqueleto_saida(ag: dict) -> dict:
    exemplo = {"agente": ag["id"], "rodada": 1, "alvo": "https://...",
               "veredito": {"vende": "vende pouco", "resumo": "1 a 2 linhas", "nota_geral": 0, "confianca": "media", "mudaria_com": "o dado que mudaria"},
               "notas": [{"criterio": c["id"], "nota": 0, "evidencia": "trecho, número ou print que justifica", "marca": "TESTADO"} for c in ag["criterios"][:2]],
               "achados": [{"tipo": "acusacao", "texto": "o que é", "prova": "a evidência", "custo": "o que custa", "marca": "EVIDENCIA", "gravidade": "alta"}],
               "acoes": [{"titulo": "verbo + objeto", "etapa": "site", "semana": 1, "dono": "quem", "impacto": 8, "facilidade": 7, "evidencia": "TESTADO",
                          "porque": "a prova", "passos": ["..."], "entregavel": "TEXTO PRONTO", "metrica": "o que medir", "meta": "+x%"}],
               "perguntas": [{"para": "ultra-...", "pergunta": "..."}], "nao_testei": ["..."]}
    if ag["id"] in conselhos()["conselhos"]["fundadores"]["membros"]:
        exemplo["temas"] = {"crescimento": "", "diferencial": "", "nivel_de_quem_usa": "", "design": "", "vendas_marketing": ""}
    if ag["id"] in conselhos()["conselhos"]["vendas"]["membros"]:
        exemplo["ofertas"] = ["(rodada 1) uma oferta no formato_oferta"]
        exemplo["votos"] = [{"oferta_id": "of-...", "notas": {"oferta.garantia": 8, "preco.ancora": 6}, "roubaria": "o melhor componente", "comentario": "..."}]
    if "etapas" in ag:
        exemplo["entregas"] = [{"etapa": ag["etapas"][0], "tipo": "copy", "titulo": "...", "texto": "ENTREGA PRONTA"},
                               {"etapa": "identidade", "tipo": "paleta", "titulo": "Paleta", "cores": [{"hex": "#000000", "nome": "", "uso": "", "destaque": False}]}]
    return exemplo


def prompt_agente(aid: str, para: str) -> str:
    ag = expandir(aid)
    rg = regras()
    executor = ag.get("tipo") == "executor"
    ultra = "~/.ultra-skills/ultra.py"
    L = [f"# {ag['nome']}: {ag['titulo']}", "",
         f"Você é o agente `{aid}` do sistema Ultra. Você não interpreta um personagem: você RODA os parâmetros abaixo "
         f"(critérios com peso e régua, testes, alertas e números com fonte), tirados das obras de {ag['nome']}"
         + (" e de quem formou essa mente." if ag.get("escola") else ".") + " Raciocine pela lógica dele; nunca invente frases entre aspas.", ""]
    L += ["## Como trabalhar", ""]
    if executor:
        L += [f"1. Leia a tarefa do orquestrador (o que fazer, o que ler e onde salvar).",
              f"2. Rode os comandos dos parâmetros (`comandos`). Python: `python3` (Windows: `py`). O motor fica em `{ultra}` (Windows: `%USERPROFILE%\\.ultra-skills\\ultra.py`).",
              "3. Confira o resultado antes de entregar e salve exatamente no caminho pedido.",
              "4. Responda ao orquestrador em até 6 linhas: o que foi feito, caminhos e o que ficou de fora."]
    else:
        L += ["1. Leia a tarefa do orquestrador: ela diz a rodada, os arquivos para ler (mapa do scan, prints, folhas de logo, consolidados) e onde salvar.",
              "2. Leia os arquivos. Se puder testar algo da sua régua (abrir página, buscar concorrente, rodar PageSpeed), teste: TESTADO vale mais que tudo.",
              "3. Dê nota de 0 a 10 a CADA critério de PARÂMETROS.criterios, usando a escala do critério. Cada nota tem evidência e marca. Sem como ver: nota null e 'não vi: motivo'.",
              "4. Escreva achados (3 a 5) e ações com entregável PRONTO. Faça as perguntas de `pergunta_para` no campo `perguntas`.",
              f"5. Salve o JSON no caminho pedido e rode `python3 {ultra} validar CAMINHO`. Corrija até passar.",
              "6. Responda ao orquestrador só com: caminho, nota_geral, veredito em 1 linha e as 3 ações de maior impacto."]
    L += ["", "## Regras (sempre)", ""] + [f"- {r}" for r in rg["regras"]]
    L += ["", "Escada de evidência: " + " > ".join(rg["escada_de_evidencia"]), "", rg["notas"], "", rg["acoes"]]
    if not executor:
        L += ["", "## Formato da saída (JSON)", "", "Esqueleto (complete todos os critérios; schema completo em ~/.ultra-skills/params/saida.schema.json):", "",
              "```json", json.dumps(esqueleto_saida(ag), ensure_ascii=False, indent=1), "```"]
    corpo = {k: v for k, v in ag.items() if k not in ("conselhos",)}
    if para == "chatgpt":
        L += ["", "## Parâmetros", "", f"Os parâmetros completos estão no arquivo de conhecimento `{aid}.json`. Leia antes de responder. "
              "Sem terminal: entregue o JSON na resposta, em bloco de código, em vez de salvar arquivo."]
    else:
        L += ["", "## PARÂMETROS", "", "```json", json.dumps(corpo, ensure_ascii=False, indent=1), "```"]
    return "\n".join(L) + "\n"


def descricao(aid: str) -> str:
    ag = agentes()[aid]
    cons = ", ".join(conselhos()["conselhos"][c]["nome"] for c in ag.get("conselhos", []) if c in conselhos()["conselhos"])
    return f"Agente Ultra: {ag['nome']} ({ag['titulo']}). Use quando a análise Ultra (skill analise-ultra) chamar o conselho {cons}."


def cmd_build(a):
    base = Path(a.saida) if a.saida else AQUI.parent / "agents"
    (base / "claude").mkdir(parents=True, exist_ok=True)
    (base / "codex").mkdir(parents=True, exist_ok=True)
    (base / "chatgpt").mkdir(parents=True, exist_ok=True)
    tools = "Read, Write, Edit, Bash, Glob, Grep, WebSearch, WebFetch"
    for aid in agentes():
        desc = descricao(aid)
        claude = prompt_agente(aid, "claude")
        (base / "claude" / f"{aid}.md").write_text(
            f"---\nname: {aid}\ndescription: {json.dumps(desc, ensure_ascii=False)}\ntools: {tools}\nmodel: inherit\n---\n\n{claude}", encoding="utf-8")
        codex = prompt_agente(aid, "codex")
        if "'''" in codex:
            sys.exit(f"{aid}: o texto tem ''' e quebraria o TOML")
        (base / "codex" / f"{aid}.toml").write_text(
            f"name = {json.dumps(aid)}\ndescription = {json.dumps(desc, ensure_ascii=False)}\n"
            f"nickname_candidates = [{json.dumps(agentes()[aid]['nome'], ensure_ascii=False)}]\n"
            f"developer_instructions = '''\n{codex}'''\n", encoding="utf-8")
        gpt = prompt_agente(aid, "chatgpt")
        pasta_gpt = base / "chatgpt" / aid
        pasta_gpt.mkdir(exist_ok=True)
        (pasta_gpt / "instrucoes.md").write_text(gpt, encoding="utf-8")
        salvar_json(pasta_gpt / f"{aid}.json", {"parametros": expandir(aid), "regras": regras(), "formato_saida": ler_json(PARAMS / "saida.schema.json")})
        if len(gpt) > 8000:
            print(f"  aviso: instruções do ChatGPT de {aid} com {len(gpt)} caracteres (limite 8000)")
    salvar_json(base / "chatgpt" / "_todos-os-parametros.json", {
        "como_usar": "Suba este arquivo num Projeto do ChatGPT e diga: 'aja como ultra-jobs e analise o mapa do scan que eu colei'. Cada agente tem parâmetros, regras e formato de saída aqui dentro.",
        "agentes": {aid: expandir(aid) for aid in agentes()}, "conselhos": conselhos(), "regras": regras(),
        "formato_saida": ler_json(PARAMS / "saida.schema.json")})
    (base / "claude" / "LEIA-ME.md").write_text(LEIA_CLAUDE, encoding="utf-8")
    (base / "codex" / "LEIA-ME.md").write_text(LEIA_CODEX, encoding="utf-8")
    (base / "chatgpt" / "LEIA-ME.md").write_text(LEIA_CHATGPT, encoding="utf-8")
    print(f"{len(agentes())} agentes -> {base}/claude (*.md), {base}/codex (*.toml), {base}/chatgpt/<agente>/")


LEIA_CLAUDE = """# Agentes Ultra no Claude Code

Arquivos gerados por `ultra.py build` a partir de `nucleo/params`. Não edite aqui: edite os JSON e rode o build.

Instalação: `python3 install.py` copia para `~/.claude/agents/` (todos os projetos).
Uso: peça "faz uma análise ultra do https://site.com" (a skill analise-ultra chama os agentes em paralelo),
ou chame um só: "use o agente ultra-kennedy para avaliar o preço desta página".
Os agentes precisam do motor em `~/.ultra-skills/ultra.py` (o instalador coloca lá).
"""

LEIA_CODEX = """# Agentes Ultra no Codex

Arquivos TOML (name, description, developer_instructions) gerados por `ultra.py build`.

Instalação: `python3 install.py --codex` copia para `~/.codex/agents/`.
O Codex não chama agentes sozinho: peça explicitamente, por exemplo
"rode a skill analise-ultra para https://site.com e use os agentes ultra-* em paralelo",
ou "spawn ultra-jobs, ultra-wozniak, ultra-huang e ultra-bezos em paralelo com as tarefas de `ultra.py proximo --json`".
Para mais agentes em paralelo, em ~/.codex/config.toml:  [agents]  max_threads = 8
"""

LEIA_CHATGPT = """# Agentes Ultra no ChatGPT

Duas formas:

1. Um GPT por agente (Explorar GPTs > Criar > Configurar):
   - Instruções: cole o conteúdo de `<agente>/instrucoes.md` (cabe no limite de 8.000 caracteres).
   - Conhecimento: anexe `<agente>/<agente>.json`.
2. Um Projeto com todos: crie um Projeto, suba `_todos-os-parametros.json` e diga
   "aja como ultra-hormozi" (ou outro agente). Cole o mapa do scan (.md) na conversa.

Sem terminal, o agente devolve o JSON na resposta; salve e rode `ultra.py validar` e `ultra.py consolidar` no computador.
"""


# ---------------------------------------------------------------- listar / params

def cmd_listar(a):
    for nome in conselhos()["pipeline"]:
        c = conselhos()["conselhos"][nome]
        print(f"\n{c['nome']}  [{c['pasta']}]")
        for m in c["membros"]:
            ag = expandir(m)
            print(f"  - {m:<26} {ag['nome']}: {ag['titulo']}  ({len(ag['criterios'])} critérios)")
    print(f"\n{len(agentes())} agentes · {sum(len(b['criterios']) for b in bibliotecas().values())} critérios em {len(bibliotecas())} bibliotecas: "
          + ", ".join(bibliotecas()))


def cmd_params(a):
    p = expandir(a.agente)
    print(json.dumps(p, ensure_ascii=False, separators=(",", ":")) if a.compacto else json.dumps(p, ensure_ascii=False, indent=1))


def main(argv=None):
    utf8()
    ap = argparse.ArgumentParser(description=f"Ultra {VERSAO}: motor de parâmetros dos agentes")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("listar").set_defaults(f=cmd_listar)
    s = sub.add_parser("params"); s.add_argument("agente"); s.add_argument("--compacto", action="store_true"); s.set_defaults(f=cmd_params)
    s = sub.add_parser("iniciar"); s.add_argument("url"); s.add_argument("--concorrentes", nargs="*", default=[]); s.add_argument("--pasta"); s.add_argument("--print", action="store_true"); s.set_defaults(f=cmd_iniciar)
    s = sub.add_parser("proximo"); s.add_argument("--pasta"); s.add_argument("--json", action="store_true"); s.set_defaults(f=cmd_proximo)
    s = sub.add_parser("status"); s.add_argument("--pasta"); s.set_defaults(f=cmd_status)
    s = sub.add_parser("validar"); s.add_argument("alvo"); s.set_defaults(f=cmd_validar)
    s = sub.add_parser("consolidar"); s.add_argument("pasta"); s.add_argument("--rodada", type=int); s.set_defaults(f=cmd_consolidar)
    s = sub.add_parser("duelo"); s.add_argument("pasta"); s.set_defaults(f=cmd_duelo)
    s = sub.add_parser("logo-teste"); s.add_argument("imagem"); s.add_argument("--saida"); s.add_argument("--fundo", default="#111111"); s.set_defaults(f=cmd_logo)
    s = sub.add_parser("plano"); s.add_argument("pasta"); s.add_argument("--pdf", action="store_true"); s.add_argument("--max", type=int, default=25); s.set_defaults(f=cmd_plano)
    s = sub.add_parser("build"); s.add_argument("--saida"); s.set_defaults(f=cmd_build)
    a = ap.parse_args(argv)
    return a.f(a) or 0


if __name__ == "__main__":
    sys.exit(main())
