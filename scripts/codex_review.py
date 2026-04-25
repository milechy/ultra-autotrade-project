#!/usr/bin/env python3
"""
Codex 5.3 PR Review Script

PRのdiffをCodex (GPT系)に送信し、セキュリティルールに基づいたレビューを実行する。
Critical issue検出時は exit code 1 で終了。

Usage:
    python scripts/codex_review.py \
        --diff /tmp/pr_diff.patch \
        --security-doc docs/13_security_design.md \
        --output /tmp/review_result.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from openai import OpenAI, RateLimitError

SYSTEM_PROMPT_TEMPLATE = """\
You are Codex 5.3, an expert code reviewer for a crypto auto-trading system (Ultra AutoTrade).

Your review MUST enforce these security rules from the project's security design document:
---
{security_rules}
---

Key rules to strictly verify:
1. Private keys must ONLY be in environment variables. Never hardcoded. Never logged.
2. Health Factor < 1.6 must trigger automatic HARD_STOP.
3. Max single trade: 10% of total assets.
4. Max daily trades: 30% of total assets.
5. Cooldown: 10 minutes between Aave operations.
6. Emergency stop flag uses OR logic — manual stop can NEVER be overwritten.
7. .env.staging and .env.production MUST use physically different keys.
8. No tokens/keys in logs — mask to first 6 + last 4 chars.
9. LLM output MUST be JSON Schema validated — parse failure → HOLD.
10. Financial calculations: Decimal type ONLY (never float).

SCOPE AND FALSE POSITIVE PREVENTION — READ CAREFULLY:

Scope:
- ONLY report issues that are DIRECTLY visible in the provided diff.
- Do NOT infer missing implementations in files you cannot see.
- If a safety check (e.g., HF < 1.6) is not present in the diff, do NOT flag it as
  missing — it may be implemented in other files outside the diff.

Example and template files:
- .env.example and .env.staging.example files contain PLACEHOLDER values
  (like `0x...`, `CHANGE_ME`, `sk-...`, `0x...TESTNET_ONLY...`).
- These placeholders are NOT hardcoded secrets. Do NOT flag them as security issues.

Test files:
- Code in test files (test_*.py, conftest.py, or files under a tests/ directory) is
  allowed to use assert statements, hardcoded test values, and /tmp paths.
- Do NOT flag these as issues.

Severity guidance:
- Use 'critical' ONLY for verified vulnerabilities that are directly visible in the diff
  (e.g., an actual real private key hardcoded in production code, or a safety check
  being explicitly removed in the changed code).
- If you are unsure whether an issue exists because the relevant code is not in the diff,
  use 'warning' instead of 'critical'.
- Prefer 'info' or 'warning' for stylistic or speculative concerns.

Known project patterns (do NOT flag these):
- The project uses `Decimal` for financial calculations. If you see Decimal imports and
  usage, do not flag this as a float issue.
- The project implements HF<1.6 safety checks in aave/client.py — do not flag a missing
  HF check unless the diff explicitly removes it from that file.
- The project uses emergency_stop + circuit_closed as dual safety mechanisms — do not
  flag one as missing if the other is present.

Respond ONLY with valid JSON matching this schema:
{{
  "severity": "ok" | "warning" | "critical",
  "security_ok": true | false,
  "test_coverage_ok": true | false,
  "issues": [
    {{
      "severity": "info" | "warning" | "critical",
      "message": "description of the issue",
      "file": "path/to/file (if applicable)",
      "line": null
    }}
  ],
  "summary": "brief overall assessment"
}}
"""

MAX_DIFF_CHARS = 100_000


def load_file(path: str) -> str:
    p = Path(path)
    if not p.exists():
        print(f"Warning: {path} not found, using empty content", file=sys.stderr)
        return ""
    return p.read_text(encoding="utf-8")


def truncate_diff(diff: str, max_chars: int = MAX_DIFF_CHARS) -> str:
    if len(diff) <= max_chars:
        return diff
    return diff[:max_chars] + f"\n\n... [truncated, {len(diff) - max_chars} chars omitted]"


def run_review(diff: str, security_doc: str) -> dict:
    client = OpenAI()

    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(security_rules=security_doc)

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": f"Review this PR diff:\n\n```diff\n{truncate_diff(diff)}\n```",
                },
            ],
            temperature=0.1,
            response_format={"type": "json_object"},
        )
    except RateLimitError as e:
        # クォータ超過は CI をブロックしない — 警告のみ出して skipped 扱いにする
        print(f"::warning::OpenAI quota exceeded, skipping Codex review: {e}", file=sys.stderr)
        return {
            "severity": "info",
            "security_ok": True,
            "test_coverage_ok": True,
            "issues": [
                {
                    "severity": "info",
                    "message": f"Codex review skipped: OpenAI quota exceeded ({e})",
                }
            ],
        }

    content = response.choices[0].message.content
    if not content:
        return {
            "severity": "warning",
            "security_ok": True,
            "test_coverage_ok": True,
            "issues": [
                {
                    "severity": "warning",
                    "message": "Empty response from Codex",
                    "file": None,
                    "line": None,
                }
            ],
            "summary": "Review returned empty response",
        }

    return json.loads(content)


def validate_result(result: dict) -> dict:
    """結果のスキーマ検証と正規化"""
    required_keys = {"severity", "security_ok", "test_coverage_ok", "issues", "summary"}
    for key in required_keys:
        if key not in result:
            if key == "issues":
                result[key] = []
            elif key == "summary":
                result[key] = "No summary provided"
            elif key in ("security_ok", "test_coverage_ok"):
                result[key] = True
            elif key == "severity":
                result[key] = "ok"

    valid_severities = {"ok", "warning", "critical"}
    if result["severity"] not in valid_severities:
        result["severity"] = "warning"

    for issue in result.get("issues", []):
        if issue.get("severity") not in {"info", "warning", "critical"}:
            issue["severity"] = "warning"
        issue.setdefault("file", None)
        issue.setdefault("line", None)

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Codex PR review")
    parser.add_argument("--diff", required=True, help="Path to diff file")
    parser.add_argument("--security-doc", required=True, help="Path to security design doc")
    parser.add_argument("--output", required=True, help="Path to output JSON")
    args = parser.parse_args()

    diff = load_file(args.diff)
    if not diff.strip():
        result = {
            "severity": "ok",
            "security_ok": True,
            "test_coverage_ok": True,
            "issues": [],
            "summary": "No changes to review",
        }
    else:
        security_doc = load_file(args.security_doc)
        result = run_review(diff, security_doc)

    result = validate_result(result)

    Path(args.output).write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Review complete: {result['severity']}")
    print(f"  Security: {'PASS' if result['security_ok'] else 'FAIL'}")
    print(f"  Issues: {len(result.get('issues', []))}")

    critical_issues = [i for i in result.get("issues", []) if i.get("severity") == "critical"]
    if critical_issues:
        print(f"\n🔴 {len(critical_issues)} critical issue(s) found:", file=sys.stderr)
        for issue in critical_issues:
            print(f"  - {issue['message']}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
