"""
Section 5 -- Learned discriminator.

Small, explicit classifier for telling true modulated-beacon event clusters
from sensor-noise clusters. The model consumes hand-engineered cluster
features only; raw pixels/events are never fed into a deep model.
"""

from __future__ import annotations

import os
import json
from dataclasses import dataclass
from typing import Iterable

import joblib
import sklearn
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.model_selection import train_test_split

from ai.lockon import lock_on, summarize_detections
from core.event_emulator import add_sensor_noise_events, frames_to_events
from core.scene_gen import TurbulenceParams, VibrationParams, generate_scene


FEATURE_NAMES = [
    "event_rate_hz",
    "n_events",
    "fft_blink_score",
    "isi_regularity",
    "spatial_compactness",
    "polarity_balance",
    "blink_edge_concentration",
    "temporal_consistency",
    "centroid_x_norm",
    "centroid_y_norm",
]


@dataclass
class CandidateCluster:
    window_index: int
    t: float
    x: float
    y: float
    n_events: int
    features: np.ndarray
    label: int | None = None
    probability: float | None = None


def _blink_edge_concentration(times: np.ndarray, blink_freq_hz: float) -> float:
    if times.size == 0:
        return 0.0
    phase = (times * blink_freq_hz) % 1.0
    distance_to_edge = np.minimum.reduce([
        np.abs(phase - 0.0),
        np.abs(phase - 0.5),
        np.abs(phase - 1.0),
    ])
    return float(np.mean(np.exp(-0.5 * (distance_to_edge / 0.08) ** 2)))


def _isi_regularity(times: np.ndarray, blink_freq_hz: float) -> float:
    if times.size < 4:
        return 0.0
    diffs = np.diff(np.sort(times))
    diffs = diffs[diffs > 1e-6]
    if diffs.size == 0:
        return 0.0
    expected = 0.5 / blink_freq_hz
    nearest_multiple = np.maximum(1, np.round(diffs / expected)) * expected
    rel_error = np.abs(diffs - nearest_multiple) / expected
    return float(np.exp(-np.median(rel_error)))


def _fft_blink_score(times: np.ndarray, t0: float, t1: float,
                     blink_freq_hz: float, n_bins: int = 12) -> float:
    if times.size < 4:
        return 0.0
    counts, _ = np.histogram(times, bins=np.linspace(t0, t1, n_bins + 1))
    counts = counts.astype(float) - counts.mean()
    spectrum = np.abs(np.fft.rfft(counts))
    freqs = np.fft.rfftfreq(n_bins, d=(t1 - t0) / n_bins)
    if spectrum.size < 2:
        return 0.0
    band = (freqs >= 0.65 * blink_freq_hz) & (freqs <= 1.35 * blink_freq_hz)
    return float(spectrum[band].sum() / (spectrum[1:].sum() + 1e-9))


