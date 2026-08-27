import stat

from google.oauth2.credentials import Credentials

from meridian.auth.token_store import EncryptedTokenStore


def _dummy_credentials() -> Credentials:
    return Credentials(
        token="super-secret-access-token",
        refresh_token="super-secret-refresh-token",
        token_uri="https://oauth2.googleapis.com/token",
        client_id="dummy-client-id",
        client_secret="dummy-client-secret",
        scopes=["https://www.googleapis.com/auth/gmail.readonly"],
    )


def test_save_then_load_round_trips_credentials(tmp_path):
    store = EncryptedTokenStore(tmp_path)
    original = _dummy_credentials()

    store.save(original)
    loaded = store.load()

    assert loaded is not None
    assert loaded.token == original.token
    assert loaded.refresh_token == original.refresh_token
    assert loaded.client_id == original.client_id
    assert loaded.scopes == original.scopes


def test_token_file_is_encrypted_not_plaintext(tmp_path):
    store = EncryptedTokenStore(tmp_path)
    store.save(_dummy_credentials())

    on_disk = (tmp_path / "token.enc").read_bytes()

    assert b"super-secret-access-token" not in on_disk
    assert b"super-secret-refresh-token" not in on_disk


def test_key_and_token_files_are_owner_only_permissions(tmp_path):
    store = EncryptedTokenStore(tmp_path)
    store.save(_dummy_credentials())

    for name in ("key.bin", "token.enc"):
        mode = stat.S_IMODE((tmp_path / name).stat().st_mode)
        assert mode == 0o600


def test_load_returns_none_when_no_token_stored(tmp_path):
    store = EncryptedTokenStore(tmp_path)

    assert store.load() is None


def test_clear_removes_token_but_load_still_safe(tmp_path):
    store = EncryptedTokenStore(tmp_path)
    store.save(_dummy_credentials())

    store.clear()

    assert store.load() is None
    assert not (tmp_path / "token.enc").exists()
