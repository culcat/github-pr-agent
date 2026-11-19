"""Unit tests for config, parser, and formatting."""

import unittest
from unittest.mock import MagicMock

from src.config import Config, DEFAULT_EXCLUDED_PATTERNS
from src.llm_client import LLMClient, SYSTEM_PROMPT, ReviewResult, ReviewComment
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


class TestStackReviewPrompt(unittest.TestCase):
    """System prompt stack expertise and REVIEW_EXTRA_INSTRUCTIONS support."""

    def test_system_prompt_contains_stack_expertise(self):
        self.assertIn("Stack expertise", SYSTEM_PROMPT)
        self.assertIn("Next.js App Router", SYSTEM_PROMPT)
        self.assertIn("'use client'", SYSTEM_PROMPT)
        self.assertIn("revalidatePath", SYSTEM_PROMPT)
        self.assertIn("TypeScript (strict mode)", SYSTEM_PROMPT)
        self.assertIn("SCSS Modules", SYSTEM_PROMPT)
        self.assertIn("*.module.scss", SYSTEM_PROMPT)
        self.assertIn("React best practices", SYSTEM_PROMPT)
        self.assertIn("Security", SYSTEM_PROMPT)

    def test_no_extra_instructions_by_default(self):
        client = LLMClient(api_key="dummy", provider="openai")
        self.assertEqual(client.system_prompt, SYSTEM_PROMPT)

    def test_extra_instructions_appended_to_system_prompt(self):
        extra = "Always flag deprecated React lifecycle methods."
        client = LLMClient(api_key="dummy", provider="openai", extra_instructions=extra)
        self.assertTrue(client.system_prompt.startswith(SYSTEM_PROMPT))
        self.assertTrue(client.system_prompt.rstrip().endswith(extra))
        self.assertIn("Additional review instructions", client.system_prompt)
        # Original prompt content is preserved before the appended part
        self.assertIn("Stack expertise", client.system_prompt)

    def test_extra_instructions_sent_in_payload(self):
        client = LLMClient(
            api_key="dummy", provider="openai", extra_instructions="Prefer server components."
        )
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
            captured["payload"] = json
            return FakeResp()

        client.session.post = fake_post
        client.review_code(pr_title="T", pr_description="D", files_diff="+x")
        system_message = captured["payload"]["messages"][0]["content"]
        self.assertIn("Prefer server components.", system_message)
        self.assertIn("Stack expertise", system_message)


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
