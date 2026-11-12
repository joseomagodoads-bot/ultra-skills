# Agentes Ultra no Codex

Arquivos TOML (name, description, developer_instructions) gerados por `ultra.py build`.

Instalação: `python3 install.py --codex` copia para `~/.codex/agents/`.
O Codex não chama agentes sozinho: peça explicitamente, por exemplo
"rode a skill analise-ultra para https://site.com e use os agentes ultra-* em paralelo",
ou "spawn ultra-jobs, ultra-wozniak, ultra-huang e ultra-bezos em paralelo com as tarefas de `ultra.py proximo --json`".
Para mais agentes em paralelo, em ~/.codex/config.toml:  [agents]  max_threads = 8
