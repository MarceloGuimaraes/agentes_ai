# Agente 2

API que responde perguntas em linguagem natural sobre uma **base SQLite local**, a partir do
[agente 1](../01_chat_terminal/README.md). A chamada à OpenAI continua em **HTTP puro** (`urllib`, sem
SDK); o que muda é que o modelo agora consulta os dados por **tools fixas** e o chat é servido
por uma API **FastAPI**.

## Como rodar

```bash
cp .env.example .env   # preencha OPENAI_API_KEY
uv run seed_db.py      # gera loja.db com dados fictícios
uv run main.py         # API em http://127.0.0.1:8000 (documentação em /docs)
```

Variáveis (no `.env` ou no ambiente):

| Variável          | Padrão                      |
|-------------------|-----------------------------|
| `OPENAI_API_KEY`  | obrigatória                 |
| `OPENAI_MODEL`    | `gpt-4o-mini`               |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` |
| `DATABASE_PATH`   | `loja.db`                   |
| `HOST`            | `127.0.0.1`                 |
| `PORT`            | `8000`                      |

## Endpoints

| Método e rota                 | O que faz                                                    |
|-------------------------------|--------------------------------------------------------------|
| `POST /chat`                  | Envia uma mensagem e recebe a resposta completa em JSON      |
| `POST /chat/stream`           | Igual, mas a resposta chega aos poucos via SSE               |
| `DELETE /sessions/{id}`       | Apaga o histórico da sessão (o `/limpar` do agente 1)        |
| `GET /health`                 | Verifica se a API está no ar                                 |

```bash
curl -s localhost:8000/chat -H 'Content-Type: application/json' \
  -d '{"message": "Quais os 3 produtos mais vendidos?", "session_id": "demo"}'
```

```json
{
  "session_id": "demo",
  "reply": "Os 3 produtos mais vendidos são...",
  "tools_used": [{"name": "produtos_mais_vendidos", "arguments": {"limite": 3}}]
}
```

Sem `session_id`, a API cria uma sessão nova e devolve o id na resposta; envie-o nas próximas
mensagens para manter o contexto.

No streaming (`curl -N`), os eventos são `session`, `tool`, `token`, `done` e `error`. Como o
status HTTP já foi enviado quando o streaming começa, falhas chegam como evento `error`.

Códigos de erro em `POST /chat`: `409` se a sessão já está processando outra mensagem, `422` se
a requisição é inválida e `502` se a API do modelo falhar. Nesses casos o histórico não muda.

## Tools disponíveis

| Tool                     | Responde a                                             |
|--------------------------|--------------------------------------------------------|
| `buscar_clientes`        | Clientes por nome, e-mail, cidade ou estado            |
| `buscar_produtos`        | Produtos por nome ou categoria, com preço e estoque    |
| `listar_categorias`      | Categorias e quantidade de produtos em cada uma        |
| `pedidos_do_cliente`     | Pedidos de um cliente                                  |
| `detalhes_pedido`        | Cliente, status, total e itens de um pedido            |
| `resumo_vendas`          | Pedidos, unidades, faturamento e ticket médio no período |
| `produtos_mais_vendidos` | Ranking de produtos no período                         |

O agente só responde o que essas tools cobrem. Para uma pergunta nova, adicione um método em
[db.py](db.py) e a definição correspondente em [tools.py](tools.py). Por depender do schema da
loja, trocar `DATABASE_PATH` por outra base exige adaptar as consultas.

## Como funciona

1. `main.py` recebe a mensagem e chama o loop em `agent.py`.
2. `llm.py` envia system prompt, histórico da sessão e tools para `POST /chat/completions`, com
   `"stream": true`, e lê os Server-Sent Events como no agente 1, agora juntando também os
   pedaços de `tool_calls`.
3. Se o modelo pedir tools, `tools.py` as executa em `db.py` e os resultados voltam ao modelo. O
   ciclo se repete até 5 vezes; na rodada seguinte as tools não são oferecidas, o que força uma
   resposta.
4. O turno inteiro só entra no histórico ao final, então uma falha não deixa a sessão pela metade.

A base é aberta com `mode=ro`, as consultas são parametrizadas e o modelo nunca escreve SQL.

## Limitações

- **Sem autenticação:** por isso a API escuta só em `127.0.0.1`. Quem a alcança pode gastar sua
  cota da OpenAI e ler os dados, então não a exponha sem adicionar autenticação.
- **Sessões em memória:** somem ao reiniciar, não expiram e o histórico não é truncado. Conversas
  muito longas podem exceder o limite de contexto do modelo; apague a sessão nesse caso.
- **Um processo só:** as sessões não são compartilhadas entre vários workers.

## Testes

```bash
uv run pytest
```

Os testes usam uma base temporária e um servidor local que imita a API da OpenAI, então não
precisam de chave nem de rede.
