import sqlite3
from contextlib import closing
from datetime import date

import pytest

from db import MAX_ROWS, Database
from seed_db import seed
from tools import TOOLS, execute_tool


def test_connection_is_read_only(db):
    with closing(db.connect()) as conn, pytest.raises(sqlite3.OperationalError, match="readonly"):
        conn.execute("DELETE FROM clientes")


def test_missing_database_is_not_created(tmp_path):
    path = tmp_path / "nao_existe.db"
    with pytest.raises(sqlite3.OperationalError):
        Database(path).listar_categorias()
    assert not path.exists()


def test_search_ignores_accents_and_case(db):
    expected = db.buscar_clientes(cidade="São Paulo")
    assert expected["total"] > 0
    assert db.buscar_clientes(cidade="SAO PAULO") == expected
    assert db.buscar_produtos(categoria="moveis")["total"] == 4


def test_like_wildcards_are_literal(db):
    assert db.buscar_clientes(termo="%")["total"] == 0
    assert db.buscar_clientes(termo="_")["total"] == 0


def test_results_are_capped_but_report_real_total(tmp_path):
    path = tmp_path / "grande.db"
    seed(path)
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.executemany(
            "INSERT INTO clientes VALUES (?, ?, ?, 'Natal', 'RN')",
            [(1000 + i, f"Cliente {i}", f"c{i}@example.com") for i in range(MAX_ROWS + 5)],
        )
    result = Database(path).buscar_clientes(estado="rn")
    assert result["total"] == MAX_ROWS + 5
    assert result["exibidos"] == MAX_ROWS
    assert len(result["resultados"]) == MAX_ROWS


def test_sales_summary_excludes_cancelled_orders(db):
    with closing(db.connect()) as conn:
        expected = conn.execute(
            """
            SELECT COUNT(DISTINCT p.id), SUM(i.quantidade * i.preco_unitario_centavos)
            FROM pedidos p JOIN itens_pedido i ON i.pedido_id = p.id
            WHERE p.status <> 'cancelado'
            """
        ).fetchone()
        cancelled = conn.execute("SELECT COUNT(*) FROM pedidos WHERE status = 'cancelado'").fetchone()[0]
    assert cancelled > 0

    summary = db.resumo_vendas()
    assert summary["pedidos"] == expected[0]
    assert summary["faturamento"] == round(expected[1] / 100, 2)
    assert summary["ticket_medio"] == round(expected[1] / expected[0] / 100, 2)


def test_sales_summary_of_empty_period(db):
    summary = db.resumo_vendas(data_inicio="2000-01-01", data_fim="2000-12-31")
    assert summary["pedidos"] == 0
    assert summary["faturamento"] == 0
    assert summary["ticket_medio"] == 0


def test_period_is_inclusive(db):
    with closing(db.connect()) as conn:
        day = conn.execute("SELECT data FROM pedidos WHERE status <> 'cancelado' LIMIT 1").fetchone()[0]
    assert db.resumo_vendas(data_inicio=day, data_fim=day)["pedidos"] >= 1


def test_order_details_total_matches_items(db):
    order = db.detalhes_pedido(1)
    assert order["itens"]
    assert order["total"] == round(sum(i["quantidade"] * i["preco_unitario"] for i in order["itens"]), 2)
    assert "erro" in db.detalhes_pedido(999999)


def test_best_sellers_respect_limit_and_order(db):
    ranking = db.produtos_mais_vendidos(limite=3)["resultados"]
    assert len(ranking) == 3
    assert ranking[0]["unidades"] >= ranking[1]["unidades"] >= ranking[2]["unidades"]
    assert all(p["categoria"] == "Móveis" for p in db.produtos_mais_vendidos(categoria="moveis")["resultados"])


def test_every_tool_maps_to_a_database_method_and_runs(db):
    required_args = {"pedidos_do_cliente": {"cliente_id": 1}, "detalhes_pedido": {"pedido_id": 1}}
    for tool in TOOLS:
        name = tool["function"]["name"]
        result = execute_tool(db, name, required_args.get(name, {}))
        assert "erro" not in result, name


@pytest.mark.parametrize(
    ("name", "arguments"),
    [
        ("nao_existe", {}),
        ("connect", {}),
        ("buscar_clientes", None),
        ("buscar_clientes", {"coluna": "x"}),
        ("buscar_clientes", {"termo": 123}),
        ("resumo_vendas", {"data_inicio": "ontem"}),
        ("produtos_mais_vendidos", {"limite": "muitos"}),
    ],
)
def test_invalid_tool_calls_return_error_as_data(db, name, arguments):
    assert "erro" in execute_tool(db, name, arguments)


def test_seed_is_deterministic(tmp_path, db_path):
    other = tmp_path / "outra.db"
    seed(other, today=date(2026, 6, 30))
    assert Database(other).resumo_vendas() == Database(db_path).resumo_vendas()
