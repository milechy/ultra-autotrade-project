#!/usr/bin/env python3
"""
Reddit MCP PoC — FT Pipeline 向け市場センチメント取得スクリプト
Asana GID 1214076983253101

アプローチ:
  PoC: Reddit 公開 JSON API (認証不要、10 req/min)
  本番: PRAW + OAuth2 (60 req/min) → docs/50_reddit_mcp_integration.md 参照
"""

from __future__ import annotations

import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests

SUBREDDITS = ["ethereum", "defi", "cryptocurrency"]
HOURS_LOOKBACK = 24
POSTS_PER_SUBREDDIT = 25
REQUEST_DELAY_SECONDS = 1.0  # 公開APIのレート制限対策

USER_AGENT = os.getenv("REDDIT_USER_AGENT", "ultra-autotrade-ft-pipeline/0.1 (PoC)")
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": USER_AGENT})


def fetch_recent_posts(subreddit: str, hours: int = HOURS_LOOKBACK) -> list[dict[str, Any]]:
    url = f"https://www.reddit.com/r/{subreddit}/new.json"
    params = {"limit": POSTS_PER_SUBREDDIT}
    cutoff_ts = time.time() - hours * 3600

    try:
        resp = SESSION.get(url, params=params, timeout=10)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[ERROR] r/{subreddit} fetch failed: {e}")
        return []

    children = resp.json().get("data", {}).get("children", [])
    results = []
    for child in children:
        post = child.get("data", {})
        if post.get("created_utc", 0) < cutoff_ts:
            continue
        results.append(
            {
                "id": post.get("id"),
                "title": post.get("title"),
                "url": f"https://www.reddit.com{post.get('permalink')}",
                "score": post.get("score"),
                "num_comments": post.get("num_comments"),
                "created_utc": post.get("created_utc"),
                "created_at": datetime.fromtimestamp(
                    post.get("created_utc", 0), tz=UTC
                ).isoformat(),
                "flair": post.get("link_flair_text"),
                "selftext_preview": (post.get("selftext") or "")[:200],
                "subreddit": subreddit,
            }
        )
    return results


def sentiment_summary(posts: list[dict[str, Any]]) -> dict[str, Any]:
    """スコア合計・コメント数から簡易センチメントスコアを算出 (0.0〜1.0)。"""
    if not posts:
        return {"score": 0.5, "post_count": 0, "total_score": 0, "total_comments": 0}
    total_score = sum(p.get("score", 0) for p in posts)
    total_comments = sum(p.get("num_comments", 0) for p in posts)
    # 正規化: スコア合計 1000 超 → 強気寄り
    normalized = min(1.0, max(0.0, (total_score / max(1, len(posts))) / 1000))
    return {
        "score": round(0.5 + (normalized - 0.5) * 0.6, 3),
        "post_count": len(posts),
        "total_score": total_score,
        "total_comments": total_comments,
    }


def main() -> None:
    all_results: dict[str, Any] = {
        "fetched_at": datetime.now(tz=UTC).isoformat(),
        "lookback_hours": HOURS_LOOKBACK,
        "subreddits": {},
    }

    for sub in SUBREDDITS:
        print(f"Fetching r/{sub} ...")
        posts = fetch_recent_posts(sub)
        summary = sentiment_summary(posts)
        all_results["subreddits"][sub] = {
            "summary": summary,
            "posts": posts,
        }
        print(
            f"  → {summary['post_count']} posts in last {HOURS_LOOKBACK}h | "
            f"sentiment={summary['score']} | "
            f"total_score={summary['total_score']}"
        )
        if posts:
            print(f"  Top post: [{posts[0]['score']}pt] {posts[0]['title'][:80]}")
        time.sleep(REQUEST_DELAY_SECONDS)

    output_path = Path("/tmp/reddit_mcp_poc_result.json")  # noqa: S108
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f"\nFull results saved to {output_path}")
    print("\n=== 5-post sample (r/defi) ===")
    for post in all_results["subreddits"].get("defi", {}).get("posts", [])[:5]:
        score = post.get("score", 0)
        ts = post.get("created_at", "")[:16]
        title = post.get("title", "")[:70]
        print(f"  [{score:>4}pt] {ts} — {title}")


if __name__ == "__main__":
    main()
