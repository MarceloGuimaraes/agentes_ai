"""Tools fixas expostas ao modelo. Cada uma corresponde a um método de db.Database."""

import logging
import sqlite3

from db import Database

logger = logging.getLogger(__name__)

_PERIOD = {
    "data_inicio": {"type": "string", "description": "Data inicial inclusiva, AAAA-MM-DD."},
    "data_fim": {"type": "string", "description": "Data final inclusiva, AAAA-MM-DD."},
}


def _tool(name: str, description: str, properties: dict | None = None, required: tuple = ()) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties or {},
                "required": list(required),
            },
        },
    }


TOOLS = [
    _tool(
        "buscar_clientes",
        "Busca clientes por nome ou e-mail, cidade e estado. Sem filtros, lista todos.",
        {
            "termo": {"type": "string", "description": "Parte do nome ou do e-mail."},
            "cidade": {"type": "string"},
            "estado": {"type": "string", "description": "Sigla da UF, ex.: SP."},
        },
    ),
    _tool(
        "buscar_produtos",
        "Busca produtos por nome e categoria, com preço em reais e estoque. Sem filtros, lista todos.",
        {
            "termo": {"type": "string", "description": "Parte do nome do produto."},
            "categoria": {"type": "string"},
            "apenas_em_estoque": {"type": "boolean"},
        },
    ),
    _tool("listar_categorias", "Lista as categorias de produto e quantos produtos cada uma tem."),
    _tool(
        "pedidos_do_cliente",
        "Lista os pedidos de um cliente, do mais recente ao mais antigo. Use buscar_clientes para obter o id.",
        {"cliente_id": {"type": "integer"}},
        ("cliente_id",),
    ),
    _tool(
        "detalhes_pedido",
        "Mostra cliente, status, total e itens de um pedido.",
        {"pedido_id": {"type": "integer"}},
        ("pedido_id",),
    ),
    _tool(
        "resumo_vendas",
        "Totais de pedidos, unidades, faturamento e ticket médio no período, sem pedidos cancelados. "
        "Sem datas, considera todo o histórico.",
        _PERIOD,
    ),
    _tool(
        "produtos_mais_vendidos",
        "Ranking de produtos por unidades vendidas no período, sem pedidos cancelados.",
        {
            "limite": {"type": "integer", "description": "Quantos produtos retornar (padrão 5)."},
            "categoria": {"type": "string"},
            **_PERIOD,
        },
    ),
]

_TOOL_NAMES = {tool["function"]["name"] for tool in TOOLS}


def execute_tool(db: Database, name: str, arguments: dict | None) -> dict:
    """Executa uma tool. Erros voltam como dados, para o modelo poder corrigir ou explicar."""
    if name not in _TOOL_NAMES:
        return {"erro": f"Tool desconhecida: {name}"}
    try:
        return getattr(db, name)(**arguments)
    except (TypeError, ValueError) as e:
        return {"erro": f"Argumentos inválidos para {name}: {e}"}
    except sqlite3.Error as e:
        logger.error("Falha ao executar %s: %s", name, e)
        return {"erro": "Falha ao consultar a base de dados."}
