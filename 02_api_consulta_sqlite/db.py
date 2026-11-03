"""Consultas fixas à base SQLite local. Todas usam conexão somente leitura."""

import sqlite3
import unicodedata
from contextlib import closing
from datetime import date
from pathlib import Path

MAX_ROWS = 50


def normalize(text: str) -> str:
    """Remove acentos e caixa, para "sao paulo" encontrar "São Paulo"."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()


def _contains(term: str) -> str:
    """Monta o padrão de LIKE, tratando % e _ do termo como texto comum."""
    escaped = normalize(term).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _reais(cents: int | None) -> float:
    return round((cents or 0) / 100, 2)


def _period(start: str | None, end: str | None) -> tuple[str, list[str]]:
    """Filtro de datas (inclusivo) sobre pedidos; datas inválidas geram ValueError."""
    sql, params = "", []
    if start:
        sql += " AND p.data >= ?"
        params.append(date.fromisoformat(start).isoformat())
    if end:
        sql += " AND p.data <= ?"
        params.append(date.fromisoformat(end).isoformat())
    return sql, params


def _page(rows: list[dict]) -> dict:
    """Limita o que vai ao modelo, mas informa o total real para ele não contar errado."""
    return {"total": len(rows), "exibidos": min(len(rows), MAX_ROWS), "resultados": rows[:MAX_ROWS]}


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(f"{self.path.resolve().as_uri()}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        conn.create_function("norm", 1, normalize, deterministic=True)
        return conn

    def _query(self, sql: str, params: list | tuple = ()) -> list[dict]:
        with closing(self.connect()) as conn:
            return [dict(row) for row in conn.execute(sql, params)]

    def buscar_clientes(
        self, termo: str | None = None, cidade: str | None = None, estado: str | None = None
    ) -> dict:
        sql = "SELECT id, nome, email, cidade, estado FROM clientes WHERE 1 = 1"
        params = []
        if termo:
            sql += " AND (norm(nome) LIKE ? ESCAPE '\\' OR norm(email) LIKE ? ESCAPE '\\')"
            params += [_contains(termo), _contains(termo)]
        if cidade:
            sql += " AND norm(cidade) LIKE ? ESCAPE '\\'"
            params.append(_contains(cidade))
        if estado:
            sql += " AND norm(estado) = ?"
            params.append(normalize(estado))
        return _page(self._query(sql + " ORDER BY nome", params))

    def buscar_produtos(
        self,
        termo: str | None = None,
        categoria: str | None = None,
        apenas_em_estoque: bool = False,
    ) -> dict:
        sql = """
            SELECT id, nome, categoria, preco_centavos, estoque
            FROM produtos WHERE 1 = 1
        """
        params = []
        if termo:
            sql += " AND norm(nome) LIKE ? ESCAPE '\\'"
            params.append(_contains(termo))
        if categoria:
            sql += " AND norm(categoria) LIKE ? ESCAPE '\\'"
            params.append(_contains(categoria))
        if apenas_em_estoque:
            sql += " AND estoque > 0"
        rows = self._query(sql + " ORDER BY nome", params)
        for row in rows:
            row["preco"] = _reais(row.pop("preco_centavos"))
        return _page(rows)

    def listar_categorias(self) -> dict:
        return _page(
            self._query(
                "SELECT categoria, COUNT(*) AS produtos FROM produtos GROUP BY categoria ORDER BY categoria"
            )
        )

    def pedidos_do_cliente(self, cliente_id: int) -> dict:
        rows = self._query(
            """
            SELECT p.id, p.data, p.status,
                   SUM(i.quantidade * i.preco_unitario_centavos) AS total_centavos
            FROM pedidos p JOIN itens_pedido i ON i.pedido_id = p.id
            WHERE p.cliente_id = ?
            GROUP BY p.id
            ORDER BY p.data DESC, p.id DESC
            """,
            (cliente_id,),
        )
        for row in rows:
            row["total"] = _reais(row.pop("total_centavos"))
        return _page(rows)

    def detalhes_pedido(self, pedido_id: int) -> dict:
        orders = self._query(
            """
            SELECT p.id, p.data, p.status, c.id AS cliente_id, c.nome AS cliente
            FROM pedidos p JOIN clientes c ON c.id = p.cliente_id
            WHERE p.id = ?
            """,
            (pedido_id,),
        )
        if not orders:
            return {"erro": f"Pedido {pedido_id} não encontrado."}
        items = self._query(
            """
            SELECT pr.id AS produto_id, pr.nome AS produto, i.quantidade, i.preco_unitario_centavos
            FROM itens_pedido i JOIN produtos pr ON pr.id = i.produto_id
            WHERE i.pedido_id = ?
            ORDER BY pr.nome
            """,
            (pedido_id,),
        )
        total = 0
        for item in items:
            cents = item.pop("preco_unitario_centavos")
            total += cents * item["quantidade"]
            item["preco_unitario"] = _reais(cents)
        return {**orders[0], "total": _reais(total), "itens": items}

    def resumo_vendas(self, data_inicio: str | None = None, data_fim: str | None = None) -> dict:
        period, params = _period(data_inicio, data_fim)
        row = self._query(
            f"""
            SELECT COUNT(DISTINCT p.id) AS pedidos,
                   COALESCE(SUM(i.quantidade), 0) AS unidades,
                   COALESCE(SUM(i.quantidade * i.preco_unitario_centavos), 0) AS centavos
            FROM pedidos p JOIN itens_pedido i ON i.pedido_id = p.id
            WHERE p.status <> 'cancelado'{period}
            """,
            params,
        )[0]
        return {
            "pedidos": row["pedidos"],
            "unidades": row["unidades"],
            "faturamento": _reais(row["centavos"]),
            "ticket_medio": _reais(row["centavos"] / row["pedidos"]) if row["pedidos"] else 0.0,
        }

    def produtos_mais_vendidos(
        self,
        limite: int = 5,
        data_inicio: str | None = None,
        data_fim: str | None = None,
        categoria: str | None = None,
    ) -> dict:
        limit = max(1, min(int(limite), MAX_ROWS))
        period, params = _period(data_inicio, data_fim)
        if categoria:
            period += " AND norm(pr.categoria) LIKE ? ESCAPE '\\'"
            params.append(_contains(categoria))
        rows = self._query(
            f"""
            SELECT pr.id, pr.nome, pr.categoria,
                   SUM(i.quantidade) AS unidades,
                   SUM(i.quantidade * i.preco_unitario_centavos) AS centavos
            FROM itens_pedido i
            JOIN pedidos p ON p.id = i.pedido_id
            JOIN produtos pr ON pr.id = i.produto_id
            WHERE p.status <> 'cancelado'{period}
            GROUP BY pr.id
            ORDER BY unidades DESC, centavos DESC, pr.id
            LIMIT ?
            """,
            [*params, limit],
        )
        for row in rows:
            row["faturamento"] = _reais(row.pop("centavos"))
        return {"resultados": rows}
