#!/usr/bin/env python3
"""
Codex-based automated code review script.

Usage:
    python codex_review.py --files "file1.py file2.ts"
    python codex_review.py --diff HEAD~1
"""

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Any

try:
    import openai
except ImportError:
    print("ERROR: openai package not installed. Run: pip install openai")
    sys.exit(1)


@dataclass
class ReviewIssue:
    """Single code review issue."""
    file: str
    line: int
    severity: str  # "error", "warning", "info"
    message: str
    suggestion: str = ""


@dataclass
class ReviewResult:
    """Complete review result."""
    files_reviewed: int
    issues: List[ReviewIssue]
    suggestions: List[ReviewIssue]
    summary: str
    review_time_seconds: float


def get_git_diff(base_ref: str = "HEAD~1") -> str:
    """Get git diff for changed files."""
    try:
        result = subprocess.run(
            ["git", "diff", base_ref],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        print(f"ERROR: Git diff failed: {e}")
        return ""


def get_file_content(filepath: str) -> str:
    """Read file content."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        print(f"WARNING: Could not read {filepath}: {e}")
        return ""


def review_code_with_openai(code: str, filename: str, api_key: str) -> Dict[str, Any]:
    """
    Send code to OpenAI for review.
    
    Returns structured review data.
    """
    openai.api_key = api_key
    
    prompt = f"""You are a senior code reviewer for the Ultra AutoTrade cryptocurrency trading system.

Review the following code and provide:
1. Security issues (API keys, vulnerabilities)
2. Performance issues
3. Code quality issues
4. Best practice violations
5. Suggestions for improvement

Code file: {filename}

```
{code}
```

Respond in JSON format:
{{
  "issues": [
    {{
      "line": 45,
      "severity": "error",
      "message": "Brief description",
      "suggestion": "How to fix"
    }}
  ],
  "summary": "Overall assessment"
}}
"""
    
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",  # または gpt-3.5-turbo（コスト削減）
            messages=[
                {"role": "system", "content": "You are an expert code reviewer specializing in Python, TypeScript, and cryptocurrency trading systems."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=2000,
        )
        
        content = response.choices[0].message.content
        
        # Extract JSON from markdown code blocks if present
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        
        return json.loads(content)
    
    except json.JSONDecodeError as e:
        print(f"WARNING: Could not parse OpenAI response as JSON: {e}")
        return {"issues": [], "summary": "Review parsing failed"}
    except Exception as e:
        print(f"ERROR: OpenAI API call failed: {e}")
        return {"issues": [], "summary": f"API error: {str(e)}"}


def review_files(files: List[str], api_key: str) -> ReviewResult:
    """Review multiple files and aggregate results."""
    import time
    start_time = time.time()
    
    all_issues = []
    all_suggestions = []
    files_reviewed = 0
    
    for filepath in files:
        if not os.path.exists(filepath):
            print(f"WARNING: File not found: {filepath}")
            continue
        
        # Skip non-code files
        if not filepath.endswith(('.py', '.ts', '.tsx', '.js', '.jsx')):
            continue
        
        code = get_file_content(filepath)
        if not code:
            continue
        
        print(f"Reviewing: {filepath}")
        review_data = review_code_with_openai(code, filepath, api_key)
        
        for issue in review_data.get("issues", []):
            issue_obj = ReviewIssue(
                file=filepath,
                line=issue.get("line", 0),
                severity=issue.get("severity", "info"),
                message=issue.get("message", ""),
                suggestion=issue.get("suggestion", ""),
            )
            
            if issue_obj.severity in ("error", "warning"):
                all_issues.append(issue_obj)
            else:
                all_suggestions.append(issue_obj)
        
        files_reviewed += 1
        
        # Rate limiting: 3 RPM for free tier
        time.sleep(20)
    
    elapsed = time.time() - start_time
    
    summary = f"Reviewed {files_reviewed} files. Found {len(all_issues)} issues and {len(all_suggestions)} suggestions."
    
    return ReviewResult(
        files_reviewed=files_reviewed,
        issues=all_issues,
        suggestions=all_suggestions,
        summary=summary,
        review_time_seconds=elapsed,
    )


def save_review_json(result: ReviewResult, output_path: str):
    """Save review result as JSON."""
    data = {
        "files_reviewed": result.files_reviewed,
        "issues": [
            {
                "file": i.file,
                "line": i.line,
                "severity": i.severity,
                "message": i.message,
                "suggestion": i.suggestion,
            }
            for i in result.issues
        ],
        "suggestions": [
            {
                "file": s.file,
                "line": s.line,
                "severity": s.severity,
                "message": s.message,
                "suggestion": s.suggestion,
            }
            for s in result.suggestions
        ],
        "summary": result.summary,
        "review_time_seconds": result.review_time_seconds,
    }
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"Review saved to: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Automated code review with OpenAI Codex")
    parser.add_argument("--files", help="Space-separated list of files to review")
    parser.add_argument("--diff", help="Git ref to diff against (e.g., HEAD~1)")
    parser.add_argument("--output", default="review_result.json", help="Output JSON file")
    
    args = parser.parse_args()
    
    # Get API key from environment
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("ERROR: OPENAI_API_KEY environment variable not set")
        sys.exit(1)
    
    # Determine files to review
    files_to_review = []
    
    if args.files:
        files_to_review = args.files.split()
    elif args.diff:
        # Get changed files from git diff
        diff_output = get_git_diff(args.diff)
        # Parse diff to extract filenames (simplified)
        for line in diff_output.split("\n"):
            if line.startswith("diff --git"):
                parts = line.split()
                if len(parts) >= 4:
                    filepath = parts[2].replace("a/", "")
                    if os.path.exists(filepath):
                        files_to_review.append(filepath)
    else:
        print("ERROR: Must specify --files or --diff")
        sys.exit(1)
    
    if not files_to_review:
        print("No files to review")
        sys.exit(0)
    
    print(f"Reviewing {len(files_to_review)} files...")
    result = review_files(files_to_review, api_key)
    
    save_review_json(result, args.output)
    
    # Print summary
    print("\n" + "="*60)
    print(f"REVIEW SUMMARY")
    print("="*60)
    print(result.summary)
    print(f"⚠️  Issues: {len(result.issues)}")
    print(f"💡 Suggestions: {len(result.suggestions)}")
    print(f"⏱️  Time: {result.review_time_seconds:.1f}s")
    
    # Exit with error code if critical issues found
    critical_count = sum(1 for i in result.issues if i.severity == "error")
    if critical_count > 0:
        print(f"\n❌ {critical_count} critical issues found")
        sys.exit(1)
    
    print("\n✅ Review complete")


if __name__ == "__main__":
    main()