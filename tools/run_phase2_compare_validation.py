"""Persist a live, deterministic Phase 2 /compare response for audit evidence."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from api.main import app


REQUEST = {
    "vibration_freq_hz": 17.3,
    "vibration_amp_px": 3.0,
    "clutter_level": 0.35,
    "noise_rate_hz_per_px": 5.0,
    "range_km": 1000,
    "angular_offset_deg": 0,
    "acquisition_cone_px": 64,
    "seed": 812,
}


def main() -> None:
    response = TestClient(app).post("/compare", json=REQUEST)
    response.raise_for_status()
    result = response.json()
    output = ROOT / "outputs" / "logs" / "phase2_compare_seed812.json"
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    rms = {name: result[name]["rms_error_px"] for name in (
        "classical_frame_baseline", "event_only_no_ai", "scintilla"
    )}
    if len(set(rms.values())) != 3:
        raise SystemExit(f"Comparison paths did not produce three distinct RMS values: {rms}")
    print(f"Persisted {output}: {rms}")


if __name__ == "__main__":
    main()
