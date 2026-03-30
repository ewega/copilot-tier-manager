"""GitHub Enterprise API client for Copilot seat and PRU usage data."""
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


class GitHubClient:
    """Wraps GitHub REST API for Copilot billing and seat management."""

    def __init__(self, token: Optional[str] = None, enterprise: str = ""):
        self.enterprise = enterprise
        self.token = token or os.environ.get("GITHUB_TOKEN") or self._token_from_cli()
        self.base_url = "https://api.github.com"
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _token_from_cli(self) -> str:
        """Fall back to gh CLI auth token."""
        try:
            result = subprocess.run(
                ["gh", "auth", "token"], capture_output=True, text=True, check=True
            )
            return result.stdout.strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            raise RuntimeError("No GITHUB_TOKEN set and gh CLI not available")

    def list_copilot_seats(self, org: Optional[str] = None) -> list[dict]:
        """List all Copilot seat holders. Uses enterprise-level endpoint by default."""
        if org:
            url = f"{self.base_url}/orgs/{org}/copilot/billing/seats"
        else:
            url = f"{self.base_url}/enterprises/{self.enterprise}/copilot/billing/seats"

        all_seats = []
        page = 1
        per_page = 100
        while True:
            resp = _request_with_retry(
                requests.get,
                url, headers={**self.headers, "X-GitHub-Api-Version": "2026-03-10"},
                params={"page": page, "per_page": per_page},
            )
            resp.raise_for_status()
            data = resp.json()
            seats = data.get("seats", [])
            if not seats:
                break
            all_seats.extend(seats)
            if len(seats) < per_page:
                break  # Last page (partial results)
            page += 1
        return all_seats

    def _list_enterprise_seats(self) -> list[dict]:
        """List seats across all orgs in the enterprise via GraphQL."""
        orgs = self._list_enterprise_orgs()
        all_seats = []
        for org in orgs:
            try:
                seats = self.list_copilot_seats(org=org)
                all_seats.extend(seats)
            except requests.HTTPError as e:
                if e.response.status_code == 404:
                    continue  # Org may not have Copilot enabled
                raise
        return all_seats

    def _list_enterprise_orgs(self) -> list[str]:
        """List all orgs in the enterprise via GraphQL."""
        url = f"{self.base_url}/graphql"
        all_orgs = []
        cursor = None
        while True:
            query = """
            query($slug: String!, $cursor: String) {
                enterprise(slug: $slug) {
                    organizations(first: 100, after: $cursor) {
                        nodes { login }
                        pageInfo { hasNextPage endCursor }
                    }
                }
            }
            """
            variables = {"slug": self.enterprise, "cursor": cursor}
            resp = _request_with_retry(requests.post, url, headers=self.headers, json={"query": query, "variables": variables})
            resp.raise_for_status()
            data = resp.json()
            if "errors" in data:
                raise RuntimeError(f"GraphQL errors: {data['errors']}")
            orgs_data = data["data"]["enterprise"]["organizations"]
            all_orgs.extend([o["login"] for o in orgs_data["nodes"]])
            if not orgs_data["pageInfo"]["hasNextPage"]:
                break
            cursor = orgs_data["pageInfo"]["endCursor"]
        return all_orgs

    def get_pru_usage(self, user: str) -> float:
        """Get total premium request usage for a user in the current billing period."""
        url = f"{self.base_url}/enterprises/{self.enterprise}/settings/billing/premium_request/usage"
        resp = _request_with_retry(requests.get, url, headers=self.headers, params={"user": user})
        if resp.status_code == 404:
            return 0.0
        resp.raise_for_status()
        data = resp.json()
        usage_items = data.get("usageItems", [])
        # Sum gross amounts and convert to PRU count
        total = sum(item.get("grossAmount", 0) for item in usage_items)
        return total

    def get_pru_usage_v2(self, user: str, month: Optional[int] = None, year: Optional[int] = None) -> float:
        """Alternative endpoint for premium request usage."""
        url = f"{self.base_url}/enterprises/{self.enterprise}/copilot/billing/premium-requests"
        params = {"user": user}
        if month:
            params["month"] = month
        if year:
            params["year"] = year
        resp = _request_with_retry(requests.get, url, headers=self.headers, params=params)
        if resp.status_code == 404:
            return 0.0
        resp.raise_for_status()
        data = resp.json()
        return data.get("total_premium_requests", 0.0)
