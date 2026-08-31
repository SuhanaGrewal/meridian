from unittest.mock import MagicMock

from meridian.ingestion.gmail import client as client_module


def test_build_gmail_service_uses_get_credentials_when_none_injected(monkeypatch):
    fake_creds = MagicMock()
    get_credentials = MagicMock(return_value=fake_creds)
    monkeypatch.setattr(client_module, "get_credentials", get_credentials)

    fake_service = MagicMock()
    build = MagicMock(return_value=fake_service)
    monkeypatch.setattr(client_module, "build", build)

    config = MagicMock()
    result = client_module.build_gmail_service(config=config)

    get_credentials.assert_called_once_with(config=config)
    build.assert_called_once_with("gmail", "v1", credentials=fake_creds, cache_discovery=False)
    assert result is fake_service


def test_build_gmail_service_uses_injected_credentials_as_is(monkeypatch):
    get_credentials = MagicMock()
    monkeypatch.setattr(client_module, "get_credentials", get_credentials)

    fake_service = MagicMock()
    build = MagicMock(return_value=fake_service)
    monkeypatch.setattr(client_module, "build", build)

    injected_creds = MagicMock()
    result = client_module.build_gmail_service(credentials=injected_creds)

    get_credentials.assert_not_called()
    build.assert_called_once_with("gmail", "v1", credentials=injected_creds, cache_discovery=False)
    assert result is fake_service
