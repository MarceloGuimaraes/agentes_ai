"""Gera a base SQLite de exemplo com dados fictícios de uma loja."""

import argparse
import random
import sqlite3
import sys
import unicodedata
from contextlib import closing
from datetime import date, timedelta
from pathlib import Path

from config import database_path

SCHEMA = """
CREATE TABLE clientes (
    id INTEGER PRIMARY KEY,
    nome TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    cidade TEXT NOT NULL,
    estado TEXT NOT NULL
);
CREATE TABLE produtos (
    id INTEGER PRIMARY KEY,
    nome TEXT NOT NULL,
    categoria TEXT NOT NULL,
    preco_centavos INTEGER NOT NULL,
    estoque INTEGER NOT NULL
);
CREATE TABLE pedidos (
    id INTEGER PRIMARY KEY,
    cliente_id INTEGER NOT NULL REFERENCES clientes(id),
    data TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pago', 'enviado', 'entregue', 'cancelado'))
);
CREATE TABLE itens_pedido (
    pedido_id INTEGER NOT NULL REFERENCES pedidos(id),
    produto_id INTEGER NOT NULL REFERENCES produtos(id),
    quantidade INTEGER NOT NULL CHECK (quantidade > 0),
    preco_unitario_centavos INTEGER NOT NULL,
    PRIMARY KEY (pedido_id, produto_id)
);
CREATE INDEX idx_pedidos_cliente ON pedidos(cliente_id);
CREATE INDEX idx_pedidos_data ON pedidos(data);
"""

FIRST_NAMES = ["Ana", "João", "Márcia", "Pedro", "Luísa", "Rafael", "Camila", "André", "Beatriz", "Tomás"]
LAST_NAMES = ["Souza", "Conceição", "Araújo", "Lima", "Gonçalves", "Ribeiro", "Melo"]
CITIES = [
    ("São Paulo", "SP"),
    ("Campinas", "SP"),
    ("Rio de Janeiro", "RJ"),
    ("Belo Horizonte", "MG"),
    ("Curitiba", "PR"),
    ("Porto Alegre", "RS"),
    ("Salvador", "BA"),
    ("Recife", "PE"),
    ("Florianópolis", "SC"),
    ("Brasília", "DF"),
]
PRODUCTS = [
    ("Notebook 14 polegadas", "Informática", 389900),
    ("Monitor 27 polegadas", "Informática", 149900),
    ("Teclado mecânico", "Informática", 34990),
    ("Mouse sem fio", "Informática", 12990),
    ("Webcam Full HD", "Informática", 24990),
    ("Smartphone 128 GB", "Telefonia", 219900),
    ("Fone Bluetooth", "Telefonia", 19990),
    ("Carregador rápido", "Telefonia", 8990),
    ("Capa protetora", "Telefonia", 3990),
    ("Cafeteira elétrica", "Eletrodomésticos", 29990),
    ("Liquidificador", "Eletrodomésticos", 17990),
    ("Aspirador de pó", "Eletrodomésticos", 45990),
    ("Air fryer", "Eletrodomésticos", 39990),
    ("Cadeira de escritório", "Móveis", 89900),
    ("Mesa para computador", "Móveis", 64900),
    ("Estante de livros", "Móveis", 42900),
    ("Luminária de mesa", "Móveis", 11990),
    ("Caderno universitário", "Papelaria", 2490),
    ("Caneta esferográfica", "Papelaria", 390),
    ("Mochila executiva", "Papelaria", 15990),
]
NUM_CUSTOMERS = 30
NUM_ORDERS = 200
HISTORY_DAYS = 365


def _slug(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", text.lower()) if not unicodedata.combining(c) and c != " "
    )


def seed(path: Path, today: date | None = None) -> None:
    """Cria a base em `path`. Os dados são sempre os mesmos, com datas relativas a `today`."""
    today = today or date.today()
    rng = random.Random(42)
    names = [f"{first} {last}" for first in FIRST_NAMES for last in LAST_NAMES]
    customers = [
        (i, name, f"{_slug(name)}@example.com", *rng.choice(CITIES))
        for i, name in enumerate(rng.sample(names, NUM_CUSTOMERS), start=1)
    ]
    # Produtos com estoque zerado permitem testar perguntas sobre disponibilidade.
    products = [
        (i, name, category, price, rng.choice([0, 3, 8, 15, 40, 120]))
        for i, (name, category, price) in enumerate(PRODUCTS, start=1)
    ]

    orders, items = [], []
    for order_id in range(1, NUM_ORDERS + 1):
        ordered_on = today - timedelta(days=rng.randrange(HISTORY_DAYS))
        age = (today - ordered_on).days
        status = "pago" if age < 3 else "enviado" if age < 10 else "entregue"
        if rng.random() < 0.08:
            status = "cancelado"
        orders.append((order_id, rng.randint(1, NUM_CUSTOMERS), ordered_on.isoformat(), status))
        for product in rng.sample(products, rng.randint(1, 4)):
            items.append((order_id, product[0], rng.randint(1, 3), product[3]))

    with closing(sqlite3.connect(path)) as conn, conn:
        conn.executescript(SCHEMA)
        conn.executemany("INSERT INTO clientes VALUES (?, ?, ?, ?, ?)", customers)
        conn.executemany("INSERT INTO produtos VALUES (?, ?, ?, ?, ?)", products)
        conn.executemany("INSERT INTO pedidos VALUES (?, ?, ?, ?)", orders)
        conn.executemany("INSERT INTO itens_pedido VALUES (?, ?, ?, ?)", items)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="apaga a base existente antes de gerar")
    args = parser.parse_args()

    path = database_path()
    if path.exists():
        if not args.force:
            sys.exit(f"Erro: {path} já existe. Use --force para apagar e gerar de novo.")
        path.unlink()
    seed(path)
    print(f"Base criada em {path}")


if __name__ == "__main__":
    main()
