from cryptography.fernet import Fernet

from meridian.security.field_encryption import decrypt_field, derive_or_load_key, encrypt_field


def test_encrypt_decrypt_round_trip():
    key = Fernet.generate_key()

    ciphertext = encrypt_field("hello world", key)
    plaintext = decrypt_field(ciphertext, key)

    assert plaintext == "hello world"


def test_encrypt_field_output_is_not_the_plaintext():
    key = Fernet.generate_key()

    ciphertext = encrypt_field("secret content", key)

    assert "secret content" not in ciphertext


def test_derive_or_load_key_generates_a_random_key_with_no_passphrase(tmp_path, monkeypatch):
    monkeypatch.delenv("MERIDIAN_ENCRYPTION_PASSPHRASE", raising=False)

    key = derive_or_load_key(tmp_path)

    assert (tmp_path / "key.bin").exists()
    assert not (tmp_path / "key.bin.salt").exists()
    # a valid fernet key can actually be used
    Fernet(key)


def test_derive_or_load_key_returns_the_same_key_on_subsequent_calls(tmp_path, monkeypatch):
    monkeypatch.delenv("MERIDIAN_ENCRYPTION_PASSPHRASE", raising=False)

    first = derive_or_load_key(tmp_path)
    second = derive_or_load_key(tmp_path)

    assert first == second


def test_derive_or_load_key_with_passphrase_creates_a_salt_file(tmp_path, monkeypatch):
    monkeypatch.setenv("MERIDIAN_ENCRYPTION_PASSPHRASE", "correct horse battery staple")

    key = derive_or_load_key(tmp_path)

    assert (tmp_path / "key.bin").exists()
    assert (tmp_path / "key.bin.salt").exists()
    Fernet(key)


def test_derive_or_load_key_different_passphrases_produce_different_keys(tmp_path, monkeypatch):
    monkeypatch.setenv("MERIDIAN_ENCRYPTION_PASSPHRASE", "passphrase-one")
    key_one = derive_or_load_key(tmp_path / "a")

    monkeypatch.setenv("MERIDIAN_ENCRYPTION_PASSPHRASE", "passphrase-two")
    key_two = derive_or_load_key(tmp_path / "b")

    assert key_one != key_two


def test_derive_or_load_key_uses_a_custom_filename(tmp_path, monkeypatch):
    monkeypatch.delenv("MERIDIAN_ENCRYPTION_PASSPHRASE", raising=False)

    derive_or_load_key(tmp_path, key_filename="other.bin")

    assert (tmp_path / "other.bin").exists()
    assert not (tmp_path / "key.bin").exists()


def test_key_generated_via_old_raw_fernet_logic_is_read_back_unchanged(tmp_path, monkeypatch):
    """simulates a pre-Phase-11 key.bin written by the old raw
    Fernet.generate_key() + chmod logic directly, with no knowledge of
    derive_or_load_key at all - confirms it's read back byte-for-byte,
    the backward-compatibility guarantee token_store.py's refactor relies on."""
    import os

    monkeypatch.delenv("MERIDIAN_ENCRYPTION_PASSPHRASE", raising=False)
    tmp_path.mkdir(parents=True, exist_ok=True)
    pre_existing_key = Fernet.generate_key()
    key_path = tmp_path / "key.bin"
    key_path.write_bytes(pre_existing_key)
    os.chmod(key_path, 0o600)

    loaded = derive_or_load_key(tmp_path)

    assert loaded == pre_existing_key
