"""Agente 2: API que responde perguntas sobre uma base SQLite local usando tools fixas."""

import json
import os
import sys
import uuid
from collections.abc import Generator
from contextlib import closing

import uvicorn
from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.types import Receive, Scope, Send

from agent import Agent, SessionBusy
from config import Settings, load_settings
from db import Database
from llm import LLMError

BUSY_MESSAGE = "Já existe uma mensagem em andamento nesta sessão."


class ChatRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    message: str = Field(min_length=1, max_length=8000)
    session_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        description="Identifica a conversa. Se omitido, uma nova sessão é criada.",
    )


class ToolUse(BaseModel):
    name: str
    arguments: dict | None


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    tools_used: list[ToolUse]


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


class EventStreamResponse(StreamingResponse):
    """Fecha o gerador ao terminar: o Starlette só para de iterar quando o cliente
    desconecta, o que deixaria o turno suspenso segurando o lock da sessão."""

    def __init__(self, events: Generator[str]) -> None:
        super().__init__(events, media_type="text/event-stream")
        self.events = events

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            self.events.close()


def create_app(settings: Settings) -> FastAPI:
    app = FastAPI(title="Agente 2", description="Perguntas em linguagem natural sobre a base local.")
    agent = Agent(settings, Database(settings.database_path))
    app.state.agent = agent

    # As rotas são síncronas de propósito: o FastAPI as executa em threads, e tanto
    # urllib quanto sqlite3 bloqueiam.
    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "model": settings.model}

    @app.post("/chat")
    def chat(request: ChatRequest) -> ChatResponse:
        """Responde de uma vez só, depois de concluir todas as consultas."""
        session_id = request.session_id or str(uuid.uuid4())
        reply, tools_used = [], []
        try:
            for event in agent.run_turn(session_id, request.message):
                if event["type"] == "token":
                    reply.append(event["text"])
                else:
                    # Texto anterior a uma tool é preâmbulo, não faz parte da resposta final.
                    reply.clear()
                    tools_used.append(ToolUse(name=event["name"], arguments=event["arguments"]))
        except SessionBusy:
            raise HTTPException(status_code=409, detail=BUSY_MESSAGE) from None
        except LLMError as e:
            raise HTTPException(status_code=502, detail=str(e)) from e
        return ChatResponse(session_id=session_id, reply="".join(reply), tools_used=tools_used)

    @app.post("/chat/stream")
    def chat_stream(request: ChatRequest) -> EventStreamResponse:
        """Responde via SSE com os eventos session, tool, token, done e error."""
        session_id = request.session_id or str(uuid.uuid4())

        def events() -> Generator[str]:
            yield sse("session", {"session_id": session_id})
            try:
                with closing(agent.run_turn(session_id, request.message)) as turn:
                    for event in turn:
                        if event["type"] == "token":
                            yield sse("token", {"text": event["text"]})
                        else:
                            yield sse("tool", {"name": event["name"], "arguments": event["arguments"]})
            except SessionBusy:
                yield sse("error", {"detail": BUSY_MESSAGE})
            except LLMError as e:
                yield sse("error", {"detail": str(e)})
            else:
                yield sse("done", {"session_id": session_id})

        return EventStreamResponse(events())

    @app.delete("/sessions/{session_id}", status_code=204)
    def clear_session(session_id: str) -> Response:
        """Apaga o histórico da sessão, como o /limpar do agente 1."""
        agent.sessions.delete(session_id)
        return Response(status_code=204)

    return app


def main() -> None:
    settings = load_settings()
    if not settings.database_path.exists():
        sys.exit(f"Erro: base {settings.database_path} não encontrada. Gere-a com: uv run seed_db.py")
    uvicorn.run(
        create_app(settings),
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "8000")),
    )


if __name__ == "__main__":
    main()
