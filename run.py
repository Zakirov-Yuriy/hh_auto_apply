"""Entry point for hh_auto_apply."""

from __future__ import annotations

import sys

from hh_auto_apply.cli.main import main

if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--local-ocr-demo":
        from hh_auto_apply.local_ocr_demo.demo import main as local_demo_main

        local_demo_main()
        raise SystemExit(0)
    raise SystemExit(main())
