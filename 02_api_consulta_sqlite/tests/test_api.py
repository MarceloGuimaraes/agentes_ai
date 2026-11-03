import json
from dataclasses import replace

from agent import MAX_TOOL_ROUNDS
from conftest import text_reply, tool_reply


def parse_sse(body: str) -> list[tuple[str, dict]]:
    events = []
    for block in body.strip().split("\n\n"):
        event, data = block.split("\n")
        events.append((event.removeprefix("event: "), json.loads(data.removeprefix("data: "))))
    return events


def test_health(client):
    assert client.get("/health").json() == {"status": "ok", "model": "test-model"}


def test_chat_without_tools(client, openai):
    openai.replies = [text_reply("Olá", ", tudo bem?")]

    response = client.post("/chat", json={"message": "oi"})

    assert response.status_code == 200
    body = response.json()
    assert body["reply"] == "Olá, tudo bem?"
    assert body["tools_used"] == []
    assert body["session_id"]
    request = openai.requests[0]
    assert request["stream"] is True
    assert request["messages"][0]["role"] == "system"
    assert request["messages"][-1] == {"role": "user", "content": "oi"}
    assert {t["function"]["name"] for t in request["tools"]} >= {"buscar_clientes", "resumo_vendas"}


def test_chat_runs_tool_and_sends_result_to_model(client, openai, db):
    arguments = json.dumps({"categoria": "móveis"})
    openai.replies = [
        text_reply("Vou consultar.") + tool_reply("buscar_produtos", arguments),
        text_reply("Há 4 produtos."),
    ]

    body = client.post("/chat", json={"message": "quantos móveis?"}).json()

    assert body["reply"] == "Há 4 produtos."
    assert body["tools_used"] == [{"name": "buscar_produtos", "arguments": {"categoria": "móveis"}}]
    assistant, tool_message = openai.requests[1]["messages"][-2:]
    assert assistant["tool_calls"][0]["id"] == "call_1"
    assert assistant["tool_calls"][0]["function"] == {"name": "buscar_produtos", "arguments": arguments}
    assert tool_message["role"] == "tool"
    assert tool_message["tool_call_id"] == "call_1"
    assert json.loads(tool_message["content"]) == db.buscar_produtos(categoria="móveis")


def test_malformed_tool_arguments_go_back_to_model(client, openai):
    openai.replies = [tool_reply("buscar_produtos", '{"termo": '), text_reply("Não consegui consultar.")]

    body = client.post("/chat", json={"message": "x"}).json()

    assert body["tools_used"] == [{"name": "buscar_produtos", "arguments": None}]
    assert "erro" in json.loads(openai.requests[1]["messages"][-1]["content"])


def test_tool_rounds_are_limited(client, openai):
    openai.replies = [tool_reply("listar_categorias", "{}") for _ in range(MAX_TOOL_ROUNDS)]
    openai.replies.append(text_reply("Resposta final."))

    body = client.post("/chat", json={"message": "x"}).json()

    assert body["reply"] == "Resposta final."
    assert len(openai.requests) == MAX_TOOL_ROUNDS + 1
    assert "tools" in openai.requests[-2]
    assert "tools" not in openai.requests[-1]


def test_session_keeps_history_until_cleared(client, openai):
    openai.replies = [text_reply("Prazer, Ana."), text_reply("Ana."), text_reply("Não sei.")]

    first = client.post("/chat", json={"message": "meu nome é Ana", "session_id": "s1"}).json()
    assert first["session_id"] == "s1"
    client.post("/chat", json={"message": "qual meu nome?", "session_id": "s1"})
    assert [m["content"] for m in openai.requests[1]["messages"][1:]] == [
        "meu nome é Ana",
        "Prazer, Ana.",
        "qual meu nome?",
    ]

    assert client.delete("/sessions/s1").status_code == 204
    client.post("/chat", json={"message": "qual meu nome?", "session_id": "s1"})
    assert [m["content"] for m in openai.requests[2]["messages"][1:]] == ["qual meu nome?"]


def test_sessions_are_isolated(client, openai):
    openai.replies = [text_reply("a"), text_reply("b")]

    client.post("/chat", json={"message": "primeira", "session_id": "s1"})
    client.post("/chat", json={"message": "segunda", "session_id": "s2"})

    assert [m["content"] for m in openai.requests[1]["messages"][1:]] == ["segunda"]


def test_upstream_error_returns_502_and_keeps_history_clean(client, openai):
    openai.replies = [401, text_reply("ok")]

    response = client.post("/chat", json={"message": "falha", "session_id": "s1"})
    assert response.status_code == 502
    assert "401" in response.json()["detail"]

    client.post("/chat", json={"message": "de novo", "session_id": "s1"})
    assert [m["content"] for m in openai.requests[1]["messages"][1:]] == ["de novo"]


def test_failure_after_tool_discards_whole_turn(client, openai):
    openai.replies = [tool_reply("listar_categorias", "{}"), 500, text_reply("ok")]

    assert client.post("/chat", json={"message": "falha", "session_id": "s1"}).status_code == 502

    client.post("/chat", json={"message": "de novo", "session_id": "s1"})
    assert [m["role"] for m in openai.requests[-1]["messages"][1:]] == ["user"]


def test_unreachable_upstream_returns_502(client, openai):
    agent = client.app.state.agent
    agent.settings = replace(agent.settings, base_url="http://127.0.0.1:1")
    assert client.post("/chat", json={"message": "x"}).status_code == 502


def test_busy_session_returns_409(client, openai):
    session = client.app.state.agent.sessions.get("s1")
    session.lock.acquire()
    try:
        assert client.post("/chat", json={"message": "x", "session_id": "s1"}).status_code == 409
        events = parse_sse(client.post("/chat/stream", json={"message": "x", "session_id": "s1"}).text)
        assert events[-1][0] == "error"
    finally:
        session.lock.release()
    assert openai.requests == []


def test_abandoned_turn_releases_session_and_saves_nothing(client, openai):
    openai.replies = [text_reply("um", "dois")]
    agent = client.app.state.agent

    turn = agent.run_turn("s1", "x")
    assert next(turn) == {"type": "token", "text": "um"}
    assert agent.sessions.get("s1").lock.locked()
    turn.close()

    session = agent.sessions.get("s1")
    assert not session.lock.locked()
    assert session.history == []


def test_stream_emits_events_in_order(client, openai):
    openai.replies = [tool_reply("listar_categorias", "{}"), text_reply("Cinco", " categorias.")]

    response = client.post("/chat/stream", json={"message": "x", "session_id": "s1"})

    assert response.headers["content-type"].startswith("text/event-stream")
    assert parse_sse(response.text) == [
        ("session", {"session_id": "s1"}),
        ("tool", {"name": "listar_categorias", "arguments": {}}),
        ("token", {"text": "Cinco"}),
        ("token", {"text": " categorias."}),
        ("done", {"session_id": "s1"}),
    ]


def test_stream_reports_upstream_error_as_event(client, openai):
    openai.replies = [500]

    events = parse_sse(client.post("/chat/stream", json={"message": "x"}).text)

    assert events[-1][0] == "error"
    assert "500" in events[-1][1]["detail"]
    assert "done" not in [name for name, _ in events]


def test_invalid_requests_are_rejected(client, openai):
    assert client.post("/chat", json={"message": "   "}).status_code == 422
    assert client.post("/chat", json={}).status_code == 422
    assert client.post("/chat", json={"message": "x" * 8001}).status_code == 422
    assert client.post("/chat", json={"message": "x", "session_id": ""}).status_code == 422
    assert openai.requests == []
