from __future__ import annotations

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from meridian.auth.scopes import SCOPES

AUTH_URI = "https://accounts.google.com/o/oauth2/auth"
TOKEN_URI = "https://oauth2.googleapis.com/token"


def build_flow(client_id: str, client_secret: str) -> InstalledAppFlow:
    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": AUTH_URI,
            "token_uri": TOKEN_URI,
            "redirect_uris": ["http://localhost"],
        }
    }
    return InstalledAppFlow.from_client_config(client_config, scopes=SCOPES)


def run_consent_flow(client_id: str, client_secret: str) -> Credentials:
    """Runs the interactive browser consent flow for all scopes at once.

    access_type="offline" + prompt="consent" are required for Google to
    reliably return a refresh_token, not just a short-lived access_token.
    """
    flow = build_flow(client_id, client_secret)
    return flow.run_local_server(port=0, access_type="offline", prompt="consent")
