#!/usr/bin/env python3
"""Main CLI entry point for AI PR Review Agent."""

import argparse
import logging
import sys

from src.config import load_config
from src.agent import PRAgent


def main():
    parser = argparse.ArgumentParser(description="AI PR Review Agent with Telegram alerts")
    parser.add_argument("--repo", help="Target GitHub repository (owner/repo)")
    parser.add_argument("--pr", type=int, help="Target Pull Request number")
    parser.add_argument("--provider", help="LLM provider (gemini, deepseek, groq, openai)")
    parser.add_argument("--model", help="LLM model name")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose debug logging")

    args = parser.parse_args()

    # Logging setup
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    config = load_config()

    if args.repo:
        config.github_repository = args.repo
    if args.pr:
        config.pr_number = args.pr
    if args.provider:
        config.llm_provider = args.provider
    if args.model:
        config.llm_model = args.model

    try:
        config.validate()
    except ValueError as e:
        logging.error("Configuration error: %s", e)
        sys.exit(1)

    agent = PRAgent(config)
    success = agent.run(pr_number=args.pr)

    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
