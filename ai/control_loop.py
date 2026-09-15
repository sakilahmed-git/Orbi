"""
Section 8 -- Control-loop handoff demo.

Simple simulated gimbal/fine-tracking loop that consumes beacon detections
and the disturbance estimate from Section 6. This is intentionally small:
the goal is to show the downstream value of the disturbance state, not to
pretend we built a flight controller.
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


@dataclass
class ControlRun:
    mode: str
    rms_error_px: float
    p95_error_px: float
    settle_time_s: float | None
    gain_kp: float
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


def _simulate_tracker(measured_xy: np.ndarray, true_xy: np.ndarray, times: np.ndarray,
                      kp: float, kd: float, actuator_tau_s: float = 0.035):
    gimbal = measured_xy[0].copy()
    velocity = np.zeros(2)
    prev_error = measured_xy[0] - gimbal
    gimbal_trace = []
    residuals = []
    for i, t in enumerate(times):
        dt = float(times[i] - times[i - 1]) if i else float(times[1] - times[0])
        error = measured_xy[i] - gimbal
        derivative = (error - prev_error) / max(dt, 1e-6)
        command_velocity = kp * error + kd * derivative
        velocity += (command_velocity - velocity) * min(1.0, dt / actuator_tau_s)
        gimbal = gimbal + velocity * dt
        prev_error = error
        gimbal_trace.append(gimbal.copy())
        residuals.append(float(np.hypot(*(true_xy[i] - gimbal))))
    return np.asarray(gimbal_trace), np.asarray(residuals)


def _settle_time(times: np.ndarray, errors: np.ndarray, threshold_px: float = 1.5,
                 hold_s: float = 0.25) -> float | None:
    dt = float(np.median(np.diff(times)))
    hold_n = max(1, int(hold_s / dt))
    for i in range(0, max(1, len(errors) - hold_n)):
        if np.all(errors[i:i + hold_n] <= threshold_px):
            return float(times[i])
    return None


def run_control_demo(
    model_path: str = "outputs/models/discriminator_gbc.joblib",
    plot_path: str = "outputs/plots/section8_control_loop_handoff.png",
    log_path: str = "outputs/logs/section8_control_loop_metrics.json",
) -> dict:
    frames, gt = generate_scene(
        duration_s=2.0,
        fps=240,
        blink_freq_hz=20.0,
        vibration=VibrationParams(components=[(17.3, 3.0, 0.2)], broadband_std_px=0.25),
        turbulence=TurbulenceParams(strength=0.25, correlation_time_s=0.05),
        background_clutter_level=0.35,
        frame_size=(128, 128),
        seed=812,
    )
    clean = frames_to_events(frames, fps=gt.fps, threshold=0.15)
    noisy = add_sensor_noise_events(clean, tuple(gt.frame_size), gt.duration_s,
                                    rate_hz_per_pixel=5.0, seed=812)
    model = load_discriminator(model_path)
    detections = discriminate_lock_on(noisy, tuple(gt.frame_size), gt.blink_freq_hz, model)
    centroid_t, centroid_xy, _ = track_centroid_trace(noisy, detections, tuple(gt.frame_size),
                                                      sample_window_s=0.01, roi_radius_px=10.0)
    disturbance = estimate_vibration_psd(centroid_t, centroid_xy)

    times = np.arange(len(gt.true_xy)) / gt.fps
    true_xy = np.asarray(gt.true_xy)
    measured_xy = _interpolate_detections(detections, times, true_xy)

    baseline_kp, baseline_kd = 7.0, 0.02
    freq = disturbance.dominant_frequency or 0.0
    confidence = disturbance.confidence
    schedule = 1.0 + min(1.5, (freq / 18.0) * confidence * 2.5)
    armed_kp = baseline_kp * schedule
    armed_kd = baseline_kd + 0.05 * confidence

    baseline_trace, baseline_err = _simulate_tracker(measured_xy, true_xy, times,
                                                     baseline_kp, baseline_kd)
    armed_trace, armed_err = _simulate_tracker(measured_xy, true_xy, times,
                                               armed_kp, armed_kd)

    baseline = ControlRun(
        mode="fixed_gain_baseline",
        rms_error_px=float(np.sqrt(np.mean(baseline_err ** 2))),
        p95_error_px=float(np.percentile(baseline_err, 95)),
        settle_time_s=_settle_time(times, baseline_err),
        gain_kp=baseline_kp,
        gain_kd=baseline_kd,
    )
    armed = ControlRun(
        mode="disturbance_armed_gain_schedule",
        rms_error_px=float(np.sqrt(np.mean(armed_err ** 2))),
        p95_error_px=float(np.percentile(armed_err, 95)),
        settle_time_s=_settle_time(times, armed_err),
        gain_kp=float(armed_kp),
        gain_kd=float(armed_kd),
    )

    os.makedirs(os.path.dirname(plot_path), exist_ok=True)
    plt.figure(figsize=(9, 5))
    plt.plot(times, baseline_err, label=f"baseline RMS {baseline.rms_error_px:.2f}px")
    plt.plot(times, armed_err, label=f"disturbance-armed RMS {armed.rms_error_px:.2f}px")
    plt.axhline(1.5, color="k", linestyle="--", linewidth=1, label="settle threshold")
    plt.xlabel("time (s)")
    plt.ylabel("tracking residual (px)")
    plt.title(f"Section 8 control handoff, disturbance estimate {freq:.2f} Hz")
    plt.legend()
    plt.tight_layout()
    plt.savefig(plot_path, dpi=160)
    plt.close()

    result = {
        "disturbance_state": asdict(disturbance),
        "baseline": asdict(baseline),
        "disturbance_armed": asdict(armed),
        "rms_improvement_px": float(baseline.rms_error_px - armed.rms_error_px),
        "rms_improvement_percent": float(
            100.0 * (baseline.rms_error_px - armed.rms_error_px) / baseline.rms_error_px
        ),
        "plot": plot_path,
    }
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "w") as f:
        json.dump(result, f, indent=2)
    return result


if __name__ == "__main__":
    print("section8_control_loop:", run_control_demo())
