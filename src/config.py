"""Configuration management for the PR Review Agent."""

import os
from dataclasses import dataclass, field
from typing import List, Optional

# Load local .env if python-dotenv is installed
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


DEFAULT_EXCLUDED_PATTERNS = [
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "Pipfile.lock",
    "Cargo.lock",
    "go.sum",
    "composer.lock",
    "*.min.js",
    "*.min.css",
    "*.map",
    "*.svg",
    "*.png",
    "*.jpg",
    "*.jpeg",
    "*.gif",
    "*.ico",
    "*.woff",
    "*.woff2",
    "*.ttf",
    "dist/*",
    "build/*",
    ".next/*",
    ".nuxt/*",
]


@dataclass
class Config:
    """Holds agent configuration loaded from environment or CLI."""

    # GitHub Settings
    github_token: str = field(
        default_factory=lambda: os.getenv("GITHUB_TOKEN", "")
    )
    github_repository: str = field(
        default_factory=lambda: os.getenv("GITHUB_REPOSITORY", "")
    )
    github_event_path: Optional[str] = field(
        default_factory=lambda: os.getenv("GITHUB_EVENT_PATH")
    )
    pr_number: Optional[int] = field(
        default_factory=lambda: int(os.getenv("PR_NUMBER"))
        if os.getenv("PR_NUMBER")
        else None
    )

    # Telegram Settings
    telegram_bot_token: str = field(
        default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN", "")
    )
    telegram_chat_id: str = field(
        default_factory=lambda: os.getenv("TELEGRAM_CHAT_ID", "")
    )

    # LLM Settings
    llm_api_key: str = field(
        default_factory=lambda: os.getenv("LLM_API_KEY", os.getenv("GEMINI_API_KEY", ""))
    )
    llm_provider: str = field(
        default_factory=lambda: os.getenv("LLM_PROVIDER", "gemini").lower()
    )
    llm_model: str = field(
        default_factory=lambda: os.getenv("LLM_MODEL", "")
    )
    llm_base_url: Optional[str] = field(
        default_factory=lambda: os.getenv("LLM_BASE_URL")
    )

    # Review Tuning
    max_diff_lines: int = field(
        default_factory=lambda: int(os.getenv("MAX_DIFF_LINES", "1500"))
    )
    excluded_patterns: List[str] = field(
        default_factory=lambda: DEFAULT_EXCLUDED_PATTERNS
    )

    def validate(self) -> None:
        """Validate required settings."""
        missing = []
        if not self.github_token:
            missing.append("GITHUB_TOKEN")
        if not self.telegram_bot_token:
            missing.append("TELEGRAM_BOT_TOKEN")
        if not self.telegram_chat_id:
            missing.append("TELEGRAM_CHAT_ID")
        if not self.llm_api_key:
            missing.append("LLM_API_KEY / GEMINI_API_KEY")

        if missing:
            raise ValueError(
                f"Missing required environment variables: {', '.join(missing)}"
            )


def load_config() -> Config:
    """Instantiate and return configuration."""
    return Config()
