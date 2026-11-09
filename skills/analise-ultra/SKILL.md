---
name: analise-ultra
description: Use quando pedirem análise completa de um site, SaaS ou produto com plano de marketing. Roda scan-ultra, pare-de-pensar-como-ia, teu-saas-e-uma-merda, tu-e-doido-isso-que-e-marketing e mega-plano (PDF).
---

# Análise Ultra (orquestrador)

## A sequência

| # | Skill | O que faz | Saída |
|---|---|---|---|
| 1 | `scan-ultra` | Lê o site e os concorrentes em segundos, com código, e confere o mapa | `01-scan/` |
| 2 | `pare-de-pensar-como-ia` | Isso vende? As 5 pessoas e o confronto entre IA e pessoas | `02-pessoas.md` |
| 3 | `teu-saas-e-uma-merda` | Jobs, Wozniak, Huang e Bezos atacam e provam | `03-fundadores.md` |
| 4 | `tu-e-doido-isso-que-e-marketing` | 10 mestres montam o plano estratégico | `04-plano-estrategico.md` |
| 5 | `mega-plano` | Reclassifica tudo por prioridade e gera o plano de ação em PDF, o arquivo para IA e o checklist | `05-plano/` |

Cada etapa usa as saídas das anteriores como prova. Não pule etapas. Se o usuário pedir só uma parte, rode até ela.

## Como rodar

1. **Antes de tudo**, pergunte (ou tire da conversa):
   - a URL do site;
   - de 3 a 10 concorrentes (se ele não souber, busque e proponha);
   - se tem Instagram e qual é o @;
   - qual é o objetivo.
2. **Inicie o pipeline.** O scan roda sozinho e já aponta a próxima etapa:
   ```bash
   python3 <pasta-desta-skill>/scripts/pipeline.py iniciar https://site.com --concorrentes https://c1.com https://c2.com --print
   ```
   Use `--print` quando houver navegador (Playwright), para ter os prints que as etapas 2 a 4 usam no visual.
3. **Para cada etapa:**
   - carregue o `SKILL.md` da skill indicada;
   - leia os arquivos que o pipeline listou;
   - faça a etapa;
   - grave a saída no arquivo indicado;
   - rode `pipeline.py proximo` para ver a seguinte.

   `pipeline.py status` mostra o que já foi feito.
4. **No fim**, entregue ao usuário:
   - o PDF do plano de ação (`05-plano/plano-de-acao.pdf`);
   - o `plano-para-ia.md`;
   - o `checklist.csv`;
   - em 3 linhas: o veredito, a primeira ação e por quê.

   Os arquivos ficam na pasta `ultra-run-<site>/`.

## Sem terminal

Se não houver como rodar Python, siga a mesma ordem usando as ferramentas disponíveis (leitura de páginas, busca). Monte o mapa à mão na estrutura do `scan-ultra` e avise que não houve conferência automática.

## Regras que valem em todas as etapas

- Nada genérico: se a frase serviria para outro site do nicho, corte.
- Marcação `[TESTADO]`, `[EVIDÊNCIA]` ou `[HIPÓTESE]` em toda afirmação.
- Correção sempre pronta: texto, preço, cor em hex, botão.
- Nenhuma citação inventada de pessoa real.
