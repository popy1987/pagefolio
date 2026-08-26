#!/usr/bin/env python3
"""Start web server (compat wrapper)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pagefolio.server.app import run_server

if __name__ == "__main__":
    run_server()
