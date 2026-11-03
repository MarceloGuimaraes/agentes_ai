"""Desconexão real durante o streaming: o TestClient não consegue reproduzir este caso."""

import http.client
import json
import threading
import time

import uvicorn

from config import Settings
from conftest import text_reply
from main import create_app


def test_client_disconnect_during_stream_releases_session(openai, db_path):
    openai.chunk_delay = 0.2
    openai.replies = [text_reply(*"abcdefghij")]
    settings = Settings(api_key="test", model="m", base_url=openai.base_url, database_path=db_path)
    app = create_app(settings)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        while not server.started:
            time.sleep(0.01)
        port = server.servers[0].sockets[0].getsockname()[1]

        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request(
            "POST",
            "/chat/stream",
            body=json.dumps({"message": "x", "session_id": "s1"}),
            headers={"Content-Type": "application/json"},
        )
        response = conn.getresponse()
        while b"token" not in response.readline():
            pass
        session = app.state.agent.sessions.get("s1")
        assert session.lock.locked()
        conn.sock.close()
        response.close()
        conn.close()

        deadline = time.monotonic() + 5
        while session.lock.locked() and time.monotonic() < deadline:
            time.sleep(0.05)

        assert not session.lock.locked()
        assert session.history == []
    finally:
        server.should_exit = True
        thread.join(timeout=5)
