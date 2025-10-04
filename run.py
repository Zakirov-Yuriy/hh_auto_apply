import sys

from hh_auto_apply.app import App
from hh_auto_apply.config import build_cli_cfg

if __name__ == "__main__":
    app_cfg, dry = build_cli_cfg()
    app = App(app_cfg, dry_run=dry)
    sys.exit(app.run())
