"""
Section 2 — Event emulator + frame-camera baseline.

Two independent conversions of the SAME high-fps synthetic frames from
Section 1, so the comparison between them is fair:

1. frames_to_events(...)       -> a DVS-style asynchronous event stream
                                   (x, y, t, polarity), using a standard
                                   per-pixel log-intensity accumulator model.

2. frames_to_frame_camera(...) -> a realistic lower-fps "conventional
                                   camera" sequence, produced by averaging
                                   (exposure-integrating) blocks of the same
                                   high-fps frames -- this gives REAL motion
                                   blur from real sub-frame motion, not an
                                   approximated blur kernel.

Both take the same `frames` array from core.scene_gen.generate_scene, so
whatever vibration/clutter was injected there is what breaks (or doesn't)
the frame-camera path here.
"""

from __future__ import annotations

import numpy as np


# --------------------------------------------------------------------------
# 1. Event emulator (per-pixel log-intensity accumulator -- the standard,
#    well-documented way to approximate DVS behaviour from a frame sequence)
# --------------------------------------------------------------------------

def frames_to_events(frames: np.ndarray, fps: int, threshold: float = 0.15,
                      eps: float = 1e-3, refractory_frames: int = 0):
    """Convert a (N, H, W) float32 [0,1] frame sequence into a synthetic
    event stream.

    Model: each pixel keeps a running log-intensity reference. Whenever the
    current log-intensity has drifted from the reference by more than
    `threshold` (up or down), an event of the corresponding polarity fires,
    and the reference is stepped by exactly `threshold` in that direction
    (so multiple events can fire between two frames if the change is large --
    this is the standard way DVS pixels behave, and it's what gives event
    cameras their high dynamic range: change is measured in log space,
    not absolute brightness).

    Returns
    -------
    events : np.ndarray, shape (M, 4), columns = [x, y, t_seconds, polarity]
             polarity is +1 (brighter) or -1 (dimmer). Sorted by time.
    """
    n, h, w = frames.shape
    log_frames = np.log(frames.astype(np.float64) + eps)

    ref = log_frames[0].copy()
    events_x, events_y, events_t, events_p = [], [], [], []

    for i in range(1, n):
        cur = log_frames[i]
        t = i / fps
        diff = cur - ref
        # A pixel can cross the threshold multiple times if the jump is big;
        # loop is bounded (clutter/blink changes are small in practice, but
        # this keeps the model honest rather than silently capping at 1).
        remaining = diff.copy()
        while True:
            fire_pos = remaining >= threshold
            fire_neg = remaining <= -threshold
            if not (fire_pos.any() or fire_neg.any()):
                break
            ys, xs = np.where(fire_pos)
            events_x.append(xs); events_y.append(ys)
            events_t.append(np.full(len(xs), t)); events_p.append(np.ones(len(xs)))
            ref_update_pos = fire_pos * threshold
            ys, xs = np.where(fire_neg)
            events_x.append(xs); events_y.append(ys)
            events_t.append(np.full(len(xs), t)); events_p.append(-np.ones(len(xs)))
            ref_update_neg = fire_neg * threshold
            ref += ref_update_pos
            ref -= ref_update_neg
            remaining = cur - ref

    if not events_x:
        return np.zeros((0, 4))

    x = np.concatenate(events_x)
    y = np.concatenate(events_y)
    t = np.concatenate(events_t)
    p = np.concatenate(events_p)
    events = np.stack([x, y, t, p], axis=1)
    events = events[np.argsort(events[:, 2])]
    return events


def accumulate_events_to_frame(events: np.ndarray, frame_shape: tuple,
                                t_start: float, t_end: float) -> np.ndarray:
    """Render a window of events into a viewable image for comparison /
    demo purposes: positive events -> one channel, negative -> another,
    background stays dark (this is the classic 'event frame' visualization,
    NOT how the algorithm actually consumes events -- the algorithm should
    work on the raw (x, y, t, polarity) stream).
    """
    h, w = frame_shape
    img = np.zeros((h, w, 3), dtype=np.float32)
    if events.shape[0] == 0:
        return img
    mask = (events[:, 2] >= t_start) & (events[:, 2] < t_end)
    sub = events[mask]
    for x, y, _, p in sub:
        x, y = int(x), int(y)
        if p > 0:
            img[y, x, 1] = min(1.0, img[y, x, 1] + 0.3)   # green = brighter
        else:
            img[y, x, 0] = min(1.0, img[y, x, 0] + 0.3)   # red = dimmer
    return img


# --------------------------------------------------------------------------
# 2. Frame-camera baseline (real exposure-averaging motion blur, not a
#    kernel approximation -- because we have the high-fps ground-truth
#    frames, we can integrate them directly)
# --------------------------------------------------------------------------

def frames_to_frame_camera(frames: np.ndarray, fps_in: int,
                            target_fps: int = 30,
                            exposure_fraction: float = 1.0) -> tuple:
    """Downsample the high-fps synthetic sequence into what a real
    `target_fps` frame camera would have captured, including genuine motion
    blur from integrating over the exposure window.

    exposure_fraction: fraction of each output frame's period that the
    'shutter' is open. 1.0 = full-frame exposure (maximum blur), lower
    values = shorter exposure (less blur, more noise in a real camera --
    we don't model added photon noise here, just the blur trade-off).

    Returns
    -------
    out_frames : np.ndarray, shape (M, H, W), float32 in [0,1]
    out_fps    : int (== target_fps)
    """
    n, h, w = frames.shape
    frames_per_output = max(1, int(round(fps_in / target_fps)))
    exposure_frames = max(1, int(round(frames_per_output * exposure_fraction)))

    out = []
    i = 0
    while i + frames_per_output <= n:
        window = frames[i : i + exposure_frames]
        out.append(window.mean(axis=0))
        i += frames_per_output

    out_frames = np.stack(out, axis=0) if out else np.zeros((0, h, w), dtype=np.float32)
    return out_frames.astype(np.float32), target_fps


if __name__ == "__main__":
    import os
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from core.scene_gen import load_scene

    frames, gt = load_scene("outputs/demo_scene")
    fps = gt["fps"]

    print("Converting to events...")
    events = frames_to_events(frames, fps=fps, threshold=0.15)
    print(f"  {events.shape[0]} events generated from {frames.shape[0]} frames")

    print("Converting to frame-camera baseline (30fps, full exposure)...")
    blurred, out_fps = frames_to_frame_camera(frames, fps_in=fps, target_fps=30,
                                               exposure_fraction=1.0)
    print(f"  {blurred.shape[0]} output frames at {out_fps} fps")

    np.savez_compressed("outputs/demo_scene_events.npz",
                         events=events)
    np.savez_compressed("outputs/demo_scene_blurred.npz",
                         frames=blurred, fps=out_fps)
    print("Saved event stream and blurred baseline.")
