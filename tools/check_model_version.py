from __future__ import annotations
import joblib
import sklearn

artifact = joblib.load("outputs/models/discriminator_gbc.joblib")
saved = artifact.get("sklearn_version")
if saved != sklearn.__version__:
    raise SystemExit(f"Model sklearn version {saved!r} does not match runtime {sklearn.__version__!r}")
print(f"Model sklearn version verified: {saved}")
