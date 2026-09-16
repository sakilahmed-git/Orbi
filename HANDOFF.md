# Scintilla Phase 2 handoff

## Verified on 2026-09-16

- `pip install -r requirements.txt` installed the pinned scikit-learn 1.8.0.
- The discriminator was retrained and reserialized under 1.8.0. Loading it with
  `InconsistentVersionWarning` promoted to an error succeeds, and
  `tools/check_model_version.py` confirms that both the artifact and runtime
  declare 1.8.0.
- A fresh FastAPI `POST /compare` run using seed 812 is saved verbatim at
  `outputs/logs/phase2_compare_seed812.json`. Its RMS errors are
  5.580439998539663 px for the classical frame-camera baseline,
  15.345482274996947 px for event-only/no-AI classical lock-on, and
  5.446402091379099 px for full Scintilla. The three returned traces differ.
- `/compare` is a synthetic simulation endpoint. Its returned label explicitly
  says so; it is not a hardware or real e-STURT result.
- The compare page sends each control set to `/compare`. Its heatmap marker
  renders the actual `/envelope-sweep` grid and snaps to the returned grid
  coordinates, rather than drawing a decorative gradient.

## Outstanding before Phase 3

- Real e-STURT ingestion is qualitative only. No quantitative real-data
  disturbance or lock-on result has been established.
- Section 7 is a precomputed, synthetic surrogate envelope. It does not rerun
  a sweep for every compare slider adjustment.
- The landing mission-control dashboard remains a clearly labeled client-side
  simulation; `/demo`, `/compare`, and `/envelope` are the backend-backed
  synthetic views.
