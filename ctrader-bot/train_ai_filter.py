"""Train an experimental logistic-regression gate from a CSV of historical close prices.

CSV must have a column named 'close' in chronological order. This script is for
offline research only. It writes a model only when the chronological holdout is
large enough and contains both classes. It does not connect to a broker.
"""
import argparse
import csv
import json
import math
from pathlib import Path

from ai_filter import FEATURE_NAMES, extract_features


def sigmoid(z):
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-min(z, 700.0)))
    ez = math.exp(max(z, -700.0))
    return ez / (1.0 + ez)


def read_closes(path):
    with open(path, newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or "close" not in reader.fieldnames:
            raise ValueError("O CSV precisa ter uma coluna chamada close")
        closes = [float(row["close"]) for row in reader if row.get("close")]
    if len(closes) < 300 or any(not math.isfinite(x) or x <= 0 for x in closes):
        raise ValueError("Use pelo menos 300 fechamentos positivos e válidos")
    return closes


def build_rows(closes, horizon, cost_threshold):
    rows, labels = [], []
    for end in range(22, len(closes) - horizon):
        history = closes[:end]
        future_return = closes[end + horizon - 1] / closes[end - 1] - 1.0
        rows.append(extract_features(history))
        labels.append(1 if future_return > cost_threshold else 0)
    return rows, labels


def train(input_csv, output_json, horizon=5, cost_threshold=0.0002, epochs=1600, learning_rate=0.03):
    closes = read_closes(input_csv)
    rows, labels = build_rows(closes, horizon, cost_threshold)
    split = int(len(rows) * 0.75)
    x_train, y_train = rows[:split], labels[:split]
    x_test, y_test = rows[split:], labels[split:]
    if len(x_test) < 30 or len(set(y_train)) < 2 or len(set(y_test)) < 2:
        raise ValueError("Dados insuficientes ou holdout cronológico sem as duas classes; não foi salvo modelo")
    means = [sum(row[j] for row in x_train) / len(x_train) for j in range(len(FEATURE_NAMES))]
    scales = []
    for j, mean in enumerate(means):
        variance = sum((row[j] - mean) ** 2 for row in x_train) / len(x_train)
        scales.append(max(math.sqrt(variance), 1e-9))
    normalized = [[(row[j] - means[j]) / scales[j] for j in range(len(FEATURE_NAMES))] for row in x_train]
    weights = [0.0] * len(FEATURE_NAMES)
    bias = 0.0
    for epoch in range(epochs):
        grad_w = [0.0] * len(weights)
        grad_b = 0.0
        for row, label in zip(normalized, y_train):
            error = sigmoid(bias + sum(w * x for w, x in zip(weights, row))) - label
            for j, value in enumerate(row):
                grad_w[j] += error * value
            grad_b += error
        rate = learning_rate / math.sqrt(1.0 + epoch / 100.0)
        count = len(normalized)
        weights = [w - rate * (g / count + 0.001 * w) for w, g in zip(weights, grad_w)]
        bias -= rate * grad_b / count
    model = {"version": 1, "trained": True, "feature_names": FEATURE_NAMES, "mean": means,
             "scale": scales, "weights": weights, "bias": bias,
             "training": {"rows": len(rows), "train_rows": len(x_train), "holdout_rows": len(x_test),
                          "horizon": horizon, "cost_threshold": cost_threshold}}
    predictions = [sigmoid(bias + sum(w * ((row[j] - means[j]) / scales[j]) for j, w in enumerate(weights))) for row in x_test]
    accuracy = sum((p >= 0.5) == bool(y) for p, y in zip(predictions, y_test)) / len(y_test)
    model["training"]["holdout_accuracy"] = round(accuracy, 4)
    model["training"]["holdout_positive_rate"] = round(sum(y_test) / len(y_test), 4)
    # Deliberately do not claim profitability: this is only classification accuracy.
    Path(output_json).write_text(json.dumps(model, indent=2), encoding="utf-8")
    return model


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", help="CSV histórico com coluna close")
    parser.add_argument("--output", default="ctrader-bot/ai_model.json")
    parser.add_argument("--horizon", type=int, default=5)
    parser.add_argument("--cost-threshold", type=float, default=0.0002, help="Retorno mínimo futuro, por exemplo 0.0002 = 0,02%%")
    args = parser.parse_args()
    result = train(args.csv, args.output, args.horizon, args.cost_threshold)
    print(json.dumps(result["training"], indent=2))
