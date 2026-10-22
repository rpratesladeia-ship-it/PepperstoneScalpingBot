"""Treina o classificador direcional do robô com CSV histórico de fechamento.

Uso: python ctrader-bot/train_ai_model.py caminho/ohlc.csv --close Close --horizon 3
O CSV deve conter preços históricos ordenados do mais antigo para o mais recente.
Não use dados futuros ou misture ativos diferentes no mesmo arquivo.
"""
import argparse
import csv
import json
import math
from pathlib import Path

from ai_filter import FEATURE_NAMES, extract_features


def sigmoid(z):
    if z >= 0:
        e = math.exp(-min(z, 700))
        return 1.0 / (1.0 + e)
    e = math.exp(max(z, -700))
    return e / (1.0 + e)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path")
    parser.add_argument("--close", default="Close")
    parser.add_argument("--horizon", type=int, default=3, help="quantidade de candles à frente para o rótulo")
    parser.add_argument("--output", default="ctrader-bot/ai_model.json")
    parser.add_argument("--epochs", type=int, default=1200)
    parser.add_argument("--learning-rate", type=float, default=0.03)
    args = parser.parse_args()
    if args.horizon < 1 or args.epochs < 1 or args.learning_rate <= 0:
        raise SystemExit("horizon/epochs devem ser positivos e learning-rate maior que zero")

    with open(args.csv_path, newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or args.close not in reader.fieldnames:
            raise SystemExit("Coluna de fechamento não encontrada. Colunas: " + str(reader.fieldnames))
        prices = [float(row[args.close]) for row in reader if row.get(args.close)]
    if len(prices) < 600:
        raise SystemExit("Use pelo menos 600 candles históricos; com menos dados o treino não será salvo.")
    if any(not math.isfinite(p) or p <= 0 for p in prices):
        raise SystemExit("CSV contém preço inválido.")

    samples = []
    # Features use only data available at index i; label uses a future close.
    for i in range(22, len(prices) - args.horizon):
        window = prices[:i + 1]
        try:
            features = extract_features(window)
        except ValueError:
            continue
        label = 1.0 if prices[i + args.horizon] > prices[i] else 0.0
        samples.append((features, label))
    split = int(len(samples) * 0.8)
    train, test = samples[:split], samples[split:]
    if len(train) < 400 or len(test) < 80:
        raise SystemExit("Dados insuficientes após preparar amostras.")

    n = len(FEATURE_NAMES)
    mean = [sum(row[0][j] for row in train) / len(train) for j in range(n)]
    scale = []
    for j in range(n):
        variance = sum((row[0][j] - mean[j]) ** 2 for row in train) / len(train)
        scale.append(max(math.sqrt(variance), 1e-9))
    x_train = [[(f[j] - mean[j]) / scale[j] for j in range(n)] for f, _ in train]
    y_train = [y for _, y in train]
    weights, bias = [0.0] * n, 0.0
    lr = args.learning_rate
    for epoch in range(args.epochs):
        grad_w, grad_b = [0.0] * n, 0.0
        for x, y in zip(x_train, y_train):
            error = sigmoid(bias + sum(w * v for w, v in zip(weights, x))) - y
            grad_b += error
            for j in range(n):
                grad_w[j] += error * x[j]
        factor = 1.0 / len(x_train)
        bias -= lr * grad_b * factor
        for j in range(n):
            weights[j] -= lr * (grad_w[j] * factor + 0.001 * weights[j])

    predictions = []
    for features, label in test:
        x = [(features[j] - mean[j]) / scale[j] for j in range(n)]
        p = sigmoid(bias + sum(w * v for w, v in zip(weights, x)))
        predictions.append((p, label))
    accuracy = sum((p >= 0.5) == bool(y) for p, y in predictions) / len(predictions)
    baseline = max(sum(y for _, y in test), len(test) - sum(y for _, y in test)) / len(test)
    model = {
        "version": 1, "trained": True, "feature_names": FEATURE_NAMES,
        "weights": weights, "mean": mean, "scale": scale, "bias": bias,
        "training_info": {"samples": len(samples), "train_samples": len(train),
                          "test_samples": len(test), "horizon_candles": args.horizon,
                          "test_accuracy": round(accuracy, 4),
                          "majority_baseline_accuracy": round(baseline, 4),
                          "note": "Acurácia histórica não garante resultado futuro; validar por ativo e custos."}
    }
    if accuracy <= baseline:
        raise SystemExit(
            f"Treino não superou a referência simples: teste={accuracy:.3f}, baseline={baseline:.3f}. "
            "Modelo não salvo para evitar ativar um classificador sem vantagem observada."
        )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(model, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(model["training_info"], ensure_ascii=False, indent=2))
    print("Modelo salvo em:", output)


if __name__ == "__main__":
    main()
