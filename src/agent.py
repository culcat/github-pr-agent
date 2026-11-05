"""Core orchestrator for the AI PR Review Agent."""

import logging
from typing import Optional

from .config import Config
from .github_client import GitHubClient, PullRequestMetadata
from .llm_client import LLMClient, ReviewResult
from .telegram_client import TelegramClient

logger = logging.getLogger(__name__)


class PRAgent:
    """Coordinates PR fetching, AI review, GitHub commenting, and Telegram alerting."""

    def __init__(self, config: Config):
        self.config = config
        self.github = GitHubClient(
            token=self.config.github_token,
            repository=self.config.github_repository,
        )
        self.llm = LLMClient(
            api_key=self.config.llm_api_key,
            provider=self.config.llm_provider,
            model=self.config.llm_model or None,
            base_url=self.config.llm_base_url,
        )
        self.telegram = TelegramClient(
            bot_token=self.config.telegram_bot_token,
            chat_id=self.config.telegram_chat_id,
        )

    def run(self, pr_number: Optional[int] = None) -> bool:
        """Execute the full review lifecycle."""
        logger.info("Starting PR Review Agent for repo: %s", self.config.github_repository)

        # 1. Fetch PR metadata
        pr = self.github.get_pr_metadata(
            pr_number=pr_number or self.config.pr_number,
            event_path=self.config.github_event_path,
        )
        logger.info("Processing PR #%d: '%s' by @%s", pr.number, pr.title, pr.author)

        # 2. Fetch modified files
        files = self.github.get_pr_files(
            pr_number=pr.number,
            excluded_patterns=self.config.excluded_patterns,
        )

        if not files:
            logger.info("No reviewable files found in PR #%d (all ignored or binary). Skipping.", pr.number)
            return True

        # 3. Assemble diff
        diff_text, total_lines = self._build_diff_text(files)
        logger.info("Assembled diff for %d files (%d lines)", len(files), total_lines)

        # 4. Generate AI review
        logger.info("Requesting review from LLM (%s)...", self.llm.model)
        review = self.llm.review_code(
            pr_title=pr.title,
            pr_description=pr.body or "",
            files_diff=diff_text,
        )
        logger.info(
            "Review generated: Verdict=%s, Score=%d/10, Comments=%d",
            review.verdict,
            review.score,
            len(review.comments),
        )

        # 5. Post review to GitHub
        review_body = self._build_github_review_body(review)
        formatted_comments = [
            {"path": c.path, "line": c.line, "body": c.body}
            for c in review.comments
        ]

        logger.info("Posting review to GitHub PR #%d...", pr.number)
        self.github.post_review(
            pr_number=pr.number,
            commit_sha=pr.head_sha,
            body=review_body,
            event=review.verdict,
            comments=formatted_comments,
        )

        # 6. Notify Telegram
        logger.info("Sending summary notification to Telegram...")
        tg_success = self.telegram.send_review_notification(
            pr=pr,
            review=review,
            repo_name=self.config.github_repository,
        )

        if tg_success:
            logger.info("Telegram notification delivered successfully.")
        else:
            logger.warning("Telegram notification failed.")

        return True

    def _build_diff_text(self, files) -> tuple[str, int]:
        """Combine file patches up to max_diff_lines limit."""
        diff_chunks = []
        current_lines = 0
        truncated = False

        for f in files:
            if not f.patch:
                continue

            file_header = f"diff --git a/{f.filename} b/{f.filename}\n--- a/{f.filename}\n+++ b/{f.filename}\n"
            patch_lines = f.patch.count("\n") + 1

            if current_lines + patch_lines > self.config.max_diff_lines:
                remaining = max(0, self.config.max_diff_lines - current_lines)
                if remaining > 0:
                    truncated_patch = "\n".join(f.patch.split("\n")[:remaining])
                    diff_chunks.append(file_header + truncated_patch)
                truncated = True
                break

            diff_chunks.append(file_header + f.patch)
            current_lines += patch_lines

        combined = "\n\n".join(diff_chunks)
        if truncated:
            combined += (
                f"\n\n[Diff truncated: exceeded max limit of {self.config.max_diff_lines} lines]"
            )

        return combined, current_lines

    def _build_github_review_body(self, review: ReviewResult) -> str:
        """Compose GitHub PR review comment body in Markdown."""
        verdict_badge = {
            "APPROVE": "🟢 **Approved**",
            "REQUEST_CHANGES": "🔴 **Changes Requested**",
            "COMMENT": "🟡 **Commented**",
        }.get(review.verdict, "🟡 **Commented**")

        body_lines = [
            f"## 🤖 AI Code Review Summary ({verdict_badge})",
            "",
            f"**Quality Score:** `{review.score}/10`",
            "",
            "### 📋 Overview",
            review.summary,
            "",
        ]

        if review.key_points:
            body_lines.append("### 🔍 Key Findings")
            for pt in review.key_points:
                body_lines.append(f"- {pt}")
            body_lines.append("")

        body_lines.append("---")
        body_lines.append(
            "_Automated review provided by AI PR Agent. Please verify suggestions before merging._"
        )

        return "\n".join(body_lines)
