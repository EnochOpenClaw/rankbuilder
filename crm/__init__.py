"""
RankBuilder CRM — FastAPI Backend
Phase 1: Lead capture API + SQLite database + HOS client portal
"""

import sys
from pathlib import Path

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.app import app  # noqa: F401

__all__ = ["app"]