def extract_candidate_clusters(
    events: np.ndarray,
    frame_size: tuple[int, int],
    blink_freq_hz: float,
    window_s: float = 0.05,
    grid_size: int = 8,
    min_events: int = 12,
    true_xy: Iterable | None = None,
    fps: int | None = None,
    label_radius_px: float = 12.0,
) -> list[CandidateCluster]:
    """Extract candidate event clusters and explicit features per window."""
    h, w = frame_size
    if events.size == 0:
        return []

    n_cells_x = int(np.ceil(w / grid_size))
    t_max = float(events[:, 2].max())
    true_xy_arr = np.asarray(list(true_xy), dtype=float) if true_xy is not None else None
    candidates: list[CandidateCluster] = []
    per_window: dict[int, list[int]] = {}

    t = 0.0
    window_index = 0
    while t < t_max:
        t1 = t + window_s
        win = events[(events[:, 2] >= t) & (events[:, 2] < t1)]
        if win.shape[0] >= min_events:
            cx_cell = np.clip((win[:, 0] // grid_size).astype(int), 0, n_cells_x - 1)
            cy_cell = np.clip((win[:, 1] // grid_size).astype(int), 0, int(np.ceil(h / grid_size)) - 1)
            cell_ids = cy_cell * n_cells_x + cx_cell
            for cid in np.unique(cell_ids):
                ce = win[cell_ids == cid]
                if ce.shape[0] < min_events:
                    continue
                x = float(ce[:, 0].mean())
                y = float(ce[:, 1].mean())
                centered = ce[:, :2] - np.array([x, y])
                rms_radius = float(np.sqrt(np.mean(np.sum(centered * centered, axis=1))))
                compactness = float(1.0 / (1.0 + rms_radius))
                polarity_balance = float(1.0 - abs(np.mean(ce[:, 3])))

                base_features = np.array([
                    ce.shape[0] / window_s,
                    ce.shape[0],
                    _fft_blink_score(ce[:, 2], t, t1, blink_freq_hz),
                    _isi_regularity(ce[:, 2], blink_freq_hz),
                    compactness,
                    polarity_balance,
                    _blink_edge_concentration(ce[:, 2], blink_freq_hz),
                    0.0,  # filled after all windows are known
                    x / max(1, w),
                    y / max(1, h),
                ], dtype=float)

                label = None
                if true_xy_arr is not None and fps is not None:
                    gt_idx = min(int((t + 0.5 * window_s) * fps), len(true_xy_arr) - 1)
                    label = int(np.hypot(x - true_xy_arr[gt_idx, 0],
                                         y - true_xy_arr[gt_idx, 1]) <= label_radius_px)

                idx = len(candidates)
                candidates.append(CandidateCluster(window_index, t, x, y,
                                                   int(ce.shape[0]), base_features, label))
                per_window.setdefault(window_index, []).append(idx)
        t += window_s
        window_index += 1

    for i, cand in enumerate(candidates):
        neighbor_scores = []
        for j in per_window.get(cand.window_index - 1, []) + per_window.get(cand.window_index + 1, []):
            other = candidates[j]
            neighbor_scores.append(np.exp(-np.hypot(cand.x - other.x, cand.y - other.y) / 12.0))
        cand.features[7] = float(max(neighbor_scores) if neighbor_scores else 0.0)

    return candidates


def candidates_to_matrix(candidates: list[CandidateCluster]) -> tuple[np.ndarray, np.ndarray]:
    x = np.vstack([c.features for c in candidates]).astype(float)
    y = np.array([c.label for c in candidates], dtype=int)
    return x, y


def generate_training_dataset() -> tuple[np.ndarray, np.ndarray]:
    rows: list[np.ndarray] = []
    labels: list[int] = []
    vib_amps = [0.8, 2.5, 4.5]
    turb_levels = [0.0, 0.35]
    clutter_levels = [0.1, 0.5]
    noise_rates = [0.5, 2.0, 5.0]
    seeds = [3, 11]

    for seed in seeds:
        for amp in vib_amps:
            for turb in turb_levels:
                for clutter in clutter_levels:
                    for noise_rate in noise_rates:
                        frames, gt = generate_scene(
                            duration_s=1.0,
                            fps=200,
                            blink_freq_hz=20.0,
                            vibration=VibrationParams(
                                components=[(15.0, amp, 0.15 * seed)],
                                broadband_std_px=0.15 + 0.1 * amp,
                            ),
                            turbulence=TurbulenceParams(strength=turb, correlation_time_s=0.05),
                            background_clutter_level=clutter,
                            frame_size=(128, 128),
                            seed=seed,
                        )
                        clean = frames_to_events(frames, fps=gt.fps, threshold=0.15)
                        noisy = add_sensor_noise_events(clean, tuple(gt.frame_size), gt.duration_s,
                                                        rate_hz_per_pixel=noise_rate, seed=seed)
                        cands = extract_candidate_clusters(noisy, tuple(gt.frame_size),
                                                           gt.blink_freq_hz, true_xy=gt.true_xy,
                                                           fps=gt.fps)
                        for c in cands:
                            rows.append(c.features)
                            labels.append(int(c.label))

    return np.vstack(rows), np.asarray(labels, dtype=int)


def train_discriminator(model_path: str = "outputs/models/discriminator_gbc.joblib"):
    x, y = generate_training_dataset()
    x_train, x_test, y_train, y_test = train_test_split(
        x, y, test_size=0.25, random_state=7, stratify=y
    )
    clf = GradientBoostingClassifier(random_state=7, n_estimators=120, max_depth=2)
    clf.fit(x_train, y_train)
    y_pred = clf.predict(x_test)

    os.makedirs(os.path.dirname(model_path), exist_ok=True)
    # Write atomically so an interrupted retrain never removes the last known
    # good artifact. The version tag is checked at load time by the API.
    tmp_path = f"{model_path}.tmp"
    joblib.dump({"model": clf, "feature_names": FEATURE_NAMES,
                 "sklearn_version": sklearn.__version__}, tmp_path)
    os.replace(tmp_path, model_path)
    metrics = {
        "n_samples": int(len(y)),
        "positive_rate": float(y.mean()),
        "test_report": classification_report(y_test, y_pred, output_dict=True, zero_division=0),
        "confusion_matrix": confusion_matrix(y_test, y_pred).tolist(),
    }
    return clf, metrics


def load_discriminator(model_path: str = "outputs/models/discriminator_gbc.joblib"):
    artifact = joblib.load(model_path)
    saved_version = artifact.get("sklearn_version")
    if saved_version != sklearn.__version__:
        raise RuntimeError(
            f"discriminator artifact sklearn={saved_version or 'unknown'}; runtime sklearn={sklearn.__version__}. "
            "Retrain with the pinned requirements before serving results."
        )
    return artifact["model"]


def discriminate_lock_on(
    events: np.ndarray,
    frame_size: tuple[int, int],
    blink_freq_hz: float,
    model,
    window_s: float = 0.05,
    grid_size: int = 8,
    probability_threshold: float = 0.15,
) -> list[dict | None]:
    cands = extract_candidate_clusters(events, frame_size, blink_freq_hz,
                                       window_s=window_s, grid_size=grid_size)
    by_window: dict[int, list[CandidateCluster]] = {}
    for c in cands:
        c.probability = float(model.predict_proba(c.features.reshape(1, -1))[0, 1])
        by_window.setdefault(c.window_index, []).append(c)

    n_windows = int(np.ceil((events[:, 2].max() if events.size else 0.0) / window_s))
    detections: list[dict | None] = []
    for wi in range(n_windows):
        window_cands = by_window.get(wi, [])
        if not window_cands:
            detections.append(None)
            continue
        best = max(window_cands, key=lambda c: c.probability or 0.0)
        if (best.probability or 0.0) < probability_threshold:
            detections.append(None)
        else:
            detections.append({
                "t": best.t,
                "x": best.x,
                "y": best.y,
                "confidence": float(best.probability),
                "n_events": best.n_events,
            })
    return detections


def exact_section5_scenario(seed: int = 42):
    vib = VibrationParams(components=[(15.0, 2.5, 0.0)], broadband_std_px=0.4)
    turb = TurbulenceParams(strength=0.35, correlation_time_s=0.05)
    frames, gt = generate_scene(
        duration_s=1.0,
        fps=200,
        blink_freq_hz=20.0,
        vibration=vib,
        turbulence=turb,
        background_clutter_level=0.3,
        frame_size=(128, 128),
        seed=seed,
    )
    clean = frames_to_events(frames, fps=gt.fps, threshold=0.15)
    noisy = add_sensor_noise_events(clean, tuple(gt.frame_size), gt.duration_s,
                                    rate_hz_per_pixel=5.0, seed=seed)
    return clean, noisy, gt


def evaluate_exact_scenario(model, plot_path: str = "outputs/plots/section5_discriminator_comparison.png"):
    clean, noisy, gt = exact_section5_scenario()
    true_at_windows = [
        gt.true_xy[min(int(i * 0.05 * gt.fps), len(gt.true_xy) - 1)]
        for i in range(int(np.ceil(gt.duration_s / 0.05)))
    ]
    clean_dets = lock_on(clean, tuple(gt.frame_size), gt.blink_freq_hz)
    noisy_dets = lock_on(noisy, tuple(gt.frame_size), gt.blink_freq_hz)
    learned_dets = discriminate_lock_on(noisy, tuple(gt.frame_size), gt.blink_freq_hz, model)

    clean_summary = summarize_detections(clean_dets, true_at_windows)
    noisy_summary = summarize_detections(noisy_dets, true_at_windows)
    learned_summary = summarize_detections(learned_dets, true_at_windows,
                                           confidence_threshold=0.15)

    os.makedirs(os.path.dirname(plot_path), exist_ok=True)
    gt_xy = np.asarray(gt.true_xy)
    plt.figure(figsize=(8, 6))
    plt.plot(gt_xy[:, 0], gt_xy[:, 1], "k-", lw=2, label="true beacon trace")
    for label, dets, color in [
        ("classical clean", clean_dets, "tab:green"),
        ("classical + 5 Hz/px noise", noisy_dets, "tab:red"),
        ("learned discriminator + 5 Hz/px noise", learned_dets, "tab:blue"),
    ]:
        pts = np.array([[d["x"], d["y"]] for d in dets if d is not None and d["confidence"] >= 0.15])
        if pts.size:
            plt.scatter(pts[:, 0], pts[:, 1], s=28, alpha=0.75, label=label, c=color)
    plt.gca().invert_yaxis()
    plt.axis("equal")
    plt.xlabel("x (px)")
    plt.ylabel("y (px)")
    plt.title("Section 5: exact 5 Hz/px noisy lock-on scenario")
    plt.legend()
    plt.tight_layout()
    plt.savefig(plot_path, dpi=160)
    plt.close()

    return {
        "clean_classical": clean_summary,
        "noisy_classical": noisy_summary,
        "noisy_learned": learned_summary,
        "plot": plot_path,
    }


def _mean_error(detections: list[dict | None], gt, confidence_threshold: float = 0.15) -> float | None:
    errors = []
    for i, det in enumerate(detections):
        if det is None or det["confidence"] < confidence_threshold:
            continue
        gt_idx = min(int(i * 0.05 * gt.fps), len(gt.true_xy) - 1)
        tx, ty = gt.true_xy[gt_idx]
        errors.append(float(np.hypot(det["x"] - tx, det["y"] - ty)))
    return float(np.mean(errors)) if errors else None


def evaluate_heldout_scenarios(
    model,
    seeds: Iterable[int] = range(1000, 1020),
    plot_path: str = "outputs/plots/section5_heldout_generalization.png",
    log_path: str = "outputs/logs/section5_heldout_generalization.json",
) -> dict:
    """Evaluate classical vs learned lock-on on unseen seeds/scenario settings."""
    rows = []
    for idx, seed in enumerate(seeds):
        amp = [1.2, 2.5, 4.0, 5.5][idx % 4]
        turb = [0.0, 0.2, 0.45, 0.65][idx % 4]
        clutter = [0.1, 0.3, 0.55, 0.75][(idx // 2) % 4]
        noise_rate = [2.0, 3.5, 5.0, 7.0][(idx // 3) % 4]
        freq = [12.0, 15.0, 18.0][idx % 3]
        frames, gt = generate_scene(
            duration_s=1.0,
            fps=200,
            blink_freq_hz=20.0,
            vibration=VibrationParams(
                components=[(freq, amp, 0.07 * seed)],
                broadband_std_px=0.15 + 0.08 * amp,
            ),
            turbulence=TurbulenceParams(strength=turb, correlation_time_s=0.05),
            background_clutter_level=clutter,
            frame_size=(128, 128),
            seed=seed,
        )
        clean = frames_to_events(frames, fps=gt.fps, threshold=0.15)
        noisy = add_sensor_noise_events(clean, tuple(gt.frame_size), gt.duration_s,
                                        rate_hz_per_pixel=noise_rate, seed=seed)
        classical = lock_on(noisy, tuple(gt.frame_size), gt.blink_freq_hz)
        learned = discriminate_lock_on(noisy, tuple(gt.frame_size), gt.blink_freq_hz, model)
        rows.append({
            "seed": int(seed),
            "vibration_frequency_hz": float(freq),
            "vibration_amplitude_px": float(amp),
            "turbulence_strength": float(turb),
            "clutter_level": float(clutter),
            "noise_rate_hz_per_px": float(noise_rate),
            "classical_mean_error_px": _mean_error(classical, gt),
            "learned_mean_error_px": _mean_error(learned, gt),
            "classical_hits": int(sum(d is not None and d["confidence"] >= 0.15 for d in classical)),
            "learned_hits": int(sum(d is not None and d["confidence"] >= 0.15 for d in learned)),
        })

    classical_errors = np.array([r["classical_mean_error_px"] for r in rows if r["classical_mean_error_px"] is not None])
    learned_errors = np.array([r["learned_mean_error_px"] for r in rows if r["learned_mean_error_px"] is not None])
    summary = {
        "train_seeds": [3, 11],
        "heldout_seeds": [int(s) for s in seeds],
        "seed_overlap_with_original_acceptance_seed_42": False,
        "classical_mean_error_px_mean": float(classical_errors.mean()),
        "classical_mean_error_px_std": float(classical_errors.std(ddof=1)),
        "learned_mean_error_px_mean": float(learned_errors.mean()),
        "learned_mean_error_px_std": float(learned_errors.std(ddof=1)),
        "n_scenarios": len(rows),
    }

    os.makedirs(os.path.dirname(plot_path), exist_ok=True)
    xs = np.arange(len(rows))
    plt.figure(figsize=(10, 4.8))
    plt.plot(xs, [r["classical_mean_error_px"] for r in rows], "o-", label="classical noisy")
    plt.plot(xs, [r["learned_mean_error_px"] for r in rows], "o-", label="learned noisy")
    plt.xlabel("held-out scenario index")
    plt.ylabel("mean position error (px)")
    plt.title("Section 5 held-out generalization audit")
    plt.legend()
    plt.tight_layout()
    plt.savefig(plot_path, dpi=160)
    plt.close()

    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    result = {"summary": summary, "scenarios": rows, "plot": plot_path}
    with open(log_path, "w") as f:
        json.dump(result, f, indent=2)
    return result


if __name__ == "__main__":
    clf, training_metrics = train_discriminator()
    comparison = evaluate_exact_scenario(clf)
    heldout = evaluate_heldout_scenarios(clf)
    os.makedirs("outputs/logs", exist_ok=True)
    with open("outputs/logs/section5_discriminator_metrics.json", "w") as f:
        json.dump({"training_metrics": training_metrics, "exact_5hzpx_comparison": comparison,
                   "heldout_generalization": heldout["summary"]},
                  f, indent=2)
    print("training_metrics:", training_metrics)
    print("exact_5hzpx_comparison:", comparison)
    print("heldout_generalization:", heldout["summary"])
