"""Fail when a pitch/doc/UI float cannot be traced to outputs/logs JSON.

Historical audit statements may include an incorrect number only when the
same line explicitly calls it historic, corrected, or unverified.
"""
from __future__ import annotations
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NUMBER = re.compile(r"(?<![\w.])-?\d+\.\d{3,}(?![\w.])")
TARGETS = [ROOT / "README.md", ROOT / "AUDIT_REPORT.md", ROOT / "docs", ROOT / "web" / "src"]
EXTENSIONS = {".md", ".tsx", ".ts", ".jsx", ".js"}

def values(value):
    if isinstance(value, dict):
        for item in value.values(): yield from values(item)
    elif isinstance(value, list):
        for item in value: yield from values(item)
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        yield float(value)

logged = []
for path in (ROOT / "outputs" / "logs").glob("*.json"):
    logged.extend(values(json.loads(path.read_text())))

problems = []
for target in TARGETS:
    paths = [target] if target.is_file() else target.rglob("*") if target.exists() else []
    for path in paths:
        if not path.is_file() or path.suffix not in EXTENSIONS: continue
        for line_no, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            if re.search(r"historic|corrected|unverified|mismatch", line, re.I): continue
            for token in NUMBER.findall(line):
                number = float(token)
                tolerance = 0.5 * 10 ** (-len(token.split(".")[1]))
                if not any(abs(number - item) <= tolerance for item in logged):
                    problems.append(f"{path.relative_to(ROOT)}:{line_no}: {token} is not in outputs/logs JSON")
if problems:
    print("Untraceable claimed floats:", *problems, sep="\n")
    sys.exit(1)
print("Claimed-number guard passed.")
