"""
Section 4 -- Classical beacon lock-on.

A non-learned baseline: spatial binning + FFT-based matched filtering
against the known blink frequency. This is explicitly the "signal
processing, not AI" half of the pipeline -- it exists so Section 5's
learned discriminator has a fair, honestly-weaker baseline to beat, and so
we can show judges precisely WHERE and WHY a fixed matched filter breaks
(real sensor noise, see core.event_emulator.add_sensor_noise_events),
rather than asserting "AI is better" without evidence.
"""

from __future__ import annotations

import numpy as np


def evaluate_classical_baseline(
    seed: int = 42,
    log_path: str = "outputs/logs/section4_classical_baseline.json",
    plot_path: str = "outputs/plots/section4_classical_failure.png",
    persist: bool = True,
) -> dict:
    """Run and persist the canonical clean/noisy Section 4 baseline.

    This is deliberately one fixed, reproducible scenario.  The resulting
    JSON is the sole source for any pitch number describing this comparison.
    """
    import json
    import os
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from core.event_emulator import add_sensor_noise_events, frames_to_events
    from core.scene_gen import TurbulenceParams, VibrationParams, generate_scene

    frames, gt = generate_scene(
        duration_s=1.0, fps=200, blink_freq_hz=20.0,
        vibration=VibrationParams(components=[(15.0, 2.5, 0.0)], broadband_std_px=0.4),
        turbulence=TurbulenceParams(strength=0.35, correlation_time_s=0.05),
        background_clutter_level=0.3, frame_size=(128, 128), seed=seed,
    )
    clean_events = frames_to_events(frames, fps=gt.fps, threshold=0.15)
    noisy_events = add_sensor_noise_events(
        clean_events, tuple(gt.frame_size), gt.duration_s, rate_hz_per_pixel=5.0, seed=seed
    )
    truth = [gt.true_xy[min(int(i * 0.05 * gt.fps), len(gt.true_xy) - 1)] for i in range(20)]
    clean = lock_on(clean_events, tuple(gt.frame_size), gt.blink_freq_hz)
    noisy = lock_on(noisy_events, tuple(gt.frame_size), gt.blink_freq_hz)
    result = {
        "method": "classical_grid_fft_lock_on",
        "scenario": {"seed": seed, "duration_s": 1.0, "fps": 200, "blink_freq_hz": 20.0,
                     "vibration_frequency_hz": 15.0, "vibration_amplitude_px": 2.5,
                     "sensor_noise_rate_hz_per_px": 5.0},
        "clean": summarize_detections(clean, truth),
        "noisy": summarize_detections(noisy, truth),
        "plot": plot_path,
    }
    if persist:
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        os.makedirs(os.path.dirname(plot_path), exist_ok=True)
        with open(log_path, "w") as f:
            json.dump(result, f, indent=2)

    plt.figure(figsize=(7, 5))
    xy = np.asarray(gt.true_xy)
    plt.plot(xy[:, 0], xy[:, 1], "k-", label="injected beacon trace")
    for label, detections, color in [("classical clean", clean, "tab:green"),
                                     ("classical + sensor noise", noisy, "tab:red")]:
        points = np.asarray([[d["x"], d["y"]] for d in detections if d is not None])
        if points.size:
            plt.scatter(points[:, 0], points[:, 1], s=25, label=label, c=color)
    plt.gca().invert_yaxis()
    plt.axis("equal")
    plt.xlabel("x (px)")
    plt.ylabel("y (px)")
    plt.title("Section 4 classical baseline — fixed seed 42")
    plt.legend()
    plt.tight_layout()
    if persist:
        plt.savefig(plot_path, dpi=160)
    plt.close()
    return result


