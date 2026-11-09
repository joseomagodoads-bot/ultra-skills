---
name: scan-ultra
description: Use antes de analisar qualquer site, landing page ou concorrente. Lê a página inteira em segundos com código, gera um mapa estruturado, confere o mapa e entrega para a análise.
---

# Scan Ultra

## Para que serve

Ler uma página aos pedaços (buscar, abrir, resumir, abrir de novo) é lento e deixa buracos. O Scan Ultra baixa tudo de uma vez, em paralelo, e transforma a página em um mapa: títulos, textos por seção, CTAs e para onde levam, preços, percentuais, prova social, garantia, teste grátis, urgência, formulários, WhatsApp, CNPJ, redes, pixel, GA, GTM, stack, SEO, cores e fontes do CSS, robots.txt, sitemap e llms.txt. Depois confere se o mapa bate com o HTML. Só então a análise começa.

## Passo 1: rodar o scan

O script fica em `scripts/scan.py`, dentro da pasta desta skill. Só usa Python 3 padrão.

```bash
# uma página
python3 <pasta-da-skill>/scripts/scan.py https://site.com --links

# o site e os concorrentes de uma vez (rodam em paralelo e geram comparativo.md)
python3 <pasta-da-skill>/scripts/scan.py https://site.com https://concorrente1.com https://concorrente2.com

# site feito em JavaScript (React, Next, Lovable, Vite...) ou quando precisar ver o visual
python3 <pasta-da-skill>/scripts/scan.py https://site.com --print
```

Opções úteis:
- `--saida PASTA` para escolher onde salvar (padrão `./scan-ultra-saida`).
- `--arquivo urls.txt` para passar uma lista, uma URL por linha.
- `--links` testa até 40 links internos e acusa os quebrados.
- `--render` usa navegador (Playwright). `--print` também salva prints desktop e mobile.
- `--css 0` pula o download de CSS, se a pressa for extrema.

Para cada URL saem `<site>.json` (mapa completo) e `<site>.md` (resumo para leitura rápida). Com mais de uma URL, sai também `comparativo.md`.

Leia o `.md` primeiro. Vá ao `.json` só quando precisar de algo que o `.md` cortou (texto longo de seção, lista completa de links).

## Passo 2: conferir o mapeamento

Todo `.md` começa com **"Conferência do mapeamento"**. O script compara o próprio mapa com o HTML bruto: links, títulos, formulários, imagens e preços. Também avisa se a página depende de JavaScript.

- **Confiança alta:** siga para a análise.
- **Confiança média:** leia os itens com ✖ e diga na análise o que pode estar incompleto.
- **Confiança baixa:** não analise ainda. O motivo mais comum é página montada em JavaScript. Rode de novo com `--render`. Se não houver Playwright, instale (`pip install playwright && playwright install chromium`). Se a instalação não for possível, use a ferramenta de navegador ou de busca disponível e marque a análise inteira como incompleta.

Depois, faça a sua própria conferência rápida, porque o script não entende contexto:
1. O H1 do mapa é mesmo a promessa principal da página?
2. Os preços encontrados são da oferta, ou de exemplos e simulações? Separe os dois.
3. Algum CTA aparece com "(botão, ação via JavaScript)"? Ele pode não levar a lugar nenhum. Anote como item para testar.
4. Os "Sinais objetivos" fazem sentido? Ausência de pixel no HTML não prova ausência de pixel (ele pode carregar via GTM). Diga "não encontrado no HTML", nunca "não tem".
5. Se rodou com `--print`, abra os prints. É a única forma de julgar o visual.

Escreva o resultado em 3 a 6 linhas: o que o mapa cobre, o que ficou de fora e a confiança final.

## Passo 3: entregar para a análise

O mapa é a matéria-prima. Ele não é a análise. Passe para a próxima skill (`pare-de-pensar-como-ia`, ou a sequência inteira em `analise-ultra`) com:
- o caminho do `.md` de cada página;
- a conferência do Passo 2;
- os "Sinais objetivos", que viram evidência `[TESTADO]` na análise.

Tudo que veio do scan conta como `[TESTADO]`. Tudo que o scan não cobre (visual sem print, clique, checkout, área logada) continua `[HIPÓTESE]` até alguém testar.

## Quando o script não pode rodar

Se não houver terminal, ou se a rede do terminal estiver bloqueada (erro de proxy, 403 no túnel), use a ferramenta de leitura de páginas disponível e peça a mesma estrutura do mapa: títulos, texto por seção, CTAs com destino, preços, sinais de oferta, contato, rastreadores, SEO. Avise que o mapa foi montado sem conferência automática.
