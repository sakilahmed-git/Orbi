import subprocess
import sys
from pathlib import Path

def test_claimed_numbers_are_traceable():
    root = Path(__file__).resolve().parents[1]
    subprocess.run([sys.executable, "tools/check_claimed_numbers.py"], cwd=root, check=True)
