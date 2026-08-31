from __future__ import annotations

import logging

from google.auth.exceptions import TransportError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from meridian.auth.oauth_flow import run_consent_flow
from meridian.auth.token_store import EncryptedTokenStore
from meridian.common.config import Config, ensure_dirs, load_config
from meridian.common.logging import get_logger, log_operation
from meridian.common.retry import retry_with_backoff


def get_credentials(
    config: Config | None = None,
    *,
    interactive: bool = True,
    force_refresh: bool = False,
) -> Credentials:
    """Returns valid credentials, refreshing or running consent as needed.

    - force_refresh, or an expired credential with a refresh_token: refresh.
    - a still-valid stored credential: returned as-is, no network call.
    - nothing usable stored: runs the interactive consent flow (unless
      interactive=False, in which case it raises).
    """
    config = config or load_config()
    ensure_dirs(config)
    logger = get_logger("meridian.auth", log_dir=config.log_dir)
    store = EncryptedTokenStore(config.auth_dir)

    with log_operation(logger, "auth.get_credentials"):
        creds = store.load()

        if creds is not None and force_refresh and creds.refresh_token:
            return _refresh_and_save(creds, store, logger)

        if creds is not None and creds.valid:
            return creds

        if creds is not None and creds.expired and creds.refresh_token:
            return _refresh_and_save(creds, store, logger)

        if not interactive:
            raise RuntimeError(
                "No valid stored credentials and interactive consent is disabled"
            )

        creds = run_consent_flow(config.google_client_id, config.google_client_secret)
        store.save(creds)
        return creds


def _refresh_and_save(
    creds: Credentials, store: EncryptedTokenStore, logger: logging.Logger
) -> Credentials:
    def do_refresh() -> Credentials:
        creds.refresh(Request())
        return creds

    refreshed = retry_with_backoff(
        do_refresh,
        exceptions=(TransportError,),
        max_attempts=5,
        logger=logger,
        operation="auth.refresh_token",
    )
    store.save(refreshed)
    return refreshed
