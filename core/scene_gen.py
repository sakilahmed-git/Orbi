"""
Section 1 — Physics core: scene generator.

Generates a synthetic scene of a frequency-modulated point-source beacon
against a noisy background, with an injectable vibration/turbulence profile
and exact ground truth for everything (position trace, PSD parameters used,
blink frequency, per-frame brightness).

No dependency on anything else in the project — this is the foundation
every other section builds on.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import Optional

import numpy as np


# --------------------------------------------------------------------------
# Parameter containers (kept explicit and serializable so ground truth is
# never ambiguous to a later session or a judge asking "how was this made?")
# --------------------------------------------------------------------------

@dataclass
class VibrationParams:
    """Defines the injected mechanical vibration as a sum of sinusoids plus
    optional broadband jitter. This is the 'known ground truth' that
    Section 6 (disturbance characterization) has to recover from event
    statistics alone.
    """
    # Dominant vibration component(s): list of (freq_hz, amplitude_px, phase_rad)
    components: list = field(default_factory=lambda: [(15.0, 2.0, 0.0)])
    # Broadband jitter standard deviation (px) added on top, per-frame,
    # smoothed with a short correlation time to avoid pure white noise.
    broadband_std_px: float = 0.3
    broadband_correlation_frames: int = 2


@dataclass
class TurbulenceParams:
    """Scintillation-style brightness flicker: a correlated random walk
    multiplying beacon intensity. correlation_time_s controls how fast the
    flicker decorrelates -- shorter = faster flicker (higher-frequency
    turbulence), longer = slower fades.
    """
    strength: float = 0.3          # 0 = no flicker, 1 = can fully dim the beacon
    correlation_time_s: float = 0.05


@dataclass
class SceneGroundTruth:
    fps: int
    duration_s: float
    frame_size: tuple
    blink_freq_hz: float
    vibration: dict
    turbulence: dict
    background_clutter_level: float
    beacon_base_xy: tuple
    # Per-frame arrays (as lists for JSON-friendliness; also saved as .npz)
    true_xy: list            # [(x, y), ...] exact beacon center per frame, px
    true_brightness: list    # [b, ...] exact beacon brightness per frame, 0..1
    injected_jitter_xy: list  # [(dx, dy), ...] exact vibration offset per frame, px

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)


# --------------------------------------------------------------------------
# Core generator
# --------------------------------------------------------------------------

def _make_vibration_trace(n_frames: int, fps: int, params: VibrationParams,
                           rng: np.random.Generator) -> np.ndarray:
    """Returns an (n_frames, 2) array of exact (dx, dy) jitter offsets in
    pixels. Deterministic given the same rng seed -- this trace IS the
    ground truth Section 6 must recover from event statistics.
    """
    t = np.arange(n_frames) / fps
    dx = np.zeros(n_frames)
    dy = np.zeros(n_frames)

    for (freq_hz, amp_px, phase) in params.components:
        dx += amp_px * np.sin(2 * np.pi * freq_hz * t + phase)
        dy += amp_px * np.cos(2 * np.pi * freq_hz * t + phase * 1.3)

    if params.broadband_std_px > 0:
        raw = rng.normal(0, params.broadband_std_px, size=(n_frames, 2))
        k = max(1, params.broadband_correlation_frames)
        kernel = np.ones(k) / k
        raw[:, 0] = np.convolve(raw[:, 0], kernel, mode="same")
        raw[:, 1] = np.convolve(raw[:, 1], kernel, mode="same")
        dx += raw[:, 0]
        dy += raw[:, 1]

    return np.stack([dx, dy], axis=1)


def _make_turbulence_trace(n_frames: int, fps: int, params: TurbulenceParams,
                            rng: np.random.Generator) -> np.ndarray:
    """Returns an (n_frames,) array of brightness multipliers in [1-strength, 1],
    a correlated random walk standing in for atmospheric scintillation.
    """
    if params.strength <= 0:
        return np.ones(n_frames)

    corr_frames = max(1, int(params.correlation_time_s * fps))
    raw = rng.normal(0, 1.0, size=n_frames)
    kernel = np.ones(corr_frames) / corr_frames
    smoothed = np.convolve(raw, kernel, mode="same")
    smoothed = (smoothed - smoothed.min()) / (np.ptp(smoothed) + 1e-9)  # -> [0,1]
    return 1.0 - params.strength * smoothed


def _draw_gaussian_blob(frame: np.ndarray, x: float, y: float,
                         brightness: float, sigma: float = 2.0) -> None:
    """In-place draw of a bright Gaussian blob centered at (x, y)."""
    h, w = frame.shape
    xi, yi = int(round(x)), int(round(y))
    r = int(sigma * 4)
    x0, x1 = max(0, xi - r), min(w, xi + r + 1)
    y0, y1 = max(0, yi - r), min(h, yi + r + 1)
    if x0 >= x1 or y0 >= y1:
        return
    xs = np.arange(x0, x1)
    ys = np.arange(y0, y1)
    xx, yy = np.meshgrid(xs, ys)
    g = np.exp(-(((xx - x) ** 2 + (yy - y) ** 2) / (2 * sigma ** 2)))
    frame[y0:y1, x0:x1] = np.clip(
        frame[y0:y1, x0:x1] + brightness * g, 0.0, 1.0
    )


def _make_clutter_field(frame_size: tuple, level: float,
                         rng: np.random.Generator) -> np.ndarray:
    """Generates a STATIC clutter background (fixed speckle positions +
    a fixed low-level ambient texture), computed ONCE per scene.

    This matters physically, not just for tidiness: a real DVS pixel only
    fires on brightness CHANGE. Unchanging background clutter (sun glint,
    background stars, sensor fixed-pattern noise) should be event-silent --
    that silence is the actual dynamic-range advantage event sensors have
    over frame cameras. An earlier version of this function re-randomized
    speckle positions every frame, which made the whole background 'change'
    constantly and flooded the event stream with spurious noise (millions
    of events from clutter alone). Keeping clutter static and only letting
    the BEACON change is what makes the beacon stand out in event space,
    which is the entire point of the demo.
    """
    h, w = frame_size
    field = np.zeros((h, w), dtype=np.float32)
    if level <= 0:
        return field
    ambient = rng.normal(0, 0.01 * level, size=(h, w)).astype(np.float32)
    field += ambient
    n_speckles = int(level * 8)
    for _ in range(n_speckles):
        sx, sy = rng.uniform(0, w), rng.uniform(0, h)
        sb = rng.uniform(0.2, 0.9) * level
        _draw_gaussian_blob(field, sx, sy, sb, sigma=rng.uniform(0.8, 1.5))
    np.clip(field, 0.0, 1.0, out=field)
    return field


def generate_scene(
    duration_s: float = 2.0,
    fps: int = 200,
    blink_freq_hz: float = 20.0,
    vibration: Optional[VibrationParams] = None,
    turbulence: Optional[TurbulenceParams] = None,
    background_clutter_level: float = 0.3,
    frame_size: tuple = (128, 128),
    beacon_base_xy: Optional[tuple] = None,
    seed: int = 0,
):
    """Generate a synthetic FSOC-beacon scene.

    Returns
    -------
    frames : np.ndarray, shape (n_frames, H, W), float32 in [0, 1]
    ground_truth : SceneGroundTruth
    """
    vibration = vibration or VibrationParams()
    turbulence = turbulence or TurbulenceParams()
    h, w = frame_size
    beacon_base_xy = beacon_base_xy or (w / 2.0, h / 2.0)

    rng = np.random.default_rng(seed)
    n_frames = int(duration_s * fps)

    jitter_xy = _make_vibration_trace(n_frames, fps, vibration, rng)
    turb_mult = _make_turbulence_trace(n_frames, fps, turbulence, rng)

    t = np.arange(n_frames) / fps
    # Square-wave-ish blink (soft edges) -- this is the "frequency-modulated
    # beacon" signal every downstream matched filter is looking for.
    blink = 0.5 * (1 + np.sign(np.sin(2 * np.pi * blink_freq_hz * t)))
    blink = 0.15 + 0.85 * blink  # never fully off, keeps some signal at all times

    clutter_field = _make_clutter_field(frame_size, background_clutter_level, rng)

    frames = np.zeros((n_frames, h, w), dtype=np.float32)
    true_xy = np.zeros((n_frames, 2))
    true_brightness = np.zeros(n_frames)

    for i in range(n_frames):
        x = beacon_base_xy[0] + jitter_xy[i, 0]
        y = beacon_base_xy[1] + jitter_xy[i, 1]
        b = float(blink[i] * turb_mult[i])
        true_xy[i] = (x, y)
        true_brightness[i] = b

        frame = clutter_field.copy()
        _draw_gaussian_blob(frame, x, y, b, sigma=2.0)
        np.clip(frame, 0.0, 1.0, out=frame)
        frames[i] = frame

    gt = SceneGroundTruth(
        fps=fps,
        duration_s=duration_s,
        frame_size=frame_size,
        blink_freq_hz=blink_freq_hz,
        vibration=asdict(vibration),
        turbulence=asdict(turbulence),
        background_clutter_level=background_clutter_level,
        beacon_base_xy=tuple(beacon_base_xy),
        true_xy=true_xy.tolist(),
        true_brightness=true_brightness.tolist(),
        injected_jitter_xy=jitter_xy.tolist(),
    )
    return frames, gt


def save_scene(frames: np.ndarray, gt: SceneGroundTruth, out_prefix: str) -> None:
    """Saves frames as a compressed .npz and ground truth as .json, so
    later sections (and later Claude sessions) can load a fixed test scene
    without regenerating it."""
    np.savez_compressed(f"{out_prefix}_frames.npz", frames=frames)
    with open(f"{out_prefix}_ground_truth.json", "w") as f:
        f.write(gt.to_json())


def load_scene(out_prefix: str):
    data = np.load(f"{out_prefix}_frames.npz")
    frames = data["frames"]
    with open(f"{out_prefix}_ground_truth.json") as f:
        gt = json.load(f)
    return frames, gt


if __name__ == "__main__":
    # Quick smoke test / demo-scene generator.
    vib = VibrationParams(components=[(15.0, 2.5, 0.0)], broadband_std_px=0.4)
    turb = TurbulenceParams(strength=0.35, correlation_time_s=0.05)
    frames, gt = generate_scene(
        duration_s=1.0, fps=200, blink_freq_hz=20.0,
        vibration=vib, turbulence=turb,
        background_clutter_level=0.3, frame_size=(128, 128), seed=42,
    )
    print("frames shape:", frames.shape, "dtype:", frames.dtype)
    print("brightness range:", frames.min(), frames.max())
    print("example true_xy[0:3]:", gt.true_xy[:3])
    save_scene(frames, gt, "outputs/demo_scene")
    print("Saved demo scene to outputs/demo_scene_*")
