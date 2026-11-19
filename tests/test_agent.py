"""Unit tests for config, parser, and formatting."""

import unittest
from unittest.mock import MagicMock

from src.config import Config, DEFAULT_EXCLUDED_PATTERNS
from src.llm_client import LLMClient, ReviewResult, ReviewComment
from src.telegram_client import TelegramClient
from src.github_client import PullRequestMetadata, ChangedFile


class TestConfig(unittest.TestCase):
    def test_validation_fails_on_missing_fields(self):
        cfg = Config(github_token="", telegram_bot_token="", telegram_chat_id="", llm_api_key="")
        with self.assertRaises(ValueError):
            cfg.validate()

    def test_validation_succeeds_when_fields_present(self):
        cfg = Config(
            github_token="gh_token",
            github_repository="owner/repo",
            telegram_bot_token="tg_token",
            telegram_chat_id="123",
            llm_api_key="llm_key",
        )
        # Should not raise
        cfg.validate()

    def test_validation_succeeds_without_telegram(self):
        """Telegram is optional: only GITHUB_TOKEN and LLM key are required."""
        cfg = Config(
            github_token="gh_token",
            telegram_bot_token="",
            telegram_chat_id="",
            llm_api_key="llm_key",
        )
        # Should not raise
        cfg.validate()

    def test_validation_fails_without_llm_key(self):
        cfg = Config(github_token="gh_token", llm_api_key="")
        with self.assertRaises(ValueError):
            cfg.validate()


class TestAgentTelegramNotification(unittest.TestCase):
    """PRAgent.run() must notify Telegram only when it is fully configured."""

    def _make_agent(self, telegram_bot_token: str, telegram_chat_id: str):
        from src.agent import PRAgent

        cfg = Config(
            github_token="gh_token",
            github_repository="owner/repo",
            telegram_bot_token=telegram_bot_token,
            telegram_chat_id=telegram_chat_id,
            llm_api_key="llm_key",
        )
        return PRAgent(cfg)

    def _mock_review_flow(self, agent):
        pr = PullRequestMetadata(
            number=1,
            title="Add feature",
            author="octocat",
            html_url="https://github.com/owner/repo/pull/1",
            head_sha="abcdef123456",
            base_branch="main",
            head_branch="feature/x",
        )
        agent.github.get_pr_metadata = MagicMock(return_value=pr)
        agent.github.get_pr_files = MagicMock(
            return_value=[
                ChangedFile(
                    filename="src/app.py",
                    status="modified",
                    additions=1,
                    deletions=0,
                    patch="+print('hi')",
                )
            ]
        )
        agent.llm.review_code = MagicMock(
            return_value=ReviewResult(
                verdict="COMMENT",
                score=7,
                summary="Fine overall.",
                key_points=[],
                comments=[],
            )
        )
        agent.github.post_review = MagicMock(return_value={})
        agent.telegram.send_review_notification = MagicMock(return_value=True)
        return agent

    def test_run_skips_telegram_when_not_configured(self):
        agent = self._mock_review_flow(self._make_agent("", ""))
        self.assertTrue(agent.run(pr_number=1))
        agent.telegram.send_review_notification.assert_not_called()

    def test_run_notifies_telegram_when_configured(self):
        agent = self._mock_review_flow(self._make_agent("tg_token", "123"))
        self.assertTrue(agent.run(pr_number=1))
        agent.telegram.send_review_notification.assert_called_once()


class TestLLMParser(unittest.TestCase):
    def setUp(self):
        self.client = LLMClient(api_key="dummy", provider="openai")

    def test_parse_valid_json_with_codeblock(self):
        raw = """```json
        {
          "verdict": "APPROVE",
          "score": 9,
          "summary": "Looks great, well architected.",
          "key_points": ["Good error handling"],
          "comments": [
            {"path": "main.py", "line": 15, "body": "Consider using pathlib"}
          ]
        }
        ```"""
        result = self.client._parse_response(raw)
        self.assertEqual(result.verdict, "APPROVE")
        self.assertEqual(result.score, 9)
        self.assertEqual(len(result.comments), 1)
        self.assertEqual(result.comments[0].path, "main.py")
        self.assertEqual(result.comments[0].line, 15)

    def test_parse_corrupted_response(self):
        raw = "Sorry, I cannot review this as code."
        result = self.client._parse_response(raw)
        self.assertEqual(result.verdict, "COMMENT")
        self.assertIn("Automated review completed", result.summary)


class TestTelegramBuilder(unittest.TestCase):
    def test_message_formatting(self):
        tg = TelegramClient(bot_token="dummy", chat_id="123")
        pr = PullRequestMetadata(
            number=42,
            title="Feature: Add AI Review",
            author="octocat",
            html_url="https://github.com/octocat/repo/pull/42",
            head_sha="abcdef123456",
            base_branch="main",
            head_branch="feature",
        )
        review = ReviewResult(
            verdict="APPROVE",
            score=10,
            summary="Clean implementation with high test coverage.",
            key_points=["Added tests"],
            comments=[
                ReviewComment(path="test.py", line=10, body="Minor style fix")
            ],
        )

        msg = tg._build_message(pr, review, "octocat/repo")
        self.assertIn("#42 Feature: Add AI Review", msg)
        self.assertIn("@octocat", msg)
        self.assertIn("Одобрено", msg)
        self.assertIn("10/10", msg)
        self.assertIn("test.py:10", msg)


if __name__ == "__main__":
    unittest.main()
