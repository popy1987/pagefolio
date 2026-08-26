#!/usr/bin/env python3
"""Pagefolio entry point.

  python run.py          # start web UI
  python run.py init     # initialize reading.db
  python run.py scrape   # batch scrape covers (pass extra args)
"""

from __future__ import annotations

import sys


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "serve"

    if cmd == "serve":
        from pagefolio.server.app import run_server

        run_server()
    elif cmd == "init":
        from pagefolio.db import init_db

        print(init_db())
    elif cmd == "scrape":
        sys.argv = ["scrape_covers", *sys.argv[2:]]
        from pagefolio.covers import main as scrape_main

        scrape_main()
    else:
        raise SystemExit(f"Unknown command: {cmd}\nUsage: python run.py [serve|init|scrape]")


if __name__ == "__main__":
    main()
