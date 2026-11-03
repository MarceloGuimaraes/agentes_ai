"""Loop do agente: conversa com o modelo e executa as tools até haver uma resposta final."""

import json
import threading
from collections.abc import Generator
from dataclasses import dataclass, field
from datetime import date

from config import Settings
from db import Database
from llm import chat_stream
from tools import TOOLS, execute_tool

SYSTEM_PROMPT = """Você é um assistente útil e conciso que responde sobre os dados de uma loja.
Responda em português. Hoje é {today}.
Para qualquer dado da loja, consulte as tools e baseie-se apenas no que elas retornarem; nunca invente valores.
Se as tools não permitirem responder, diga isso claramente.
Valores monetários estão em reais (R$). Quando "total" for maior que "exibidos", a lista está incompleta: informe isso."""

MAX_TOOL_ROUNDS = 5


class SessionBusy(Exception):
    """Já existe um turno em andamento nesta sessão."""


@dataclass
class Session:
    history: list[dict] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)


class SessionStore:
    """Sessões na memória do processo: são perdidas ao reiniciar."""

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}
        self._lock = threading.Lock()

    def get(self, session_id: str) -> Session:
        with self._lock:
            return self._sessions.setdefault(session_id, Session())

    def delete(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)


class Agent:
    def __init__(self, settings: Settings, db: Database) -> None:
        self.settings = settings
        self.db = db
        self.sessions = SessionStore()

    def run_turn(self, session_id: str, message: str) -> Generator[dict]:
        """Processa uma mensagem e devolve eventos de progresso ("token" e "tool").

        O histórico só é gravado ao final: se o turno falhar ou o cliente desconectar,
        a sessão continua como estava, como o messages.pop() do agente 1.
        """
        session = self.sessions.get(session_id)
        if not session.lock.acquire(blocking=False):
            raise SessionBusy
        try:
            system = {"role": "system", "content": SYSTEM_PROMPT.format(today=date.today().isoformat())}
            turn = [{"role": "user", "content": message}]
            # A última rodada não oferece tools, o que obriga o modelo a responder.
            for tools in [TOOLS] * MAX_TOOL_ROUNDS + [None]:
                text, tool_calls = [], []
                for kind, value in chat_stream(
                    [system, *session.history, *turn],
                    api_key=self.settings.api_key,
                    model=self.settings.model,
                    base_url=self.settings.base_url,
                    tools=tools,
                ):
                    if kind == "text":
                        text.append(value)
                        yield {"type": "token", "text": value}
                    else:
                        tool_calls = value

                assistant = {"role": "assistant", "content": "".join(text)}
                if tool_calls:
                    assistant["tool_calls"] = tool_calls
                turn.append(assistant)
                if not tool_calls:
                    break

                for call in tool_calls:
                    name = call["function"]["name"]
                    try:
                        arguments = json.loads(call["function"]["arguments"] or "{}")
                    except ValueError:
                        arguments = None
                    yield {"type": "tool", "name": name, "arguments": arguments}
                    result = execute_tool(self.db, name, arguments)
                    turn.append(
                        {
                            "role": "tool",
                            "tool_call_id": call["id"],
                            "content": json.dumps(result, ensure_ascii=False),
                        }
                    )
            session.history.extend(turn)
        finally:
            session.lock.release()
