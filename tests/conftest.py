"""Test bootstrap: make repository-root modules importable under pytest.

Keeping this in the test suite avoids relying on pytest's import-mode defaults
or on a globally configured PYTHONPATH.
"""

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
