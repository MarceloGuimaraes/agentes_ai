"""Agente 1: chat no terminal com a OpenAI via HTTP puro (sem SDK, sem tools)."""

import json
import os
import sys
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path

SYSTEM_PROMPT = "Você é um assistente útil e conciso. Responda em português."


def load_env(path: Path) -> None:
    """Carrega variáveis de um arquivo .env simples (CHAVE=valor), sem sobrescrever o ambiente."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def chat_stream(messages: list[dict], *, api_key: str, model: str, base_url: str) -> Iterator[str]:
    """Envia o histórico para /chat/completions e devolve os pedaços de texto via SSE."""
    body = json.dumps({"model": model, "messages": messages, "stream": True}).encode()
    request = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
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
            content = chunk["choices"][0].get("delta", {}).get("content")
            if content:
                yield content


def main() -> None:
    load_env(Path(__file__).parent / ".env")
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        sys.exit("Erro: defina OPENAI_API_KEY no ambiente ou no arquivo .env")
    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    print(f"Agente 1 ({model}). Comandos: /limpar, /sair\n")

    while True:
        try:
            user_input = input("Você: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not user_input:
            continue
        if user_input == "/sair":
            break
        if user_input == "/limpar":
            messages = messages[:1]
            print("Histórico limpo.\n")
            continue

        messages.append({"role": "user", "content": user_input})
        print("Agente: ", end="", flush=True)
        reply = []
        try:
            for piece in chat_stream(messages, api_key=api_key, model=model, base_url=base_url):
                print(piece, end="", flush=True)
                reply.append(piece)
        except urllib.error.HTTPError as e:
            print(f"\n[erro HTTP {e.code}] {e.read().decode('utf-8', 'replace')}\n")
            messages.pop()
            continue
        except urllib.error.URLError as e:
            print(f"\n[erro de conexão] {e.reason}\n")
            messages.pop()
            continue
        except KeyboardInterrupt:
            print(" [interrompido]")
        print("\n")
        messages.append({"role": "assistant", "content": "".join(reply)})


if __name__ == "__main__":
    main()
