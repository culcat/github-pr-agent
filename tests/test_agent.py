"""Unit tests for config, parser, and formatting."""

import unittest
import uuid
from unittest.mock import MagicMock

from src.config import Config, DEFAULT_EXCLUDED_PATTERNS
from src.llm_client import (
    LLMClient,
    PROVIDER_CONFIGS,
    ReviewResult,
    ReviewComment,
)
from src.telegram_client import TelegramClient
from src.github_client import PullRequestMetadata


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


class TestOpenCodeGoProvider(unittest.TestCase):
    """OpenCode Go provider: endpoint, model, and required headers."""

    def test_provider_config_registered(self):
        self.assertIn("opencode-go", PROVIDER_CONFIGS)
        self.assertEqual(
            PROVIDER_CONFIGS["opencode-go"]["base_url"],
            "https://opencode.ai/inference/go/v1",
        )
        self.assertEqual(PROVIDER_CONFIGS["opencode-go"]["default_model"], "glm-5.3")

    def test_default_base_url_and_model(self):
        client = LLMClient(api_key="dummy", provider="opencode-go")
        self.assertEqual(client.base_url, "https://opencode.ai/inference/go/v1")
        self.assertEqual(client.model, "glm-5.3")

    def test_required_headers_present(self):
        client = LLMClient(api_key="dummy", provider="opencode-go")
        self.assertEqual(client.session.headers["User-Agent"], "culcat-pr-agent/1.0")
        session_id = client.session.headers["x-opencode-session"]
        # Must be a valid UUID
        uuid.UUID(session_id)

    def test_session_id_is_unique_per_client(self):
        client_a = LLMClient(api_key="dummy", provider="opencode-go")
        client_b = LLMClient(api_key="dummy", provider="opencode-go")
        self.assertNotEqual(
            client_a.session.headers["x-opencode-session"],
            client_b.session.headers["x-opencode-session"],
        )

    def test_other_providers_do_not_get_opencode_headers(self):
        client = LLMClient(api_key="dummy", provider="openai")
        self.assertNotIn("x-opencode-session", client.session.headers)
        self.assertNotEqual(client.session.headers.get("User-Agent"), "culcat-pr-agent/1.0")

    def test_response_format_not_sent_for_opencode_go(self):
        client = LLMClient(api_key="dummy", provider="opencode-go")
        captured = {}

        class FakeResp:
            def raise_for_status(self):
                pass

            def json(self):
                return {
                    "choices": [
                        {
                            "message": {
                                "content": '{"verdict": "COMMENT", "score": 7, "summary": "ok"}'
                            }
                        }
                    ]
                }

        def fake_post(url, json=None, timeout=None):
            captured["url"] = url
            captured["payload"] = json
            return FakeResp()

        client.session.post = fake_post
        result = client.review_code(
            pr_title="Add feature",
            pr_description="desc",
            files_diff="+print('hi')",
        )

        self.assertEqual(result.verdict, "COMMENT")
        self.assertEqual(
            captured["url"],
            "https://opencode.ai/inference/go/v1/chat/completions",
        )
        self.assertNotIn("response_format", captured["payload"])


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
