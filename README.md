# agentes_ai

Agentes de IA em Python construídos passo a passo, do mais simples ao mais completo. Cada
diretório numerado é um projeto independente, que acrescenta um conceito ao anterior e tem
dependências, configuração e README próprios.

## Agentes

| Projeto | O que faz | O que acrescenta |
|---|---|---|
| [01_chat_terminal](01_chat_terminal/README.md) | Chat no terminal com a API da OpenAI | Streaming e memória da conversa com HTTP puro, sem SDK nem dependências |
| [02_api_consulta_sqlite](02_api_consulta_sqlite/README.md) | API que responde perguntas sobre uma base SQLite local | Tools fixas, API FastAPI, sessões e consultas somente leitura |

## Pré-requisitos

- [uv](https://docs.astral.sh/uv/), que instala o Python 3.13 e as dependências de cada projeto
- Uma chave da [API da OpenAI](https://platform.openai.com/api-keys); o uso é cobrado pela OpenAI

## Como começar

```bash
git clone git@github.com:MarceloGuimaraes/agentes_ai.git
cd agentes_ai/01_chat_terminal   # ou o projeto que quiser rodar
cp .env.example .env             # preencha OPENAI_API_KEY
uv run main.py
```

O `02_api_consulta_sqlite` precisa também gerar a base de exemplo com `uv run seed_db.py` antes de
rodar. Os detalhes de uso estão no README de cada projeto.

## Estrutura

```
agentes_ai/
├── 01_chat_terminal/         # chat no terminal
├── 02_api_consulta_sqlite/   # API com consulta a SQLite
└── plan/                     # planejamento de cada agente
```

O arquivo `.env` guarda a chave da API e não é versionado; nunca o adicione a um commit.
