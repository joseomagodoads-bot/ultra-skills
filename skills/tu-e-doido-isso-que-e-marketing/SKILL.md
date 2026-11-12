---
name: tu-e-doido-isso-que-e-marketing
description: Use para montar o plano estratégico de marketing e vendas de um produto com 10 mestres de todos os tempos: aquisição, copy do site, identidade visual, Instagram, oferta, 3 ofertas por público, aplicação e conteúdo.
---

# Tu é doido? Isso que é marketing

## Para que serve

Pegar tudo que as análises anteriores provaram (`scan-ultra`, `pare-de-pensar-como-ia`, `teu-saas-e-uma-merda`) e colocar 10 dos maiores nomes de marketing, vendas e crescimento para construir o plano. O plano é por etapas, cada etapa com entrega escrita e pronta para usar, nunca com conselho genérico.

## Regras

1. **Nada genérico.** Valem todas as regras da `pare-de-pensar-como-ia`. Se a copy, a cor ou a ideia de conteúdo serviria para o concorrente, ela está errada.
2. **Tudo vem de 10 concorrentes reais.** A estratégia nasce de onde eles estão iguais e de onde ninguém está.
3. **Cada canal é um funil com um objetivo.** O site tem o funil de conversão dele e o Instagram tem o funil de conteúdo dele. Diga o objetivo de cada um antes de escrever qualquer coisa.
4. **Entrega pronta.** Copy escrita, cores em hex, bio escrita, destaques nomeados, ofertas com preço, roteiro de conteúdo com gancho. Nada de "crie uma headline forte".
5. **Conteúdo vem do que gente de verdade fala.** Toda ideia de conteúdo aponta o sinal real que a originou: comentário, busca, reclamação, pergunta em grupo, avaliação de concorrente, dado. Sem sinal, a ideia não entra.
6. **Mestres falam pela lógica deles, sem citação inventada.**

## Os 10 mestres (a régua)

| # | Mestre | Área | O que ele cobra | Teste que aplica |
|---|---|---|---|---|
| 1 | **David Ogilvy** | Copy e marca | A promessa concreta vende, não a criatividade. A headline faz 80% do trabalho. Pesquisa antes de escrever. | A headline sozinha, sem o resto, faz alguém querer ler? Tem benefício e especificidade? |
| 2 | **Eugene Schwartz** | Copy e consciência | Não se cria desejo, se canaliza um desejo que já existe. A mensagem muda conforme o nível de consciência do público (inconsciente, consciente do problema, da solução, do produto, mais consciente) e conforme a sofisticação do mercado. | Em que nível está esse público? A copy começa nesse nível? O mercado já ouviu essa promessa mil vezes? |
| 3 | **Claude Hopkins** | Performance e teste | Propaganda é venda e se mede. Testar pequeno antes de escalar. Especificidade convence mais que superlativo. | Como isso vai ser medido? Qual é o teste barato antes de gastar? |
| 4 | **Alex Hormozi** | Oferta | Oferta tão boa que a pessoa se sente burra dizendo não. Valor = (resultado dos sonhos × probabilidade percebida) ÷ (tempo × esforço). Bônus, garantia, escassez e urgência reais. | Nota de 1 a 10 em cada parte da equação. O que aumenta a probabilidade e reduz tempo e esforço? |
| 5 | **Russell Brunson** | Funil | Cada etapa do funil tem um único objetivo. Isca, ponte, oferta, upsell. Escada de valor. A história do fundador vende. | Qual é a única ação desta página? Qual é o próximo degrau depois da compra? |
| 6 | **Sean Ellis** | Growth | Primeiro achar o encaixe produto-mercado (o teste dos 40%: quantos ficariam "muito desapontados" sem o produto). Depois, uma métrica norte e ciclos rápidos de experimento. | Qual é a métrica norte? Quais 3 experimentos rodam esta semana? |
| 7 | **Al Ries e Jack Trout** | Posicionamento | É melhor ser o primeiro numa categoria do que melhor numa categoria que já tem dono. Ocupar uma palavra na cabeça do cliente. | Que palavra essa marca ocupa? A categoria já tem dono? Dá para criar uma categoria nova? |
| 8 | **Byron Sharp** | Crescimento de marca | Marcas crescem com mais compradores, inclusive os leves, não só com fidelização. Disponibilidade mental e física. Ativos distintivos (cor, forma, personagem) usados sempre do mesmo jeito. | A marca é lembrada no momento da compra? Quais ativos distintivos ela tem e repete? |
| 9 | **Gary Vaynerchuk** | Conteúdo orgânico | Atenção está onde está subestimada. Volume e contexto nativo de cada plataforma. Dar valor muitas vezes antes de pedir a venda. Documentar em vez de criar. | O conteúdo é nativo da plataforma? Dá valor sem pedir nada? Dá para produzir isso todo dia? |
| 10 | **Aaron Ross** | Vendas (máquina de receita) | Separar prospecção, fechamento e sucesso do cliente. Receita previsível vem de processo, não de herói. Nichar antes de escalar. | Quem prospecta, quem fecha, quem retém? Qual é o funil de vendas em números (leads, reuniões, fechamentos)? |

