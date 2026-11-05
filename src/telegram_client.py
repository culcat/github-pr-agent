"""Telegram notification client for PR review alerts."""

import html
import logging
from typing import Optional
import requests

from .github_client import PullRequestMetadata
from .llm_client import ReviewResult

logger = logging.getLogger(__name__)


class TelegramClient:
    """Client for Telegram Bot API."""

    def __init__(self, bot_token: str, chat_id: str, api_url: str = "https://api.telegram.org"):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.api_url = api_url.rstrip("/")
        self.session = requests.Session()

    def send_review_notification(
        self,
        pr: PullRequestMetadata,
        review: ReviewResult,
        repo_name: str,
    ) -> bool:
        """Format review summary and send message to Telegram."""
        text = self._build_message(pr, review, repo_name)
        url = f"{self.api_url}/bot{self.bot_token}/sendMessage"

        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }

        try:
            resp = self.session.post(url, json=payload, timeout=20)
            resp.raise_for_status()
            logger.info("Successfully sent review notification to Telegram chat %s", self.chat_id)
            return True
        except requests.RequestException as e:
            logger.error("Failed to send Telegram notification: %s", e)
            return False

    def _build_message(
        self,
        pr: PullRequestMetadata,
        review: ReviewResult,
        repo_name: str,
    ) -> str:
        """Compose an HTML-formatted message card for Telegram."""
        # Icons based on verdict
        if review.verdict == "APPROVE":
            verdict_badge = "✅ <b>Одобрено (Approved)</b>"
        elif review.verdict == "REQUEST_CHANGES":
            verdict_badge = "⚠️ <b>Требуются правки (Changes Requested)</b>"
        else:
            verdict_badge = "💬 <b>Комментарий (Commented)</b>"

        # Stars rating visualization
        stars = "⭐️" * (review.score // 2) if review.score > 0 else "⭐️"

        safe_title = html.escape(pr.title)
        safe_repo = html.escape(repo_name)
        safe_author = html.escape(pr.author)
        safe_summary = html.escape(review.summary)

        lines = [
            f"🤖 <b>AI Code Review</b> | <code>{safe_repo}</code>",
            f"<b>PR:</b> <a href=\"{pr.html_url}\">#{pr.number} {safe_title}</a>",
            f"👤 <b>Автор:</b> @{safe_author}",
            f"📊 <b>Вердикт:</b> {verdict_badge}",
            f"📈 <b>Оценка качества:</b> {stars} ({review.score}/10)",
            "",
            f"📝 <b>Резюме:</b>\n{safe_summary}",
        ]

        if review.key_points:
            lines.append("\n🔍 <b>Ключевые моменты:</b>")
            for pt in review.key_points[:5]:  # limit to top 5 points
                lines.append(f"• {html.escape(pt)}")

        if review.comments:
            lines.append(f"\n💬 <b>Замечаний в коде:</b> {len(review.comments)}")
            # Mention top 3 issues with file and line
            for c in review.comments[:3]:
                safe_file = html.escape(c.path)
                safe_body = html.escape(c.body[:120] + ("..." if len(c.body) > 120 else ""))
                lines.append(f"  └ <code>{safe_file}:{c.line}</code>: {safe_body}")
            if len(review.comments) > 3:
                lines.append(f"  <i>...и еще {len(review.comments) - 3} замечаний в PR</i>")

        lines.append(f"\n🔗 <a href=\"{pr.html_url}\"><b>Открыть Pull Request на GitHub</b></a>")

        return "\n".join(lines)
