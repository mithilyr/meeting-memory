"""Runtime configuration, read from the environment.

Adapted from the CodeFest ashen-assistant. Paths resolve from this file, so the
code works from any working directory. Model names live here so a swap is one
edit, not a search.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_PATH = PROJECT_ROOT.parent / "Catalist_AI_Intern_Build_Test_Data"


@dataclass(frozen=True)
class Settings:
    data_path: Path
    cache_dir: Path
    db_path: Path
    ollama_url: str
    #: Local model for extraction and answering. $0, runs on the 6GB GPU.
    llm_model: str
    #: Local embedding model, served by Ollama.
    embed_model: str
    openrouter_api_key: str | None

    @property
    def transcripts_dir(self) -> Path:
        return self.data_path / "transcripts"

    @property
    def inbox_dir(self) -> Path:
        """Where new transcripts go (UI upload or a recorder drop). The data folder stays read-only."""
        return PROJECT_ROOT / "inbox"

    @property
    def questions_path(self) -> Path:
        return self.data_path / "questions.json"

    def require_data(self) -> Path:
        if not self.transcripts_dir.is_dir():
            raise FileNotFoundError(
                f"No transcripts at {self.transcripts_dir}. "
                "Set DATA_PATH in .env to the folder holding transcripts/ and questions.json."
            )
        return self.transcripts_dir


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    load_dotenv(PROJECT_ROOT / ".env")
    cache_dir = Path(os.getenv("CACHE_DIR", PROJECT_ROOT / ".cache"))
    return Settings(
        data_path=Path(os.getenv("DATA_PATH", DEFAULT_DATA_PATH)),
        cache_dir=cache_dir,
        db_path=Path(os.getenv("DB_PATH", cache_dir / "memory.sqlite")),
        ollama_url=os.getenv("OLLAMA_URL", "http://localhost:11434"),
        llm_model=os.getenv("LLM_MODEL", "qwen3:8b"),
        embed_model=os.getenv("EMBED_MODEL", "nomic-embed-text"),
        openrouter_api_key=os.getenv("OPENROUTER_API_KEY") or None,
    )
