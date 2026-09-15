"""
Section 7 -- Acquisition-envelope surrogate.

Runs a compact synthetic sweep through the existing Scintilla pipeline and
trains a lightweight model that predicts acquisition success probability
from scenario parameters.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass

import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import accuracy_score, confusion_matrix
from sklearn.model_selection import train_test_split

from ai.discriminator import discriminate_lock_on, load_discriminator
from core.event_emulator import add_sensor_noise_events, frames_to_events
from core.scene_gen import TurbulenceParams, VibrationParams, generate_scene


@dataclass
class EnvelopeScenarioResult:
    vibration_amp_px: float
    vibration_frequency_hz: float
    turbulence_strength: float
    clutter_level: float
    noise_rate_hz_per_px: float
    seed: int
    mean_error_px: float | None
    hit_rate: float
    success: int


def _score_detections(detections, gt, max_error_px: float = 6.0, min_hit_rate: float = 0.8):
    errors = []
    hits = 0
    for i, det in enumerate(detections):
        if det is None or det["confidence"] < 0.15:
            continue
        hits += 1
        gt_idx = min(int(i * 0.05 * gt.fps), len(gt.true_xy) - 1)
        tx, ty = gt.true_xy[gt_idx]
        errors.append(float(np.hypot(det["x"] - tx, det["y"] - ty)))
    hit_rate = hits / max(1, len(detections))
    mean_error = float(np.mean(errors)) if errors else None
    success = int(mean_error is not None and mean_error <= max_error_px and hit_rate >= min_hit_rate)
    return mean_error, hit_rate, success


def run_envelope_sweep(
    discriminator_model_path: str = "outputs/models/discriminator_gbc.joblib",
    out_json: str = "outputs/logs/section7_envelope_sweep.json",
) -> list[EnvelopeScenarioResult]:
    model = load_discriminator(discriminator_model_path)
    amps = [1.0, 3.5, 6.0]
    turbs = [0.0, 0.5]
    clutters = [0.1, 0.8]
    noise_rates = [1.0, 5.0, 8.0]
    rows: list[EnvelopeScenarioResult] = []

    for idx, (amp, turb, clutter, noise) in enumerate(
        (a, t, c, n) for a in amps for t in turbs for c in clutters for n in noise_rates
    ):
        seed = 3000 + idx
        frames, gt = generate_scene(
            duration_s=0.6,
            fps=200,
            blink_freq_hz=20.0,
            vibration=VibrationParams(
                components=[(15.0 + 0.7 * (idx % 5), amp, 0.11 * idx)],
                broadband_std_px=0.12 + 0.07 * amp,
            ),
            turbulence=TurbulenceParams(strength=turb, correlation_time_s=0.05),
            background_clutter_level=clutter,
            frame_size=(128, 128),
            seed=seed,
        )
        clean = frames_to_events(frames, fps=gt.fps, threshold=0.15)
        noisy = add_sensor_noise_events(clean, tuple(gt.frame_size), gt.duration_s,
                                        rate_hz_per_pixel=noise, seed=seed)
        detections = discriminate_lock_on(noisy, tuple(gt.frame_size), gt.blink_freq_hz, model)
        mean_error, hit_rate, success = _score_detections(detections, gt)
        rows.append(EnvelopeScenarioResult(
            vibration_amp_px=float(amp),
            vibration_frequency_hz=float(15.0 + 0.7 * (idx % 5)),
            turbulence_strength=float(turb),
            clutter_level=float(clutter),
            noise_rate_hz_per_px=float(noise),
            seed=seed,
            mean_error_px=mean_error,
            hit_rate=float(hit_rate),
            success=success,
        ))

    os.makedirs(os.path.dirname(out_json), exist_ok=True)
    with open(out_json, "w") as f:
        json.dump([asdict(r) for r in rows], f, indent=2)
    return rows


def _feature_matrix(rows: list[EnvelopeScenarioResult]):
    x = np.array([
        [r.vibration_amp_px, r.turbulence_strength, r.clutter_level, r.noise_rate_hz_per_px]
        for r in rows
    ], dtype=float)
    y = np.array([r.success for r in rows], dtype=int)
    return x, y


def train_envelope_surrogate(
    rows: list[EnvelopeScenarioResult],
    model_path: str = "outputs/models/envelope_surrogate.joblib",
) -> tuple[GradientBoostingClassifier, dict]:
    x, y = _feature_matrix(rows)
    stratify = y if len(np.unique(y)) == 2 and min(np.bincount(y)) >= 2 else None
    x_train, x_test, y_train, y_test = train_test_split(
        x, y, test_size=0.25, random_state=77, stratify=stratify
    )
    clf = GradientBoostingClassifier(random_state=77, n_estimators=80, max_depth=2)
    clf.fit(x_train, y_train)
    pred = clf.predict(x_test)
    metrics = {
        "n_scenarios": int(len(rows)),
        "success_rate": float(y.mean()),
        "test_accuracy": float(accuracy_score(y_test, pred)),
        "confusion_matrix": confusion_matrix(y_test, pred).tolist(),
        "feature_order": ["vibration_amp_px", "turbulence_strength", "clutter_level", "noise_rate_hz_per_px"],
    }
    os.makedirs(os.path.dirname(model_path), exist_ok=True)
    joblib.dump({"model": clf, "metrics": metrics}, model_path)
    return clf, metrics


def make_heatmap(
    surrogate,
    plot_path: str = "outputs/plots/section7_acquisition_envelope_heatmap.png",
    data_path: str = "outputs/logs/section7_heatmap_grid.json",
    turbulence_strength: float = 0.35,
    noise_rate_hz_per_px: float = 5.0,
) -> dict:
    amps = np.linspace(0.5, 7.0, 40)
    clutters = np.linspace(0.0, 0.9, 40)
    grid = np.zeros((len(clutters), len(amps)), dtype=float)
    for iy, clutter in enumerate(clutters):
        x = np.array([[amp, turbulence_strength, clutter, noise_rate_hz_per_px] for amp in amps])
        grid[iy, :] = surrogate.predict_proba(x)[:, 1]

    os.makedirs(os.path.dirname(plot_path), exist_ok=True)
    plt.figure(figsize=(8, 5.5))
    im = plt.imshow(
        grid,
        origin="lower",
        aspect="auto",
        extent=[amps.min(), amps.max(), clutters.min(), clutters.max()],
        vmin=0,
        vmax=1,
        cmap="viridis",
    )
    plt.colorbar(im, label="predicted acquisition success probability")
    plt.xlabel("vibration amplitude (px)")
    plt.ylabel("clutter level")
    plt.title(f"Section 7 envelope: turbulence={turbulence_strength}, noise={noise_rate_hz_per_px} Hz/px")
    plt.tight_layout()
    plt.savefig(plot_path, dpi=160)
    plt.close()

    heatmap = {
        "vibration_amp_px": amps.tolist(),
        "clutter_level": clutters.tolist(),
        "success_probability": grid.tolist(),
        "fixed_turbulence_strength": turbulence_strength,
        "fixed_noise_rate_hz_per_px": noise_rate_hz_per_px,
        "plot": plot_path,
    }
    os.makedirs(os.path.dirname(data_path), exist_ok=True)
    with open(data_path, "w") as f:
        json.dump(heatmap, f, indent=2)
    return heatmap


def build_envelope():
    rows = run_envelope_sweep()
    surrogate, metrics = train_envelope_surrogate(rows)
    heatmap = make_heatmap(surrogate)
    summary = {"metrics": metrics, "heatmap": {k: v for k, v in heatmap.items() if k != "success_probability"}}
    with open("outputs/logs/section7_envelope_metrics.json", "w") as f:
        json.dump(summary, f, indent=2)
    return summary


if __name__ == "__main__":
    result = build_envelope()
    print("section7_envelope:", result)
