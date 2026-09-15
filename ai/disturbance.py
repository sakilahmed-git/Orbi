"""
Section 6 -- Disturbance characterization.

Estimate vibration state from event-cluster centroid motion and validate it
separately against synthetic ground truth and available real e-STURT files.
"""

from __future__ import annotations

import glob
import json
import os
from dataclasses import asdict, dataclass

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy import signal

from ai.discriminator import discriminate_lock_on, exact_section5_scenario, load_discriminator
from core.event_emulator import add_sensor_noise_events, frames_to_events
from core.scene_gen import TurbulenceParams, VibrationParams, generate_scene
from core.real_data import load_camera_events, load_shaker_log


@dataclass
class DisturbanceState:
    t_start: float
    t_end: float
    vibration_psd: dict
    dominant_frequency: float | None
    confidence: float
    method: str = "event_cluster_centroid_psd"


def track_centroid_trace(
    events: np.ndarray,
    detections: list[dict | None] | None = None,
    frame_size: tuple[int, int] = (128, 128),
    sample_window_s: float = 0.01,
    roi_radius_px: float = 10.0,
    min_events: int = 4,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Track cluster centroids in short windows."""
    if events.size == 0:
        return np.zeros(0), np.zeros((0, 2)), np.zeros(0)
    h, w = frame_size
    t_max = float(events[:, 2].max())
    dets = [d for d in (detections or []) if d is not None]
    fallback_center = np.array([w / 2.0, h / 2.0], dtype=float)
    times, xy, counts = [], [], []
    prev = None

    t = 0.0
    while t < t_max:
        t1 = t + sample_window_s
        center = prev
        nearby = [d for d in dets if abs(d["t"] - t) <= 0.05]
        if nearby:
            best = min(nearby, key=lambda d: abs(d["t"] - t))
            center = np.array([best["x"], best["y"]], dtype=float)
        elif center is None:
            center = fallback_center

        win = events[(events[:, 2] >= t) & (events[:, 2] < t1)]
        if win.shape[0] and center is not None:
            dist = np.hypot(win[:, 0] - center[0], win[:, 1] - center[1])
            win = win[dist <= roi_radius_px]
        if win.shape[0] >= min_events:
            c = np.array([float(win[:, 0].mean()), float(win[:, 1].mean())])
            prev = c
            times.append(t + 0.5 * sample_window_s)
            xy.append(c)
            counts.append(win.shape[0])
        t += sample_window_s

    return np.asarray(times), np.asarray(xy), np.asarray(counts)


def estimate_vibration_psd(times: np.ndarray, xy: np.ndarray) -> DisturbanceState:
    if times.size < 8 or xy.shape[0] < 8:
        return DisturbanceState(float(times[0]) if times.size else 0.0,
                                float(times[-1]) if times.size else 0.0,
                                {"frequency_hz": [], "psd_x": [], "psd_y": [], "psd_mag": []},
                                None, 0.0)
    dt = float(np.median(np.diff(times)))
    fs = 1.0 / dt
    demeaned = xy - np.nanmean(xy, axis=0)
    nperseg = min(256, len(times))
    freqs, psd_x = signal.welch(demeaned[:, 0], fs=fs, nperseg=nperseg)
    _, psd_y = signal.welch(demeaned[:, 1], fs=fs, nperseg=nperseg)
    psd_mag = psd_x + psd_y
    valid = freqs > 0
    dom = float(freqs[valid][np.argmax(psd_mag[valid])]) if valid.any() else None
    confidence = float(psd_mag[valid].max() / (psd_mag[valid].sum() + 1e-12)) if valid.any() else 0.0
    return DisturbanceState(
        t_start=float(times[0]),
        t_end=float(times[-1]),
        vibration_psd={
            "frequency_hz": freqs.tolist(),
            "psd_x": psd_x.tolist(),
            "psd_y": psd_y.tolist(),
            "psd_mag": psd_mag.tolist(),
        },
        dominant_frequency=dom,
        confidence=confidence,
    )


def validate_synthetic(
    model_path: str = "outputs/models/discriminator_gbc.joblib",
    plot_path: str = "outputs/plots/section6_synthetic_psd.png",
):
    clean, noisy, gt = exact_section5_scenario(seed=42)
    model = load_discriminator(model_path)
    dets = discriminate_lock_on(noisy, tuple(gt.frame_size), gt.blink_freq_hz, model)
    times, xy, counts = track_centroid_trace(noisy, dets, tuple(gt.frame_size),
                                             sample_window_s=0.01, roi_radius_px=10.0)
    state = estimate_vibration_psd(times, xy)

    true_xy = np.asarray(gt.true_xy)
    true_t = np.arange(len(true_xy)) / gt.fps
    est_true = np.column_stack([
        np.interp(times, true_t, true_xy[:, 0]),
        np.interp(times, true_t, true_xy[:, 1]),
    ])
    true_state = estimate_vibration_psd(times, est_true)
    centroid_rmse = float(np.sqrt(np.mean(np.sum((xy - est_true) ** 2, axis=1)))) if len(times) else None
    dominant_error = (
        abs(state.dominant_frequency - true_state.dominant_frequency)
        if state.dominant_frequency is not None and true_state.dominant_frequency is not None
        else None
    )

    os.makedirs(os.path.dirname(plot_path), exist_ok=True)
    plt.figure(figsize=(8, 5))
    f_est = np.asarray(state.vibration_psd["frequency_hz"])
    p_est = np.asarray(state.vibration_psd["psd_mag"])
    f_true = np.asarray(true_state.vibration_psd["frequency_hz"])
    p_true = np.asarray(true_state.vibration_psd["psd_mag"])
    if p_est.size:
        plt.semilogy(f_est, p_est + 1e-12, label=f"estimated events ({state.dominant_frequency:.2f} Hz)")
    if p_true.size:
        plt.semilogy(f_true, p_true + 1e-12, label=f"synthetic ground truth ({true_state.dominant_frequency:.2f} Hz)")
    plt.xlim(0, 50)
    plt.xlabel("frequency (Hz)")
    plt.ylabel("PSD (px^2/Hz)")
    plt.title("Section 6 synthetic disturbance PSD")
    plt.legend()
    plt.tight_layout()
    plt.savefig(plot_path, dpi=160)
    plt.close()

    return {
        "state": asdict(state),
        "true_state": asdict(true_state),
        "centroid_rmse_px": centroid_rmse,
        "dominant_frequency_error_hz": float(dominant_error) if dominant_error is not None else None,
        "n_centroid_samples": int(len(times)),
        "plot": plot_path,
    }


def validate_nonround_synthetic(
    model_path: str = "outputs/models/discriminator_gbc.joblib",
    vibration_frequency_hz: float = 17.3,
    noise_rates: tuple[float, ...] = (2.0, 5.0),
    plot_path: str = "outputs/plots/section6_nonround_frequency_audit.png",
    log_path: str = "outputs/logs/section6_nonround_frequency_audit.json",
) -> dict:
    """Audit disturbance recovery where the injected frequency is not on an FFT bin."""
    model = load_discriminator(model_path)
    rows = []
    plt.figure(figsize=(8, 5))
    for noise_rate in noise_rates:
        frames, gt = generate_scene(
            duration_s=2.0,
            fps=240,
            blink_freq_hz=20.0,
            vibration=VibrationParams(
                components=[(vibration_frequency_hz, 2.5, 0.23)],
                broadband_std_px=0.25,
            ),
            turbulence=TurbulenceParams(strength=0.25, correlation_time_s=0.05),
            background_clutter_level=0.3,
            frame_size=(128, 128),
            seed=222 + int(noise_rate * 10),
        )
        clean = frames_to_events(frames, fps=gt.fps, threshold=0.15)
        noisy = add_sensor_noise_events(clean, tuple(gt.frame_size), gt.duration_s,
                                        rate_hz_per_pixel=noise_rate, seed=222)
        dets = discriminate_lock_on(noisy, tuple(gt.frame_size), gt.blink_freq_hz, model)
        times, xy, _ = track_centroid_trace(noisy, dets, tuple(gt.frame_size),
                                            sample_window_s=0.01, roi_radius_px=10.0)
        state = estimate_vibration_psd(times, xy)
        f = np.asarray(state.vibration_psd["frequency_hz"])
        p = np.asarray(state.vibration_psd["psd_mag"])
        if p.size:
            plt.semilogy(f, p + 1e-12, label=f"{noise_rate:g} Hz/px, est {state.dominant_frequency:.2f} Hz")
        rows.append({
            "noise_rate_hz_per_px": float(noise_rate),
            "injected_frequency_hz": float(vibration_frequency_hz),
            "estimated_frequency_hz": state.dominant_frequency,
            "absolute_error_hz": (
                float(abs(state.dominant_frequency - vibration_frequency_hz))
                if state.dominant_frequency is not None else None
            ),
            "confidence": state.confidence,
            "n_centroid_samples": int(len(times)),
        })

    plt.axvline(vibration_frequency_hz, color="k", linestyle="--", label="injected 17.3 Hz")
    plt.xlim(0, 45)
    plt.xlabel("frequency (Hz)")
    plt.ylabel("PSD (px^2/Hz)")
    plt.title("Section 6 non-round frequency audit")
    plt.legend()
    plt.tight_layout()
    os.makedirs(os.path.dirname(plot_path), exist_ok=True)
    plt.savefig(plot_path, dpi=160)
    plt.close()

    result = {
        "no_ground_truth_leakage_note": (
            "The estimate path uses noisy events, discriminator detections, "
            "short-window event centroids, and Welch PSD only. Ground-truth "
            "frequency is used only after estimation to compute the error."
        ),
        "rows": rows,
        "plot": plot_path,
    }
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "w") as f:
        json.dump(result, f, indent=2)
    return result


def _load_longest_real_events():
    event_files = glob.glob("data/esturt/*event*.csv")
    best = None
    for path in event_files:
        ev = load_camera_events(path)
        duration = float(np.ptp(ev[:, 2])) if ev.size else 0.0
        if best is None or duration > best[0]:
            best = (duration, path, ev)
    return best


def attempt_real_validation(plot_path: str = "outputs/plots/section6_real_esturt_format_check.png"):
    longest = _load_longest_real_events()
    shaker_files = glob.glob("data/esturt/*shaker_log_cleaned.csv")
    if longest is None or not shaker_files:
        return {"status": "blocked", "reason": "Missing real event or shaker CSV files."}

    duration, event_path, events = longest
    shaker = load_shaker_log(shaker_files[0])
    median_dt = float(shaker["t_s"].diff().median())
    usable_shaker = shaker[(shaker["t_s"] >= 0) & (shaker["t_s"] <= duration)]

    # e-STURT sample is a full star-field event stream, not a beacon ROI.
    # Use the global centroid only as a format/qualitative disturbance check.
    times, xy, counts = track_centroid_trace(events, detections=None, frame_size=(720, 1280),
                                             sample_window_s=0.02, roi_radius_px=2000.0,
                                             min_events=20)
    state = estimate_vibration_psd(times, xy)

    os.makedirs(os.path.dirname(plot_path), exist_ok=True)
    fig, axes = plt.subplots(2, 1, figsize=(8, 7), sharex=False)
    if len(times):
        axes[0].plot(times, xy[:, 0] - np.mean(xy[:, 0]), label="event centroid x (demeaned)")
        axes[0].plot(times, xy[:, 1] - np.mean(xy[:, 1]), label="event centroid y (demeaned)")
    if len(usable_shaker):
        axes[0].plot(usable_shaker["t_s"], usable_shaker["axis1"] - usable_shaker["axis1"].mean(),
                     "k--", alpha=0.7, label="shaker axis1 (demeaned)")
    axes[0].set_title("Real e-STURT qualitative format check")
    axes[0].set_xlabel("time (s)")
    axes[0].legend()
    f = np.asarray(state.vibration_psd["frequency_hz"])
    p = np.asarray(state.vibration_psd["psd_mag"])
    if p.size:
        axes[1].semilogy(f, p + 1e-12, label="event global-centroid PSD")
    axes[1].set_xlabel("frequency (Hz)")
    axes[1].set_ylabel("PSD")
    axes[1].legend()
    plt.tight_layout()
    plt.savefig(plot_path, dpi=160)
    plt.close()

    quantitative_ok = bool(duration >= 3.0 and len(usable_shaker.dropna()) >= 40)
    return {
        "status": "quantitative_attempted" if quantitative_ok else "qualitative_format_check_only",
        "event_file": event_path,
        "event_duration_s": duration,
        "shaker_file": shaker_files[0],
        "shaker_median_dt_s": median_dt,
        "shaker_samples_over_event_window": int(len(usable_shaker)),
        "state": asdict(state),
        "plot": plot_path,
        "limitation": (
            "This real sample is not a modulated-beacon ROI and is only "
            f"{duration:.3f}s long. A quantitative real validation needs "
            "several seconds of time-aligned real events from a stable tracked "
            "feature or beacon-like ROI, with enough shaker samples to resolve "
            "the injected vibration band without aliasing."
        ),
    }


if __name__ == "__main__":
    synthetic = validate_synthetic()
    nonround = validate_nonround_synthetic()
    real = attempt_real_validation()
    os.makedirs("outputs/logs", exist_ok=True)
    with open("outputs/logs/section6_disturbance_metrics.json", "w") as f:
        json.dump({"synthetic_validation": synthetic, "nonround_frequency_audit": nonround,
                   "real_validation": real}, f, indent=2)
    print("synthetic_validation:", synthetic)
    print("nonround_frequency_audit:", nonround)
    print("real_validation:", real)
