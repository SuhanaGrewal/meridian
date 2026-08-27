from __future__ import annotations

import json
import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from google.oauth2.credentials import Credentials


class EncryptedTokenStore:
    """Stores OAuth credentials at rest, encrypted with a locally-generated key."""

    def __init__(self, auth_dir: Path):
        self._auth_dir = auth_dir
        self._key_path = auth_dir / "key.bin"
        self._token_path = auth_dir / "token.enc"

    def save(self, credentials: Credentials) -> None:
        key = self._get_or_create_key()
        encrypted = Fernet(key).encrypt(credentials.to_json().encode("utf-8"))
        self._write_atomic(self._token_path, encrypted)

    def load(self) -> Credentials | None:
        if not self._token_path.exists() or not self._key_path.exists():
            return None

        key = self._key_path.read_bytes()
        try:
            decrypted = Fernet(key).decrypt(self._token_path.read_bytes())
        except InvalidToken:
            return None

        return Credentials.from_authorized_user_info(json.loads(decrypted))

    def clear(self) -> None:
        self._token_path.unlink(missing_ok=True)

    def _get_or_create_key(self) -> bytes:
        self._auth_dir.mkdir(parents=True, exist_ok=True)
        if self._key_path.exists():
            return self._key_path.read_bytes()

        key = Fernet.generate_key()
        self._write_atomic(self._key_path, key)
        return key

    @staticmethod
    def _write_atomic(path: Path, data: bytes) -> None:
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        tmp_path.write_bytes(data)
        os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, path)
