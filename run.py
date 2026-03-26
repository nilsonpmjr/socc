"""
run.py
Backward-compatible entrypoint for the current MVP runtime.
Execute: python run.py
"""
import sys
from pathlib import Path

# Keep the repository root importable for both legacy and installable layouts.
sys.path.insert(0, str(Path(__file__).parent))

from socc.cli.main import main


if __name__ == "__main__":
    raise SystemExit(main(["serve"]))
