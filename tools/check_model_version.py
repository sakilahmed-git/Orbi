from __future__ import annotations
import joblib
import sklearn
import warnings
from sklearn.exceptions import InconsistentVersionWarning

# Treat a serialized-estimator version warning as a hard failure.  Checking the
# metadata only after a permissive load would allow an incompatible pickle to
# slip through CI.
warnings.simplefilter("error", InconsistentVersionWarning)
artifact = joblib.load("outputs/models/discriminator_gbc.joblib")
saved = artifact.get("sklearn_version")
if not saved:
    raise SystemExit("Model artifact does not declare sklearn_version; retrain with the pinned requirements.")
if saved != sklearn.__version__:
    raise SystemExit(f"Model sklearn version {saved!r} does not match runtime {sklearn.__version__!r}")
print(f"Model sklearn version verified: {saved}")