def lock_on(events: np.ndarray, frame_size: tuple, blink_freq_hz: float,
            window_s: float = 0.05, grid_size: int = 8,
            min_events: int = 5, freq_tolerance: float = 0.35,
            time_bin_s: float = None):
    """Scans the event stream in sliding time windows, bins events
    spatially into a coarse grid, and scores each occupied cell by how
    well its event-count time series matches the expected blink frequency
    (FFT peak within `freq_tolerance` fractional band of blink_freq_hz).

    Returns a list of detections, one per window (or None if nothing
    scored above a minimal confidence in that window):
        [{"t": window_start, "x": float, "y": float, "confidence": float}, ...]
    """
    h, w = frame_size
    if time_bin_s is None:
        # Nyquist-ish: at least 6 samples per blink period
        time_bin_s = 1.0 / (6 * blink_freq_hz)

    t_max = events[:, 2].max() if events.shape[0] else 0.0
    detections = []

    t = 0.0
    while t < t_max:
        t_end = t + window_s
        mask = (events[:, 2] >= t) & (events[:, 2] < t_end)
        win_events = events[mask]

        best = None
        if win_events.shape[0] >= min_events:
            cell_x = (win_events[:, 0] // grid_size).astype(int)
            cell_y = (win_events[:, 1] // grid_size).astype(int)
            cell_ids = cell_x * ((h // grid_size) + 1) + cell_y
            unique_cells = np.unique(cell_ids)

            n_bins = max(4, int(window_s / time_bin_s))
            bin_edges = np.linspace(t, t_end, n_bins + 1)

            for cid in unique_cells:
                cmask = cell_ids == cid
                cevents = win_events[cmask]
                if cevents.shape[0] < min_events:
                    continue

                counts, _ = np.histogram(cevents[:, 2], bins=bin_edges)
                if counts.sum() == 0:
                    continue

                counts = counts.astype(float) - counts.mean()
                spectrum = np.abs(np.fft.rfft(counts))
                freqs = np.fft.rfftfreq(n_bins, d=time_bin_s)

                if len(freqs) < 2:
                    continue
                band = (freqs >= blink_freq_hz * (1 - freq_tolerance)) & \
                       (freqs <= blink_freq_hz * (1 + freq_tolerance))
                total_power = spectrum[1:].sum() + 1e-9  # exclude DC
                band_power = spectrum[band].sum() if band.any() else 0.0
                score = band_power / total_power

                if best is None or score > best["confidence"]:
                    cx = cevents[:, 0].mean()
                    cy = cevents[:, 1].mean()
                    best = {"t": t, "x": float(cx), "y": float(cy),
                            "confidence": float(score),
                            "n_events": int(cevents.shape[0])}

        detections.append(best)
        t += window_s

    return detections


def summarize_detections(detections, true_xy_at_window_starts=None,
                          confidence_threshold: float = 0.15):
    """Quick pass/fail summary: fraction of windows where a detection above
    threshold exists, and (if ground truth is provided) mean position error
    on those windows. Used to produce the clean-vs-noisy comparison numbers
    for the pitch.
    """
    n_windows = len(detections)
    hits = [d for d in detections if d is not None and d["confidence"] >= confidence_threshold]
    hit_rate = len(hits) / n_windows if n_windows else 0.0

    result = {"n_windows": n_windows, "n_hits": len(hits), "hit_rate": hit_rate}

    if true_xy_at_window_starts is not None:
        errors = []
        for i, d in enumerate(detections):
            if d is not None and d["confidence"] >= confidence_threshold and i < len(true_xy_at_window_starts):
                tx, ty = true_xy_at_window_starts[i]
                err = np.hypot(d["x"] - tx, d["y"] - ty)
                errors.append(err)
        result["mean_position_error_px"] = float(np.mean(errors)) if errors else None
        result["n_scored"] = len(errors)

    return result


if __name__ == "__main__":
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from core.scene_gen import load_scene
    from core.event_emulator import frames_to_events, add_sensor_noise_events

    frames, gt = load_scene("outputs/demo_scene")
    fps = gt["fps"]
    frame_size = tuple(gt["frame_size"])
    blink_hz = gt["blink_freq_hz"]
    duration_s = gt["duration_s"]

    clean_events = frames_to_events(frames, fps=fps, threshold=0.15)

    print("=== Clean events (no sensor noise) ===")
    dets = lock_on(clean_events, frame_size, blink_hz)
    true_xy = gt["true_xy"]
    # sample true_xy at each window's starting frame index
    window_frames = [int(d["t"] * fps) if d else None for d in
                      [{"t": i * 0.05} for i in range(len(dets))]]
    true_at_windows = [true_xy[min(int(i*0.05*fps), len(true_xy)-1)] for i in range(len(dets))]
    summary_clean = summarize_detections(dets, true_at_windows)
    print(summary_clean)

    print()
    print("=== With realistic sensor background-activity noise (0.5 Hz/px) ===")
    noisy_events = add_sensor_noise_events(clean_events, frame_size, duration_s,
                                            rate_hz_per_pixel=0.5, seed=gt.get("seed", 42) if isinstance(gt, dict) else 42)
    dets_noisy = lock_on(noisy_events, frame_size, blink_hz)
    summary_noisy = summarize_detections(dets_noisy, true_at_windows)
    print(summary_noisy)
    print("Persisted baseline:", evaluate_classical_baseline())
