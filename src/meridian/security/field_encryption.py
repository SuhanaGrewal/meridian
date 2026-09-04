from __future__ import annotations

import base64
import os
from pathlib import Path

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

_PBKDF2_ITERATIONS = 600_000


def _write_atomic(path: Path, data: bytes) -> None:
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_bytes(data)
    os.chmod(tmp_path, 0o600)
    os.replace(tmp_path, path)


def derive_or_load_key(
    key_dir: Path,
    *,
    key_filename: str = "key.bin",
    passphrase_env_var: str = "MERIDIAN_ENCRYPTION_PASSPHRASE",
) -> bytes:
    """returns a Fernet key, generating one on first use.

    if a key file already exists, it's read and returned byte-for-byte -
    zero behavior change for any existing installation. otherwise, if
    `passphrase_env_var` is set, the key is derived from it via PBKDF2
    (with a randomly generated, persisted salt) so the key isn't stored
    on disk at all - only the salt is. if no passphrase is set, falls
    back to exactly the prior behavior of a randomly generated key stored
    on disk, so zero-config users see no change."""
    key_dir.mkdir(parents=True, exist_ok=True)
    key_path = key_dir / key_filename
    if key_path.exists():
        return key_path.read_bytes()

    passphrase = os.environ.get(passphrase_env_var, "")
    if passphrase:
        salt_path = key_dir / f"{key_filename}.salt"
        salt = os.urandom(16)
        _write_atomic(salt_path, salt)
        kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=_PBKDF2_ITERATIONS)
        key = base64.urlsafe_b64encode(kdf.derive(passphrase.encode("utf-8")))
        _write_atomic(key_path, key)
        return key

    key = Fernet.generate_key()
    _write_atomic(key_path, key)
    return key


def encrypt_field(value: str, key: bytes) -> str:
    return Fernet(key).encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_field(token: str, key: bytes) -> str:
    return Fernet(key).decrypt(token.encode("ascii")).decode("utf-8")
