"""Regression guard against copied Section 4 baseline results."""
from __future__ import annotations

import unittest

from ai.lockon import evaluate_classical_baseline


class Section4ReproducibilityTests(unittest.TestCase):
    def test_different_seeds_change_classical_baseline_errors(self) -> None:
        """The scenario seed must affect both generated inputs and results."""
        seed_42 = evaluate_classical_baseline(seed=42, persist=False)
        seed_7 = evaluate_classical_baseline(seed=7, persist=False)

        for condition in ("clean", "noisy"):
            self.assertNotEqual(
                seed_42[condition]["mean_position_error_px"],
                seed_7[condition]["mean_position_error_px"],
                f"{condition} baseline result ignored the scenario seed",
            )


if __name__ == "__main__":
    unittest.main()
