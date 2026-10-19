import asyncio, json, logging, os, time
from datetime import datetime, timezone
from typing import Optional
import httpx
from fastapi import FastAPI
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
# Never let httpx log request URLs: Telegram bot URLs contain the secret token.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
log = logging.getLogger("pocket-ai")
app = FastAPI(title="Meu Pocket AI Trader", version="1.0.0")
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
OPENAI_KEY = os.getenv("OPENAI_API_KEY", "").strip()
MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
ASSETS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT"]
INTERVALS = {"1m":"1m", "3m":"3m", "5m":"5m", "15m":"15m"}
EXPIRIES = {"5s", "10s", "15s", "30s", "1m", "3m", "5m"}
state = {"offset":0, "chats":set(), "running":False, "interval":"1m", "amount":1.0, "expiry":"5m", "daily_limit":5.0, "ai":False, "last_scan":0}
history = []

@app.get("/")
async def root():
    return {"name":"Meu Pocket AI Trader","status":"online","runtime":"python","telegram_configured":bool(TOKEN),"ai_configured":bool(OPENAI_KEY),"mode":"demo_signals_only","order_execution":False}
@app.get("/health")
async def health():
    return await root()
@app.get("/api/status")
async def api_status():
    return {"status":"online","runtime":"python","telegram_configured":bool(TOKEN),"ai_configured":bool(OPENAI_KEY),"monitoring":state["running"],"settings":{"interval":state["interval"],"amount_usd":state["amount"],"expiry":state["expiry"],"daily_loss_limit_usd":state["daily_limit"],"assets":ASSETS},"order_execution":False,"history":history[-20:]}

async def send(chat, text):
    if not TOKEN: return
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r=await c.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage",json={"chat_id":chat,"text":text})
            if r.status_code >= 400: log.error("Telegram sendMessage HTTP %s: %s",r.status_code,r.text[:250])
    except Exception as e: log.exception("Telegram send failed: %s",e)

async def candles(symbol, interval):
    # Public Binance candles are for signal research only; not Pocket Option/OTC prices.
    async with httpx.AsyncClient(timeout=12) as c:
        r=await c.get("https://api.binance.com/api/v3/klines",params={"symbol":symbol,"interval":INTERVALS[interval],"limit":100})
        r.raise_for_status()
        rows=r.json()
    now=int(time.time()*1000)
    return [{"o":float(x[1]),"h":float(x[2]),"l":float(x[3]),"c":float(x[4]),"t":int(x[0]),"closed":now>=int(x[6])} for x in rows if now>=int(x[6])]

def ema(values, period):
    k=2/(period+1); v=values[0]
    for x in values[1:]: v=x*k+v*(1-k)
    return v

async def analyze(symbol):
    try:
        cs=await candles(symbol,state["interval"])
        if len(cs)<25: raise ValueError("Dados insuficientes")
        close=[x["c"] for x in cs]
        e9,e21=ema(close,9),ema(close,21)
        delta=[close[i]-close[i-1] for i in range(len(close)-14,len(close))]
        gains=sum(max(x,0) for x in delta)/14; losses=sum(max(-x,0) for x in delta)/14
        rsi=100 if losses==0 else 100-100/(1+gains/losses)
        mom=(close[-1]-close[-4])/close[-4]*100
        body=cs[-1]["c"]-cs[-1]["o"]
        signal="CALL" if e9>e21 and body>0 and mom>0 else "PUT" if e9<e21 and body<0 and mom<0 else "NO_TRADE"
        if (signal=="CALL" and rsi>=72) or (signal=="PUT" and rsi<=28): signal="NO_TRADE"
        approved=False; reason=("Filtro de IA desligado; sinal baseado apenas na análise técnica." if not state["ai"] else "Filtro de IA indisponível; entrada bloqueada.")
        if signal!="NO_TRADE" and state["ai"] and OPENAI_KEY:
            try:
                async with httpx.AsyncClient(timeout=18) as client:
                    res=await client.post("https://api.openai.com/v1/responses",headers={"Authorization":f"Bearer {OPENAI_KEY}"},json={"model":MODEL,"input":"Filtro conservador para sinal DEMO. Não prometa lucro. Aprove apenas se os dados sustentarem o sinal. Responda JSON com approved (boolean) e reason (string). Dados: "+json.dumps({"symbol":symbol,"signal":signal,"rsi":round(rsi,2),"momentum_pct":round(mom,4),"ema9":e9,"ema21":e21})})
                    res.raise_for_status(); data=res.json()
                txt=data.get("output_text","")
                if not txt:
                    txt="".join(p.get("text","") for item in data.get("output",[]) for p in item.get("content",[]) if p.get("type")=="output_text")
                d=json.loads(txt); approved=d.get("approved") is True; reason=str(d.get("reason","Filtro IA"))[:200]
            except Exception as e: reason="Falha no filtro de IA; sinal bloqueado."
        final=signal if (signal!="NO_TRADE" and (approved if state["ai"] else True)) else "NO_TRADE"
        result={"asset":symbol,"interval":state["interval"],"technical_signal":signal,"signal":final,"rsi":round(rsi,2),"momentum_pct":round(mom,4),"ai_approved":approved,"reason":reason,"time":datetime.now(timezone.utc).isoformat(),"source":"Binance Spot","order_execution":False}
        history.append(result); del history[:-100]
        return result
    except Exception as e:
        log.warning("Analysis %s failed: %s",symbol,e)
        return {"asset":symbol,"signal":"ERROR","reason":"Não foi possível obter/analisar candles agora.","order_execution":False}

