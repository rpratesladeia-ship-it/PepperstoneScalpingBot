"""Local, explainable strategy telemetry and downloadable backup (DEMO only)."""
import json
import os
import threading
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

_LOCK = threading.RLock()
_DATA_DIR = Path(os.getenv("TRADER_DATA_DIR", "/tmp/trader-data"))
_EVENTS = _DATA_DIR / "strategy_events.jsonl"

def record_event(event_type, **fields):
    event = {"timestamp": datetime.now(timezone.utc).isoformat(), "type": str(event_type), **fields}
    try:
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        with _LOCK:
            with _EVENTS.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
    except OSError:
        return False
    return True

def read_events(limit=5000):
    try:
        with _LOCK:
            if not _EVENTS.exists():
                return []
            lines = _EVENTS.read_text(encoding="utf-8").splitlines()[-limit:]
        result = []
        for line in lines:
            try:
                result.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return result
    except OSError:
        return []

def analysis_report():
    events = read_events()
    counts = Counter(e.get("type", "unknown") for e in events)
    signals = [e for e in events if e.get("type") == "signal"]
    reasons = Counter(e.get("decision", "sem decisão") for e in signals)
    symbols = Counter(e.get("symbol", "?") for e in signals)
    sides = Counter(e.get("side", "?") for e in signals)
    orders = [e for e in events if e.get("type") in ("order_queued", "order_response")]
    pnl = [e for e in events if e.get("type") == "position_pnl"]
    return {
        "mode": "análise explicável baseada em regras; não é previsão nem modelo treinado",
        "events_total": len(events), "event_counts": dict(counts),
        "signals_logged": len(signals), "signal_decisions": dict(reasons),
        "signals_by_symbol": dict(symbols.most_common(20)), "signals_by_side": dict(sides),
        "order_events": len(orders), "pnl_samples": len(pnl), "latest_events": events[-12:],
        "note": "Dados disponíveis apenas desde a instrumentação; reinícios da hospedagem podem apagar este arquivo. Baixe backups periodicamente."
    }

def export_backup():
    return {"backup_created_at": datetime.now(timezone.utc).isoformat(),
            "app": "Meu Trader Multimercado", "mode": "DEMO",
            "analysis": analysis_report(), "events": read_events(limit=20000)}
