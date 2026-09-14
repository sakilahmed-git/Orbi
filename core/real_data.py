"""
Section 3 -- Real-data ingestion: e-STURT dataset.

Verified against the actual Zenodo record (10.5281/zenodo.14031911) on
2026-09-14 -- this is not written against the paper's abstract alone.

CONFIRMED REAL STRUCTURE (from the Zenodo record page itself):
  <episode_folder>/
    no_jitter/
      camera<ID>_<YYMMDD>_<HHMMSS>.bias
      camera<ID>_<YYMMDD>_<HHMMSS>.csv
    pos0.1_vel1_6_sst0.05_MOVMAC1S/      # 0-30 Hz, axis 1 only
      camera<ID>_<YYMMDD>_<HHMMSS>.bias
      camera<ID>_<YYMMDD>_<HHMMSS>.csv
      out_<timestamp>_..._shaker_log_cleaned.csv
    ... (9 vibration subfolders total: 3 freq bands x 3 axis configs)

  Freq band naming: pos0.1_vel1_6   -> 0-30 Hz
                     pos0.1_vel6_20  -> 30-100 Hz
                     pos0.1_vel20_40 -> 100-200 Hz
  Axis naming:       MOVMAC1S -> axis 1 only, MOVMAC2S -> axis 2 only,
                      MOVMACS  -> both axes

  IMPORTANT (stated explicitly on the dataset page): zeros in
  shaker_log_cleaned.csv mean MISSING DATA, not "zero motion" -- must be
  treated as NaN, not a real ground-truth value.

NOT YET VERIFIED (flagging honestly rather than guessing silently):
  The exact column order/header of the raw camera*.csv event files. The
  paper's algorithm section describes events as (x, y, t, polarity), and
  Prophesee's standard CSV export is typically ordered close to that, but
  I have not seen an actual row of this specific file, so the column
  mapping below is a best-guess default with autodetection fallback --
  DO NOT trust results from this loader until it's been run against a
  real downloaded sample and the column mapping has been confirmed or
  corrected. See `inspect_raw_csv()` below -- run that FIRST on any new
  real file, before trusting `load_camera_events()`.
"""

from __future__ import annotations

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

    Returns a DataFrame; exact column names are inferred from the file's
    own header (should be present, unlike the camera csv) -- printed so
    you can see them on first real use.
    """
    df = pd.read_csv(path)
    print("shaker_log_cleaned.csv columns found:", list(df.columns))
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    for col in numeric_cols:
        df[col] = df[col].replace(0, np.nan)
    return df


# --------------------------------------------------------------------------
# Raw event stream -- column order is the UNVERIFIED part, see docstring.
# --------------------------------------------------------------------------

def load_camera_events(path: str,
                        assumed_columns: tuple = ("t", "x", "y", "p"),
                        max_rows: int = None) -> np.ndarray:
    """Loads camera*.csv into the same (x, y, t, polarity) shape used by
    core.event_emulator.frames_to_events, so downstream detection code
    (Sections 4/5/6) doesn't need to know whether it's looking at synthetic
    or real e-STURT data.

    `assumed_columns` is a best guess (see module docstring) -- ALWAYS
    call inspect_raw_csv() on a new file first and pass the corrected
    order in here once confirmed.
    """
    df = pd.read_csv(path, header=None, nrows=max_rows,
                      names=list(assumed_columns))
    events = np.stack([
        df["x"].to_numpy(dtype=np.float64),
        df["y"].to_numpy(dtype=np.float64),
        df["t"].to_numpy(dtype=np.float64),
        df["p"].to_numpy(dtype=np.float64),
    ], axis=1)
    return events


if __name__ == "__main__":
    print(__doc__)
    print("\nThis module has NOT been run against real data yet.")
    print("Provide a real sample (see the handoff message) and run "
          "inspect_raw_csv() on it before trusting load_camera_events().")
