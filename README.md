# Ultra Skills

**Pare de receber análise genérica de IA.** Seis skills gratuitas que fazem a IA ler um site em segundos, provar cada crítica, debater com a cabeça de fundadores e mestres de marketing e entregar **um plano de ação em PDF pronto para aplicar**.

Funcionam no **Claude Code** e no **Codex**. O texto das skills também pode ser colado em qualquer outra IA.

```
scan-ultra → pare-de-pensar-como-ia → teu-saas-e-uma-merda → tu-e-doido-isso-que-e-marketing → mega-plano
   (lê)          (5 pessoas)             (4 fundadores)            (10 mestres)                    (PDF)
```

| Skill | O que faz |
|---|---|
| **scan-ultra** | Lê o site e os concorrentes em segundos, com Python. Passa por firewall, abre sites feitos em JavaScript usando o Chrome/Edge do próprio computador, lê sozinho as páginas de termos, preços e contato, e entrega um **Raio-X de venda** (promessa, oferta, prova, confiança, CTA, atrito, medição, SEO) conferido contra o HTML. |
| **pare-de-pensar-como-ia** | Começa por "isso vende?". Depois vêm 5 pessoas (vendas; artista sem dinheiro; crescimento; técnico; crítico), cada uma com uma mente montada a partir dos melhores da área: escola, perguntas, roteiro, testes e números com fonte. Um mapa diz o que cada uma roda em site, anúncio, oferta, copy, funil, produto, estratégia e perfil, com régua para Brasil e para fora. No fim, um confronto entre o que a IA pensou e o que elas viram. |
| **teu-saas-e-uma-merda** | Jobs, Wozniak, Huang e Bezos, a partir de mapas mentais tirados de livros e cartas, atacam o produto em 5 rodadas. Toda acusação precisa de prova. |
| **tu-e-doido-isso-que-e-marketing** | 10 mestres (Ogilvy, Schwartz, Hopkins, Hormozi, Brunson, Sean Ellis, Ries e Trout, Byron Sharp, Gary Vee, Aaron Ross) montam o plano: concorrentes, aquisição, copy, paleta provada por código, Instagram, oferta, 3 ofertas, 90 dias e conteúdo com sinal real. |
| **mega-plano** | Reclassifica tudo por prioridade (ICE) e gera o **plano de ação em PDF**, o **arquivo para colar em qualquer IA** e o **checklist** para Trello, Notion ou Sheets. |
| **analise-ultra** | O orquestrador: roda as cinco em ordem e guarda cada etapa em arquivo. |

## Instalar

```bash
git clone https://github.com/joseomagodoads-bot/ultra-skills.git
cd ultra-skills
python3 install.py            # Claude Code + Codex   (Windows: py install.py)
python3 install.py --claude   # só Claude Code  (~/.claude/skills)
python3 install.py --codex    # só Codex        (~/.codex/skills)
python3 install.py --projeto  # só no projeto atual
```

Sem git: em **Code → Download ZIP**, descompacte e rode `python3 install.py` (Windows: `py install.py`) dentro da pasta. No Linux e no macOS, `bash install.sh` também funciona.

**Requisitos:**
- **Obrigatório:** Python 3.8+.
- **Para sites em JavaScript e prints:** basta ter Chrome, Edge, Brave ou Chromium instalado. O Playwright é opcional (`pip install playwright && playwright install chromium`).
- **Para o PDF:** `pip install reportlab`. Sem ele, o mega-plano gera HTML para imprimir em PDF.
- **No macOS, se der erro de certificado:** `pip install certifi`.

**Codex:** as versões recentes leem skills em `~/.codex/skills`. Se a sua não ler, aponte o `AGENTS.md` do projeto para `skills/analise-ultra/SKILL.md`.

**Outras IAs:** cole o `SKILL.md` nas instruções. Sem terminal, a IA monta o mapa com as ferramentas dela e avisa que não houve conferência automática.

## Usar

Basta pedir à IA:

