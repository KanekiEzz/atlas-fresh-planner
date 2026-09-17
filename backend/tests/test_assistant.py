"""Re-export and run assistant tests under backend/tests for make test integration."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.tests.test_assistant import TestAssistant

__all__ = ["TestAssistant"]
