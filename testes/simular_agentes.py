#!/usr/bin/env python3
"""
Teste de fumaça do motor: simula os agentes respondendo cada rodada com JSON válido
(notas aleatórias, mas reprodutíveis) e roda o pipeline inteiro até o PDF.

Não testa a QUALIDADE da análise (isso é trabalho dos agentes de verdade); testa se o
motor valida, consolida, acha divergências, faz o duelo, monta o plano e gera o PDF.

  python3 testes/simular_agentes.py PASTA_ultra-run   (depois de 'ultra.py iniciar')
"""

import json
import random
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
ULTRA = RAIZ / "nucleo" / "ultra.py"
sys.path.insert(0, str(RAIZ / "nucleo"))
import ultra  # noqa: E402

random.seed(7)


def saida_falsa(agente: str, rodada: int, conselho: str, pasta: Path) -> dict:
    ag = ultra.expandir(agente)
    vies = {"ultra-jobs": -2, "ultra-wozniak": 1, "ultra-huang": -3, "ultra-bezos": 0}.get(agente, 0)
    notas = [{"criterio": c["id"], "nota": max(0, min(10, random.randint(3, 8) + vies)),
              "evidencia": f"simulado: trecho do mapa para {c['id']}", "marca": random.choice(["TESTADO", "EVIDENCIA", "HIPOTESE"])}
             for c in ag["criterios"]]
    d = {"agente": agente, "rodada": rodada, "alvo": "simulado",
         "veredito": {"vende": random.choice(["vende pouco", "nao vende", "vende pouco"]), "resumo": f"{ag['nome']}: resumo simulado",
                      "nota_geral": round(sum(n["nota"] for n in notas) / max(1, len(notas)), 1) if notas else None, "confianca": "media"},
         "notas": notas,
         "achados": [{"tipo": "acusacao", "texto": "Empresa não identificada no rodapé nem nos termos", "prova": "scan: CNPJ ausente", "marca": "TESTADO", "gravidade": "alta"},
                     {"tipo": "risco", "texto": f"Risco visto por {ag['nome']}", "prova": "simulado", "marca": "HIPOTESE"}],
         "acoes": [{"titulo": "Mostrar CNPJ e razão social no rodapé", "etapa": "tecnico", "semana": 1, "dono": "Dono", "impacto": 8, "facilidade": 9,
                    "evidencia": "TESTADO", "porque": "scan não achou CNPJ", "passos": ["Colar no rodapé"], "entregavel": "Empresa X Ltda · CNPJ 00.000.000/0001-00",
                    "metrica": "conversão do checkout", "meta": "+10%"},
                   {"titulo": f"Ação própria de {ag['nome']}", "etapa": random.choice(ultra.ETAPAS[:-1]), "semana": random.randint(1, 6), "dono": "Time",
                    "impacto": random.randint(4, 9), "facilidade": random.randint(3, 9), "evidencia": random.choice(["EVIDENCIA", "HIPOTESE"]),
                    "porque": "simulado", "passos": [], "entregavel": "texto pronto simulado", "metrica": "métrica simulada"}],
         "perguntas": [{"para": k, "pergunta": v} for k, v in list(ag.get("pergunta_para", {}).items())[:1]],
         "nao_testei": ["checkout real (simulação)"]}
    if conselho == "fundadores":
        d["temas"] = {t.split(":")[0]: "simulado" for t in ultra.conselhos()["conselhos"]["fundadores"]["temas"]}
    if conselho == "vendas" and rodada == 1:
        d["ofertas"] = [{"id": f"of-{ultra.curto(agente)}", "nome": f"Oferta {ag['nome']}", "publico": "dono pequeno", "promessa": "resultado em 7 dias",
                         "mecanismo": "simulado", "componentes": [{"item": "produto", "resolve": "dor", "valor_declarado": 500}],
                         "preco": {"principal": random.choice([79.9, 97, 149.9]), "moeda": "BRL", "ancora": "custo do problema", "parcelas": "12x"},
                         "niveis": [{"nome": "principal", "preco": 97, "o_que_muda": ""}], "garantia": {"tipo": "incondicional", "prazo_dias": 30, "como_pedir": "e-mail"},
                         "urgencia": {"tipo": "vagas", "motivo_real": "capacidade de implantação"}, "headline": f"Headline de {ag['nome']}", "por_que_vence": "simulado"}]
    if conselho == "vendas" and rodada == 2:
        ofs = [o["id"] for p in (pasta / "04-vendas" / "r1").glob("*.json") for o in json.loads(p.read_text(encoding="utf-8")).get("ofertas", [])]
        crit = [c for c in ultra.pesos() if c.startswith(("oferta.", "preco."))]
        d["votos"] = [{"oferta_id": o, "notas": {c: random.randint(3, 10) for c in crit}, "roubaria": "a garantia"} for o in ofs]
    if conselho == "marketing":
        d["entregas"] = [{"etapa": "site", "tipo": "copy", "titulo": "Hero", "texto": f"Copy simulada de {ag['nome']}"}]
        if agente == "ultra-design":
            d["entregas"].append({"etapa": "identidade", "tipo": "paleta", "titulo": "Paleta",
                                  "cores": [{"hex": "#0f3d2e", "nome": "Verde", "uso": "texto"}, {"hex": "#f2b705", "nome": "Amarelo", "uso": "ação", "destaque": True}]})
        if agente == "ultra-ries-trout":
            d["entregas"].append({"etapa": "estrategia", "tipo": "posicionamento", "titulo": "Posicionamento", "texto": "A palavra é 'sobra' (simulado)."})
        if agente == "ultra-vaynerchuk":
            d["entregas"].append({"etapa": "conteudo", "tipo": "ideias_conteudo", "titulo": "Ideias",
                                  "itens": [{"sinal": "comentário real (simulado)", "gancho": "Gancho simulado", "formato": "Reel", "funil": "Topo"}]})
    return d


