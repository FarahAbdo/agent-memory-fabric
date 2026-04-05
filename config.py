"""
Configuration loader for the Agent Memory Fabric demo.
Reads from .env file and provides typed access to all settings.
"""

import os
import sys
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel

console = Console()
load_dotenv()


# ─── Cosmos DB Settings ───────────────────────────────────────────
COSMOS_ENDPOINT: str = os.getenv("COSMOS_ENDPOINT", "")
COSMOS_KEY: str = os.getenv("COSMOS_KEY", "")
DATABASE_NAME: str = os.getenv("DATABASE_NAME", "agent-memory-fabric")

# ─── OpenAI Settings ─────────────────────────────────────────────
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
EMBEDDING_MODEL: str = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
CHAT_MODEL: str = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")

# ─── Container Names ─────────────────────────────────────────────
CONTAINER_MEMORY: str = "agent-memory"
CONTAINER_EVENTS: str = "agent-events"
CONTAINER_STATE: str = "shared-state"

# ─── Emulator Detection ──────────────────────────────────────────
IS_EMULATOR: bool = "localhost" in COSMOS_ENDPOINT or "127.0.0.1" in COSMOS_ENDPOINT

# ─── Semantic Cache Settings ─────────────────────────────────────
SIMILARITY_THRESHOLD: float = 0.85
EMBEDDING_DIMENSIONS: int = 1536


def validate_config() -> bool:
    """Validate that all required configuration is present."""
    missing = []
    if not COSMOS_ENDPOINT:
        missing.append("COSMOS_ENDPOINT")
    if not COSMOS_KEY:
        missing.append("COSMOS_KEY")
    if not OPENAI_API_KEY:
        missing.append("OPENAI_API_KEY")

    if missing:
        console.print(Panel(
            f"[red bold]Missing environment variables:[/]\n"
            + "\n".join(f"  - {v}" for v in missing)
            + "\n\n[dim]Copy .env.example to .env and fill in your values.[/]",
            title="Configuration Error",
            border_style="red"
        ))
        return False

    mode = "Emulator" if IS_EMULATOR else "Azure"
    console.print(
        f"[dim]Config loaded — {mode} mode | "
        f"DB: {DATABASE_NAME} | "
        f"Embedding: {EMBEDDING_MODEL}[/]"
    )
    return True


if __name__ == "__main__":
    if validate_config():
        console.print("[green]All configuration valid.[/]")
    else:
        sys.exit(1)
