"""Optional, offline-trained ML gate for demo trading.

This module deliberately does not invent a model. The filter is unavailable until a
model has been trained on historical data and its JSON artifact is supplied.
"""
import json
import math
import os
from pathlib import Path

FEATURE_NAMES = ["return_3", "return_8", "return_14", "volatility_14", "ema_gap_9_21", "directional_efficiency_14"]


def _ema(values, period):
    alpha = 2.0 / (period + 1.0)
    result = float(values[0])
    for value in values[1:]:
        result = alpha * float(value) + (1.0 - alpha) * result
    return result


def extract_features(prices):
    values = [float(x) for x in prices]
    if len(values) < 22 or any(not math.isfinite(x) or x <= 0 for x in values):
        raise ValueError("São necessários pelo menos 22 preços positivos e válidos")
    last = values[-1]
    returns = [(values[i] / values[i - 1]) - 1.0 for i in range(1, len(values))]
    recent = returns[-14:]
    mean = sum(recent) / len(recent)
    volatility = math.sqrt(sum((x - mean) ** 2 for x in recent) / len(recent))
    movement = sum(abs(x) for x in recent)
    efficiency = sum(recent) / movement if movement else 0.0
    return [
        last / values[-4] - 1.0,
        last / values[-9] - 1.0,
        last / values[-15] - 1.0,
        volatility,
        (_ema(values[-21:], 9) - _ema(values[-21:], 21)) / last,
        efficiency,
    ]


def load_model(path=None):
    model_path = Path(path or os.getenv("AI_MODEL_PATH", "ctrader-bot/ai_model.json"))
    if not model_path.is_file():
        return None
    try:
        model = json.loads(model_path.read_text(encoding="utf-8"))
        if model.get("version") != 1 or model.get("feature_names") != FEATURE_NAMES:
            return None
        if not model.get("trained") or len(model.get("weights", [])) != len(FEATURE_NAMES):
            return None
        if any(len(model.get(k, [])) != len(FEATURE_NAMES) for k in ("mean", "scale")):
            return None
        if any(float(x) <= 0 for x in model["scale"]):
            return None
        return model
    except (OSError, ValueError, TypeError, KeyError):
        return None


def predict_up_probability(prices, model):
    features = extract_features(prices)
    normalized = [(x - float(mu)) / float(scale) for x, mu, scale in zip(features, model["mean"], model["scale"])]
    z = float(model["bias"]) + sum(float(w) * x for w, x in zip(model["weights"], normalized))
    # Numerically stable logistic function.
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-min(z, 700.0)))
    ez = math.exp(max(z, -700.0))
    return ez / (1.0 + ez)


def evaluate_ml_gate(prices, side, model=None, buy_threshold=0.60, sell_threshold=0.40):
    """Return (allowed, probability, reason); missing model always blocks when enabled."""
    if model is None:
        return False, None, "Filtro IA ativado, mas modelo treinado não encontrado; entrada bloqueada"
    probability = predict_up_probability(prices, model)
    side = side.upper()
    if side == "BUY" and probability >= buy_threshold:
        return True, probability, "Modelo favorece alta acima do limiar configurado"
    if side == "SELL" and probability <= sell_threshold:
        return True, probability, "Modelo não favorece alta; limiar de venda atendido"
    return False, probability, "Probabilidade do modelo não confirmou o sinal técnico"
