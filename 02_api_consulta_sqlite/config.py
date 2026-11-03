"""Configuração do agente, lida do ambiente ou do arquivo .env."""

import os
import sys
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).parent


@dataclass(frozen=True)
class Settings:
    api_key: str
    model: str
    base_url: str
    database_path: Path


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


def database_path() -> Path:
    """Caminho da base SQLite; um caminho relativo parte do diretório do projeto."""
    load_env(BASE_DIR / ".env")
    return BASE_DIR / os.environ.get("DATABASE_PATH", "loja.db")


def load_settings() -> Settings:
    load_env(BASE_DIR / ".env")
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        sys.exit("Erro: defina OPENAI_API_KEY no ambiente ou no arquivo .env")
    return Settings(
        api_key=api_key,
        model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
        base_url=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
        database_path=database_path(),
    )
