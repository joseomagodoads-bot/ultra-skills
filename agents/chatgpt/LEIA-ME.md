# Agentes Ultra no ChatGPT

Duas formas:

1. Um GPT por agente (Explorar GPTs > Criar > Configurar):
   - Instruções: cole o conteúdo de `<agente>/instrucoes.md` (cabe no limite de 8.000 caracteres).
   - Conhecimento: anexe `<agente>/<agente>.json`.
2. Um Projeto com todos: crie um Projeto, suba `_todos-os-parametros.json` e diga
   "aja como ultra-hormozi" (ou outro agente). Cole o mapa do scan (.md) na conversa.

Sem terminal, o agente devolve o JSON na resposta; salve e rode `ultra.py validar` e `ultra.py consolidar` no computador.
