"""Fixtures dos testes: base temporária e um servidor local que imita a API da OpenAI."""

import json
import threading
import time
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from fastapi.testclient import TestClient

from config import Settings
from db import Database
from main import create_app
from seed_db import seed


def text_reply(*pieces: str) -> list[dict]:
    return [{"choices": [{"delta": {"content": piece}}]} for piece in pieces]


def tool_reply(name: str, arguments: str, call_id: str = "call_1") -> list[dict]:
    """Resposta com tool call, com os argumentos fragmentados como no streaming real."""
    middle = len(arguments) // 2
    first = {"index": 0, "id": call_id, "type": "function", "function": {"name": name, "arguments": ""}}
    return [
        {"choices": [{"delta": {"tool_calls": [first]}}]},
        {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": arguments[:middle]}}]}}]},
        {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": arguments[middle:]}}]}}]},
    ]


class FakeOpenAI:
    """Devolve as respostas de `replies`, em ordem, e guarda as requisições recebidas."""

    def __init__(self) -> None:
        self.replies: list[list[dict] | int] = []
        self.requests: list[dict] = []
        self.chunk_delay = 0.0
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                length = int(self.headers["Content-Length"])
                fake.requests.append(json.loads(self.rfile.read(length)))
                reply = fake.replies.pop(0)
                if isinstance(reply, int):
                    self.send_error(reply)
                    return
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                for chunk in reply:
                    self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
                    self.wfile.flush()
                    time.sleep(fake.chunk_delay)
                self.wfile.write(b"data: [DONE]\n\n")

            def log_message(self, *args) -> None:
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"


@pytest.fixture
def openai():
    fake = FakeOpenAI()
    thread = threading.Thread(target=fake.server.serve_forever, daemon=True)
    thread.start()
    yield fake
    fake.server.shutdown()
    fake.server.server_close()


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "loja.db"
    seed(path, today=date(2026, 6, 30))
    return path


@pytest.fixture
def db(db_path):
    return Database(db_path)


@pytest.fixture
def client(openai, db_path):
    settings = Settings(api_key="test", model="test-model", base_url=openai.base_url, database_path=db_path)
    with TestClient(create_app(settings)) as test_client:
        yield test_client
