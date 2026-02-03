#!/usr/bin/env python3
"""
Send code review results to Slack with interactive buttons.

Usage:
    python slack_notify.py --review review_result.json
"""

import argparse
import json
import os
import sys
from typing import Dict, Any, List

try:
    import requests
except ImportError:
    print("ERROR: requests package not installed. Run: pip install requests")
    sys.exit(1)


def load_review_result(filepath: str) -> Dict[str, Any]:
    """Load review result JSON."""
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def build_slack_blocks(review: Dict[str, Any], pr_url: str = "") -> List[Dict[str, Any]]:
    """
    Build Slack Block Kit message with interactive buttons.
    
    https://api.slack.com/reference/block-kit
    """
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "🤖 Code Review Complete",
                "emoji": True
            }
        },
        {
            "type": "divider"
        },
        {
            "type": "section",
            "fields": [
                {
                    "type": "mrkdwn",
                    "text": f"*Files Reviewed:*\n{review['files_reviewed']}"
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Review Time:*\n{review['review_time_seconds']:.1f}s"
                },
                {
                    "type": "mrkdwn",
                    "text": f"*⚠️ Issues:*\n{len(review['issues'])}"
                },
                {
                    "type": "mrkdwn",
                    "text": f"*💡 Suggestions:*\n{len(review['suggestions'])}"
                }
            ]
        }
    ]
    
    # Add top issues (max 3)
    if review['issues']:
        issues_text = ""
        for i, issue in enumerate(review['issues'][:3], 1):
            issues_text += f"\n*{i}. {issue['file']}:{issue['line']}*\n"
            issues_text += f"  {issue['severity'].upper()}: {issue['message']}\n"
            if issue.get('suggestion'):
                issues_text += f"  _💡 {issue['suggestion']}_\n"
        
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*🔍 Top Issues:*{issues_text}"
            }
        })
    
    # Add suggestions (max 2)
    if review['suggestions']:
        suggestions_text = ""
        for i, sugg in enumerate(review['suggestions'][:2], 1):
            suggestions_text += f"\n*{i}. {sugg['file']}:{sugg['line']}*\n"
            suggestions_text += f"  {sugg['message']}\n"
        
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*✨ Suggestions:*{suggestions_text}"
            }
        })
    
    blocks.append({"type": "divider"})
    
    # Summary
    blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": f"*Summary:*\n{review['summary']}"
        }
    })
    
    # PR link if available
    if pr_url:
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"🔗 <{pr_url}|View Pull Request>"
            }
        })
    
    # Interactive buttons
    blocks.append({
        "type": "actions",
        "elements": [
            {
                "type": "button",
                "text": {
                    "type": "plain_text",
                    "text": "✅ Approve",
                    "emoji": True
                },
                "style": "primary",
                "value": "approve",
                "action_id": "review_approve"
            },
            {
                "type": "button",
                "text": {
                    "type": "plain_text",
                    "text": "🔄 Request Changes",
                    "emoji": True
                },
                "value": "request_changes",
                "action_id": "review_request_changes"
            },
            {
                "type": "button",
                "text": {
                    "type": "plain_text",
                    "text": "❌ Reject",
                    "emoji": True
                },
                "style": "danger",
                "value": "reject",
                "action_id": "review_reject"
            }
        ]
    })
    
    return blocks


def send_to_slack(webhook_url: str, blocks: List[Dict[str, Any]]) -> bool:
    """Send message to Slack via Webhook."""
    payload = {
        "blocks": blocks,
        "text": "Code Review Complete"  # Fallback text
    }
    
    try:
        response = requests.post(
            webhook_url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        response.raise_for_status()
        print(f"✅ Slack notification sent successfully")
        return True
    except requests.exceptions.RequestException as e:
        print(f"❌ Slack notification failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Send code review to Slack")
    parser.add_argument("--review", required=True, help="Path to review_result.json")
    parser.add_argument("--pr-url", default="", help="Pull request URL")
    
    args = parser.parse_args()
    
    # Get webhook URL from environment
    webhook_url = os.getenv("SLACK_WEBHOOK_URL")
    if not webhook_url:
        print("ERROR: SLACK_WEBHOOK_URL environment variable not set")
        sys.exit(1)
    
    # Load review result
    review = load_review_result(args.review)
    
    # Build Slack message
    blocks = build_slack_blocks(review, args.pr_url)
    
    # Send to Slack
    success = send_to_slack(webhook_url, blocks)
    
    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()