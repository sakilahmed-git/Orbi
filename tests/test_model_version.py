import subprocess
import sys
from pathlib import Path


def test_model_pickle_matches_pinned_sklearn() -> None:
    root = Path(__file__).resolve().parents[1]
    subprocess.run([sys.executable, "tools/check_model_version.py"], cwd=root, check=True)
