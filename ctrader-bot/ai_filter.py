"""Filtro ML experimental para sinais DEMO; requer modelo treinado offline."""
import json, math, os
from pathlib import Path

FEATURE_NAMES = ["return_3", "return_8", "return_14", "volatility_14", "ema_gap_9_21", "directional_efficiency_14"]

def _ema(values, period):
    alpha = 2.0 / (period + 1.0)
    result = float(values[0])
    for value in values[1:]:
        result = alpha * float(value) + (1.0-alpha) * result
    return result

def extract_features(prices):
    values=[float(x) for x in prices]
    if len(values)<22 or any(not math.isfinite(x) or x<=0 for x in values):
        raise ValueError("A IA precisa de pelo menos 22 preços positivos e válidos")
    last=values[-1]
    returns=[values[i]/values[i-1]-1.0 for i in range(1,len(values))]
    recent=returns[-14:]
    mean=sum(recent)/len(recent)
    volatility=math.sqrt(sum((x-mean)**2 for x in recent)/len(recent))
    movement=sum(abs(x) for x in recent)
    efficiency=sum(recent)/movement if movement else 0.0
    return [last/values[-4]-1.0,last/values[-9]-1.0,last/values[-15]-1.0,volatility,
            (_ema(values[-21:],9)-_ema(values[-21:],21))/last,efficiency]

def load_model(path=None):
    p=Path(path or os.getenv("AI_MODEL_PATH","ctrader-bot/ai_model.json"))
    try:
        m=json.loads(p.read_text(encoding="utf-8"))
        if m.get("version")!=1 or m.get("feature_names")!=FEATURE_NAMES or not m.get("trained"): return None
        if any(len(m.get(k,[]))!=len(FEATURE_NAMES) for k in ("weights","mean","scale")): return None
        if any(not math.isfinite(float(v)) for k in ("weights","mean","scale") for v in m[k]): return None
        if any(float(v)<=0 for v in m["scale"]): return None
        if not math.isfinite(float(m["bias"])): return None
        return m
    except (OSError,ValueError,TypeError,KeyError): return None

def predict_up_probability(prices, model):
    f=extract_features(prices)
    z=float(model["bias"])+sum(float(w)*((x-float(mu))/float(scale)) for x,w,mu,scale in zip(f,model["weights"],model["mean"],model["scale"]))
    if z>=0: return 1.0/(1.0+math.exp(-min(z,700.0)))
    ez=math.exp(max(z,-700.0)); return ez/(1.0+ez)

def evaluate_ml_gate(prices, side, model, buy_threshold=0.60, sell_threshold=0.40):
    if model is None: return False,None,"IA ativada sem modelo treinado; entrada bloqueada por segurança"
    p=predict_up_probability(prices,model)
    if side.upper()=="BUY" and p>=buy_threshold: return True,p,"IA confirmou sinal de compra"
    if side.upper()=="SELL" and p<=sell_threshold: return True,p,"IA confirmou sinal de venda"
    return False,p,"IA não confirmou o sinal técnico"
