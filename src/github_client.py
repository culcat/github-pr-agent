"""GitHub API client for reading pull requests and submitting reviews."""

import fnmatch
import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
import requests

logger = logging.getLogger(__name__)


@dataclass
class PullRequestMetadata:
    """PR information required for review."""

    number: int
    title: str
    author: str
    html_url: str
    head_sha: str
    base_branch: str
    head_branch: str
    body: Optional[str] = ""


@dataclass
class ChangedFile:
    """Represents a file changed in the PR."""

    filename: str
    status: str
    additions: int
    deletions: int
    patch: Optional[str]


class GitHubClient:
    """Client for GitHub REST API."""

    def __init__(self, token: str, repository: str, api_url: str = "https://api.github.com"):
        self.token = token
        self.repository = repository  # "owner/repo"
        self.api_url = api_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "AI-PR-Review-Agent",
        })

    def get_pr_metadata(
        self,
        pr_number: Optional[int] = None,
        event_path: Optional[str] = None
    ) -> PullRequestMetadata:
        """Extract PR metadata from event payload (CI) or via REST API."""
        if event_path and os.path.exists(event_path):
            try:
                with open(event_path, "r", encoding="utf-8") as f:
                    event_data = json.load(f)
                if "pull_request" in event_data:
                    pr = event_data["pull_request"]
                    return PullRequestMetadata(
                        number=pr["number"],
                        title=pr.get("title", ""),
                        author=pr.get("user", {}).get("login", "unknown"),
                        html_url=pr.get("html_url", ""),
                        head_sha=pr["head"]["sha"],
                        base_branch=pr["base"]["ref"],
                        head_branch=pr["head"]["ref"],
                        body=pr.get("body", ""),
                    )
            except Exception as e:
                logger.warning("Failed to parse event path, falling back to API: %s", e)

        if not pr_number:
            raise ValueError("PR number must be specified when not running from GitHub event.")

        url = f"{self.api_url}/repos/{self.repository}/pulls/{pr_number}"
        resp = self.session.get(url)
        resp.raise_for_status()
        pr = resp.json()

        return PullRequestMetadata(
            number=pr["number"],
            title=pr.get("title", ""),
            author=pr.get("user", {}).get("login", "unknown"),
            html_url=pr.get("html_url", ""),
            head_sha=pr["head"]["sha"],
            base_branch=pr["base"]["ref"],
            head_branch=pr["head"]["ref"],
            body=pr.get("body", ""),
        )

    def get_pr_files(
        self,
        pr_number: int,
        excluded_patterns: Optional[List[str]] = None
    ) -> List[ChangedFile]:
        """Fetch files changed in the PR, filtering out lockfiles/binaries."""
        excluded_patterns = excluded_patterns or []
        files: List[ChangedFile] = []
        page = 1
        per_page = 100

        while True:
            url = f"{self.api_url}/repos/{self.repository}/pulls/{pr_number}/files"
            resp = self.session.get(url, params={"page": page, "per_page": per_page})
            resp.raise_for_status()
            data = resp.json()

            if not data:
                break

            for item in data:
                filename = item["filename"]

                # Check if ignored
                if any(fnmatch.fnmatch(filename, pat) for pat in excluded_patterns):
                    logger.debug("Skipping ignored file: %s", filename)
                    continue

                # Skip removed files or files without patches (e.g. binaries)
                if item.get("status") == "removed" or not item.get("patch"):
                    continue

                files.append(
                    ChangedFile(
                        filename=filename,
                        status=item.get("status", "modified"),
                        additions=item.get("additions", 0),
                        deletions=item.get("deletions", 0),
                        patch=item.get("patch"),
                    )
                )

            if len(data) < per_page:
                break
            page += 1

        return files

    def post_review(
        self,
        pr_number: int,
        commit_sha: str,
        body: str,
        event: str = "COMMENT",
        comments: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Submit a GitHub Pull Request review with summary and inline comments.

        Handles GitHub API 422 if an inline comment line is outside diff hunk.
        """
        url = f"{self.api_url}/repos/{self.repository}/pulls/{pr_number}/reviews"
        comments = comments or []

        # Validate event type
        event = event.upper()
        if event not in ("APPROVE", "REQUEST_CHANGES", "COMMENT"):
            event = "COMMENT"

        # Attempt batch review submission
        payload: Dict[str, Any] = {
            "commit_id": commit_sha,
            "body": body,
            "event": event,
        }

        if comments:
            formatted_comments = []
            for c in comments:
                formatted_comments.append({
                    "path": c["path"],
                    "line": int(c["line"]),
                    "body": c["body"],
                })
            payload["comments"] = formatted_comments

        resp = self.session.post(url, json=payload)

        # If batch submission succeeds, return
        if resp.status_code in (200, 201):
            return resp.json()

        # If HTTP 422 (e.g. line outside diff hunk), fallback to body comments
        logger.warning(
            "Batch review failed with status %d: %s. Falling back to body comments.",
            resp.status_code,
            resp.text,
        )

        fallback_body = body
        if comments:
            fallback_body += "\n\n### 💬 Inline Comments (Fallback)\n"
            for c in comments:
                fallback_body += f"\n- **`{c['path']}` (line {c['line']})**:\n  {c['body']}\n"

        fallback_payload = {
            "commit_id": commit_sha,
            "body": fallback_body,
            "event": event,
        }

        fallback_resp = self.session.post(url, json=fallback_payload)
        fallback_resp.raise_for_status()
        return fallback_resp.json()