async def scan(chat):
    results=await asyncio.gather(*(analyze(a) for a in ASSETS))
    lines=["🤖 MEU POCKET AI TRADER — DEMO / SINAIS"]
    for x in results:
        lines.append(f'\n{x["asset"]}: {x["signal"]} (técnico: {x.get("technical_signal","—")})')
        if "rsi" in x: lines.append(f'RSI {x["rsi"]} | momentum {x["momentum_pct"]}%')
        lines.append(x.get("reason",""))
    lines += ["",f'Gráfico: {state["interval"]} | valor configurado: US$ {state["amount"]:.2f} | expiração desejada: {state["expiry"]}',"Fonte: Binance Spot; preços podem diferir da Pocket Option/OTC.","Modo sinais: nenhuma ordem foi enviada."]
    await send(chat,"\n".join(lines))

HELP="""🤖 MEU POCKET AI TRADER (PYTHON) — DEMO
/start — ligar monitoramento dos 6 ativos
/status — estado e configurações
/scan — analisar os 6 ativos agora
/parar — parar monitoramento
/periodo 1m — gráfico: 1m, 3m, 5m ou 15m
/valor 1 — valor configurado por entrada (US$)
/expiracao 5m — duração desejada: 5s, 10s, 15s, 30s, 1m, 3m ou 5m
/ia on ou /ia off — filtro de IA
/ajuda — comandos
Obs.: cotações são Binance Spot, não Pocket OTC. Execução de ordens ainda não conectada."""
async def handle(update):
    msg=update.get("message") or {}
    chat=(msg.get("chat") or {}).get("id"); text=(msg.get("text") or "").strip()
    if not chat or not text: return
    state["chats"].add(chat); parts=text.split(); cmd=parts[0].split("@")[0].lower()
    if cmd in ("/start",):
        state["running"]=True
        await send(chat,"Bot Python conectado. Monitoramento de sinais iniciado para os seis ativos. Filtro de IA desligado: sinais técnicos apenas; nenhuma ordem é enviada.\n\n"+HELP)
        await scan(chat); return
    if cmd in ("/ajuda","/help"): await send(chat,HELP); return
    if cmd=="/status":
        await send(chat,f'Online: sim\nRuntime: Python\nToken Telegram: {"configurado" if TOKEN else "AUSENTE"}\nIA: {"configurada" if OPENAI_KEY else "não configurada"}\nMonitoramento: {state["running"]}\nAtivos: {", ".join(ASSETS)}\nGráfico: {state["interval"]}\nValor: US$ {state["amount"]:.2f}\nExpiração desejada: {state["expiry"]}\nLimite diário configurado: US$ {state["daily_limit"]:.2f}\nExecução Pocket Option: não conectada.'); return
    if cmd=="/ativos": await send(chat,", ".join(ASSETS)); return
    if cmd=="/periodo":
        p=parts[1] if len(parts)>1 else ""
        if p not in INTERVALS: await send(chat,"Períodos suportados na fonte atual: 1m, 3m, 5m, 15m. Segundos não são oferecidos pela API de candles atual."); return
        state["interval"]=p; await send(chat,"Gráfico definido: "+p); return
    if cmd=="/valor":
        try: v=float(parts[1].replace(",","."))
        except Exception: v=0
        if not 0.01<=v<=1000: await send(chat,"Use /valor 1 (mínimo US$ 0,01; máximo US$ 1000)."); return
        state["amount"]=round(v,2); await send(chat,f'Valor configurado: US$ {state["amount"]:.2f}. Ainda não aplicado a ordens.'); return
    if cmd=="/expiracao":
        p=parts[1].lower() if len(parts)>1 else ""
        if p not in EXPIRIES: await send(chat,"Opções: "+", ".join(sorted(EXPIRIES))); return
        state["expiry"]=p; await send(chat,"Expiração desejada: "+p+". Ainda não aplicada a ordens."); return
    if cmd=="/ia":
        v=parts[1].lower() if len(parts)>1 else ""
        if v not in ("on","off"): await send(chat,"Use /ia on ou /ia off."); return
        state["ai"]=v=="on"; await send(chat,"Filtro IA "+("ligado" if state["ai"] else "desligado")+". "+("Os sinais podem ser bloqueados se a API falhar." if state["ai"] else "Os sinais passam a depender apenas dos critérios técnicos. Nenhuma ordem é enviada.")); return
    if cmd=="/scan": await scan(chat); return
    if cmd=="/parar": state["running"]=False; await send(chat,"Monitoramento parado."); return
    await send(chat,"Comando não reconhecido. Use /ajuda.")

async def poll():
    if not TOKEN:
        log.error("TELEGRAM_BOT_TOKEN ausente: bot não vai iniciar polling.")
        return
    log.info("Telegram polling started (token configured; request URLs are redacted).")
    async with httpx.AsyncClient(timeout=40) as client:
        while True:
            try:
                r=await client.get(f"https://api.telegram.org/bot{TOKEN}/getUpdates",params={"offset":state["offset"],"timeout":25},timeout=35)
                data=r.json()
                if r.status_code>=400 or not data.get("ok"):
                    log.error("Telegram getUpdates failed: HTTP %s; %s",r.status_code,str(data)[:200]); await asyncio.sleep(5); continue
                updates=data.get("result",[])
                if updates:
                    log.info("Telegram updates received: %s", len(updates))
                for upd in updates:
                    state["offset"]=upd["update_id"]+1
                    await handle(upd)
            except Exception as e:
                log.exception("Telegram polling exception: %s",e); await asyncio.sleep(5)

async def monitor():
    while True:
        await asyncio.sleep(60)
        if state["running"]:
            for chat in list(state["chats"]):
                try: await scan(chat)
                except Exception: log.exception("scan failed")
@app.on_event("startup")
async def startup():
    if TOKEN: asyncio.create_task(poll())
    asyncio.create_task(monitor())
    log.info("Python service started; telegram_token_configured=%s; order_execution=False",bool(TOKEN))
