"""Microsoft Graph API client for Entra ID group management."""
import os
import subprocess
import json
import time
import logging
import requests
from typing import Optional

logger = logging.getLogger(__name__)


def _request_with_retry(method, url, max_retries=5, **kwargs):
    """Make HTTP request with exponential backoff retry on rate limits."""
    for attempt in range(max_retries + 1):
        resp = method(url, **kwargs)
        if resp.status_code in (429, 503):
            if attempt == max_retries:
                resp.raise_for_status()
            retry_after = int(resp.headers.get("Retry-After", min(2 ** attempt, 60)))
            logger.warning(
                f"Rate limited ({resp.status_code}), retrying in {retry_after}s "
                f"(attempt {attempt + 1}/{max_retries})"
            )
            time.sleep(retry_after)
            continue
        return resp
    return resp

import msal


class GraphClient:
    """Wraps Microsoft Graph API for Entra ID security group management."""

    def __init__(
        self,
        tenant_id: Optional[str] = None,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
    ):
        self.tenant_id = tenant_id or os.environ.get("AZURE_TENANT_ID", "")
        self.client_id = client_id or os.environ.get("AZURE_CLIENT_ID", "")
        self.client_secret = client_secret or os.environ.get("AZURE_CLIENT_SECRET", "")
        self.base_url = "https://graph.microsoft.com/v1.0"
        self._msal_app: Optional[msal.ConfidentialClientApplication] = None
        self._cli_token: Optional[str] = None

    @property
    def token(self) -> str:
        if self.client_id and self.client_secret:
            return self._acquire_token_sp()
        if self._cli_token:
            return self._cli_token
        self._cli_token = self._token_from_cli()
        return self._cli_token

    @property
    def headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    def _acquire_token_sp(self) -> str:
        """Acquire token via service principal (for CI/CD).

        MSAL internally caches and refreshes tokens, so calling this
        repeatedly is cheap and avoids using expired tokens.
        """
        if not self._msal_app:
            self._msal_app = msal.ConfidentialClientApplication(
                self.client_id,
                authority=f"https://login.microsoftonline.com/{self.tenant_id}",
                client_credential=self.client_secret,
            )
        result = self._msal_app.acquire_token_for_client(
            scopes=["https://graph.microsoft.com/.default"]
        )
        if "access_token" not in result:
            raise RuntimeError(f"Failed to acquire Graph token: {result.get('error_description', 'Unknown error')}")
        return result["access_token"]

    def _token_from_cli(self) -> str:
        """Fall back to az CLI token for local development."""
        try:
            result = subprocess.run(
                ["az", "account", "get-access-token", "--resource", "https://graph.microsoft.com", "--query", "accessToken", "-o", "tsv"],
                capture_output=True, text=True, check=True,
            )
            return result.stdout.strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            raise RuntimeError("No Azure SP credentials set and az CLI not available")

    def list_group_members(self, group_id: str) -> list[dict]:
        """List all members of an Entra ID security group."""
        url = f"{self.base_url}/groups/{group_id}/members"
        all_members = []
        while url:
            resp = _request_with_retry(requests.get, url, headers=self.headers)
            resp.raise_for_status()
            data = resp.json()
            all_members.extend(data.get("value", []))
            url = data.get("@odata.nextLink")
        return all_members

    def add_group_member(self, group_id: str, user_id: str) -> None:
        """Add a user to an Entra ID security group."""
        url = f"{self.base_url}/groups/{group_id}/members/$ref"
        body = {"@odata.id": f"{self.base_url}/directoryObjects/{user_id}"}
        resp = _request_with_retry(requests.post, url, headers=self.headers, json=body)
        if resp.status_code == 400 and "already exist" in resp.text.lower():
            return  # User already in group
        resp.raise_for_status()

    def remove_group_member(self, group_id: str, user_id: str) -> None:
        """Remove a user from an Entra ID security group."""
        url = f"{self.base_url}/groups/{group_id}/members/{user_id}/$ref"
        resp = _request_with_retry(requests.delete, url, headers=self.headers)
        if resp.status_code == 404:
            return  # User not in group
        resp.raise_for_status()

    def get_user_by_upn(self, upn: str) -> Optional[dict]:
        """Look up an Entra ID user by UPN."""
        url = f"{self.base_url}/users/{upn}"
        resp = _request_with_retry(requests.get, url, headers=self.headers)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()

    def create_security_group(self, display_name: str, description: str = "") -> dict:
        """Create an Entra ID security group (for testing setup)."""
        url = f"{self.base_url}/groups"
        body = {
            "displayName": display_name,
            "description": description or f"Copilot tier group: {display_name}",
            "mailEnabled": False,
            "mailNickname": display_name.replace(" ", "-").lower(),
            "securityEnabled": True,
        }
        resp = _request_with_retry(requests.post, url, headers=self.headers, json=body)
        resp.raise_for_status()
        return resp.json()
