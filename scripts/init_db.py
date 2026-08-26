#!/usr/bin/env python3
"""Initialize reading.db (compat wrapper)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pagefolio.db import init_db

if __name__ == "__main__":
    print(init_db())
