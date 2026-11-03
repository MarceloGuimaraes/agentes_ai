"""Cliente da OpenAI via HTTP puro: mesmo streaming SSE do agente 1, agora com tools."""

import http.client
import json
import logging
import urllib.error
import urllib.request
from collections.abc import Iterator

logger = logging.getLogger(__name__)


class LLMError(Exception):
    """Falha ao falar com a API do modelo. A mensagem pode ser mostrada ao cliente da API."""


def _merge_tool_call_deltas(calls: dict[int, dict], deltas: list[dict]) -> None:
    """Junta os pedaços de tool_calls do streaming; os argumentos chegam fragmentados."""
    for delta in deltas:
        call = calls.setdefault(
            delta["index"],
            {"id": "", "type": "function", "function": {"name": "", "arguments": ""}},
        )
        call["id"] = delta.get("id") or call["id"]
        function = delta.get("function", {})
        call["function"]["name"] += function.get("name") or ""
        call["function"]["arguments"] += function.get("arguments") or ""


def chat_stream(
    messages: list[dict],
    *,
    api_key: str,
    model: str,
    base_url: str,
    tools: list[dict] | None = None,
) -> Iterator[tuple[str, str | list[dict]]]:
    """Envia o histórico para /chat/completions e devolve eventos via SSE.

    Cada pedaço de texto vira ("text", pedaço). Se o modelo pedir tools, o último
    evento é ("tool_calls", chamadas completas).
    """
    payload = {"model": model, "messages": messages, "stream": True}
    if tools:
        payload["tools"] = tools
    request = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    calls: dict[int, dict] = {}
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            for raw_line in response:
                line = raw_line.decode("utf-8").strip()
                if not line.startswith("data:"):
                    continue
                data = line.removeprefix("data:").strip()
                if data == "[DONE]":
                    break
                chunk = json.loads(data)
                if not chunk.get("choices"):
                    continue
                delta = chunk["choices"][0].get("delta", {})
                if delta.get("content"):
                    yield "text", delta["content"]
                _merge_tool_call_deltas(calls, delta.get("tool_calls") or [])
    except urllib.error.HTTPError as e:
        logger.error("Erro HTTP %s da API do modelo: %s", e.code, e.read().decode("utf-8", "replace"))
        raise LLMError(f"A API do modelo respondeu com erro HTTP {e.code}.") from e
    except (OSError, http.client.HTTPException, ValueError, KeyError) as e:
        logger.error("Falha na comunicação com a API do modelo: %s", e)
        raise LLMError("Falha na comunicação com a API do modelo.") from e
    if calls:
        yield "tool_calls", [calls[index] for index in sorted(calls)]
