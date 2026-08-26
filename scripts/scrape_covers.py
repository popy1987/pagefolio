#!/usr/bin/env python3
"""Batch scrape covers (compat wrapper)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pagefolio.covers import main

if __name__ == "__main__":
    main()
