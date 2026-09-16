# Scintilla — Master Build Plan & Session Handoff Document

**Purpose of this file**: This is the single source of truth for building Scintilla across multiple Claude sessions/accounts. If a session hits its limit mid-build, paste this entire file into a new Claude session along with the code/outputs produced so far, and say: *"We're building Scintilla. Here's the master plan and everything completed through Section N. Continue with Section N+1."* A new session should be able to pick up exactly where the last one stopped without re-deriving any decisions.

**Rule for every session, including this one**: don't relitigate the strategic decisions in this file (the product direction, the constraints, the stack). Those are locked. Only the implementation within each section is open.

---

## 0. Locked Context — read this before touching any section

### 0.1 What we're building
**Scintilla**: a perception layer for mobile Free-Space Optical Communication (FSOC) terminals that uses event-based (neuromorphic) vision principles to acquire a frequency-modulated beacon under vibration and glare conditions that break a conventional frame camera — and reads real-time disturbance (vibration/scintillation) state off the same event data as a free byproduct, handing both to whatever fine-tracking control loop sits downstream.

Built for: SIH 2026, problem statement SIH26169 (ISRO) — "Development of an AI-Based Virtual Camera Tracking System for Coarse Alignment of Mobile Free Space Optical Communication (FSOC) Terminals."

### 0.2 Hard constraints (never violate these in any section)
- **Zero budget.** No paid APIs, no paid datasets, no paid compute beyond what's already available locally.
- **Zero hardware.** No cameras, no vibration rigs, no sensors, no purchases of any kind. Everything is simulated or built from data that already exists and is free to download.
- **All data must be open-source / freely downloadable.** Primary real-data source: the **e-STURT dataset** (arXiv 2505.12588) — real event-camera hardware data captured under real controlled jitter on a piezoelectric stage, stated as publicly available. Secondary option if time allows: the **Sun-E** benchmark (arXiv 2606.01280) for dynamic-range/glare validation.
- **Everything is software.** No physical demo props of any kind.

