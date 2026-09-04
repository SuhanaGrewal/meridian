from unittest.mock import MagicMock

import pytest

from meridian.auth import credentials as credentials_module
from meridian.common.config import Config


def _make_config(tmp_path) -> Config:
    return Config(
        data_dir=tmp_path,
        log_dir=tmp_path / "logs",
        notes_folder=None,
        google_client_id="client-id",
        google_client_secret="client-secret",
        llm_api_key="",
        llm_model="claude-haiku-4-5",
    )


def test_get_credentials_runs_consent_flow_when_store_is_empty(tmp_path, monkeypatch):
    config = _make_config(tmp_path)

    mock_store = MagicMock()
    mock_store.load.return_value = None
    monkeypatch.setattr(credentials_module, "EncryptedTokenStore", lambda auth_dir: mock_store)

    fake_creds = MagicMock()
    run_consent_flow = MagicMock(return_value=fake_creds)
    monkeypatch.setattr(credentials_module, "run_consent_flow", run_consent_flow)

    result = credentials_module.get_credentials(config=config)

    run_consent_flow.assert_called_once_with("client-id", "client-secret")
    mock_store.save.assert_called_once_with(fake_creds)
    assert result is fake_creds


def test_get_credentials_returns_valid_stored_credentials_without_refresh_or_consent(
    tmp_path, monkeypatch
):
    config = _make_config(tmp_path)

    valid_creds = MagicMock(valid=True, expired=False)
    mock_store = MagicMock()
    mock_store.load.return_value = valid_creds
    monkeypatch.setattr(credentials_module, "EncryptedTokenStore", lambda auth_dir: mock_store)

    run_consent_flow = MagicMock()
    monkeypatch.setattr(credentials_module, "run_consent_flow", run_consent_flow)

    result = credentials_module.get_credentials(config=config)

    run_consent_flow.assert_not_called()
    mock_store.save.assert_not_called()
    assert result is valid_creds


def test_get_credentials_refreshes_expired_credentials_with_refresh_token(tmp_path, monkeypatch):
    config = _make_config(tmp_path)

    expired_creds = MagicMock(valid=False, expired=True, refresh_token="refresh-token")
    mock_store = MagicMock()
    mock_store.load.return_value = expired_creds
    monkeypatch.setattr(credentials_module, "EncryptedTokenStore", lambda auth_dir: mock_store)

    run_consent_flow = MagicMock()
    monkeypatch.setattr(credentials_module, "run_consent_flow", run_consent_flow)

    result = credentials_module.get_credentials(config=config)

    expired_creds.refresh.assert_called_once()
    mock_store.save.assert_called_once_with(expired_creds)
    run_consent_flow.assert_not_called()
    assert result is expired_creds


def test_get_credentials_raises_when_noninteractive_and_no_credentials(tmp_path, monkeypatch):
    config = _make_config(tmp_path)

    mock_store = MagicMock()
    mock_store.load.return_value = None
    monkeypatch.setattr(credentials_module, "EncryptedTokenStore", lambda auth_dir: mock_store)

    with pytest.raises(RuntimeError):
        credentials_module.get_credentials(config=config, interactive=False)


def test_get_credentials_force_refresh_overrides_still_valid_credentials(tmp_path, monkeypatch):
    config = _make_config(tmp_path)

    valid_creds = MagicMock(valid=True, expired=False, refresh_token="refresh-token")
    mock_store = MagicMock()
    mock_store.load.return_value = valid_creds
    monkeypatch.setattr(credentials_module, "EncryptedTokenStore", lambda auth_dir: mock_store)

    result = credentials_module.get_credentials(config=config, force_refresh=True)

    valid_creds.refresh.assert_called_once()
    mock_store.save.assert_called_once_with(valid_creds)
    assert result is valid_creds
