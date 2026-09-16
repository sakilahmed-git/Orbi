# Result-claim verification changelog

This record distinguishes the prior audit's evidence state from the current,
reproducible artifacts. Historical values in `AUDIT_REPORT.md` remain there as
explicitly marked audit discrepancies, not as current result claims.

| Claimed number | Verified number | Evidence | Status |
| --- | --- | --- | --- |
| 47.6498353138 +/- 3.2585193572 px | 47.6184955400 +/- 3.1692751721 px | `outputs/logs/section5_heldout_generalization.json` (`summary.classical_mean_error_px_mean` / `_std`) | CORRECTED in `SCINTILLA_BUILD_PLAN.md:94` |
| 8.539012500576732 px (clean) | 8.539012500576732 px (clean) | Fresh fixed-seed 42 invocation of `ai.lockon.evaluate_classical_baseline`; persisted at `outputs/logs/section4_classical_baseline.json` | NEWLY VERIFIED |
| 48.11847573414365 px (noisy) | 48.11847573414365 px (noisy) | Same fresh fixed-seed 42 invocation; plot regenerated at `outputs/plots/section4_classical_failure.png` | NEWLY VERIFIED |
| Seed-7 harness check | 7.969880502427609 px clean; 52.38281256416269 px noisy | Fresh `evaluate_classical_baseline(seed=7)` invocation, persisted in `outputs/logs/section4_classical_baseline_seed7.json` | REPRODUCTION CONTROL |

The Section 4 run uses seed 42, 1 s at 200 fps, a 20 Hz beacon, 15 Hz / 2.5 px
vibration, and 5.0 Hz/pixel sensor noise. It is deterministic by design.
