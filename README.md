# Ultra Skills

**Pare de receber análise genérica de IA.** São 24 agentes que trabalham em conjunto, cada um com **parâmetros** próprios: critérios com peso, régua de 0 a 10, testes, alertas e números com fonte. Eles leem o site em segundos, provam cada crítica, discutem entre si, montam e disputam ofertas e entregam **um plano de ação em PDF pronto para aplicar**.

Funciona no **Claude Code** e no **Codex**, com agentes de verdade rodando em paralelo, e também no **ChatGPT**, como GPTs separados ou um Projeto. É gratuito e de código aberto (MIT).

```
 Leitura ─► 5 pessoas ─► 4 fundadores ─► conselho de vendas ─► 10 de marketing ─► Plano (PDF)
 (scan)     (isso vende?)  (Apple, Nvidia,   (Brunson, Hormozi,    (posicionamento,     (ICE, roteiro,
                            Amazon)           Kennedy: duelo)       copy, Instagram…)    entregáveis)
```

## Os conselhos

| Conselho | Agentes | Como trabalham |
|---|---|---|
| **Leitura** | `ultra-scan` | Script Python: lê o site e os concorrentes, passa por firewall, abre JavaScript com o Chrome/Edge do computador, lê as páginas de preço, termos e contato, baixa os logos e gera a folha de teste do logo. |
| **Cinco pessoas** | João (vendas), Fernando (artista de 69 anos, sem dinheiro), Ana (crescimento), Robson (técnico) e André (crítico) | Os quatro primeiros em paralelo; o André depois, corta o que é achismo. |
| **Fundadores** | Jobs, Wozniak, Huang e Bezos | Acusam com prova. Se discordarem 4 pontos ou mais no mesmo critério, abre uma rodada de debate só entre eles. |
| **Conselho de vendas** | Brunson (arquitetura e escada), Hormozi (valor e garantia), Kennedy (preço e posicionamento) | Cada um propõe uma oferta e vota nas três por critério. O motor faz o duelo sem contar o autovoto, aponta o melhor componente de cada oferta e monta a **oferta campeã**. |
| **Marketing** | Ries e Trout, Schwartz, Ogilvy, Hopkins, Sean Ellis, Aaron Ross, Byron Sharp, Gary Vee e Design | Cada um é dono de uma etapa e entrega o material pronto: copy, paleta com hex, logo, perfil e destaques do Instagram, testes e conteúdo. |
| **Plano** | Moderador, André e Plano | Veredito, cortes finais e o PDF. |

### Parâmetros em vez de texto

Os agentes não leem páginas de prosa. Leem JSON em `nucleo/params/`:

- **11 bibliotecas, 96 critérios:** `logo` (régua do Apple HIG, Paul Rand e Vignelli: funciona em 16 px, em uma cor, invertido…), `identidade`, `oferta`, `preco`, `copy`, `landing`, `confianca`, `crescimento`, `tecnico`, `instagram` e `conteudo`.
- **Cada agente:** critérios próprios mais critérios das bibliotecas, com peso e régua de 0, 5 e 10, perguntas, testes, alertas e fontes.
- **Uma saída comum** (`saida.schema.json`): notas com evidência e marca (`TESTADO`, `EVIDÊNCIA`, `HIPÓTESE`), achados, ações com ICE, ofertas, votos e entregas.
- **12 regras para todos**, entre elas: nada de citação inventada, nota sem evidência vale como hipótese e escassez só se for real.

O motor `ultra.py` valida cada saída, consolida a rodada e faz o resto: matriz por dimensão, divergências, consensos, ações juntas sem repetir, placar de evidência, duelo de ofertas e plano.

## Instalar

```bash
git clone https://github.com/joseomagodoads-bot/ultra-skills.git
cd ultra-skills
python3 install.py            # Claude Code + Codex   (Windows: py install.py)
python3 install.py --claude   # só Claude Code
python3 install.py --codex    # só Codex
python3 install.py --projeto  # só no projeto atual
```

Sem git: em **Code → Download ZIP**, descompacte e rode o mesmo comando dentro da pasta.

| Onde vai | O quê |
|---|---|
| `~/.ultra-skills/` | o motor `ultra.py`, os parâmetros e os scripts |
| `~/.claude/skills/`, `~/.claude/agents/` | 7 skills e 24 agentes do Claude Code |
| `~/.codex/skills/`, `~/.agents/skills/`, `~/.codex/agents/` | as mesmas skills e os 24 agentes do Codex (TOML) |

Depois de instalar, reinicie o Claude Code ou o Codex.