**Convidados de design** para a identidade visual:
- **Paul Rand:** a marca tem que ser simples o bastante para ser lembrada e reproduzida em qualquer tamanho.
- **Massimo Vignelli:** disciplina e poucas escolhas, poucas fontes e poucas cores, usadas com rigor.

## O processo

No Windows, troque `python3` por `py` nos comandos.

### Etapa 0: perguntas antes de começar
Pergunte ao usuário, ou tire do material das skills anteriores. O que faltar, assuma e marque como suposição:
- Tem site? Qual URL? Tem Instagram? Qual @? Tem outros canais (WhatsApp, Google, marketplace, YouTube, TikTok)?
- O que é o produto, quanto custa e como se compra?
- Quem compra hoje (público primário)? Quem poderia comprar (secundário e terciário)?
- Qual é o objetivo dos próximos 90 dias, em número (vendas, leads, MRR)?
- Quanto há de verba e de tempo por semana?

### Etapa 1: os 10 concorrentes
1. Ache 10 concorrentes reais: diretos, indiretos e o "jeito antigo" que o cliente usa hoje (planilha, caderno, não fazer nada).
2. Rode o `scan-ultra` em todos de uma vez:
   ```bash
   python3 <pasta-do-scan-ultra>/scripts/scan.py URL1 URL2 ... URL10 --saida concorrentes
   ```
3. Leia o `comparativo.md` e monte o **mapa do igual**: promessa (H1), preço, oferta (teste grátis, garantia), prova, canal, cores, tom. Onde os 10 estão iguais, entrar igual é invisível.
4. **Estratégia única**, em 5 linhas: a palavra que a marca vai ocupar (Ries e Trout), o nível de consciência em que vai falar (Schwartz), o inimigo comum, a categoria e por que ninguém ocupa esse lugar ainda.

### Etapa 2: aquisição (canais)
Liste cada canal de entrada com:
- objetivo;
- etapa do funil que atende;
- estado atual (do scan ou do usuário);
- o que otimizar, com a mudança escrita;
- métrica.

Canais a considerar: site, Google orgânico, Google Ads, Meta Ads, Instagram orgânico, WhatsApp, indicação, parcerias, marketplaces e prospecção ativa (Aaron Ross). Corte os que não fazem sentido para o ticket e diga por quê.

### Etapa 3: site (copy)
1. Defina o **funil do site** e o **objetivo único** (ex.: iniciar teste, chamar no WhatsApp, agendar demo).
2. Escreva a copy completa por seção, na ordem da página: headline, subheadline, CTA, prova, problema, mecanismo, como funciona, oferta, garantia, objeções (FAQ), CTA final.
3. Cada seção tem uma linha de "por quê", com o mestre e o dado do mapa do igual.
4. Ogilvy revisa as headlines: escreva 5 opções e escolha 1 com justificativa.

### Etapa 4: identidade visual
1. Paleta de **2 ou 3 cores**, com hex e papel de cada uma (fundo, texto, ação). Justifique contra o mapa do igual.
2. Prove que não é genérica e que dá para ler:
   ```bash
   python3 <pasta-desta-skill>/scripts/paleta.py --cores "#hex1,#hex2,#hex3" --comparativo concorrentes/comparativo.json
   ```
   Se alguma cor sair "PARECE IGUAL" a um concorrente, troque. Se o contraste não passar para o uso que você deu, troque.
3. Tipografia: 1 ou 2 fontes, com o motivo.
4. Ativos distintivos (Sharp): o que se repete sempre (cor, forma, personagem, frase) e onde aparece.
5. Logo e foto de perfil: o que deve ser e o que não pode ser (Rand: precisa ser legível em 110 px).

### Etapa 5: Instagram (funil de conteúdo)
1. **Objetivo do perfil** e para onde ele leva (link, WhatsApp, site).
2. **Foto de perfil:** logo ou rosto, e por quê.
3. **Nome e bio**, escritos: quem é, para quem, prova, CTA.
4. **Destaques**, na ordem do funil, com nome curto e o que entra em cada um. Exemplo de lógica: comece aqui → resultados → como funciona → planos → dúvidas → bastidores.
5. **Funil de conteúdo:**
   - topo (alcance), meio (confiança) e fundo (venda), com a proporção de cada um;
   - formatos (reels, carrossel, stories, lives) e frequência possível com o tempo que o usuário tem.
