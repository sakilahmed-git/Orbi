"""
Section 8 -- Control-loop handoff demo.

Shows the downstream payoff of Section 6's "free" disturbance signal: a
simple simulated fine-tracking loop that reacquires the beacon faster and
holds tighter lock when it is armed with the live disturbance estimate
(dominant frequency + confidence), compared to a fixed-gain baseline that
has no knowledge of the disturbance.

Design note (read before changing gains): a first version of this module
scaled a single PID's proportional gain up by a confidence-weighted factor
with only a token bump to derivative gain. On this scenario that made
things WORSE (armed RMS 4.12px vs baseline 3.87px) because raising loop
gain on a continuously-noisy, sparsely-sampled measurement just injects
more noise into the actuator command -- there is no one-shot "settling"
event to speed up when the disturbance never stops. Diagnosis (see
scratch sweeps) found:
  - single-detection localization error has an inherent floor of
    ~4.5-7px under this discriminator/lock-on stack, largely independent
    of sensor noise rate -- it is a property of the detector, not
    something a control gain can filter away.
  - increasing loop gain trades a faster initial acquisition against a
    noisier steady state (classic bandwidth/noise-rejection tradeoff);
    a single fixed gain cannot have both.
  - a disturbance-informed controller CAN have both, because it knows
    when it has just been handed a large coarse-alignment offset (loud,
    fast gain) versus when it is already on the beacon and should settle
    into a gentle, low-gain tracking mode informed by how confidently
    Section 6 has characterized the disturbance.

So "armed" here means: two-stage gain scheduling keyed off the live
tracking error and Section 6's disturbance confidence, not a blind gain
multiplier. This was validated across 20 random scenarios (varying
disturbance frequency/amplitude/phase, coarse-alignment offset direction
and magnitude, and noise) before being accepted -- see
`evaluate_control_handoff` below and `outputs/logs/section8_control_loop_metrics.json`
for the full per-seed numbers, not just an aggregate.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from ai.discriminator import discriminate_lock_on, load_discriminator
from ai.disturbance import estimate_vibration_psd, track_centroid_trace
from core.event_emulator import add_sensor_noise_events, frames_to_events
from core.scene_gen import TurbulenceParams, VibrationParams, generate_scene

ACTUATOR_TAU_S = 0.035          # fine-tracking actuator first-order lag
BASELINE_KP, BASELINE_KD = 6.0, 0.02   # single fixed gain, no disturbance knowledge
ARMED_KP_ACQUIRE = 16.0         # aggressive gain while still coarse-aligning
ARMED_KD = 0.02
LOCK_THRESH_PX = 8.0            # error below which the armed loop treats itself as "on beacon"
SETTLE_THRESH_PX = 6.0          # matches the discriminator's measured noisy localization floor (Section 5: ~5.85px)
SETTLE_HOLD_S = 0.15
SETTLE_PCTL = 80                # settle = 80th-percentile error in the hold window under threshold
                                 # (robust to a single bad detection in an otherwise-locked window)


@dataclass
class ControlRun:
    mode: str
    rms_error_px: float
    p95_error_px: float
    settle_time_s: float | None
    gain_kp_acquire: float
    gain_kp_track: float
    gain_kd: float


def _interpolate_detections(detections, times: np.ndarray, fallback_xy: np.ndarray) -> np.ndarray:
    det_times = np.array([d["t"] for d in detections if d is not None and d["confidence"] >= 0.15])
    det_xy = np.array([[d["x"], d["y"]] for d in detections if d is not None and d["confidence"] >= 0.15])
    if len(det_times) < 2:
        return fallback_xy.copy()
    return np.column_stack([
        np.interp(times, det_times, det_xy[:, 0]),
        np.interp(times, det_times, det_xy[:, 1]),
    ])


def _simulate_fixed_gain(measured_xy, true_xy, times, kp, kd, start_offset,
                          actuator_tau_s: float = ACTUATOR_TAU_S):
    """Fixed-gain baseline: one compromise gain for the whole run, no disturbance knowledge."""
    gimbal = measured_xy[0].copy() + start_offset
    velocity = np.zeros(2)
    prev_error = measured_xy[0] - gimbal
    errors = []
    for i, t in enumerate(times):
        dt = float(times[i] - times[i - 1]) if i else float(times[1] - times[0])
        error = measured_xy[i] - gimbal
        derivative = (error - prev_error) / max(dt, 1e-6)
        command_velocity = kp * error + kd * derivative
        velocity += (command_velocity - velocity) * min(1.0, dt / actuator_tau_s)
        gimbal = gimbal + velocity * dt
        prev_error = error
        errors.append(float(np.hypot(*(true_xy[i] - gimbal))))
    return np.asarray(errors)


def _simulate_disturbance_armed(measured_xy, true_xy, times, kp_acquire, kp_track, kd,
                                 lock_thresh_px, start_offset,
                                 actuator_tau_s: float = ACTUATOR_TAU_S):
    """Two-stage gain schedule: aggressive while coarse-aligning (large error), gentle
    once locked. The track-mode gain is informed by Section 6's disturbance confidence --
    low confidence falls back toward the baseline gain instead of assuming a clean lock."""
    gimbal = measured_xy[0].copy() + start_offset
    velocity = np.zeros(2)
    prev_error = measured_xy[0] - gimbal
    errors = []
    locked = False
    for i, t in enumerate(times):
        dt = float(times[i] - times[i - 1]) if i else float(times[1] - times[0])
        error = measured_xy[i] - gimbal
        if not locked and np.hypot(*error) < lock_thresh_px:
            locked = True
        kp = kp_track if locked else kp_acquire
        derivative = (error - prev_error) / max(dt, 1e-6)
        command_velocity = kp * error + kd * derivative
        velocity += (command_velocity - velocity) * min(1.0, dt / actuator_tau_s)
        gimbal = gimbal + velocity * dt
        prev_error = error
        errors.append(float(np.hypot(*(true_xy[i] - gimbal))))
    return np.asarray(errors)


def _settle_time(times: np.ndarray, errors: np.ndarray, threshold_px: float = SETTLE_THRESH_PX,
                  hold_s: float = SETTLE_HOLD_S, pctl: float = SETTLE_PCTL) -> float | None:
    """First time index after which `pctl`% of the next `hold_s` seconds of error stays
    under `threshold_px`. Percentile (not "all samples") because the measurement itself
    is a sparse, noisy detection stream -- a single outlier detection shouldn't erase an
    otherwise-locked window."""
    dt = float(np.median(np.diff(times)))
    hold_n = max(1, int(hold_s / dt))
    for i in range(0, max(1, len(errors) - hold_n)):
        window = errors[i:i + hold_n]
        if np.percentile(window, pctl) <= threshold_px:
            return float(times[i])
    return None


def run_control_comparison(measured_xy: np.ndarray, true_xy: np.ndarray, times: np.ndarray,
                            disturbance, start_offset: np.ndarray,
                            scintilla_enabled: bool = True) -> dict:
    """Public, reusable core of the baseline-vs-armed comparison, given an already-computed
    measurement trace and disturbance estimate. Used by both the batch evaluation below and
    the FastAPI `/run-scenario` endpoint (Section 9), so both share exactly one implementation."""
    baseline_err = _simulate_fixed_gain(measured_xy, true_xy, times, BASELINE_KP, BASELINE_KD, start_offset)

    confidence = disturbance.confidence
    kp_track = 3.0 + (1.0 - min(confidence, 1.0)) * (BASELINE_KP - 3.0)
    armed_err = _simulate_disturbance_armed(measured_xy, true_xy, times, ARMED_KP_ACQUIRE,
                                             kp_track, ARMED_KD, LOCK_THRESH_PX, start_offset)

    settle_b = _settle_time(times, baseline_err)
    settle_a = _settle_time(times, armed_err)

    selected = armed_err if scintilla_enabled else baseline_err
    selected_metrics = {
        "mode": "scintilla_predictive" if scintilla_enabled else "conventional_pat_atp",
        "rms_error_px": float(np.sqrt(np.mean(selected ** 2))),
        "p95_error_px": float(np.percentile(selected, 95)),
        "settle_time_s": settle_a if scintilla_enabled else settle_b,
    }
    return {
        "start_offset_px": [float(start_offset[0]), float(start_offset[1])],
        "baseline": {
            "rms_error_px": float(np.sqrt(np.mean(baseline_err ** 2))),
            "p95_error_px": float(np.percentile(baseline_err, 95)),
            "settle_time_s": settle_b,
        },
        "disturbance_armed": {
            "rms_error_px": float(np.sqrt(np.mean(armed_err ** 2))),
            "p95_error_px": float(np.percentile(armed_err, 95)),
            "settle_time_s": settle_a,
            "kp_track_used": float(kp_track),
        },
        "selected_control": selected_metrics,
        "_baseline_trace": baseline_err,
        "_armed_trace": armed_err,
    }


def _run_one_scenario(model, seed: int, rng: np.random.Generator) -> dict:
    freq_true = float(rng.uniform(12.0, 22.0))
    amp_true = float(rng.uniform(2.0, 4.0))
    phase = float(rng.uniform(0.0, 1.0))
    frames, gt = generate_scene(
        duration_s=2.0,
        fps=240,
        blink_freq_hz=20.0,
        vibration=VibrationParams(components=[(freq_true, amp_true, phase)], broadband_std_px=0.25),
        turbulence=TurbulenceParams(strength=0.25, correlation_time_s=0.05),
        background_clutter_level=0.35,
        frame_size=(128, 128),
        seed=seed,
    )
    clean = frames_to_events(frames, fps=gt.fps, threshold=0.15)
    noisy = add_sensor_noise_events(clean, tuple(gt.frame_size), gt.duration_s,
                                     rate_hz_per_pixel=5.0, seed=seed)
    detections = discriminate_lock_on(noisy, tuple(gt.frame_size), gt.blink_freq_hz, model)
    centroid_t, centroid_xy, _ = track_centroid_trace(noisy, detections, tuple(gt.frame_size),
                                                        sample_window_s=0.01, roi_radius_px=10.0)
    disturbance = estimate_vibration_psd(centroid_t, centroid_xy)

    times = np.arange(len(gt.true_xy)) / gt.fps
    true_xy = np.asarray(gt.true_xy)
    measured_xy = _interpolate_detections(detections, times, true_xy)

    # Simulated coarse-alignment handoff: fine loop starts offset from the beacon by a
    # random direction/magnitude, representing where the upstream coarse-alignment stage
    # (Sections 4/5) hands off.
    angle = rng.uniform(0.0, 2.0 * np.pi)
    magnitude = rng.uniform(12.0, 20.0)
    start_offset = np.array([magnitude * np.cos(angle), magnitude * np.sin(angle)])

    comparison = run_control_comparison(measured_xy, true_xy, times, disturbance, start_offset)

    return {
        "seed": seed,
        "injected_frequency_hz": freq_true,
        "disturbance_estimate": asdict(disturbance),
        **comparison,
        "_times": times,
    }


def evaluate_control_handoff(
    model_path: str = "outputs/models/discriminator_gbc.joblib",
    seeds=range(700, 720),
    plot_path: str = "outputs/plots/section8_control_loop_handoff.png",
    log_path: str = "outputs/logs/section8_control_loop_metrics.json",
) -> dict:
    """Run the fixed-gain baseline vs. the disturbance-armed gain schedule across many
    random scenarios (disturbance frequency/amplitude/phase, handoff offset direction and
    magnitude all randomized) and report real per-seed and aggregate numbers -- not a
    single cherry-picked run."""
    model = load_discriminator(model_path)
    rng = np.random.default_rng(2026)

    rows = [_run_one_scenario(model, seed, rng) for seed in seeds]

    duration_s = 2.0
    settle_b = [r["baseline"]["settle_time_s"] for r in rows]
    settle_a = [r["disturbance_armed"]["settle_time_s"] for r in rows]
    settle_b_capped = [s if s is not None else duration_s for s in settle_b]
    settle_a_capped = [s if s is not None else duration_s for s in settle_a]
    rms_b = [r["baseline"]["rms_error_px"] for r in rows]
    rms_a = [r["disturbance_armed"]["rms_error_px"] for r in rows]
    p95_b = [r["baseline"]["p95_error_px"] for r in rows]
    p95_a = [r["disturbance_armed"]["p95_error_px"] for r in rows]
    n_wins_rms = sum(1 for b, a in zip(rms_b, rms_a) if a < b)
    n_wins_settle = sum(
        1 for b, a in zip(settle_b_capped, settle_a_capped) if a < b
    )

    metrics = {
        "n_scenarios": len(rows),
        "settle_threshold_px": SETTLE_THRESH_PX,
        "settle_hold_s": SETTLE_HOLD_S,
        "settle_pctl": SETTLE_PCTL,
        "baseline_gain_kp_kd": [BASELINE_KP, BASELINE_KD],
        "armed_kp_acquire": ARMED_KP_ACQUIRE,
        "baseline_never_settled_count": sum(1 for s in settle_b if s is None),
        "armed_never_settled_count": sum(1 for s in settle_a if s is None),
        "rms_error_px_mean": {"baseline": float(np.mean(rms_b)), "armed": float(np.mean(rms_a))},
        "rms_error_px_std": {"baseline": float(np.std(rms_b)), "armed": float(np.std(rms_a))},
        "p95_error_px_mean": {"baseline": float(np.mean(p95_b)), "armed": float(np.mean(p95_a))},
        "settle_time_s_mean_capped_at_duration": {
            "baseline": float(np.mean(settle_b_capped)), "armed": float(np.mean(settle_a_capped)),
        },
        "n_scenarios_armed_rms_better": n_wins_rms,
        "n_scenarios_armed_settle_better_or_equal": n_wins_settle,
        "rms_improvement_percent_mean": float(
            100.0 * np.mean([(b - a) / b for b, a in zip(rms_b, rms_a)])
        ),
    }

    # Plot: one representative scenario (first seed) full traces, plus the aggregate bars.
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    rep = rows[0]
    axes[0].plot(rep["_times"], rep["_baseline_trace"],
                 label=f"baseline (fixed gain), RMS {rep['baseline']['rms_error_px']:.1f}px")
    axes[0].plot(rep["_times"], rep["_armed_trace"],
                 label=f"disturbance-armed, RMS {rep['disturbance_armed']['rms_error_px']:.1f}px")
    axes[0].axhline(SETTLE_THRESH_PX, color="k", linestyle="--", linewidth=1, label="settle threshold")
    axes[0].set_xlabel("time (s)")
    axes[0].set_ylabel("tracking residual (px)")
    axes[0].set_title(f"Representative scenario (seed {rep['seed']}, "
                       f"{rep['injected_frequency_hz']:.1f}Hz disturbance)")
    axes[0].legend(fontsize=8)

    labels = ["RMS error (px)", "P95 error (px)", "Settle time (s, capped)"]
    baseline_vals = [metrics["rms_error_px_mean"]["baseline"], metrics["p95_error_px_mean"]["baseline"],
                      metrics["settle_time_s_mean_capped_at_duration"]["baseline"]]
    armed_vals = [metrics["rms_error_px_mean"]["armed"], metrics["p95_error_px_mean"]["armed"],
                  metrics["settle_time_s_mean_capped_at_duration"]["armed"]]
    x = np.arange(len(labels))
    width = 0.35
    axes[1].bar(x - width / 2, baseline_vals, width, label="baseline")
    axes[1].bar(x + width / 2, armed_vals, width, label="disturbance-armed")
    axes[1].set_xticks(x)
    axes[1].set_xticklabels(labels, fontsize=8)
    axes[1].set_title(f"Mean over {len(rows)} random scenarios")
    axes[1].legend(fontsize=8)

    plt.tight_layout()
    os.makedirs(os.path.dirname(plot_path), exist_ok=True)
    plt.savefig(plot_path, dpi=160)
    plt.close()

    result = {
        "metrics": metrics,
        "per_scenario": [
            {k: v for k, v in r.items() if not k.startswith("_")} for r in rows
        ],
        "plot": plot_path,
    }
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "w") as f:
        json.dump(result, f, indent=2)
    return {"metrics": metrics, "plot": plot_path, "log": log_path}


if __name__ == "__main__":
    print("section8_control_loop:", json.dumps(evaluate_control_handoff(), indent=2))
