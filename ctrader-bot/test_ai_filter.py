import json
import tempfile
import unittest
from pathlib import Path

from ai_filter import FEATURE_NAMES, evaluate_ml_gate, extract_features, load_model, predict_up_probability
from train_ai_filter import build_rows


class AIFilterTests(unittest.TestCase):
    def setUp(self):
        self.prices = [100.0 + i * 0.1 + ((i % 4) - 1.5) * 0.03 for i in range(40)]
        self.model = {"version": 1, "trained": True, "feature_names": FEATURE_NAMES,
                      "mean": [0.0] * 6, "scale": [1.0] * 6,
                      "weights": [0.0] * 6, "bias": 0.0}

    def test_requires_22_prices(self):
        with self.assertRaises(ValueError):
            extract_features([100.0] * 20)

    def test_features_are_finite(self):
        self.assertTrue(all(abs(x) < 10 for x in extract_features(self.prices)))

    def test_missing_model_blocks(self):
        allowed, probability, reason = evaluate_ml_gate(self.prices, "BUY", None)
        self.assertFalse(allowed)
        self.assertIsNone(probability)
        self.assertIn("bloqueada", reason)

    def test_prediction_probability_is_bounded(self):
        p = predict_up_probability(self.prices, self.model)
        self.assertGreaterEqual(p, 0.0)
        self.assertLessEqual(p, 1.0)

    def test_gate_rejects_ambiguous_probability(self):
        allowed, probability, _ = evaluate_ml_gate(self.prices, "BUY", self.model)
        self.assertFalse(allowed)
        self.assertEqual(probability, 0.5)

    def test_invalid_model_is_not_loaded(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "model.json"
            path.write_text(json.dumps({"version": 999}), encoding="utf-8")
            self.assertIsNone(load_model(path))

    def test_training_rows_are_chronological_and_horizon_aligned(self):
        closes = [100.0 + i for i in range(40)]
        rows, labels = build_rows(closes, horizon=2, cost_threshold=0.0)
        self.assertEqual(len(rows), len(closes) - 2 - 21)
        self.assertEqual(len(labels), len(rows))
        self.assertTrue(all(label == 1 for label in labels))

    def test_training_rejects_invalid_horizon(self):
        with self.assertRaises(ValueError):
            build_rows(self.prices, horizon=0, cost_threshold=0.0)


if __name__ == "__main__":
    unittest.main()