> Faz uma análise ultra do https://meusite.com contra https://concorrente1.com e https://concorrente2.com

Ou rode os motores direto:

```bash
# scan (várias URLs em paralelo + comparativo; no Windows use "py")
python3 skills/scan-ultra/scripts/scan.py https://meusite.com https://concorrente.com --links --print

# pipeline inteiro (o scan é automático; as etapas 2 a 5 a IA faz e grava em arquivo)
python3 skills/analise-ultra/scripts/pipeline.py iniciar https://meusite.com --concorrentes https://c1.com https://c2.com
python3 skills/analise-ultra/scripts/pipeline.py proximo

# provar que uma paleta não é genérica
python3 skills/tu-e-doido-isso-que-e-marketing/scripts/paleta.py --cores "#1f2a2e,#e8a33d,#f6f0e4" --comparativo ultra-run-meusite.com/01-scan/comparativo.json

# gerar o plano de ação em PDF (veja o formato em skills/mega-plano/exemplo/plano.json)
python3 skills/mega-plano/scripts/gerar.py skills/mega-plano/exemplo/plano.json --saida meu-plano
```

## O que o plano em PDF traz

- Capa com veredito e estratégia única.
- Como usar o plano (com IA, com checklist).
- **Matriz de prioridade:** FAÇA AGORA, PROJETO, RÁPIDO e REPENSAR. A nota é ICE = impacto × confiança × facilidade, e a confiança vem da prova (testado 9, evidência 7, hipótese 4).
- Roteiro semana a semana.
- Cada ação com passos marcáveis, **entregável pronto** (copy, e-mail, script) e métrica.
- Ofertas, ativos para copiar, paleta com amostras de cor, ideias de conteúdo com sinal real, métricas, suposições a validar, checklist e fontes.

O `plano-para-ia.md` leva o mesmo plano com instruções. Cole em qualquer IA e diga **"aplique A01"** ou **"corrija o plano: [dado novo]"**.

## Quando o scan não lê

| Mensagem | Solução |
|---|---|
| `python3` não é reconhecido | Windows: use `py` ou `python` |
| `CERTIFICATE_VERIFY_FAILED` | `pip install certifi`; no macOS, rode também "Install Certificates.command" |
| "conteúdo montado por JavaScript" + "nenhum Chrome/Edge encontrado" | Instale o Chrome, ou `pip install playwright && playwright install chromium`, ou aponte o navegador em `SCAN_ULTRA_CHROME` |
| "travou ao abrir a página" | Servidor ou contêiner: use o Playwright |
| `Tunnel connection failed` | A rede onde a IA roda bloqueia sites: rode no seu computador |

## Estrutura

```
ultra-skills/
├── install.py          (Windows, macOS, Linux)
├── install.sh          (macOS, Linux)
├── LICENSE
└── skills/
    ├── analise-ultra/                    SKILL.md + scripts/pipeline.py
    ├── scan-ultra/                       SKILL.md + scripts/scan.py
    ├── pare-de-pensar-como-ia/           SKILL.md
    ├── teu-saas-e-uma-merda/             SKILL.md
    ├── tu-e-doido-isso-que-e-marketing/  SKILL.md + scripts/paleta.py
    └── mega-plano/                       SKILL.md + scripts/gerar.py + exemplo/plano.json
```

## Limites honestos

- O scan lê o HTML. Rastreadores via GTM e conteúdo montado por JavaScript só aparecem com `--render`.
- Clique, checkout e área logada não são testados automaticamente.
- Fundadores e mestres são lentes construídas a partir de livros e cartas públicas. As skills proíbem inventar citações deles.
- Números de plano (CPA, conversão) que não vierem de teste são marcados como hipótese.

## Contribuir

Pull requests são bem-vindos: novos rastreadores no scan, novas lentes, traduções e melhorias no PDF. Abra uma issue antes de mudanças grandes.

## Licença

MIT: use, copie, modifique e distribua, inclusive para fins comerciais, mantendo o aviso de licença.
