"""Main entry point for the application."""

from __future__ import annotations

import sys
from pathlib import Path

from hh_auto_apply.cli.args import apply_cli_overrides, parse_args
from hh_auto_apply.core.config import Config


def main() -> int:
    """Main entry point.

    Returns:
        int: Exit code.
    """
    # Parse CLI arguments
    cli_args = parse_args()

    # Load configuration from environment
    cfg = Config.from_env()

    # Apply CLI overrides
    cfg = apply_cli_overrides(cfg, cli_args)

    # Import application layer only after config is ready
    try:
        from hh_auto_apply.application.run_session import App

        # Create and run the application
        app = App(cfg, dry_run=cli_args.dry_run)
        return app.run()

    except ImportError as e:
        print(f"Error: Failed to import application module: {e}", file=sys.stderr)
        return 3
    except Exception as e:
        print(f"Error: Unexpected error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
