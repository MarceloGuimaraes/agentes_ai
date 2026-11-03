# Agente 1

Chat no terminal com a API da OpenAI usando **HTTP puro** (`urllib` da stdlib):
sem SDK, sem tools/function calling, sem dependências.

## Como rodar

```bash
cp .env.example .env   # preencha OPENAI_API_KEY
uv run main.py
```

Variáveis (no `.env` ou no ambiente):

| Variável          | Padrão                      |
|-------------------|-----------------------------|
| `OPENAI_API_KEY`  | obrigatória                 |
| `OPENAI_MODEL`    | `gpt-4o-mini`               |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` |

Comandos no chat: `/limpar` apaga o histórico, `/sair` (ou Ctrl+D) encerra.

## Como funciona

1. O histórico (`messages`) começa com o system prompt.
2. Cada mensagem do usuário entra no histórico e o histórico inteiro vai para
   `POST /chat/completions` com `"stream": true`.
3. A resposta chega como Server-Sent Events (`data: {...}` até `data: [DONE]`);
   cada `delta.content` é impresso na hora.
4. A resposta completa volta para o histórico como `assistant`, dando memória à conversa.
