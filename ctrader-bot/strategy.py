"""Educational signal engine for cTrader demo integration.
No broker connection and no order execution are implemented in this module.
"""
from dataclasses import dataclass
from typing import Sequence


@dataclass
class Signal:
    symbol: str
    direction: str
    confidence: str
    reason: str
    last_close: float


def _ema(values: Sequence[float], period: int) -> float:
    if len(values) < period:
        raise ValueError(f"At least {period} candles are required")
    alpha = 2.0 / (period + 1)
    value = float(values[0])
    for item in values[1:]:
        value = alpha * float(item) + (1.0 - alpha) * value
    return value


def _rsi(values: Sequence[float], period: int = 14) -> float:
    if len(values) < period + 1:
        raise ValueError(f"At least {period + 1} closes are required")
    diffs = [float(values[i]) - float(values[i - 1]) for i in range(len(values)-period, len(values))]
    gains = sum(max(x, 0.0) for x in diffs) / period
    losses = sum(max(-x, 0.0) for x in diffs) / period
    if losses == 0:
        return 100.0 if gains else 50.0
    return 100.0 - (100.0 / (1.0 + gains / losses))


def analyze_closes(symbol: str, closes: Sequence[float]) -> Signal:
    """Analyze completed candle closes only; returns CALL, PUT, or NO_TRADE."""
    if len(closes) < 26:
        raise ValueError("Need at least 26 completed candles")
    close = [float(x) for x in closes]
    if any(x <= 0 for x in close):
        raise ValueError("Prices must be positive")
    fast, slow = _ema(close, 9), _ema(close, 21)
    momentum = (close[-1] / close[-4] - 1.0) * 100.0
    rsi = _rsi(close, 14)
    if fast > slow and momentum > 0 and 50 <= rsi < 72:
        direction, reason = "CALL", "EMA 9 acima da EMA 21, momentum positivo e RSI sem sobrecompra extrema"
    elif fast < slow and momentum < 0 and 28 < rsi <= 50:
        direction, reason = "PUT", "EMA 9 abaixo da EMA 21, momentum negativo e RSI sem sobrevenda extrema"
    else:
        direction, reason = "NO_TRADE", "Critérios de tendência, momentum e RSI não estão alinhados"
    return Signal(symbol, direction, "technical_only", reason, close[-1])


def risk_allows_trade(*, demo_mode: bool, daily_loss: float, max_daily_loss: float,
                      open_positions: int, max_open_positions: int) -> tuple[bool, str]:
    """Fail closed: demo mode required and hard limits are enforced."""
    if not demo_mode:
        return False, "Bloqueado: somente conta DEMO está autorizada nesta versão"
    if daily_loss >= max_daily_loss:
        return False, "Bloqueado: limite de perda diária atingido"
    if open_positions >= max_open_positions:
        return False, "Bloqueado: limite de posições abertas atingido"
    return True, "Dentro dos limites configurados; isso não garante lucro"