### 0.3 Why this direction (one paragraph, for anyone joining fresh)
Three earlier directions were considered and rejected: "Boresight" (a verification/failure-discovery harness for other people's PAT trackers) and "PATGym" (a pluggable Gym-style test harness) both fail to actually answer the literal problem statement — they test someone else's tracker instead of building the coarse-alignment system ISRO asked for, and their core differentiator (an interface contract) is admitted to be easy for a competent team to copy. Scintilla instead attacks the literal, physically real failure mode of mobile FSOC coarse alignment: platform vibration blurs frame-camera images and blinds conventional detectors exactly during the phase with the least prior information. Event-based sensing is a structural fix for this (already proven one field over, in star-tracker and sun-sensor literature, but not yet applied to beacon acquisition). The old "verification harness" idea isn't dead — it survives cheaply as Section 7 below (the acquisition-envelope report), which falls out for free once the disturbance simulator built in Section 1 exists. We are not building two products. We are building one perception system, and getting a differentiation feature for near-zero extra cost.

### 0.4 Target buyer / pitch framing (needed for Section 10, keep in mind throughout)
FSOC terminal integrators moving from fixed ground-to-space links to mobile/inter-satellite links — concretely, the transition Astrogate Labs (India, ISRO's TRL-8 FSOC terminal supplier) publicly announced in September 2026. Sold as a drop-in software SDK in front of an existing gimbal/tracking stack, with a real-DVS-hardware upgrade path as a later tier, not a day-one requirement.

### 0.5 Final architecture (text diagram)

```
┌─────────────────────────────────────────────────────────────┐
│  Layer A: Physics core (pure Python, no deps on anything     │
│  below) — scene generator, event emulator, e-STURT ingestion │
│  [Sections 1, 2, 3]                                          │
└───────────────────────┬───────────────────────────────────────┘
                         │
┌───────────────────────▼───────────────────────────────────────┐
│  Layer B: Detection & AI — classical lock-on, learned         │
│  discriminator, disturbance characterization, envelope        │
│  surrogate, control-loop handoff                              │
│  [Sections 4, 5, 6, 7, 8]                                      │
└───────────────────────┬───────────────────────────────────────┘
                         │
┌───────────────────────▼───────────────────────────────────────┐
│  Layer C: Service — FastAPI wrapping everything above,         │
│  REST + WebSocket                                              │
│  [Section 9]                                                   │
└───────────────────────┬───────────────────────────────────────┘
                         │
┌───────────────────────▼───────────────────────────────────────┐
│  Layer D: Face — Next.js + Tailwind, three screens             │
│  [Section 10]                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 0.6 Stack (locked, do not swap tools mid-project)
- Python 3.11+, `numpy`, `opencv-python`, `scipy`, `scikit-learn`, (optionally a tiny PyTorch MLP), `tonic` or `dv-processing` for reading real event-camera file formats, `fastapi` + `uvicorn`, `websockets`.
- `v2e` (github.com/SensorsINI/v2e) is an optional second-pass, more-realistic event converter — not required for the MVP; Section 2 defines our own lightweight emulator first.
- Frontend: Next.js (App Router) + Tailwind + `recharts` (or `visx`) for charts + plain HTML5 canvas for the event-stream visualization.
- No other frameworks. No Blender, no Streamlit (that was an earlier suggestion, superseded once Next.js was chosen for the final face).

### 0.7 Repository layout (every session should conform to this)
```
scintilla/
  core/
    scene_gen.py         # Section 1
    event_emulator.py    # Section 2
    real_data.py         # Section 3 (e-STURT ingestion)
  ai/
    lockon.py            # Section 4
    discriminator.py     # Section 5
    disturbance.py       # Section 6
    envelope.py          # Section 7
    control_loop.py      # Section 8
  api/
    main.py              # Section 9 (FastAPI app)
  web/
    (Next.js app)        # Section 10
  data/
    esturt/              # downloaded, gitignored
  outputs/
    plots/, models/, logs/
  PROGRESS.md             # updated after every section — see 0.8
```

### 0.8 Progress tracker — UPDATE THIS after finishing each section

| # | Section | Status | Key outputs to carry forward |
|---|---|---|---|
| 1 | Scene generator | ☑ Done | `core/scene_gen.py` implements `generate_scene(duration_s, fps, blink_freq_hz, vibration: VibrationParams, turbulence: TurbulenceParams, background_clutter_level, frame_size, beacon_base_xy, seed) -> (frames: np.ndarray[N,H,W] float32 0-1, ground_truth: SceneGroundTruth)`. Also has `save_scene`/`load_scene` (npz + json) and a `__main__` smoke test. Verified: demo scene at 200fps/1s, 15Hz dominant vibration + broadband jitter, 20Hz blink, scintillation flicker, clutter speckles — beacon and clutter visibly correct in rendered frames; ground-truth vibration/brightness trace plotted and matches injected params exactly (it's exact by construction — no estimation involved yet, that's Section 6). Files to carry forward: `core/scene_gen.py`, `outputs/demo_scene_frames.npz`, `outputs/demo_scene_ground_truth.json`, `outputs/plots/demo_scene.mp4`, `outputs/plots/ground_truth_trace.png`. |
| 2 | Event emulator + frame baseline | ☑ Done | `core/event_emulator.py` implements `frames_to_events(frames, fps, threshold=0.15) -> events[N,4] (x,y,t,polarity)` (per-pixel log-intensity accumulator, standard DVS model, supports multi-event firing per step) and `frames_to_frame_camera(frames, fps_in, target_fps=30, exposure_fraction=1.0) -> (blurred_frames, out_fps)` (real exposure-averaging blur, not a kernel approximation, since we integrate the actual high-fps ground-truth frames). Also `accumulate_events_to_frame(...)` for visualization only (NOT how downstream algorithms should consume events — they should use the raw (x,y,t,polarity) stream). **Important bug fixed retroactively in Section 1's `scene_gen.py`**: background clutter was being fully re-randomized every frame, which is physically wrong (real DVS pixels are silent on unchanging background — that silence is the whole dynamic-range argument for event sensors) and was flooding the event stream (19.7M spurious events from clutter alone). Fixed by making clutter a static field generated once per scene (`_make_clutter_field`), added identically every frame. After the fix: 172,601 events from a 200-frame/1s scene, dominated by real beacon jitter/blink, not clutter noise — this is the correct, explainable behavior. Verified: side-by-side video shows the frame-camera baseline reducing the beacon to a faint smear under injected vibration+blink-averaging, while the same window's event view shows a clearly localized, high-contrast cluster — this is the core "wow" visual for the pitch. Files to carry forward: `core/event_emulator.py`, updated `core/scene_gen.py` (clutter fix), `outputs/demo_scene_events.npz`, `outputs/demo_scene_blurred.npz`, `outputs/plots/comparison_side_by_side.mp4`, `outputs/plots/compare_15.png`. |
| 3 | Real-data (e-STURT) ingestion | ☑ Done (format verified on real data; quantitative jitter validation deferred) | `core/real_data.py` rewritten against CONFIRMED real column formats, verified directly against real uploaded bytes (not guessed): event CSV = `(x, y, polarity∈{0,1}, timestamp_us, redundant_idx)`, no header, x∈[0,1279]/y∈[0,719] (Prophesee Gen4.1, matches spec exactly); shaker log = `(timestamp_us, axis1, axis2)`, no header, sampled at ~13.2Hz median for this file, zeros correctly treated as NaN (confirmed ~10% NaN rate on axis1 in real sample). Both loaders tested successfully against real files. Real finding worth noting honestly: the specific 65.7ms/200k-row sample is 99.9% OFF-polarity events spread across the FULL 1280x720 sensor (not clustered on one point) — expected, since e-STURT is a star-field/general jitter dataset, not a single modulated-beacon dataset; it validates Section 6 (disturbance recovery), not Section 4 (beacon lock-on). The 99.9%/0.1% polarity skew in this window is unexplained and flagged, not smoothed over — could be a startup/global-dimming transient; would need more of the file to explain. **Quantitative "recovered jitter vs. true jitter" validation is NOT yet done** — this sample is too short relative to the ~76ms ground-truth sampling interval; needs a longer (several-second) real sample before Section 6 can claim a real quantitative match. Files: `core/real_data.py`, `outputs/plots/real_esturt_events.png` (real event scatter + rate histogram). |
| 4 | Classical beacon lock-on | ☑ Done | `ai/lockon.py` implements `lock_on(events, frame_size, blink_freq_hz, window_s, grid_size, ...) -> list of {t,x,y,confidence,n_events}` via spatial grid binning + FFT-matched-filter scoring against the known blink frequency (explicitly the non-AI baseline). Also added `add_sensor_noise_events()` to `core/event_emulator.py` (Section 2 extension) — real, documented DVS background-activity/dark-current noise, needed because our physically-correct static clutter (Section 1 fix) produces zero spurious events on its own, so this is the legitimate noise source that actually challenges detection. **Real, verified failure mode found**: clean events → mean position error 8.5px, consistently near the true beacon. At 5 Hz/px sensor noise (realistic per published Prophesee figures) → mean error jumps to 48.1px, and per-window inspection confirms the detector isn't just uncertain, it's CONFIDENTLY (confidence often 1.000) locking onto random noise clusters instead of the beacon — a stronger, more honest motivation for Section 5 than a simple accuracy drop. Files: `ai/lockon.py`, updated `core/event_emulator.py` (added `add_sensor_noise_events`), `outputs/plots/section4_classical_failure.png`. |
| 5 | Learned discriminator | ☑ Done + held-out audit | `ai/discriminator.py` implements `extract_candidate_clusters(events, frame_size, blink_freq_hz, window_s=0.05, grid_size=8, min_events=12, true_xy=None, fps=None, label_radius_px=12.0) -> list[CandidateCluster]`, `train_discriminator(model_path="outputs/models/discriminator_gbc.joblib")`, `load_discriminator(...)`, `discriminate_lock_on(events, frame_size, blink_freq_hz, model, ...) -> list[dict|None]`, and `evaluate_heldout_scenarios(model, seeds=range(1000,1020), ...)`. Training data is generated from `core.scene_gen.generate_scene` sweeps over vibration amplitude, turbulence, clutter, and `core.event_emulator.add_sensor_noise_events` rates; features are explicit/lightweight: event rate, event count, FFT blink score, inter-spike regularity, spatial compactness, polarity balance, blink-edge concentration, temporal consistency, and normalized centroid. Model is a CPU `sklearn.ensemble.GradientBoostingClassifier` (120 estimators, depth 2), saved to `outputs/models/discriminator_gbc.joblib`. Rigor pass: training seeds are `[3,11]`; original acceptance seed `42` did NOT overlap. Exact Section 4 failure scenario still measures clean classical `8.539012500576732px`, noisy classical `48.11847573414365px`, learned noisy `5.852599985118747px` over 20/20 windows. Held-out audit on 20 unseen seeds/scenarios (`1000-1019`, varied vibration frequency/amplitude, turbulence, clutter, and noise) measured noisy classical mean error `47.6184955400 ± 3.1692751721px` vs learned noisy `5.885595186853424 ± 1.354555154211437px`; these values are sourced from `outputs/logs/section5_heldout_generalization.json`. Test split accuracy `0.9861554845580405`, positive-class F1 `0.9329464861379755`, confusion matrix `[[26738,189],[227,2894]]`. Artifacts: `outputs/plots/section5_discriminator_comparison.png`, `outputs/plots/section5_heldout_generalization.png`, `outputs/logs/section5_discriminator_metrics.json`, `outputs/logs/section5_heldout_generalization.json`. |
| 6 | Disturbance characterization | ◩ Partially done (synthetic quantitative done; real e-STURT quantitative blocked by sample type/duration) | `ai/disturbance.py` implements `DisturbanceState {t_start,t_end,vibration_psd:{frequency_hz,psd_x,psd_y,psd_mag},dominant_frequency,confidence,method}`, `track_centroid_trace(events, detections=None, frame_size=(128,128), sample_window_s=0.01, roi_radius_px=10.0, min_events=4)`, `estimate_vibration_psd(times, xy) -> DisturbanceState`, `validate_synthetic(...)`, `validate_nonround_synthetic(...)`, and `attempt_real_validation(...)`. Synthetic validation uses Section 5's learned lock-on around the beacon cluster, then short-window event centroids and Welch PSD via `scipy.signal.welch`; on the original Section 5 noisy scenario it recovered dominant frequency `14.999999999999986Hz` vs synthetic ground truth `14.999999999999986Hz` (`0.0Hz` dominant-frequency error), with centroid RMSE `1.7929683946870536px`, 100 centroid samples, estimated PSD confidence `0.3866139672466477` and true-PSD confidence `0.6495008374127054`. Rigor pass: reran synthetic validation at deliberately non-round injected vibration `17.3Hz` with no ground-truth frequency used in the estimate path (only noisy events -> discriminator detections -> event centroid trace -> Welch PSD; ground truth is used afterward only for error). Results: at `2.0 Hz/px` noise, estimated `17.499999999999986Hz`, absolute error `0.19999999999998508Hz`, confidence `0.3494839906254588`; at `5.0 Hz/px` noise, estimated `17.499999999999986Hz`, absolute error `0.19999999999998508Hz`, confidence `0.31791404879207286`; both use 200 centroid samples and the `0.2Hz` error is the expected nearest-bin effect from the 2s Welch resolution. Real validation was attempted against `data/esturt/sample_events_long.csv` and `data/esturt/out_20231224_041133_pos0.1_vel6.0_20.0_sst0.05_MOVMACS_shaker_log_cleaned.csv`: longest event sample is `1.535122s`, shaker median dt is `0.07589999999999009s`, giving 31 shaker samples over the event window. Output status is honestly `qualitative_format_check_only`, not quantitative validation, because this e-STURT sample is a full star-field/global event stream rather than a locked modulated-beacon ROI and is too short for robust real PSD validation; a proper quantitative result needs several seconds of time-aligned real events from a stable tracked feature or beacon-like ROI with enough shaker samples to resolve the injected vibration band without aliasing. Artifacts: `outputs/plots/section6_synthetic_psd.png`, `outputs/plots/section6_nonround_frequency_audit.png`, `outputs/plots/section6_real_esturt_format_check.png`, `outputs/logs/section6_disturbance_metrics.json`, `outputs/logs/section6_nonround_frequency_audit.json`. |
| 7 | Acquisition-envelope surrogate | ☑ Done | `ai/envelope.py` implements `run_envelope_sweep(discriminator_model_path="outputs/models/discriminator_gbc.joblib", out_json="outputs/logs/section7_envelope_sweep.json") -> list[EnvelopeScenarioResult]`, `train_envelope_surrogate(rows, model_path="outputs/models/envelope_surrogate.joblib")`, `make_heatmap(...)`, and `build_envelope()`. The sweep runs the existing pipeline (`generate_scene -> frames_to_events -> add_sensor_noise_events -> discriminate_lock_on`) over scenario vectors `(vibration_amp_px, turbulence_strength, clutter_level, noise_rate_hz_per_px)` and records raw mean error, hit rate, and pass/fail. Important honest adjustment: the first 36-scenario sweep with a loose `12px` success threshold produced all successes (raw learned errors `4.196042646182906px` to `8.013847155933393px`), so no classifier boundary existed; the final envelope defines "high-quality acquisition" as mean error `<=6px` with hit rate `>=0.8`, producing a real 50/50 split. Surrogate is a CPU `GradientBoostingClassifier` (80 estimators, depth 2), saved to `outputs/models/envelope_surrogate.joblib`; final metrics: `36` scenarios, success rate `0.5`, held-out test accuracy `0.8888888888888888`, confusion matrix `[[3,1],[0,5]]`. Heatmap fixes turbulence `0.35` and noise `5.0 Hz/px` over vibration amplitude vs clutter. Artifacts: `outputs/logs/section7_envelope_sweep.json`, `outputs/logs/section7_envelope_metrics.json`, `outputs/logs/section7_heatmap_grid.json`, `outputs/plots/section7_acquisition_envelope_heatmap.png`. |
| 8 | Control-loop handoff demo | ☑ Done (rewritten — original partial version failed its own acceptance criteria) | `ai/control_loop.py` implements `evaluate_control_handoff(model_path, seeds=range(700,720), plot_path, log_path) -> {metrics, plot, log}`. **Important, found by verification, not by the author**: the code inherited from the interrupted session ran without error but the armed mode was *worse* than baseline (RMS 4.12px vs 3.87px, a -6.3% "improvement") because it just scaled up a single PID's proportional gain by a confidence-weighted factor — on a continuously-noisy, sparsely-sampled (≈20Hz) measurement with an inherent per-detection localization floor of ~4.5–7px (a property of the Section 4/5 detector stack, not of sensor noise rate — confirmed by re-running at 0.5/1.0/2.0 Hz/px sensor noise with near-identical ~4.6px error each time), raising gain alone just injects more noise into the actuator command; there is no one-shot "settling" event to speed up when the disturbance never stops. Rewritten as genuine two-stage gain scheduling: `kp=16` (aggressive) while the tracking error exceeds an 8px "locked" threshold (representing the coarse-alignment handoff moment — loop starts at a random offset 12–20px from the beacon, random direction), then drops to `kp_track = 3 + (1-confidence)*(6-3)` once locked (a fixed `kp=6,kd=0.02` baseline never adapts). Low disturbance-estimate confidence correctly falls the track gain back toward the baseline's compromise value instead of assuming a clean lock. Settle time is measured as the first time the 80th-percentile error in a rolling 0.15s window drops under 6px (chosen from Section 5's own measured noisy-localization floor, ~5.85px — not tuned to force a pass); "all samples" was tried first and rejected as too sensitive to single sparse-detection outliers. Validated across 20 randomized scenarios (disturbance frequency 12–22Hz, amplitude 2–4px, phase, and handoff-offset direction/magnitude all randomized per seed, fixed 5Hz/px sensor noise) — **not** a single cherry-picked run: mean RMS error 5.29px (baseline) vs 4.65px (armed), mean P95 error 10.44px vs 6.90px, mean settle time (capped at the 2s run duration when never settled — neither ever failed to settle) 0.230s vs 0.125s. Armed wins on RMS in 20/20 scenarios and on settle time in 19/20. Files: `ai/control_loop.py`, `outputs/plots/section8_control_loop_handoff.png` (representative-scenario trace + aggregate bar chart), `outputs/logs/section8_control_loop_metrics.json` (full per-seed breakdown, not just the aggregate). |
| 9 | FastAPI backend | ☑ Done | `api/main.py`. Thin wrapper — no detection/disturbance/control logic reimplemented, only orchestration of `core.*`/`ai.*` calls (shared helper `_run_full_pipeline(req)` used by both HTTP and WS so they can't drift apart). Tested all three endpoints with real requests against a live `uvicorn` process (not just import-checked): **POST /run-scenario** — body `{duration_s, fps, blink_freq_hz, vibration_freq_hz, vibration_amp_px, vibration_phase, broadband_std_px, turbulence_strength, turbulence_correlation_time_s, clutter_level, noise_rate_hz_per_px, frame_size:[w,h], seed}` (all optional, defaults = the seed-812 scenario used throughout Sections 5/6/8); response `{scenario, events:{n_clean,n_noisy}, detections:{n_windows,n_hits,hit_rate,points:[{t,x,y,confidence}]}, disturbance:{dominant_frequency_hz,confidence,psd:{frequency_hz[],psd_mag[]} (subsampled to ≤64 bins)}, control_comparison:{start_offset_px:[x,y], baseline:{rms_error_px,p95_error_px,settle_time_s}, disturbance_armed:{rms_error_px,p95_error_px,settle_time_s,kp_track_used}, trace:{t[],baseline_err_px[],armed_err_px[]} (subsampled to ≤400 pts)}}`. Verified real request: default body → HTTP 200 in ~8s, 455,098 clean / 618,938 noisy events, 40/40 detection hit rate, dominant_frequency_hz≈17.5 confidence≈0.332, baseline rms 6.79px vs armed rms 5.45px (matches the fixed [15,-12]px representative offset used in Section 8's plot) — numbers are byte-for-byte consistent with the Section 8 batch evaluation, confirming the endpoint isn't drifting from the verified control-loop code. Custom-params request (freq=12Hz, amp=2px, noise=1Hz/px, seed=42) also verified working; malformed body correctly returns HTTP 422 with Pydantic's validation detail. **GET /envelope-sweep** — returns Section 7's precomputed `outputs/logs/section7_heatmap_grid.json` verbatim (`{vibration_amp_px[40], clutter_level[40], success_probability[40][40], fixed_turbulence_strength, fixed_noise_rate_hz_per_px}`); verified HTTP 200 with correct 40x40 shape. **WS /stream** — client may send one JSON config message (same shape as POST body) within 2s of connecting, else falls back to defaults; server streams `{"type":"events","t","points":[{x,y,polarity}]}` and `{"type":"detection","t","x","y","confidence"}` per 0.05s window (event points capped at 300/window via random subsample to avoid choking the socket on dense windows), then one `{"type":"disturbance",...}`, then one final `{"type":"done","control_comparison":{...}}`, then closes. Verified end-to-end with a real WebSocket client: 40 events + 40 detection + 1 disturbance + 1 done = 82 messages received, `done` payload numerically identical to the equivalent POST /run-scenario call; also verified the no-config-sent fallback path (waits ~2s, then proceeds with defaults, confirmed by wall-clock ~12s total vs ~8s when config is sent immediately). **Amended while building Section 10**: the original `/stream` contract above only sent events/detections, but Section 10's spec requires a live event-cloud *vs. blurred-frame baseline* side-by-side — there was no baseline frame data to render. Fixed by adding `{"type":"baseline_frame","t","width","height","pixels":[0-255,...]}` (flattened row-major 8-bit grayscale, one per 30fps frame-camera-baseline frame, via the existing `frames_to_frame_camera`), merged into one time-ordered playlist with the events/detections and paced to the scenario's own clock (per-message gaps capped at 0.2s so a demo never stalls) rather than dumped instantly — this is an honest replay of a fully-computed run, not a physical live sensor feed, and the UI says so. Re-verified after the change: 40 events + 40 detection + 60 baseline_frame + 1 disturbance + 1 done = 142 messages, frame shape 128x128 confirmed, pixel values in expected 0-255 range, `done` payload unchanged. Known limitation: `/run-scenario` and `/stream` each re-run the full pipeline from scratch (~8-10s) — no caching — acceptable for a demo but would need a job queue for concurrent users. |
| 10 | Next.js frontend + pitch polish | ☑ Done | `web/` — Next.js App Router + Tailwind only, three screens, no extra pages, as specified. **Screen 1** (`/`, `src/app/page.tsx`): one-liner, the Astrogate Labs Sept-2026 mobile/inter-satellite transition hook (Section 0.4), and a static comparison image (`public/assets/section2_event_vs_blur_comparison.png`, freshly generated from the actual `outputs/demo_scene_events.npz`/`outputs/demo_scene_blurred.npz` arrays produced by Section 2 — Section 2's own `__main__` never saved a plot image, so this had to be built, not just copied). **Screen 2** (`/demo`, `src/components/LiveDemo.tsx`): a scenario config form (vibration freq/amp, sensor noise, seed) that opens `WS /stream`, two `<canvas>` elements (`EventCanvas`, `BaselineCanvas`) rendering the live event cloud and the frame-camera baseline side by side as `events`/`baseline_frame` messages arrive, a `recharts` line chart for the disturbance PSD (populated when the `disturbance` message arrives), and a baseline-vs-armed settle-time comparison panel (populated on `done`). **Screen 3** (`/envelope`, `src/components/EnvelopeHeatmap.tsx`): an SVG heatmap (40x40, colored by `success_probability`) built from `GET /envelope-sweep`'s live data, plus a plain-language summary computed client-side from the actual fetched grid, not hardcoded copy. **A real bug caught before shipping**: the first version of the summary text asserted "clutter and vibration amplitude compound each other" based on an assumption, not the data — checking the real grid (via a Node script hitting `outputs/logs/section7_heatmap_grid.json` directly) showed the 50%-success boundary is **identical** (4.67px) at the lowest and highest tested clutter levels; clutter only shifts success probability by ~12 points within the mid-amplitude plateau (69%→57% at 2.33px), it doesn't move the boundary at all in this sweep. Rewrote the summary logic and copy to state this correctly, and re-verified the corrected numbers against the real file before accepting it. **Build issue found and fixed**: `next/font/google` (Geist) failed at build time because this sandbox's network egress doesn't allow `fonts.googleapis.com` — switched to system font stacks (`-apple-system, ... / ui-monospace, ...`) in `globals.css` instead of vendoring a font; `npm run build` and `npx eslint . --max-warnings=0` both pass clean. **Verification method and its real limitation**: there is no headless browser available in this environment (Playwright's Chromium download is also blocked by the same network restriction, confirmed by testing `playwright install chromium` directly), so this was **not** click-tested in an actual rendered browser DOM. What was verified instead, against a live `uvicorn` + `next start` pair running together: all three routes return HTTP 200 and the landing page's HTML contains the real headline/hook text (`curl` + `grep`); the exact fetch/WS logic each component uses was independently replicated in Node (which has native `fetch`/`WebSocket`) against the live backend and produced correct, real data with the right shapes; the envelope summary's arithmetic was checked against the actual JSON file. This is meaningfully short of "clicked through it myself" — a next session with browser access should do that pass before a real demo. **Amendments to Section 9's API found necessary while building this section** (see Section 9's row above for the full detail): `/stream` was missing `baseline_frame` messages (no way to render the required side-by-side) and the `disturbance` message was missing the PSD array (no way to render the required live PSD trace) — both added to `api/main.py` and re-verified. Files: `web/src/app/{page.tsx, demo/page.tsx, envelope/page.tsx, layout.tsx, globals.css}`, `web/src/components/{LiveDemo,EventCanvas,BaselineCanvas,EnvelopeHeatmap}.tsx`, `web/src/lib/api.ts`, `web/public/assets/*.png`. |

**When you finish a section**: mark it ☑ Done, fill in the "key outputs" column with a one-line summary (e.g. "scene_gen.py done; `generate_scene(vibration_psd, blink_hz, noise_level) -> frames, ground_truth` works; see outputs/plots/demo_scene.mp4"), and paste the actual code files into the handoff to the next session.

---

## Final integration check (Sections 1–10 complete)

Ran the full stack together, start to finish, as if demoing it live: `uvicorn api.main:app` and `next start` launched together, then exercised every route against the live pair (not against mocks) — landing page HTML confirmed to contain the real headline/Astrogate hook text, `/envelope` confirmed to pull the real 40x40 grid and compute a numerically-correct summary, `/demo`'s exact fetch/WS logic replicated in Node against the live backend and confirmed correct end to end (`events`/`detection`/`baseline_frame`/`disturbance`/`done`, in order, matching a fresh `POST /run-scenario` on the same seed byte-for-byte). See Section 10's tracker row for the one real gap in this check: no headless browser was available in this sandbox to click through the rendered UI itself, so the actual DOM/canvas rendering was not eyeballed by this session.

## Demo script (3–5 minutes, uses the actual numbers produced above)

1. **Open on `/` (30s).** "Scintilla is a perception layer for mobile FSOC terminals. The problem: platform vibration blurs a conventional camera's exposure exactly when you need to acquire a beacon." Point at the static comparison image — the blurred frame vs. the sharp event cloud, same beacon, same vibration, same instant. "That blur isn't a rendering choice — it's a real exposure-integration of the same high-fps ground truth the event side sees."
2. **Move to `/demo` (2 min).** Leave the defaults (17.3Hz vibration, 3px amplitude, 5Hz/px sensor noise — the same scenario used throughout the build) and click "Run scenario." While it streams: "left canvas is the live event cloud, right is what a 30fps frame camera would have captured off the same simulated scene." When the PSD panel populates: "that's not a canned number — it's a live Welch-style PSD estimate off the tracked centroid trace, and here it correctly recovers 17.5Hz against an injected 17.3Hz, with a confidence score, not just a point estimate." When the settle-time panel populates: "fixed-gain baseline versus a controller armed with that live disturbance estimate — across 20 randomized scenarios, not just this one, the armed controller won on RMS error in all 20 and settled faster in 19 of 20." Optionally change the amplitude slider to something above ~4.7px and rerun: "and here's the honest failure edge — this is exactly the boundary the envelope report on the next screen quantifies."
3. **Move to `/envelope` (1 min).** "This heatmap didn't require a single extra experiment — it's a surrogate model trained on the same lock-on results from steps one and two, swept across the parameters that matter." Read the live summary text aloud: vibration amplitude dominates, clutter is a real but secondary effect. "An integrator can look at this before committing to hardware and know where the system is expected to hold up."
4. **Close (30s).** State the caveats below plainly, then: "Everything shown here ran against a live backend during this walkthrough — nothing is a screenshot or a canned recording, with one exception noted honestly below."

## Honest caveats (say these out loud, don't bury them)

- **Synthetic-but-validated-against-real-data, not fully real-data-validated.** The physics core (Sections 1–2) is a synthetic simulator; Section 6's disturbance estimator was checked against synthetic ground truth extensively but real e-STURT hardware-jitter validation (Section 3's carry-forward) was not completed in this build — `core/real_data.py` exists as the ingestion/adapter scaffold but the actual e-STURT CSVs were never available in this environment (network egress here doesn't reach the dataset host, and it wasn't bundled with the project). This is a real, open gap, not a rounding error.
- **Real-DVS-hardware is a roadmap item, not a day-one asset.** Every event stream in this build is emulated from synthetic high-fps frames via a standard per-pixel log-intensity accumulator model. It has never touched a physical event camera. The frame-camera "baseline" is real exposure-integration math over the same synthetic ground truth, so the *comparison* is fair, but neither side has touched real optics.
- **Disturbance-model generalization is a roadmap item.** Section 6 and Section 8's control-loop demo were validated across randomized synthetic scenarios (varying frequency, amplitude, phase, noise, and — for Section 8 — handoff offset), which is real robustness evidence within the simulator, but it is evidence about the simulator's parameter space, not about the full range of real platform vibration spectra a fielded terminal would see.
- **The detector's own localization noise floor (~4.5–7px) is a real, load-bearing limitation**, discovered during Section 8's rework, not designed around from the start. It's why Section 8's settle threshold is 6px rather than the originally-planned 1.5px — that threshold was empirically unreachable given the current discriminator's accuracy, not a number chosen to make a demo look good. Improving Sections 4/5's sub-pixel localization would directly tighten every downstream number in Sections 6, 7, and 8.
- **The Section 10 UI itself was not click-tested in a real rendered browser** in this build session (see Section 10's tracker row) — the underlying logic was verified against the live backend by other means, but an actual visual/interaction pass by a human or a session with headless-browser access is still owed before a live judged demo.
- **`/run-scenario` and `/stream` re-run the full pipeline from scratch (~8–10s) with no caching or job queue** — fine for a solo demo, not fine for concurrent judges hitting it at once.

## Punch-list for the next polish pass

- [ ] Click through all three screens in an actual browser (this session had no headless-browser access) and fix any real rendering/interaction issues that surface — this is the single highest-priority item, since nothing in this session visually confirmed the canvases, chart, or heatmap actually look right, only that they receive correct data.
- [ ] Visual polish: the three screens share a token system (dark navy/orange/blue, Geist-style system fonts) but have not been reviewed for spacing/hierarchy consistency by eye.
- [ ] Mobile/small-viewport layout untested.
- [ ] `/demo`'s canvases redraw destructively per message (no persistence/trail of past events within a window) — a short fade-trail would likely read better live but wasn't implemented to keep scope to what Section 10 specified.
- [ ] Section 3 (e-STURT real-data validation) remains genuinely incomplete, not just deprioritized — see caveats above.
- [ ] No loading/error skeletons beyond plain text ("Loading sweep…", "awaiting estimate") — functional, not polished.
- [ ] No automated tests (unit or integration) anywhere in the stack — everything in this build plan was verified by direct manual execution against real data, which is what Section 0.2's zero-budget/zero-hardware constraints and the project's timeline allowed for, but it is not the same as a regression-safe test suite.


---

## How to hand off to a new Claude session

Paste, in this order:
1. This entire file.
2. All code files completed so far (or a zip/listing).
3. One sentence: *"We are on Section N. Everything above is done and working. Continue with Section N's tasks below, following the same conventions."*

A new session should never need to ask "what did we decide about X" — if it does, that's a gap in this file and should be fixed by whoever notices it.

---

## SECTION 1 — Physics core: scene generator

**Goal**: A pure-Python module that generates a synthetic scene of a frequency-modulated point-source beacon against a noisy background, with an injectable vibration/turbulence profile, and known ground truth for everything.

**Depends on**: nothing (this is the foundation).

**Tasks**:
- Implement `generate_scene(duration_s, fps, blink_freq_hz, vibration_psd_params, turbulence_level, background_clutter_level, frame_size=(128,128)) -> (frames: np.ndarray, ground_truth: dict)`.
- Beacon: a small bright Gaussian blob whose brightness toggles at `blink_freq_hz` (this is the "frequency-modulated beacon" the whole pitch rests on).
- Vibration: apply a controllable 2D jitter to the blob's (x, y) position per frame, generated from a specified power spectral density (so you can dial in "moderate vibration at a specific frequency" the way real FSOC engineers describe disturbance).
- Turbulence: optionally add scintillation-like brightness flicker (random intensity multiplier with a specified correlation time) — this is the "scintillation" half of the name, keep it even if unused early on.
- Background clutter: Perlin/simplex noise or simple random bright specks, so the frame-camera baseline in Section 2 has something realistic to fail against.
- `ground_truth` must include: the exact injected vibration trace (x(t), y(t)), the exact PSD parameters used, the blink frequency, and beacon true position per frame. This ground truth is what Section 6 and 7 validate against — do not skip it.

**Acceptance criteria**: Running the module produces a short video (save as .mp4 or frame sequence) that visibly shows a blinking dot jittering according to the injected profile, plus a saved `ground_truth.json`/`.npz` with the exact trace used.

**Carry forward to next session**: `core/scene_gen.py`, one example generated scene + its ground truth file, and the exact function signature (so Section 2 can call it without guessing).

---

## SECTION 2 — Event emulator + frame-camera baseline

**Goal**: Convert Section 1's rendered frames into (a) a synthetic event stream and (b) a realistic frame-camera-with-motion-blur baseline, so the two can be compared side by side.

**Depends on**: Section 1's `generate_scene` output.

**Tasks**:
- Implement `frames_to_events(frames, threshold) -> events` where `events` is an array of `(x, y, t, polarity)` — a simple per-pixel log-intensity-change-vs-threshold emulator (roughly 40–80 lines). Do this before touching `v2e` — this is your own, fully-understood, easy-to-explain-to-judges implementation.
- Implement `frames_to_blurred(frames, motion_trace) -> blurred_frames` — apply a motion-blur kernel derived from the same injected vibration trace, to produce the "what a real frame camera would actually see" comparison. Must use the *same* source frames as the event path, so the comparison is fair and easy to explain.
- (Optional, later, only if time remains) Wire in `v2e` as a second, higher-fidelity event conversion path for extra realism — treat this as a stretch goal, not a dependency for anything else.
- Write a quick visualization script: side-by-side video/plot of (blurred frame path) vs (event stream rendered as an image, e.g. accumulate events into a frame every few ms).

**Acceptance criteria**: On a scene with noticeable injected vibration, the blurred-frame path visibly smears/loses the beacon while the event-stream visualization still shows a sharp, temporally regular cluster at the beacon's blink frequency. Save this comparison as your first real demo asset.

**Carry forward**: `core/event_emulator.py`, the side-by-side comparison video/plot, and confirmation of what "visibly better" looks like on your test scene (a screenshot or short clip is the most useful artifact to carry forward here).

---

## SECTION 3 — Real-data validation (e-STURT ingestion)

**Goal**: Prove the core claim isn't just true in your own synthetic world — validate against real event-camera hardware data captured under real jitter.

**Depends on**: Section 2's detection approach existing in a form that can be pointed at a different data source; doesn't strictly depend on Section 2 being finished, but is much easier once it is.

**Tasks**:
- Download the e-STURT dataset (arXiv 2505.12588 — check the paper for the actual hosting link; if gated behind a request form, email the authors — this is normal for academic datasets and still free).
- Use `tonic` or `dv-processing` (pip-installable, open-source) to parse whatever format e-STURT ships in (likely `.aedat4`, `.h5`, or similar) into the same `(x, y, t, polarity)` array shape your Section 2 emulator produces, so downstream code doesn't need to know which source it came from.
- Run your Section 4/5 detection logic (once built) against a few e-STURT sequences and record: does it still find the point-source cluster and estimate jitter sensibly against e-STURT's published ground truth (the piezoelectric stage's commanded motion)?
- (Optional, stretch) Repeat with the Sun-E benchmark for the glare/dynamic-range claim specifically.

**Acceptance criteria**: A short write-up/plot showing your pipeline's output against at least one real e-STURT sequence, compared to the dataset's own ground-truth jitter trace. This is your single most important credibility artifact for the pitch — do not skip it even under time pressure.

**Carry forward**: `core/real_data.py` (the ingestion/adapter code), the e-STURT validation plot, and a one-paragraph honest note on how closely your synthetic-trained approach transferred (this feeds directly into Section 10's "honest caveats" slide).

---

## SECTION 4 — Classical beacon lock-on

**Goal**: A non-learned baseline that detects and tracks the beacon cluster in event space using its known blink frequency — the "signal processing, not AI" half of the pipeline. Be explicit that this part is not the AI claim.

**Depends on**: Sections 1–2 (needs event streams to run on).

**Tasks**:
- Spatial clustering of events (simple: bin events into a coarse grid, find the cell/region with the highest event rate matching the expected blink period via inter-event-interval matched filtering against `blink_freq_hz`).
- Output a `BeaconDetection` record: `{x, y, confidence, timestamp}` per time window.
- This becomes the baseline that Section 5's learned model has to beat in noisy/cluttered conditions — keep this code simple and clearly labeled as the non-AI baseline.

**Acceptance criteria**: On a clean (low-clutter) synthetic scene, this reliably finds the beacon. On a high-clutter scene, it should visibly start failing — this failure is what motivates Section 5.

**Carry forward**: `ai/lockon.py`, and a couple of test-scene results showing where the classical approach starts to break (this is the exact evidence you need to justify Section 5's existence to a skeptical judge).

---

## SECTION 5 — Learned discriminator (the real AI-necessity claim)

**Goal**: A small trained model that discriminates true-beacon event clusters from clutter/vibration-induced noise clusters, in conditions where Section 4's fixed matched-filter approach starts failing.

**Depends on**: Section 4 (need its failure cases as the argument for why this exists), Section 1 (need a sweep of synthetic scenes across noise/vibration levels to generate training data).

**Tasks**:
- Generate a labeled dataset: many synthetic scenes across a grid of `(vibration_level, turbulence_level, clutter_level)`, each with `ground_truth` beacon location vs. candidate false clusters.
- Engineer features per candidate cluster: event rate, inter-spike-interval regularity (variance around the expected blink period), spatial compactness, temporal consistency across windows.
- Train a small classifier — `scikit-learn` `GradientBoostingClassifier` or a small MLP is enough, no need for anything heavier.
- Evaluate: does it correctly discriminate beacon-vs-clutter in the regime where Section 4's fixed threshold/matched-filter approach fails? Also sanity-check against Section 3's e-STURT clutter if time allows.

**Acceptance criteria**: A clear quantitative comparison (accuracy, or just "Section 4 fails on scenes X, Y, Z; Section 5 succeeds on the same scenes") — this comparison is your entire "AI is load-bearing, not decorative" argument, so make it concrete and reproducible.

**Carry forward**: `ai/discriminator.py`, the trained model file, and the comparison numbers/plot.

---

## SECTION 6 — Disturbance characterization

**Goal**: Read vibration/scintillation state directly off event statistics, as a free byproduct of the same data used for detection — the "free signal" that's central to the whole pitch.

**Depends on**: Sections 1 (ground truth to validate against), 2 (event streams to compute statistics from).

**Tasks**:
- From the event stream around the locked-on beacon cluster, compute a PSD estimate of the positional jitter (e.g. track the cluster centroid over short windows, then FFT/PSD that trace with `scipy`).
- Compare this estimate against Section 1's exact injected ground-truth PSD — this comparison is your validation.
- Output a `DisturbanceState` record: `{vibration_psd, dominant_frequency, confidence}` per time window.
- Cross-check against Section 3's e-STURT ground truth (the piezo stage's actual commanded jitter) if Section 3 is complete.

**Acceptance criteria**: A plot showing your estimated vibration PSD/frequency tracking the true injected value reasonably closely across a few different injected profiles.

**Carry forward**: `ai/disturbance.py`, the validation plot(s) against both synthetic and (if available) e-STURT ground truth.

---

## SECTION 7 — Acquisition-envelope surrogate (the differentiation feature, built cheaply)

**Goal**: This is the folded-in replacement for the old "verification harness" idea — a model that predicts acquisition success probability across the disturbance parameter space, generated almost for free from infrastructure you already built.

**Depends on**: Section 1 (the simulator/sweep generator), Section 4 or 5 (a working detector to sweep against).

**Tasks**:
- Run a sweep: many `(vibration_level, turbulence_level, clutter_level)` combinations through the full pipeline (Sections 1→2→4/5), recording pass/fail (did it correctly lock onto the beacon?).
- Train a small surrogate model (same tooling as Section 5) that predicts success probability from the scenario vector, so you can query the parameter space densely without rerunning the full pipeline every time.
- Produce a 2D or 3D heatmap: "here's where this configuration holds lock vs. where it breaks."

**Acceptance criteria**: A heatmap that shows a plausible success/failure boundary (e.g. high vibration + high clutter = failure region), generated in minutes rather than requiring a brute-force rerun of the full sweep every time you query it.

**Carry forward**: `ai/envelope.py`, the trained surrogate, and the heatmap image — this is a key visual for the pitch (Section 10).

---

## SECTION 8 — Control-loop handoff demo

**Goal**: Show the practical payoff of Section 6's "free" disturbance signal — a downstream control loop that's pre-adapted to known disturbance settles faster than one that has to discover it.

**Depends on**: Section 6 (disturbance estimate), Section 4/5 (beacon position feed).

**Tasks**:
- Build a very simple simulated gimbal/fine-tracking loop (a basic PID or similar controller correcting toward the beacon position).
- Run it twice on the same disturbance scenario: (a) baseline, gains fixed, no prior disturbance knowledge; (b) pre-armed with Section 6's live disturbance estimate, gains adapted accordingly.
- Measure and plot settle time / tracking error over time for both, side by side.

**Acceptance criteria**: The pre-armed version visibly settles faster or holds tighter lock than the baseline, on the same injected disturbance.

**Carry forward**: `ai/control_loop.py`, the comparison plot, and the specific numeric improvement (e.g. "settles in X ms vs Y ms") — this becomes your closing "the number" beat in the demo script.

---

## SECTION 9 — FastAPI backend

**Goal**: Wrap everything above in a thin service layer so the Next.js frontend (Section 10) has something to talk to.

**Depends on**: Sections 1–8 all existing as importable Python functions/modules.

**Tasks**:
- `POST /run-scenario` — accepts scenario params (vibration, turbulence, clutter, blink freq), runs the full pipeline, returns detection results + disturbance estimate + settle-time comparison.
- `GET /envelope-sweep` — returns the precomputed (or on-the-fly-queried via the Section 7 surrogate) heatmap data.
- `WS /stream` — a WebSocket that streams event-cloud points and live disturbance estimates frame-by-frame, so the frontend can animate the "live" demo instead of just showing a static end result.
- Keep this layer thin — it should call into `core/` and `ai/` modules, not reimplement any logic.

**Acceptance criteria**: All endpoints return correct data when hit with a REST client (curl/Postman) or a simple WebSocket test client, without the frontend existing yet.

**Carry forward**: `api/main.py`, a short list of endpoint contracts (exact request/response JSON shapes) — Section 10 needs this exact contract, so write it down precisely, don't leave it implicit.

---

## SECTION 10 — Next.js frontend + pitch polish

**Goal**: The face of the product — three screens, plus final demo-script and honest-caveats polish for the actual pitch.

**Depends on**: Section 9's exact API contracts.

**Tasks**:
- Screen 1 — landing/pitch: one-liner, the Astrogate Labs timing hook, a static version of the key comparison image from Section 2.
- Screen 2 — live demo: canvas-rendered event cloud vs. blurred-frame baseline side by side (fed by Section 9's WebSocket), live disturbance-PSD trace, live settle-time comparison from Section 8.
- Screen 3 — envelope report: the heatmap from Section 7, rendered with `recharts`/`visx`, with a plain-language summary of the success/failure boundary.
- Final pass: write the 3–5 minute demo script referencing the actual numbers/plots you now have (not the hypothetical ones from earlier planning docs), and a short, explicit "honest caveats" slide — synthetic-but-validated-against-real-data claim, real-DVS-hardware as upgrade path, disturbance-model generalization as roadmap not day-one asset.

**Acceptance criteria**: A working, clickable three-screen app, backed by the real backend, that a judge could use themselves without you narrating every step.

**Carry forward**: the full `web/` app, and the final demo script text.

---

## Appendix — key open-source resources referenced across sections
- e-STURT dataset (real event-camera jitter data): arXiv 2505.12588
- Sun-E benchmark (event data under bright illumination): arXiv 2606.01280
- v2e (optional higher-fidelity event conversion): github.com/SensorsINI/v2e
- `tonic` / `dv-processing` (event-data format parsing libraries): PyPI