**Requisitos:**
- Obrigatório: Python 3.8 ou mais novo.
- Opcionais: `pip install reportlab pillow` (PDF e folha de teste do logo) e, para sites em JavaScript, Chrome, Edge, Brave ou Chromium instalado, ou `pip install playwright && playwright install chromium`. No macOS, se der erro de certificado: `pip install certifi`.

### ChatGPT

Na pasta `agents/chatgpt/`:

- **Um GPT por agente:** em *Explorar GPTs → Criar → Configurar*, cole `instrucoes.md` (cabe no limite de 8.000 caracteres) e envie o `.json` do agente em *Conhecimento*.
- **Tudo num Projeto:** crie um Projeto, envie `_todos-os-parametros.json` e peça "aja como ultra-hormozi nesta oferta" (ou outro agente). Cole o mapa do scan (.md) na conversa.

O ChatGPT não roda o scan nem o motor. Os agentes avisam quando a leitura não foi conferida por script.

## Usar

Peça à IA:

> Faz uma análise ultra do https://meusite.com contra https://concorrente1.com e https://concorrente2.com

Também dá para pedir só uma parte, como "monta uma oferta e um preço para isso" (skill `conselho-de-vendas`) ou "só os fundadores".

### Pelo terminal (Windows: troque `python3` por `py`)

```bash
U=~/.ultra-skills/ultra.py
python3 $U listar                          # conselhos, agentes e critérios
python3 $U params ultra-kennedy            # parâmetros de um agente
python3 $U iniciar https://meusite.com --concorrentes https://c1.com https://c2.com --print
python3 $U proximo --json                  # tarefas da rodada (valida e consolida a anterior)
python3 $U status                          # o que já foi feito
python3 $U duelo PASTA/04-vendas           # duelo de ofertas
python3 $U logo-teste logo.png             # logo em 16/32/64 px, uma cor e invertido
python3 $U plano PASTA --pdf               # plano.json + PDF
python3 $U validar saida.json              # confere uma saída contra o formato
python3 nucleo/ultra.py build              # regenera os agentes depois de mexer nos parâmetros
```

### Teste do motor

```bash
python3 ~/.ultra-skills/ultra.py iniciar http://seu-site --pasta /tmp/teste
python3 testes/simular_agentes.py /tmp/teste
```

O teste simula todos os agentes com respostas válidas e roda o fluxo até o PDF. Ele confere o motor, não a qualidade da análise.

## O que o plano em PDF traz

- Capa com o veredito e a estratégia.
- **Matriz de prioridade:** faça agora, projeto, rápido e repensar. A nota é ICE = impacto × confiança × facilidade ÷ 10, e a confiança vem da prova (testado 9, evidência 7, hipótese 4).
- Roteiro semana a semana. Cada ação com passos, **entregável pronto** e métrica.
- A oferta campeã e as 3 ofertas por público, ativos para copiar, paleta, conteúdo, suposições a validar e fontes.

O `plano-para-ia.md` leva o mesmo plano para colar em qualquer IA e pedir "aplique A01". O `checklist.csv` vai para Trello, Notion ou Sheets.

## Estrutura

```
ultra-skills/
├── install.py / install.sh
├── nucleo/
│   ├── ultra.py                  o motor
│   └── params/                   regras, conselhos, saída, criterios/*.json, agentes/*.json
├── agents/                       gerado por "ultra.py build"
│   ├── claude/*.md   codex/*.toml   chatgpt/<agente>/
├── skills/
│   ├── analise-ultra/            orquestrador
│   ├── scan-ultra/               scripts/scan.py
│   ├── pare-de-pensar-como-ia/
│   ├── teu-saas-e-uma-merda/
│   ├── conselho-de-vendas/
│   ├── tu-e-doido-isso-que-e-marketing/   scripts/paleta.py
│   └── mega-plano/               scripts/gerar.py
└── testes/simular_agentes.py
```

## Limites honestos

- O scan lê HTML e, quando precisa, o navegador. Clique, checkout e área logada não são testados.
- Fundadores, mestres e o conselho de vendas são lentes construídas a partir de livros, cartas e aulas públicas, com as fontes nos parâmetros. As regras proíbem inventar frases deles.
- Número que não vem de teste (CPA, conversão) entra como hipótese.

## Contribuir

Pull requests são bem-vindos: critérios novos (edite o JSON e rode `ultra.py build`), novos agentes, traduções e melhorias no scan e no PDF. Abra uma issue antes de mudanças grandes.

## Licença

MIT: use, copie, modifique e distribua, inclusive para fins comerciais, mantendo o aviso de licença.
