"""
Notifications module for sync results.
Handles formatting and sending notifications via Teams and email.
"""

import json
import logging
from datetime import datetime
from typing import Optional

import requests

from .models import SyncResult, UserChange

logger = logging.getLogger(__name__)


def format_summary(result: SyncResult) -> str:
    """
    Format a SyncResult into a markdown summary for Teams/email.
    
    Args:
        result: SyncResult dataclass with sync operation details
        
    Returns:
        Formatted markdown string
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Header
    summary = f"# Copilot License Tier Sync Report\n"
    summary += f"**Date:** {timestamp}\n\n"
    
    # Summary counts table
    summary += "## Summary\n\n"
    summary += "| Metric | Count |\n"
    summary += "|--------|-------|\n"
    summary += f"| Total Users | {result.total_users} |\n"
    summary += f"| Moved Up | {len(result.moved_up)} |\n"
    summary += f"| Moved Down | {len(result.moved_down)} |\n"
    summary += f"| New Users | {len(result.new_users)} |\n"
    summary += f"| Unchanged | {result.unchanged} |\n"
    summary += f"| Errors | {len(result.errors)} |\n\n"
    
    # Users moved up
    if result.moved_up:
        summary += "## Moved Up 🎉\n\n"
        for user in result.moved_up:
            summary += f"- **{user.username}**: {user.old_tier} → {user.new_tier} "
            summary += f"({user.pru_usage} PRUs)\n"
        summary += "\n"
    
    # New users
    if result.new_users:
        summary += "## New Users ✨\n\n"
        for user in result.new_users:
            summary += f"- **{user.username}**: {user.new_tier} ({user.pru_usage} PRUs)\n"
        summary += "\n"
    
    # Users moved down
    if result.moved_down:
        summary += "## Moved Down ⬇️\n\n"
        for user in result.moved_down:
            summary += f"- **{user.username}**: {user.old_tier} → {user.new_tier} "
            summary += f"({user.pru_usage} PRUs)\n"
        summary += "\n"
    
    # Errors
    if result.errors:
        summary += "## Errors ❌\n\n"
        for error in result.errors:
            summary += f"- {error}\n"
        summary += "\n"
    
    return summary


def send_teams_webhook(summary: str, webhook_url: str) -> bool:
    """
    Send a formatted summary to Microsoft Teams via an incoming webhook.
    
    Args:
        summary: Markdown-formatted summary string
        webhook_url: Microsoft Teams incoming webhook URL
        
    Returns:
        True if successful, False otherwise
    """
    if not webhook_url or webhook_url.strip() == "":
        logger.info("Teams webhook URL is empty, skipping Teams notification")
        return True
    
    try:
        # Convert markdown to Teams Adaptive Card format
        card = {
            "@type": "MessageCard",
            "@context": "https://schema.org/extensions",
            "summary": "Copilot License Tier Sync Report",
            "themeColor": "0078D4",
            "sections": [
                {
                    "activityTitle": "Copilot License Tier Sync Report",
                    "activitySubtitle": f"Generated {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                    "text": summary,
                }
            ],
        }
        
        response = requests.post(
            webhook_url,
            json=card,
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        response.raise_for_status()
        logger.info("Successfully sent Teams notification")
        return True
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to send Teams notification: {e}")
        return False


def send_email_summary(summary: str, recipients: list[str]) -> bool:
    """
    Send a formatted summary via email.
    
    Args:
        summary: Markdown-formatted summary string
        recipients: List of email addresses
        
    Returns:
        True if successful, False otherwise
    """
    logger.info("Email sending not implemented")
    return False
