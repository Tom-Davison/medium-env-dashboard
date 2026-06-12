"""OAuth2 token management for the Copernicus Data Space Ecosystem.

The Sentinel Hub APIs on CDSE authenticate with client credentials, not
your account password. Create a client (it's free) under
https://shapps.dataspace.copernicus.eu/dashboard/ -> User settings ->
OAuth clients, then put the id and secret in .env.
"""

import os
import time

import requests

from config import TOKEN_URL


class TokenManager:
    """Fetches a bearer token and refreshes it shortly before expiry."""

    def __init__(self, client_id: str, client_secret: str):
        self._client_id = client_id
        self._client_secret = client_secret
        self._token: str | None = None
        self._expires_at: float = 0.0

    def get_token(self) -> str:
        if not self._token or time.time() >= self._expires_at - 60:
            self._fetch()
        return self._token

    def _fetch(self):
        resp = requests.post(
            TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": self._client_id,
                "client_secret": self._client_secret,
            },
            timeout=30,
        )
        if resp.status_code != 200:
            raise RuntimeError(
                f"Token request failed ({resp.status_code}): {resp.text[:300]}"
            )
        body = resp.json()
        self._token = body["access_token"]
        self._expires_at = time.time() + body.get("expires_in", 600)

    @property
    def headers(self) -> dict:
        return {"Authorization": f"Bearer {self.get_token()}"}


def get_token_manager() -> TokenManager:
    """Build a TokenManager from environment variables."""
    client_id = os.environ.get("SH_CLIENT_ID")
    client_secret = os.environ.get("SH_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise EnvironmentError(
            "SH_CLIENT_ID and SH_CLIENT_SECRET must be set in your .env file. "
            "The README explains how to create them (takes two minutes)."
        )
    return TokenManager(client_id, client_secret)
