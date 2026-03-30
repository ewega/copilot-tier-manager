"""Main sync orchestrator — ties GitHub, Graph, and Tier Engine together."""
import argparse
import json
import logging
import os
from typing import Optional

import yaml

from .github_client import GitHubClient
from .graph_client import GraphClient
from .models import UserChange, SyncResult
from .notifications import format_summary, send_teams_webhook
from .tier_engine import TierEngine, TierConfig

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def run_sync(
    enterprise: str,
    config_path: str = "config/tiers.yaml",
    dry_run: bool = True,
    org: Optional[str] = None,
) -> SyncResult:
    """Run the tier sync process."""
    logger.info(f"Starting tier sync for enterprise '{enterprise}' (dry_run={dry_run})")

    gh = GitHubClient(enterprise=enterprise)
    graph = GraphClient()
    engine = TierEngine(config_path=config_path)

    # Load EMU config once up front (not per-user)
    with open(config_path, encoding="utf-8") as f:
        full_config = yaml.safe_load(f)
    emu_suffix = full_config.get("emu_suffix", f"_{enterprise}")
    emu_domain = full_config.get("emu_domain", "")
    emu_separator = full_config.get("emu_username_separator", "-")

    result = SyncResult()

    # 1. Get all Copilot seat holders
    logger.info("Fetching Copilot seat holders...")
    seats = gh.list_copilot_seats(org=org)
    result.total_users = len(seats)
    logger.info(f"Found {len(seats)} seat holders")

    # 2. Build current group membership map: user_id → tier_name
    logger.info("Fetching current Entra ID group memberships...")
    current_memberships: dict[str, str] = {}  # entra_user_id → tier_name
    for tier in engine.tiers:
        if not tier.entra_group_id:
            continue
        members = graph.list_group_members(tier.entra_group_id)
        for member in members:
            current_memberships[member["id"]] = tier.name

    # 3. For each seat holder, classify and compare
    for seat in seats:
        username = seat.get("assignee", {}).get("login", "unknown")
        try:
            # Get PRU usage
            pru_usage = gh.get_pru_usage(user=username)
            logger.info(f"  {username}: {pru_usage:.0f} PRUs")

            # Classify
            target_tier = engine.classify(pru_usage)

            # Resolve Entra ID user (EMU pattern: username_enterprise)
            upn = _resolve_upn(username, emu_suffix=emu_suffix, emu_domain=emu_domain, emu_separator=emu_separator)
            entra_user = graph.get_user_by_upn(upn) if upn else None
            if not entra_user:
                result.errors.append(f"Could not resolve Entra ID user for {username} (tried UPN: {upn})")
                continue
            entra_user_id = entra_user["id"]

            # Determine current tier
            current_tier_name = current_memberships.get(entra_user_id)

            # Compare
            if current_tier_name == target_tier.name:
                result.unchanged += 1
                continue

            # Determine action
            current_tier = engine.get_tier_by_name(current_tier_name) if current_tier_name else None
            if current_tier is None:
                action = "new"
            elif target_tier.min_pru > current_tier.min_pru:
                action = "moved_up"
            else:
                action = "moved_down"

            change = UserChange(
                username=username,
                entra_user_id=entra_user_id,
                pru_usage=pru_usage,
                old_tier=current_tier_name,
                new_tier=target_tier.name,
                action=action,
            )

            if not dry_run:
                # Add to new group FIRST (prevent zero-group state)
                if target_tier.entra_group_id:
                    graph.add_group_member(target_tier.entra_group_id, entra_user_id)
                # Then remove from old group
                if current_tier and current_tier.entra_group_id:
                    graph.remove_group_member(current_tier.entra_group_id, entra_user_id)
                logger.info(f"  ✅ {username}: {current_tier_name} → {target_tier.name}")
            else:
                logger.info(f"  [DRY RUN] {username}: {current_tier_name} → {target_tier.name}")

            if action == "new":
                result.new_users.append(change)
            elif action == "moved_up":
                result.moved_up.append(change)
            else:
                result.moved_down.append(change)

        except Exception as e:
            result.errors.append(f"Error processing {username}: {e}")
            logger.error(f"  ❌ {username}: {e}")

    # 4. Summary
    logger.info("=" * 60)
    logger.info(f"Sync complete. Total: {result.total_users}")
    logger.info(f"  Moved up:    {len(result.moved_up)}")
    logger.info(f"  Moved down:  {len(result.moved_down)}")
    logger.info(f"  New users:   {len(result.new_users)}")
    logger.info(f"  Unchanged:   {result.unchanged}")
    logger.info(f"  Errors:      {len(result.errors)}")
    if dry_run:
        logger.info("  ⚠️  DRY RUN — no changes were made")

    return result


def _resolve_upn(github_username: str, emu_suffix: str, emu_domain: str, emu_separator: str = "-") -> Optional[str]:
    """Resolve GitHub EMU username to Entra ID UPN.

    EMU usernames follow the pattern: {shortname}_{emu_suffix}
    The UPN is: {shortname_with_dots}@{domain}
    """
    if not emu_domain:
        logger.warning(f"No emu_domain configured — cannot resolve UPN for {github_username}")
        return None

    # Strip the EMU suffix
    if github_username.endswith(emu_suffix):
        shortname = github_username[: -len(emu_suffix)]
    else:
        shortname = github_username

    # Replace separator (GitHub uses - but Entra UPN uses .)
    upn_local = shortname.replace(emu_separator, ".")
    return f"{upn_local}@{emu_domain}"


def main():
    parser = argparse.ArgumentParser(description="Copilot PRU Tier Sync")
    parser.add_argument("--enterprise", required=True, help="GitHub Enterprise slug")
    parser.add_argument("--org", help="Scope to a specific org (optional)")
    parser.add_argument("--config", default="config/tiers.yaml", help="Path to tiers config")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Preview changes without applying (default: True)")
    parser.add_argument("--execute", action="store_true", help="Apply changes (overrides --dry-run)")
    args = parser.parse_args()

    dry_run = not args.execute
    result = run_sync(
        enterprise=args.enterprise,
        config_path=args.config,
        dry_run=dry_run,
        org=args.org,
    )

    # Send notification summary
    summary = format_summary(result)
    print(summary)

    webhook_url = os.environ.get("TEAMS_WEBHOOK_URL", "")
    if webhook_url:
        send_teams_webhook(summary, webhook_url)

    if result.errors:
        exit(1)


if __name__ == "__main__":
    main()
