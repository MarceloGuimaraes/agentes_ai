# Agente 2 — API com tools fixas para consultar uma base SQLite local

## Context
O `01_chat_terminal/` é um chat de terminal com a OpenAI via HTTP puro, sem tools e sem acesso a dados.
O objetivo é evoluir essa base para uma **aplicação com API em Python que consulta uma base de
dados local**, em `02_api_consulta_sqlite/`. O projeto não tinha nenhuma base (`.db`, `.sqlite`, `.csv`), então
é preciso criar uma de exemplo. O `01_chat_terminal/` não é alterado.

## Decisões
| Tema       | Escolha                     | Consequência                                                        |
|------------|-----------------------------|---------------------------------------------------------------------|
| Base       | SQLite de exemplo           | `seed_db.py` gera uma loja fictícia; trocar de base exige o mesmo schema ou adaptar as consultas |
| API        | FastAPI + cliente HTTP puro | `fastapi` e `uvicorn` como dependências; OpenAI continua em `urllib` |
| Consulta   | Tools fixas                 | Previsível e seguro, mas só responde o que as tools cobrem           |
| Memória    | Sessões em memória          | `session_id` enviado pelo cliente; histórico perdido ao reiniciar    |

## Estrutura (tudo em `02_api_consulta_sqlite/`)
```
02_api_consulta_sqlite/
├── pyproject.toml     # layout plano como o 01_chat_terminal; dev: pytest, httpx2
├── .python-version    # 3.13
├── .env.example       # OPENAI_*, DATABASE_PATH, HOST, PORT
├── .gitignore         # inclui .env e *.db
├── README.md
├── main.py            # rotas FastAPI e inicialização
├── agent.py           # loop do agente e sessões
├── llm.py             # chat_stream em HTTP puro, com tool_calls
├── tools.py           # definição das tools e execução
├── db.py              # consultas fixas, conexão somente leitura
├── config.py          # load_env e Settings
├── seed_db.py         # gera loja.db
└── tests/             # conftest (falso OpenAI), test_db, test_api, test_disconnect
```
Criação: `uv init --app --no-workspace --vcs none --name 02-api-consulta-sqlite --python 3.13`. O comando gerou
um layout `src/` empacotado, que foi removido em favor do formato plano.

## Base de dados — `seed_db.py`
- Tabelas `clientes`, `produtos`, `pedidos` (`pago`, `enviado`, `entregue`, `cancelado`) e
  `itens_pedido`, com 30 clientes, 20 produtos e 200 pedidos.
- Valores em centavos (inteiros), com o preço unitário gravado em cada item do pedido.
- Geração determinística (`random.Random(42)`), com datas nos 365 dias anteriores à geração.
- Não sobrescreve uma base existente sem `--force`.

## Consultas e tools — `db.py` e `tools.py`
- **Segurança:** conexão com `mode=ro`, consultas parametrizadas e nenhum SQL vindo do modelo.
- **Busca em português:** função SQL `norm` ignora acentos e caixa ("sao paulo" acha "São Paulo");
  `%` e `_` do termo são tratados como texto comum.
- **Limite honesto:** no máximo 50 linhas vão ao modelo, sempre com `total` e `exibidos`, para ele
  não contar errado uma lista truncada.
- **Vendas:** resumo e ranking excluem pedidos cancelados; o período é inclusivo.
- **Erros como dados:** argumentos inválidos ou falha de SQL voltam ao modelo como `{"erro": ...}`.

Tools: `buscar_clientes`, `buscar_produtos`, `listar_categorias`, `pedidos_do_cliente`,
`detalhes_pedido`, `resumo_vendas`, `produtos_mais_vendidos`.

## Agente — `llm.py` e `agent.py`
- **`chat_stream`:** adapta o do agente 1. Emite `("text", pedaço)` e, ao final, `("tool_calls",
  chamadas)`, juntando os argumentos que chegam fragmentados. Falhas viram `LLMError`, com mensagem
  segura para o cliente; o corpo do erro da API fica só no log.
- **`run_turn`:** gerador que chama o modelo, executa as tools e repete até haver resposta. São até
  5 rodadas com tools; a rodada seguinte não as oferece, o que força uma resposta.
- **System prompt:** montado a cada turno com a data de hoje, para "este mês" funcionar, e proíbe
  inventar valores.
- **Histórico transacional:** o turno só entra na sessão ao final; falha ou desconexão não a altera.
- **Concorrência:** lock por sessão, sem espera; uma segunda mensagem simultânea recebe erro.

## API — `main.py`
| Rota                    | Comportamento                                                  |
|-------------------------|----------------------------------------------------------------|
| `POST /chat`            | JSON com `session_id`, `reply` e `tools_used`                  |
| `POST /chat/stream`     | SSE com eventos `session`, `tool`, `token`, `done` e `error`   |
| `DELETE /sessions/{id}` | Apaga o histórico, como o `/limpar` do agente 1                |
| `GET /health`           | Status e modelo                                                |

- **Erros em `/chat`:** `409` para sessão ocupada, `422` para requisição inválida e `502` para
  falha na API do modelo. No streaming, as falhas chegam como evento `error`.
- **Rotas síncronas:** `urllib` e `sqlite3` bloqueiam, então as rotas rodam em threads.
- **`EventStreamResponse`:** fecha o gerador ao terminar. O `StreamingResponse` do Starlette não o
  fecha quando o cliente desconecta, o que deixava a sessão travada em 409.
- **Inicialização:** escuta em `127.0.0.1` por padrão, pois não há autenticação; sem chave ou sem
  base, encerra com mensagem clara.

## Fora do escopo
Autenticação, persistência e expiração de sessões, truncamento do histórico, múltiplos workers e
SQL livre gerado pelo modelo.

## Verificação
1. `uv run pytest` usa base temporária e um falso OpenAI local, sem chave nem rede.
2. Sem `OPENAI_API_KEY` ou sem `loja.db`: `uv run main.py` encerra com mensagem legível.
3. Servidor real contra o falso OpenAI (`OPENAI_BASE_URL`), com `curl`:
   - `/chat` executa a tool e devolve `tools_used`;
   - `/chat/stream` entrega os tokens aos poucos;
   - cliente que desconecta no meio não trava a sessão nem grava o turno abandonado;
   - mensagem simultânea na mesma sessão recebe `409`.
4. **Pendente — com a OpenAI real:** `cp ../01_chat_terminal/.env .env`, `uv run main.py` e perguntar:
   - "Quais os 3 produtos mais vendidos?" (uso da tool correta);
   - "E qual o preço do primeiro?" (memória da sessão);
   - "Qual o faturamento deste mês?" (uso da data atual);
   - uma pergunta fora das tools, como margem de lucro (deve dizer que não consegue responder).
