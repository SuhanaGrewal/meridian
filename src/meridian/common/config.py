from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    data_dir: Path
    log_dir: Path
    notes_folder: Path | None
    google_client_id: str
    google_client_secret: str
    llm_api_key: str
    llm_model: str

    @property
    def auth_dir(self) -> Path:
        return self.data_dir / "auth"

    @property
    def ingestion_dir(self) -> Path:
        return self.data_dir / "ingestion"

    @property
    def indexing_dir(self) -> Path:
        return self.data_dir / "indexing"

    @property
    def entity_graph_dir(self) -> Path:
        return self.data_dir / "entity_graph"


def load_config(*, load_env_file=True) -> Config:
    if load_env_file:
        load_dotenv()

    notes_folder = os.environ.get("MERIDIAN_NOTES_FOLDER", "").strip()

    return Config(
        data_dir=Path(os.environ.get("MERIDIAN_DATA_DIR", "./data")).expanduser().resolve(),
        log_dir=Path(os.environ.get("MERIDIAN_LOG_DIR", "./logs")).expanduser().resolve(),
        notes_folder=Path(notes_folder).expanduser().resolve() if notes_folder else None,
        google_client_id=os.environ.get("GOOGLE_OAUTH_CLIENT_ID", ""),
        google_client_secret=os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", ""),
        llm_api_key=os.environ.get("LLM_API_KEY", ""),
        llm_model=os.environ.get("LLM_MODEL", "claude-haiku-4-5"),
    )


def ensure_dirs(config: Config) -> None:
    config.data_dir.mkdir(parents=True, exist_ok=True)
    config.log_dir.mkdir(parents=True, exist_ok=True)
    config.auth_dir.mkdir(parents=True, exist_ok=True)
    config.ingestion_dir.mkdir(parents=True, exist_ok=True)
    config.indexing_dir.mkdir(parents=True, exist_ok=True)
    config.entity_graph_dir.mkdir(parents=True, exist_ok=True)