def rodar(*args):
    r = subprocess.run([sys.executable, str(ULTRA), *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.stdout + r.stderr


def main():
    ultra.utf8()
    pasta = Path(sys.argv[1])
    for _ in range(30):
        info = json.loads(rodar("proximo", "--pasta", str(pasta), "--json"))
        if info.get("feito"):
            print("FIM:", info)
            break
        c, n = info["conselho"], info["rodada"]
        print(f"rodada: {c} r{n} -> {', '.join(t['agente'] for t in info['tarefas'])}")
        for t in info["tarefas"]:
            destino = Path(t["salvar_em"])
            destino.parent.mkdir(parents=True, exist_ok=True)
            ag = t["agente"]
            if ag == "ultra-scan":
                destino.write_text("# Conferência (simulada)\nConfiança alta.\n", encoding="utf-8")
            elif ag == "ultra-moderador" and c == "vendas":
                print("  " + rodar("duelo", str(pasta / "04-vendas")).strip().replace("\n", "\n  "))
                dd = json.loads((pasta / "04-vendas" / "duelo.json").read_text(encoding="utf-8"))
                campea = dict(dd["ofertas"][dd["vencedora"]["oferta_id"]], nome="Oferta campeã (híbrida)")
                (pasta / "04-vendas" / "r3").mkdir(exist_ok=True)
                (pasta / "04-vendas" / "r3" / "oferta-campea.json").write_text(json.dumps({"ofertas": [campea]}, ensure_ascii=False), encoding="utf-8")
            elif ag == "ultra-moderador":
                destino.write_text("# Veredito\nVende pouco: confiança no pagamento é o gargalo (simulado).\n", encoding="utf-8")
            elif ag == "ultra-plano":
                print("  " + rodar("plano", str(pasta), "--pdf").strip().replace("\n", "\n  "))
            else:
                destino.write_text(json.dumps(saida_falsa(ag, n, c, pasta), ensure_ascii=False, indent=1), encoding="utf-8")
        if c != "leitura":
            print("  validar:", rodar("validar", str(Path(info["tarefas"][0]["salvar_em"]).parent)).count("✔"), "ok")
    print(rodar("status", "--pasta", str(pasta)))


if __name__ == "__main__":
    main()
