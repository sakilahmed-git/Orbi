"""
Section 3 -- Real-data ingestion: e-STURT dataset.

Verified against the actual Zenodo record (10.5281/zenodo.14031911) on
2026-09-14 -- this is not written against the paper's abstract alone.

CONFIRMED REAL EVENT CSV FORMAT (verified 2026-09-14 against an actual
uploaded sample from episode-17-equivalent data, 200,000 real rows):
  Columns, NO header row: x, y, polarity, timestamp_us, relative_idx
    x            : 0-1279   (matches Prophesee Gen 4.1 sensor width, 1280px)
    y            : 0-719    (matches sensor height, 720px)
    polarity     : {0, 1}   (NOT -1/+1 like our synthetic convention --
                              mapped below: 0 -> -1, 1 -> +1)
    timestamp_us : absolute Unix microseconds, e.g. 1703353290384183
    relative_idx : REDUNDANT -- verified exactly equal to
                    (timestamp_us - constant_offset) for the whole sample,
                    i.e. just a relative microsecond counter. Dropped.

CONFIRMED REAL SHAKER LOG FORMAT (verified against an actual uploaded
ground-truth file, 3875 real rows, ~218s span):
  Columns, NO header row: timestamp_us, axis1_value, axis2_value
    Sched at ~13.2 Hz median (76ms between samples) for this specific file
    (config "MOVMACS" = both axes active) -- NOT the ~30Hz figure loosely
    implied elsewhere; measured directly from this file's own timestamps.
    axis1 had ~10% exact-zero values in the sample checked, consistent
    with the dataset's documented "zero = missing data" convention;
    axis2 had none in this particular sample -- zero-as-NaN handling is
    applied to both columns regardless, since it's a documented dataset-
    wide convention, not something to assume varies file to file.

HONEST LIMITATION, stated plainly: the specific trimmed sample used to
verify this format covers only ~65.7ms of real events (200,000 rows,
head-truncated), while the ground-truth shaker log samples arrive roughly
every 76ms. That means this particular sample contains at most one nearby
ground-truth point -- enough to confirm the FORMAT is right, NOT enough to
do a real quantitative "recovered jitter vs. true jitter" validation
(that needs several seconds of real events, matched against several real
ground-truth samples). Section 6's real-data validation should request a
longer, untrimmed sample before claiming a quantitative match -- do not
claim disturbance-recovery accuracy against real data from this sample.
"""

import numpy as np
import pandas as pd


# --------------------------------------------------------------------------
# Diagnostic -- ALWAYS run this first on a new real file, before assuming
# anything about its format.
# --------------------------------------------------------------------------

def inspect_raw_csv(path: str, n_rows: int = 20) -> None:
    """Prints header, dtypes, and a few rows of a raw file so column order
    can be confirmed by eye before any parsing logic trusts it.
    """
    with open(path, "r") as f:
        head_lines = [next(f) for _ in range(min(n_rows, 5))]
    print("First lines (raw text):")
    for line in head_lines:
        print("  ", line.rstrip())

    try:
        df = pd.read_csv(path, nrows=n_rows)
        print("\nParsed as CSV with header row:")
        print(df.dtypes)
        print(df.head())
    except Exception as e:
        print(f"\n(Could not parse with header assumption: {e})")

    try:
        df2 = pd.read_csv(path, header=None, nrows=n_rows)
        print("\nParsed as CSV with NO header row:")
        print(df2.dtypes)
        print(df2.head())
    except Exception as e:
        print(f"\n(Could not parse header=None either: {e})")


# --------------------------------------------------------------------------
# Ground truth (shaker log) -- structure is documented, this part IS
# trustworthy without a real-file check, modulo the NaN-zero handling.
# --------------------------------------------------------------------------

def load_shaker_log(path: str) -> pd.DataFrame:
    """Loads shaker_log_cleaned.csv, treating documented zero-values as
    missing data per the dataset's own usage notes.

    Format confirmed against real uploaded bytes: NO header row, columns
    are (timestamp_us, axis1_value, axis2_value). Timestamps converted to
    seconds relative to the first row, matching our synthetic convention.
    """
    df = pd.read_csv(path, header=None, names=["t_us", "axis1", "axis2"])
    t0 = df["t_us"].iloc[0]
    df["t_s"] = (df["t_us"] - t0) / 1e6
    for col in ["axis1", "axis2"]:
        df[col] = df[col].replace(0, np.nan)
    return df


# --------------------------------------------------------------------------
# Raw event stream -- column order is the UNVERIFIED part, see docstring.
# --------------------------------------------------------------------------

def load_camera_events(path: str, max_rows: int = None) -> np.ndarray:
    """Loads a real e-STURT camera*.csv into the same (x, y, t, polarity)
    shape used by core.event_emulator.frames_to_events, so downstream
    detection code (Sections 4/5/6) doesn't need to know whether it's
    looking at synthetic or real data.

    Format confirmed against real uploaded bytes -- see module docstring.
    Timestamps are converted from absolute Unix microseconds to seconds
    relative to the first event in the file (matching our synthetic
    convention of starting at t=0).
    """
    df = pd.read_csv(path, header=None,
                      names=["x", "y", "p", "t_us", "relative_idx"],
                      nrows=max_rows)
    t0 = df["t_us"].iloc[0]
    t_seconds = (df["t_us"] - t0) / 1e6
    polarity = np.where(df["p"].to_numpy() == 1, 1.0, -1.0)

    events = np.stack([
        df["x"].to_numpy(dtype=np.float64),
        df["y"].to_numpy(dtype=np.float64),
        t_seconds.to_numpy(dtype=np.float64),
        polarity,
    ], axis=1)
    return events


if __name__ == "__main__":
    print(__doc__)
    print("\nThis module has NOT been run against real data yet.")
    print("Provide a real sample (see the handoff message) and run "
          "inspect_raw_csv() on it before trusting load_camera_events().")
