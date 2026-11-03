# Agente 1 — chat CLI com OpenAI via HTTP puro (sem tooling)

## Context
O projeto `agentes_ai/` está vazio (só existe `01_chat_terminal/`). O objetivo é um primeiro agente
mínimo em Python: um loop de conversa no terminal que fala com a OpenAI **sem SDK e sem
tools/function calling** — apenas `urllib` da stdlib chamando a API REST. O projeto é
gerenciado com **uv** (Python 3.14 disponível). Serve de base didática para agentes futuros.

## Estrutura (tudo em `01_chat_terminal/`)
```
01_chat_terminal/
├── pyproject.toml     # gerado por `uv init`, sem dependências
├── .python-version
├── .env.example       # OPENAI_API_KEY=, OPENAI_MODEL=
├── README.md          # como rodar
└── main.py            # o agente
```
Criação: `cd 01_chat_terminal && uv init --app --no-workspace --name 01-chat-terminal` (depois remover o
`hello.py`/`main.py` de exemplo e escrever o nosso). Nenhuma dependência externa.

## `main.py` — design
- **Config**: `OPENAI_API_KEY` (obrigatória; erro claro se faltar), `OPENAI_MODEL`
  (default `gpt-4o-mini`, sobrescrevível), `OPENAI_BASE_URL` (default
  `https://api.openai.com/v1`). Leitura simples de `.env` local (parser de ~10 linhas,
  sem python-dotenv) para não exigir `export`.
- **`chat_stream(messages) -> Iterator[str]`**: `POST {base}/chat/completions` com
  `{"model", "messages", "stream": true}` via `urllib.request`; lê a resposta linha a linha,
  processa SSE (`data: {...}`, para em `data: [DONE]`) e faz `yield` de
  `choices[0].delta.content`. Trata `HTTPError` exibindo o corpo do erro da API.
- **Loop principal**: `messages = [{"role": "system", "content": SYSTEM_PROMPT}]`;
  lê input do usuário, adiciona ao histórico, imprime tokens conforme chegam (`flush=True`),
  adiciona a resposta completa como `assistant`. Comandos: `/sair` (ou Ctrl+D/Ctrl+C) e
  `/limpar` (reseta o histórico para só o system prompt).
- Sem tools, sem function calling, sem frameworks — só stdlib (`json`, `os`, `urllib`).

## Verificação
1. `cd 01_chat_terminal && cp .env.example .env` e preencher a chave.
2. `uv run main.py` → conversar; checar streaming e que o modelo lembra de mensagens
   anteriores (ex.: "meu nome é X" → "qual meu nome?").
3. `/limpar` → modelo não lembra mais; `/sair` encerra.
4. Sem chave / chave inválida → mensagem de erro legível (corpo do erro 401 da API).
