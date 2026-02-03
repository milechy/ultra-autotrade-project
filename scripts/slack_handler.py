#!/usr/bin/env python3
"""
Slack interaction handler - receives button clicks and triggers actions.

This Flask app should be deployed separately (e.g., on Hetzner staging server).

Usage:
    export SLACK_SIGNING_SECRET=xxxxx
    export GITHUB_TOKEN=ghp_xxxxx
    python slack_handler.py
"""

import hashlib
import hmac
import json
import os
import time
from typing import Dict, Any

from flask import Flask, request, jsonify
import requests


app = Flask(__name__)


# Configuration
SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET", "")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_REPO = os.getenv("GITHUB_REPO", "ultra-autotrade/ultra-autotrade")  # owner/repo


def verify_slack_request(request_data: bytes, timestamp: str, signature: str) -> bool:
    """
    Verify that request came from Slack.
    https://api.slack.com/authentication/verifying-requests-from-slack
    """
    if not SLACK_SIGNING_SECRET:
        return True  # Skip verification if secret not set (dev only)
    
    # Prevent replay attacks
    if abs(time.time() - int(timestamp)) > 60 * 5:
        return False
    
    # Compute expected signature
    sig_basestring = f"v0:{timestamp}:".encode() + request_data
    expected_signature = "v0=" + hmac.new(
        SLACK_SIGNING_SECRET.encode(),
        sig_basestring,
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(expected_signature, signature)


def trigger_github_action(action: str, pr_number: int, review_data: Dict[str, Any]) -> bool:
    """
    Trigger GitHub Action based on Slack button click.
    
    Actions:
    - approve: Approve PR and merge
    - request_changes: Add comment requesting changes
    - reject: Close PR with rejection message
    """
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    
    owner, repo = GITHUB_REPO.split("/")
    base_url = f"https://api.github.com/repos/{owner}/{repo}"
    
    try:
        if action == "approve":
            # Approve PR
            url = f"{base_url}/pulls/{pr_number}/reviews"
            payload = {
                "event": "APPROVE",
                "body": "✅ Approved via Slack automated review"
            }
            response = requests.post(url, headers=headers, json=payload, timeout=10)
            response.raise_for_status()
            
            # Optionally auto-merge (if configured)
            # merge_url = f"{base_url}/pulls/{pr_number}/merge"
            # requests.put(merge_url, headers=headers, json={"merge_method": "squash"})
            
            return True
        
        elif action == "request_changes":
            # Request changes via review
            url = f"{base_url}/pulls/{pr_number}/reviews"
            
            # Build comment from review issues
            issues_text = "Please address the following issues:\n\n"
            for issue in review_data.get("issues", [])[:5]:
                issues_text += f"- **{issue['file']}:{issue['line']}** - {issue['message']}\n"
                if issue.get('suggestion'):
                    issues_text += f"  > 💡 {issue['suggestion']}\n"
            
            payload = {
                "event": "REQUEST_CHANGES",
                "body": issues_text
            }
            response = requests.post(url, headers=headers, json=payload, timeout=10)
            response.raise_for_status()
            
            return True
        
        elif action == "reject":
            # Close PR
            url = f"{base_url}/pulls/{pr_number}"
            payload = {
                "state": "closed"
            }
            response = requests.patch(url, headers=headers, json=payload, timeout=10)
            response.raise_for_status()
            
            # Add rejection comment
            comment_url = f"{base_url}/issues/{pr_number}/comments"
            comment_payload = {
                "body": "❌ This PR has been rejected via Slack review. Please discuss with the team before resubmitting."
            }
            requests.post(comment_url, headers=headers, json=comment_payload, timeout=10)
            
            return True
        
        else:
            print(f"Unknown action: {action}")
            return False
    
    except requests.exceptions.RequestException as e:
        print(f"GitHub API error: {e}")
        return False


@app.route("/slack/interactions", methods=["POST"])
def handle_interaction():
    request_data = request.get_data()
    timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
    signature = request.headers.get("X-Slack-Signature", "")

    if not verify_slack_request(request_data, timestamp, signature):
        return jsonify({"error": "Invalid request signature"}), 401

    content_type = request.headers.get("Content-Type", "")
    
    if "application/json" in content_type:
        payload = request.json or {}
        if payload.get("type") == "url_verification":
            return jsonify({"challenge": payload.get("challenge")})
    else:
        payload_str = request.form.get("payload", "{}")
        payload = json.loads(payload_str)

    action_id = None
    if payload.get("type") == "block_actions" and payload.get("actions"):
        action_id = payload["actions"][0].get("action_id")
    
    if not action_id:
        return jsonify({"error": "No action provided"}), 400
    
    pr_number = None
    if "message" in payload:
        blocks = payload["message"].get("blocks", [])
        for block in blocks:
            if block.get("type") == "section" and block.get("text"):
                text = block["text"].get("text", "")
                import re
                match = re.search(r'PR #(\d+)', text)
                if match:
                    pr_number = int(match.group(1))
                    break
    
    if not pr_number:
        return jsonify({"error": "Could not find PR number"}), 400

    user = payload.get("user", {}).get("name", "unknown")
    
    try:
        if action_id == "review_approve":
            approve_pr(pr_number, user)
            message = f"✅ PR #{pr_number} approved successfully"
        elif action_id == "review_request_changes":
            request_changes_pr(pr_number, user)
            message = f"🔄 Changes requested on PR #{pr_number}"
        elif action_id == "review_reject":
            close_pr(pr_number, user)
            message = f"❌ PR #{pr_number} closed"
        else:
            return jsonify({"error": f"Unknown action: {action_id}"}), 400
        
        return jsonify({"text": message})
    
    except Exception as e:
        logger.error(f"Error handling interaction: {e}")
        return jsonify({"error": "Failed to process action"}), 500
    
    # TODO: Extract PR number from message or store it in button metadata
    # For now, hardcoded for demonstration
    pr_number = 1  # Replace with actual PR number
    
    # Load review data (in production, fetch from artifact or database)
    review_data = {"issues": [], "suggestions": []}
    
    # Trigger GitHub action
    success = trigger_github_action(action_type, pr_number, review_data)
    
    # Update Slack message to show action was taken
    response_text = {
        "approve": "✅ PR approved successfully",
        "request_changes": "🔄 Changes requested",
        "reject": "❌ PR rejected"
    }.get(action_type, "Action completed")
    
    if not success:
        response_text = f"❌ Failed to {action_type} PR"
    
    # Replace original message
    return jsonify({
        "replace_original": True,
        "text": response_text,
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": response_text
                }
            }
        ]
    })


@app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint."""
    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    if not SLACK_SIGNING_SECRET:
        print("WARNING: SLACK_SIGNING_SECRET not set - request verification disabled")
    if not GITHUB_TOKEN:
        print("WARNING: GITHUB_TOKEN not set - GitHub actions will fail")
    
    # Run Flask app
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
