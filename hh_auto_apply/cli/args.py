"""Command-line argument parser."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, replace

from hh_auto_apply.core.config import Config


@dataclass
class CLIArgs:
    """Parsed command-line arguments."""

    headless: bool = False
    dry_run: bool = False
    verbose: bool = False
    query: str | None = None


def parse_args() -> CLIArgs:
    """Parse command-line arguments.

    Returns:
        CLIArgs: Parsed arguments.
    """
    parser = argparse.ArgumentParser(description="Auto-apply to vacancies on hh.ru")
    parser.add_argument("--headless", action="store_true", help="Запуск браузера без UI")
    parser.add_argument("--dry-run", action="store_true", help="Не отправлять отклики, только сканировать")
    parser.add_argument("--verbose", action="store_true", help="Подробные логи")
    parser.add_argument("--query", type=str, help="Переопределить запрос поиска")

    args = parser.parse_args()
    return CLIArgs(
        headless=bool(args.headless),
        dry_run=bool(args.dry_run),
        verbose=bool(args.verbose),
        query=args.query,
    )


def apply_cli_overrides(cfg: Config, cli_args: CLIArgs) -> Config:
    """Apply CLI arguments as overrides to the config.

    Args:
        cfg: Base configuration from environment.
        cli_args: Parsed CLI arguments.

    Returns:
        Config: Updated configuration.
    """
    updates = {
        "headless": cli_args.headless,
        "verbose": cli_args.verbose,
    }
    if cli_args.query:
        updates["search_query"] = cli_args.query.strip()

    return replace(cfg, **updates)
