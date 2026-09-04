from pathlib import Path

from meridian.common.config import ensure_dirs, load_config


def test_load_config_maps_env_vars_to_paths(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    log_dir = tmp_path / "logs"
    notes_dir = tmp_path / "notes"

    monkeypatch.setenv("MERIDIAN_DATA_DIR", str(data_dir))
    monkeypatch.setenv("MERIDIAN_LOG_DIR", str(log_dir))
    monkeypatch.setenv("MERIDIAN_NOTES_FOLDER", str(notes_dir))
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "client-id")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("LLM_API_KEY", "llm-key")
    monkeypatch.setenv("LLM_MODEL", "claude-sonnet-5")

    config = load_config(load_env_file=False)

    assert config.data_dir == data_dir.resolve()
    assert config.log_dir == log_dir.resolve()
    assert config.notes_folder == notes_dir.resolve()
    assert config.auth_dir == data_dir.resolve() / "auth"
    assert config.ingestion_dir == data_dir.resolve() / "ingestion"
    assert config.indexing_dir == data_dir.resolve() / "indexing"
    assert config.google_client_id == "client-id"
    assert config.google_client_secret == "client-secret"
    assert config.llm_api_key == "llm-key"
    assert config.llm_model == "claude-sonnet-5"


def test_load_config_defaults_llm_model(monkeypatch):
    monkeypatch.delenv("LLM_MODEL", raising=False)

    config = load_config(load_env_file=False)

    assert config.llm_model == "claude-haiku-4-5"


def test_load_config_defaults_notes_folder_to_none(monkeypatch):
    monkeypatch.delenv("MERIDIAN_NOTES_FOLDER", raising=False)

    config = load_config(load_env_file=False)

    assert config.notes_folder is None


def test_ensure_dirs_creates_data_log_and_auth_dirs(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    log_dir = tmp_path / "logs"

    monkeypatch.setenv("MERIDIAN_DATA_DIR", str(data_dir))
    monkeypatch.setenv("MERIDIAN_LOG_DIR", str(log_dir))

    config = load_config(load_env_file=False)
    ensure_dirs(config)

    assert data_dir.is_dir()
    assert log_dir.is_dir()
    assert (data_dir / "auth").is_dir()
    assert (data_dir / "ingestion").is_dir()
    assert (data_dir / "indexing").is_dir()
