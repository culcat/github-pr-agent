"""LLM Reviewer supporting Gemini, DeepSeek, Groq, OpenAI, and custom OpenAI-compatible endpoints."""

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import requests

logger = logging.getLogger(__name__)

# Provider default endpoints and models
PROVIDER_CONFIGS = {
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "default_model": "gemini-2.5-flash",
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com",
        "default_model": "deepseek-chat",
    },
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "default_model": "llama-3.3-70b-versatile",
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o-mini",
    },
}


@dataclass
class ReviewComment:
    """An inline review comment on a specific line of code."""

    path: str
    line: int
    body: str


@dataclass
class ReviewResult:
    """Parsed review from LLM."""

    verdict: str  # APPROVE, REQUEST_CHANGES, COMMENT
    score: int  # 1-10
    summary: str
    key_points: List[str] = field(default_factory=list)
    comments: List[ReviewComment] = field(default_factory=list)
    raw_response: str = ""


SYSTEM_PROMPT = """You are an expert Senior Staff Software Engineer and Security Auditor conducting a thorough, professional Pull Request code review.

Your responsibilities:
1. Examine the git diff carefully.
2. Identify real bugs, security risks, concurrency/race conditions, resource leaks, edge cases, and performance bottlenecks.
3. Be constructive, objective, and specific. Avoid trivial cosmetic nitpicks (like whitespace or styling that automated linters catch).
4. Provide inline comments for specific lines where problems occur. Ensure the `line` number corresponds to a new or modified line in the diff chunk.
5. Provide a realistic overall score (1 to 10) and an overall verdict:
   - "APPROVE": High quality, no critical bugs or blockers.
   - "REQUEST_CHANGES": Contains critical bugs, logic errors, security flaws, or high performance risks.
   - "COMMENT": Minor questions or non-blocking suggestions.

CRITICAL: You MUST respond ONLY with valid, parseable JSON in the following exact format:
{
  "verdict": "APPROVE" | "REQUEST_CHANGES" | "COMMENT",
  "score": 8,
  "summary": "Clear, concise 2-4 sentence summary of what this PR does and overall code quality.",
  "key_points": [
    "✅ Highlights / well-designed parts",
    "⚠️ Areas of concern or items needing attention"
  ],
  "comments": [
    {
      "path": "path/to/changed_file.py",
      "line": 42,
      "body": "Specific explanation of the bug or improvement suggestion."
    }
  ]
}
Do not include any text before or after the JSON.
"""


class LLMClient:
    """Client for generating code reviews via OpenAI-compatible API."""

    def __init__(
        self,
        api_key: str,
        provider: str = "gemini",
        model: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        self.api_key = api_key
        self.provider = provider.lower()

        cfg = PROVIDER_CONFIGS.get(self.provider, {})
        self.base_url = (base_url or cfg.get("base_url", "https://api.openai.com/v1")).rstrip("/")
        self.model = model or cfg.get("default_model", "gpt-4o-mini")
        self.timeout = int(os.getenv("LLM_TIMEOUT", "180"))

        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        })

    def review_code(
        self,
        pr_title: str,
        pr_description: str,
        files_diff: str,
    ) -> ReviewResult:
        """Send PR diff to LLM and parse structured review result."""
        user_prompt = f"""### Pull Request Details
**Title:** {pr_title}
**Description:**
{pr_description or 'No description provided.'}

### Code Changes (Git Diff):
```diff
{files_diff}
```

Please review these changes and return your response in the requested JSON structure."""

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
        }

        # Enable JSON response format if supported
        if self.provider in ("openai", "gemini", "groq"):
            payload["response_format"] = {"type": "json_object"}

        url = f"{self.base_url}/chat/completions"
        logger.info("Sending review request to %s (model: %s, timeout: %ds)", self.base_url, self.model, self.timeout)
        resp = self.session.post(url, json=payload, timeout=self.timeout)
        resp.raise_for_status()

        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        return self._parse_response(content)

    def _parse_response(self, content: str) -> ReviewResult:
        """Extract and parse JSON review payload from LLM output."""
        cleaned = content.strip()

        # Strip markdown code fences if present
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)
            cleaned = cleaned.strip()

        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError as e:
            # Fallback regex search for JSON object
            match = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if match:
                try:
                    parsed = json.loads(match.group(0))
                except json.JSONDecodeError:
                    parsed = {}
            else:
                parsed = {}

        if not parsed:
            logger.warning("Failed to parse JSON response from LLM: %s", content[:200])
            return ReviewResult(
                verdict="COMMENT",
                score=5,
                summary="Automated review completed, but output formatting could not be fully parsed.",
                key_points=["Review generated with unstructured response."],
                comments=[],
                raw_response=content,
            )

        raw_comments = parsed.get("comments", [])
        parsed_comments: List[ReviewComment] = []
        for c in raw_comments:
            if isinstance(c, dict) and "path" in c and "line" in c and "body" in c:
                try:
                    parsed_comments.append(
                        ReviewComment(
                            path=str(c["path"]),
                            line=int(c["line"]),
                            body=str(c["body"]),
                        )
                    )
                except (ValueError, TypeError):
                    continue

        verdict = str(parsed.get("verdict", "COMMENT")).upper()
        if verdict not in ("APPROVE", "REQUEST_CHANGES", "COMMENT"):
            verdict = "COMMENT"

        score = parsed.get("score", 7)
        try:
            score = max(1, min(10, int(score)))
        except (ValueError, TypeError):
            score = 7

        return ReviewResult(
            verdict=verdict,
            score=score,
            summary=str(parsed.get("summary", "Code review completed.")),
            key_points=list(parsed.get("key_points", [])),
            comments=parsed_comments,
            raw_response=content,
        )
