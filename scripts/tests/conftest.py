"""conftest.py — add scripts/ directory to sys.path so that backtest_weekly can be imported."""

import sys
from pathlib import Path

# Ensure the scripts/ directory is on sys.path so `import backtest_weekly` works
# regardless of where pytest is invoked from.
scripts_dir = Path(__file__).resolve().parent.parent
if str(scripts_dir) not in sys.path:
    sys.path.insert(0, str(scripts_dir))
