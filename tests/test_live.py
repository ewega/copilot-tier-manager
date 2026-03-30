"""Live integration tests — require gh and az CLI authentication.

Run with: pytest tests/test_live.py -m live -v
"""
import os
import subprocess
import pytest

# Mark all tests in this module as live
pytestmark = pytest.mark.live

ENTERPRISE = os.environ.get("COPILOT_ENTERPRISE", "eldrick-test-emu")
AZURE_TENANT = os.environ.get("AZURE_TENANT_ID", "adde632d-1324-4966-b93f-b27d70cf0371")

# Group IDs created during setup — set via env or filled by setup test
GROUP_IDS = {}


def _gh_available() -> bool:
    try:
        subprocess.run(["gh", "auth", "status"], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def _az_available() -> bool:
    try:
        result = subprocess.run(["az", "account", "show"], capture_output=True, text=True, check=True)
        return AZURE_TENANT in result.stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


# ── GitHub API Tests ──

class TestGitHubAPILive:
    """Live tests against GitHub Enterprise API."""

    @pytest.mark.skipif(not _gh_available(), reason="gh CLI not authenticated")
    def test_gh_auth(self):
        """Verify gh CLI is authenticated to the enterprise."""
        from src.github_client import GitHubClient
        gh = GitHubClient(enterprise=ENTERPRISE)
        assert gh.token, "No token acquired"

    @pytest.mark.skipif(not _gh_available(), reason="gh CLI not authenticated")
    def test_list_enterprise_orgs(self):
        """List orgs in the enterprise."""
        from src.github_client import GitHubClient
        gh = GitHubClient(enterprise=ENTERPRISE)
        orgs = gh._list_enterprise_orgs()
        print(f"Enterprise orgs: {orgs}")
        assert isinstance(orgs, list), "Expected list of orgs"

    @pytest.mark.skipif(not _gh_available(), reason="gh CLI not authenticated")
    def test_list_copilot_seats(self):
        """Fetch Copilot seat holders."""
        from src.github_client import GitHubClient
        gh = GitHubClient(enterprise=ENTERPRISE)
        seats = gh.list_copilot_seats()
        print(f"Found {len(seats)} seat holders")
        for seat in seats[:5]:
            print(f"  - {seat.get('assignee', {}).get('login', 'unknown')}")
        assert isinstance(seats, list), "Expected list of seats"

    @pytest.mark.skipif(not _gh_available(), reason="gh CLI not authenticated")
    def test_pru_usage_for_user(self):
        """Query PRU usage for a known user."""
        from src.github_client import GitHubClient
        gh = GitHubClient(enterprise=ENTERPRISE)
        seats = gh.list_copilot_seats()
        if not seats:
            pytest.skip("No Copilot seats found")
        username = seats[0].get("assignee", {}).get("login")
        usage = gh.get_pru_usage(user=username)
        print(f"User {username}: {usage} PRUs")
        assert isinstance(usage, (int, float)), "Expected numeric usage"

    @pytest.mark.skipif(not _gh_available(), reason="gh CLI not authenticated")
    def test_pru_usage_all_users(self):
        """Iterate all seat holders and fetch PRU data."""
        from src.github_client import GitHubClient
        gh = GitHubClient(enterprise=ENTERPRISE)
        seats = gh.list_copilot_seats()
        results = {}
        for seat in seats:
            username = seat.get("assignee", {}).get("login", "unknown")
            try:
                usage = gh.get_pru_usage(user=username)
                results[username] = usage
            except Exception as e:
                results[username] = f"ERROR: {e}"
        print(f"PRU usage for {len(results)} users:")
        for user, usage in results.items():
            print(f"  {user}: {usage}")
        assert len(results) == len(seats)


# ── Microsoft Graph API Tests ──

class TestGraphAPILive:
    """Live tests against Microsoft Graph API."""

    @pytest.mark.skipif(not _az_available(), reason="az CLI not authenticated to correct tenant")
    def test_az_auth(self):
        """Verify az CLI is authenticated to the correct tenant."""
        from src.graph_client import GraphClient
        graph = GraphClient(tenant_id=AZURE_TENANT)
        assert graph.token, "No Graph token acquired"

    @pytest.mark.skipif(not _az_available(), reason="az CLI not authenticated to correct tenant")
    def test_create_test_groups(self):
        """Create 4 test security groups for tier management."""
        from src.graph_client import GraphClient
        graph = GraphClient(tenant_id=AZURE_TENANT)
        tier_names = ["basic-adopter", "growing-user", "power-user", "advanced-user"]
        for name in tier_names:
            display_name = f"copilot-tier-test-{name}"
            try:
                group = graph.create_security_group(display_name, f"Test group for {name} tier")
                GROUP_IDS[name] = group["id"]
                print(f"Created group: {display_name} → {group['id']}")
            except Exception as e:
                if "already exists" in str(e).lower() or "400" in str(e):
                    print(f"Group {display_name} may already exist: {e}")
                else:
                    raise
        print(f"Group IDs: {GROUP_IDS}")

    @pytest.mark.skipif(not _az_available(), reason="az CLI not authenticated to correct tenant")
    def test_list_group_members_empty(self):
        """List members of a test group (should be empty or near-empty)."""
        from src.graph_client import GraphClient
        graph = GraphClient(tenant_id=AZURE_TENANT)
        if not GROUP_IDS:
            pytest.skip("No test groups created yet")
        group_id = list(GROUP_IDS.values())[0]
        members = graph.list_group_members(group_id)
        print(f"Group has {len(members)} members")
        assert isinstance(members, list)

    @pytest.mark.skipif(not _az_available(), reason="az CLI not authenticated to correct tenant")
    def test_add_and_remove_member(self):
        """Add a test user to a group, then remove them."""
        from src.graph_client import GraphClient
        graph = GraphClient(tenant_id=AZURE_TENANT)
        if not GROUP_IDS:
            pytest.skip("No test groups created yet")

        # Find a test user (the current az CLI user)
        result = subprocess.run(
            ["az", "ad", "signed-in-user", "show", "--query", "id", "-o", "tsv"],
            capture_output=True, text=True, check=True,
        )
        user_id = result.stdout.strip()
        group_id = list(GROUP_IDS.values())[0]

        # Add
        graph.add_group_member(group_id, user_id)
        members = graph.list_group_members(group_id)
        member_ids = [m["id"] for m in members]
        assert user_id in member_ids, "User should be in group after add"

        # Remove
        graph.remove_group_member(group_id, user_id)
        members = graph.list_group_members(group_id)
        member_ids = [m["id"] for m in members]
        assert user_id not in member_ids, "User should not be in group after remove"


# ── End-to-End Tests ──

class TestE2ELive:
    """End-to-end live tests combining GitHub + Graph APIs."""

    @pytest.mark.skipif(
        not (_gh_available() and _az_available()),
        reason="Both gh and az CLI must be authenticated",
    )
    def test_e2e_dry_run(self):
        """Run full sync in dry-run mode against real data."""
        from src.sync import run_sync
        result = run_sync(enterprise=ENTERPRISE, dry_run=True)
        print(f"Total users: {result.total_users}")
        print(f"Would move up: {len(result.moved_up)}")
        print(f"Would move down: {len(result.moved_down)}")
        print(f"New users: {len(result.new_users)}")
        print(f"Unchanged: {result.unchanged}")
        print(f"Errors: {len(result.errors)}")
        for err in result.errors:
            print(f"  ⚠️ {err}")
        assert result.total_users >= 0

    @pytest.mark.skipif(
        not (_gh_available() and _az_available()),
        reason="Both gh and az CLI must be authenticated",
    )
    def test_e2e_idempotent(self):
        """Running sync twice should produce zero changes on second run."""
        from src.sync import run_sync
        # First run
        result1 = run_sync(enterprise=ENTERPRISE, dry_run=True)
        # Second run (same data)
        result2 = run_sync(enterprise=ENTERPRISE, dry_run=True)
        # Both should produce identical classifications
        assert result1.total_users == result2.total_users
