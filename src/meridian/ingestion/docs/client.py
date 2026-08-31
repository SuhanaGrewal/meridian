from __future__ import annotations

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import Resource, build

from meridian.auth.credentials import get_credentials
from meridian.common.config import Config


def build_drive_service(
    config: Config | None = None, *, credentials: Credentials | None = None
) -> Resource:
    credentials = credentials or get_credentials(config=config)
    return build("drive", "v3", credentials=credentials, cache_discovery=False)


def build_docs_service(
    config: Config | None = None, *, credentials: Credentials | None = None
) -> Resource:
    credentials = credentials or get_credentials(config=config)
    return build("docs", "v1", credentials=credentials, cache_discovery=False)