6. Os 9 primeiros posts da grade, nomeados.

### Etapa 6: produto e oferta
1. **Analisador de oferta (Hormozi).** Dê nota de 1 a 10 para:
   - resultado dos sonhos;
   - probabilidade percebida;
   - tempo até o resultado;
   - esforço.

   Revise também: preço e âncora, bônus, garantia, escassez e urgência (só se forem reais), prova e CTA. Veredito: a oferta é boa ou não, e por quê, com base no produto.
2. **3 ofertas diferentes**, uma para cada público:
   - **Primário:** quem mais compra hoje.
   - **Secundário:** quem compraria com outro ângulo.
   - **Terciário:** um público novo, ou o "jeito antigo".

   Cada oferta tem: público, dor principal, nível de consciência, promessa, o que entra, preço, bônus, garantia, urgência real, canal principal e headline escrita.

### Etapa 7: aplicação
Plano de 30, 60 e 90 dias, semana a semana nas 4 primeiras. Para cada ação:
- canal e oferta usada;
- quem faz;
- quanto custa;
- métrica e meta;
- o teste (Hopkins): o que se compara e quando decidir.

Inclua a máquina de vendas (Ross): números do funil necessários para bater a meta, de trás para frente.

### Etapa 8: conteúdo
Entre 15 e 30 ideias, cada uma com:
- **Sinal real:** onde a dor ou a pergunta apareceu (link ou descrição da fonte).
- **Gancho**, escrito como vai ao ar (primeira frase ou primeiro segundo).
- **Formato** e roteiro curto (3 a 6 batidas).
- **Etapa do funil** e CTA.
- Por que um ser humano pararia o scroll.

Ideias proibidas, salvo se o sinal real pedir: "5 dicas para…", "você sabia que…", "o erro que todo mundo comete", frase motivacional, conteúdo que serviria para qualquer marca do nicho. Busque o disruptivo: mostrar o número que ninguém mostra, a conta ao vivo, o bastidor feio, a briga com o "jeito antigo", o cliente real.

### Etapa 9: revisão dos mestres
Cada mestre lê o plano e aponta, em 1 ou 2 linhas, o maior erro que vê na sua área. Corrija antes de entregar. André, o crítico da `pare-de-pensar-como-ia`, dá a palavra final sobre o que é prova e o que é suposição.

## Formato da entrega

Um documento `plano-estrategico.md` (ou o formato de documento disponível) com:
1. Resumo de uma página: estratégia única, as 3 ofertas, metas de 90 dias.
2. Etapas 1 a 8, cada uma com a entrega pronta.
3. Suposições feitas e o que precisa ser validado.
4. Fontes: concorrentes escaneados e sinais reais usados.

## Fontes dos mestres

- **Ogilvy:** *Confessions of an Advertising Man* (1963) e *Ogilvy on Advertising* (1983).
- **Schwartz:** *Breakthrough Advertising* (1966).
- **Hopkins:** *Scientific Advertising* (1923).
- **Hormozi:** *$100M Offers* (2021) e *$100M Leads* (2023).
- **Brunson:** *DotCom Secrets* (2015), *Expert Secrets* (2017) e *Traffic Secrets* (2020).
- **Ellis:** *Hacking Growth*, com Morgan Brown (2017).
- **Ries e Trout:** *Positioning* (1981).
- **Sharp:** *How Brands Grow* (2010).
- **Vaynerchuk:** *Jab, Jab, Jab, Right Hook* (2013).
- **Ross:** *Predictable Revenue*, com Marylou Tyler (2011).
- **Design:** Paul Rand, *Design, Form, and Chaos* (1993); Massimo Vignelli, *The Vignelli Canon* (2010).

## Modo agentes

Os mestres são agentes, e cada um é dono de uma etapa do plano:

| Etapa | Dono |
|---|---|
| posicionamento | `ultra-ries-trout` |
| nível de consciência e mensagem | `ultra-schwartz` |
| copy do site | `ultra-ogilvy` |
| testes e números | `ultra-hopkins` |
| aquisição e funil | `ultra-ellis`, `ultra-ross` |
| marca e disponibilidade | `ultra-sharp` |
| conteúdo e Instagram | `ultra-vaynerchuk` |
| cores, logo, perfil e destaques | `ultra-design` |

**A oferta vem do conselho de vendas.** Brunson, Hormozi e Kennedy propõem, votam uns nas dos outros e o motor elege a campeã em `04-vendas/r3/oferta-campea.json`. A etapa de oferta deste plano usa essa campeã e não inventa outra.

Cada dono entrega o material pronto no campo `entregas` (textos, paleta com hex, itens dos destaques, roteiros). O `ultra.py plano` junta tudo no PDF.
