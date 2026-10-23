import os, secrets, logging, socket, time
from urllib.parse import urlencode
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from pydantic import BaseModel
from ctrader_engine import CTraderDemoBridge

logging.basicConfig(level=logging.INFO)
# Never allow HTTP client debug logs to print OAuth URLs, authorization codes, or secrets.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
log = logging.getLogger("trader-ctrader")
APP_NAME = "Meu Trader Multimercado"
CLIENT_ID = (os.getenv("CTRADER_CLIENT_ID") or os.getenv("CLIENT_ID") or "").strip()
CLIENT_SECRET = (os.getenv("CTRADER_CLIENT_SECRET") or os.getenv("CLIENT_SECRET") or "").strip()
REDIRECT_URI = (os.getenv("CTRADER_REDIRECT_URI") or os.getenv("REDIRECT_URI") or "").strip()
SESSION_SECRET = os.getenv("SESSION_SECRET", "").strip()
# Prototype: tokens remain in memory only and are cleared when the service restarts.
TOKENS = {}
BRIDGES = {}
app = FastAPI(title=APP_NAME, version="0.1.0")
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET or secrets.token_urlsafe(32), https_only=True, same_site="lax")

PAGE = """<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Meu Trader Multimercado</title><style>
:root{color-scheme:dark}*{box-sizing:border-box}body{margin:0;background:#10151f;color:#eef2f8;font:16px system-ui,sans-serif}
main{max-width:720px;margin:28px auto;padding:18px}.card{background:#1a2332;border:1px solid #2e3a4d;border-radius:18px;padding:22px;margin:14px 0}
h1{font-size:1.6rem;margin:.2rem 0}.muted{color:#b6c1d1;line-height:1.55}.status{display:inline-block;background:#344054;padding:6px 10px;border-radius:999px;font-size:.85rem}
a.btn{display:block;text-align:center;background:#75e0b0;color:#102018;padding:14px;border-radius:12px;text-decoration:none;font-weight:750;margin-top:18px}
small{color:#a9b6c8}.grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}.tile{padding:12px;background:#111925;border-radius:12px}
@media(max-width:520px){.grid{grid-template-columns:1fr}main{padding:12px}}</style></head><body><main>
<div class="card"><span class="status">DEMO / SIMULAÇÃO</span><h1>Meu Trader Multimercado</h1>
<p class="muted">Painel inicial para conectar uma conta cTrader por autorização oficial. O acesso é concedido no próprio cTrader; este painel nunca pede sua senha da corretora.</p>
<div class="grid"><div class="tile"><small>Mercados encontrados na conta</small><br><b id="symbols">Aguardando conexão</b></div><div class="tile"><small>Execução</small><br><b id="execution">BLOQUEADA ATÉ VALIDAR DEMO</b></div></div>
<button class="btn" id="connectBtn" style="width:100%;border:0;cursor:pointer;font-size:1rem">INICIAR ROBÔ DEMO</button>
<p class="muted"><small>Um único botão conecta, confirma a conta DEMO selecionada e inicia o robô. A autorização oficial do cTrader pode exigir confirmação na página segura da corretora.</small></p>
<p class="muted"><small>* Os ativos dependem da corretora e da conta conectada. Cripto pode não estar disponível em todos os brokers cTrader.</small></p></div>
<div class="card"><h2>Estado da conexão</h2><p class="muted" id="status">__STATUS__</p><p class="muted" id="accountInfo">Consultando a API cTrader…</p><div id="accountWrap" style="display:none"><label for="account">Conta DEMO selecionada</label><select id="account" style="width:100%;padding:12px;margin:8px 0;background:#111925;color:#fff;border-radius:10px"></select><button id="selectAccount" style="padding:12px;width:100%;border:0;border-radius:10px;font-weight:700">Validar conta DEMO selecionada</button></div><h3>Cotações recebidas</h3><div id="quotes" class="muted">Aguardando cotações…</div><h3>Robô automático (somente DEMO)</h3><p id="autoStatus" class="muted">Automação desligada</p><p id="aiStatus" class="muted">Filtro IA: consultando estado…</p><h3>IA de mercado — análise experimental</h3><p class="muted">Estimativas técnicas de curto prazo baseadas em ticks reais recebidos. Não é modelo ML treinado nem garantia de resultado.</p><div id="marketAi" class="muted">Aguardando histórico de cotações…</div><label for="runMinutes">Tempo de funcionamento (minutos)</label><input id="runMinutes" type="number" min="1" max="10080" step="1" value="10080" style="width:100%;padding:12px;margin:8px 0;background:#111925;color:#fff;border-radius:10px"><p id="autoTimer" class="muted">Temporizador parado</p><div class="tile" style="margin:8px 0"><b>Registro de horários (Brasília)</b><p class="muted" id="autoTimes">Início automático: —<br>Parada automática: —</p><p class="muted" id="manualTimes">Última ordem manual: —</p></div><button id="autoToggle" style="display:none">INICIAR ROBÔ DEMO</button><p class="muted"><small>Estratégia inicial: cruzamento de médias rápidas/lentas nos ticks. Volume mínimo de 1 unidade, intervalo de segurança de 5 minutos por ativo. Faça testes em DEMO; isso não garante lucro e não substitui stop-loss.</small></p><h3>Teste manual (somente DEMO)</h3><label>Ativo</label><select id="symbol" style="width:100%;padding:12px;margin:8px 0;background:#111925;color:#fff;border-radius:10px"><option>XAUUSD</option><option>EURUSD</option><option>GBPUSD</option><option>USDJPY</option><option>BTCUSD</option><option>US30</option></select><label>Volume em unidades</label><input id="volume" type="number" min="1" max="1000" value="1" style="width:100%;padding:12px;margin:8px 0;background:#111925;color:#fff;border-radius:10px;color:#fff"><div class="grid"><button class="trade" data-side="BUY" style="padding:14px;border:0;border-radius:10px;background:#75e0b0;font-weight:700">Comprar DEMO</button><button class="trade" data-side="SELL" style="padding:14px;border:0;border-radius:10px;background:#f5a3a3;font-weight:700">Vender DEMO</button></div><p id="result" class="muted"></p><p class="muted"><small>Uma ordem só será enviada após você tocar no botão e confirmar. Não é execução automática ainda.</small></p></div>
<div class="card"><h2>Política operacional da IA</h2><p id="policyStatus" class="muted">Verificando política salva no programa…</p><ul class="muted"><li>Conta DEMO; conta REAL bloqueada.</li><li>Uma posição aberta por ativo e cinco entradas bem-sucedidas em outros ativos antes de reutilizar o ativo.</li><li>Arbitragem estatística, PPO e NLP ficam desativados até validação fora da amostra.</li><li>Z-Score isolado não autoriza ordem; considerar custos, spread, slippage e qualidade dos dados.</li><li>Margem, SL/TP, estado da conexão e frescor das cotações devem ser verificados.</li></ul><p><a href="https://github.com/rpratesladeia-ship-it/PepperstoneScalpingBot/blob/ctrader-multimarket-demo/ctrader-bot/AI_TRADING_POLICY.md" target="_blank" rel="noopener">Abrir especificação completa da IA</a></p></div>
<div class="card"><h2>Calendário econômico e notícias oficiais</h2><p class="muted">Contexto para planejar as sessões; manchetes não são sinais de compra/venda. Horários oficiais devem ser conferidos na fonte.</p><p id="contextStatus" class="muted">Carregando fontes oficiais…</p><div id="contextNews" class="muted">Aguardando atualização…</div><p class="muted"><a href="https://www.federalreserve.gov/newsevents/calendar.htm" target="_blank" rel="noopener">Calendário do Federal Reserve (FOMC)</a><br><a href="https://www.bls.gov/schedule/2026/" target="_blank" rel="noopener">Calendário de indicadores dos EUA (BLS)</a><br><a href="https://www.bea.gov/news/schedule/" target="_blank" rel="noopener">Calendário econômico do BEA</a></p></div>
<div class="card"><h2>Segurança</h2><p class="muted">Não compartilhe senhas, códigos de autenticação, client secret ou tokens. As credenciais do aplicativo ficam somente nas variáveis secretas do servidor.</p></div>
</main><script>
const $=id=>document.getElementById(id);
async function refresh(){
 try{
  const r=await fetch('/api/status',{cache:'no-store'}); const d=await r.json(); const b=d.broker||{};
  $('status').textContent=!d.oauth_authorized?'Não conectado. Toque em Conectar conta cTrader.':!b.connected?'Autorização recebida; conectando à API cTrader…':!b.application_authorized?'Conectado; aguardando autorização do aplicativo…':!b.accounts?.length?'Aplicativo autorizado; aguardando lista de contas…':!b.account_authorized?'Contas carregadas. Selecione uma conta marcada DEMO e valide.': 'Conta DEMO autorizada. Verifique as cotações antes de testar.';
  $('accountInfo').textContent='Conexão: '+(b.connected?'online':'aguardando')+' | App autorizado: '+(b.application_authorized?'sim':'não')+' | Conta autorizada: '+(b.account_authorized?'sim':'não')+(b.last_error?' | Aviso: '+b.last_error:'');
  $('symbols').textContent=(b.symbols||[]).join(', ')||'Nenhum ativo ainda';
  $('execution').textContent=b.auto_trading?(b.auto_observe_only?'MONITORAMENTO DEMO ATIVO — SEM ORDENS':(b.ai_filter?.enabled&&!b.ai_filter?.model_loaded?'AUTOMÁTICA DEMO EXPERIMENTAL ATIVA':'AUTOMÁTICA DEMO ATIVA')):(b.account_authorized?'TESTE MANUAL DEMO':'BLOQUEADA');
  $('autoStatus').textContent=b.auto_status|| (b.auto_trading?'Automação ativa':'Automação desligada');
  const ai=b.ai_filter||{};
  $('aiStatus').textContent='Filtro IA: '+(ai.enabled?(ai.model_loaded?'ATIVO — modelo ML treinado':'MODO EXPERIMENTAL DEMO — modelo ML treinado ausente; sinais técnicos podem ser testados, sem alegar IA treinada'):'desligado');
  const autoButton=$('autoToggle');
  const mainButton=$('connectBtn');
  const experimentalDemo=!!(ai.enabled && !ai.model_loaded);
  autoButton.disabled=false;
  autoButton.style.opacity='1';
  autoButton.style.cursor='pointer';
  autoButton.textContent=b.auto_trading?'PARAR ROBÔ DEMO':'INICIAR ROBÔ DEMO';
  if(mainButton && !mainButton.disabled){
    if(b.auto_trading){
      mainButton.textContent='PARAR ROBÔ DEMO';
      mainButton.onclick=stopDemoFromSingleButton;
    } else {
      mainButton.textContent='INICIAR ROBÔ DEMO';
      mainButton.onclick=startDemoFromSingleButton;
    }
  }
  if(experimentalDemo && !b.auto_trading) $('autoStatus').textContent='Modo experimental DEMO: modelo ML ausente; robô pode testar sinais técnicos após validar conta, cotação e margem disponível.';
  try{const mr=await fetch('/api/market-ai',{cache:'no-store'});const md=await mr.json();$('marketAi').innerHTML=(md.results||[]).map(x=>'<div class="tile" style="margin:8px 0"><b>'+x.symbol+'</b> — Alta <b>'+x.up_pct+'%</b> / Baixa <b>'+x.down_pct+'%</b><br>'+x.signal+' · '+x.reason+'</div>').join('')||md.message||'Aguardando histórico…';}catch(_){$('marketAi').textContent='Análise indisponível no momento.'}
  const clock=ts=>ts?new Date(ts*1000).toLocaleString('pt-BR',{timeZone:'America/Sao_Paulo',hour12:false,day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit',second:'2-digit'}):'—';
  if(b.auto_trading && b.auto_deadline){
    const left=Math.max(0,Math.ceil(b.auto_deadline-Date.now()/1000));
    const elapsed=Math.max(0,Math.floor(Date.now()/1000-(b.auto_started_at||Date.now()/1000)));
    const fmt=n=>String(Math.floor(n/3600)).padStart(2,'0')+':'+String(Math.floor((n%3600)/60)).padStart(2,'0')+':'+String(n%60).padStart(2,'0');
    $('autoTimer').textContent='Trabalhando há '+fmt(elapsed)+' | Desliga em '+fmt(left);
  }else{$('autoTimer').textContent='Temporizador parado';}
  $('autoTimes').innerHTML='Início da sessão atual/última: '+clock(b.last_auto_started_at||b.auto_started_at)+'<br>Parada: '+clock(b.last_auto_stopped_at)+'<br>Motivo: '+(b.last_auto_stop_reason||(b.auto_trading?'Robô automático em execução':'Aguardando início'));
  $('manualTimes').textContent='Última ordem solicitada (manual/automática): '+clock(b.last_manual_order_at);
  const sel=$('account');
  const accountList=(b.accounts||[]).map(a=>({id:String(a.account_id),live:!!a.is_live}));
  const signature=JSON.stringify(accountList);
  let savedAccount='';try{savedAccount=localStorage.getItem('meuTraderDemoAccountId')||''}catch(_){}
  if(sel.dataset.signature!==signature){
    const previous=sel.value;
    sel.replaceChildren();
    accountList.forEach(a=>{const o=document.createElement('option');o.value=a.id;o.textContent=a.id+' — '+(a.live?'REAL (bloqueada)':'DEMO');o.disabled=a.live;sel.appendChild(o)});
    sel.dataset.signature=signature;
    if(savedAccount && accountList.some(a=>a.id===savedAccount && !a.live)) sel.value=savedAccount;
    else if(previous && accountList.some(a=>a.id===previous && !a.live)) sel.value=previous;
    else if(accountList.some(a=>a.id==='10127372' && !a.live)) sel.value='10127372';
    else if(b.selected_account_id && accountList.some(a=>a.id===String(b.selected_account_id) && !a.live)) sel.value=String(b.selected_account_id);
    if(sel.value){try{localStorage.setItem('meuTraderDemoAccountId',sel.value)}catch(_){}}
  }
  if(savedAccount && accountList.some(a=>a.id===savedAccount && !a.live)) sel.value=savedAccount;
  const q=b.prices||{}; $('quotes').textContent=Object.keys(q).length?Object.entries(q).map(([n,p])=>n+': bid raw '+(p.bid_raw??'—')+' / ask raw '+(p.ask_raw??'—')).join(' | '):'Aguardando preços do servidor cTrader…';
  if(b.last_order)$('result').textContent='Última ordem: '+JSON.stringify(b.last_order);
 }catch(e){$('status').textContent='Não foi possível consultar o estado do servidor.'}
}
async function startDemoFromSingleButton(){
 const btn=$('connectBtn');
 const minutes=Math.floor(Number($('runMinutes').value)||10080);
 if(!Number.isFinite(minutes)||minutes<1||minutes>10080){$('result').textContent='Informe um tempo entre 1 e 10080 minutos.';return;}
 btn.disabled=true;btn.textContent='CONECTANDO / VALIDANDO DEMO…';
 try{
  const stateResp=await fetch('/api/status',{cache:'no-store'}); const state=await stateResp.json(); const b=state.broker||{};
  let accountId=$('account').value || localStorage.getItem('meuTraderDemoAccountId') || '10127372';
  if(!state.oauth_authorized || !b.connected || !b.application_authorized){
    localStorage.setItem('meuTraderAutoStart','1'); localStorage.setItem('meuTraderRunMinutes',String(minutes));
    window.location.href='/connect'; return;
  }
  if(!accountId){throw new Error('Nenhuma conta DEMO selecionada.');}
  localStorage.setItem('meuTraderDemoAccountId',accountId);
  const r=await fetch('/api/start-session',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({account_id:Number(accountId),duration_minutes:minutes})});
  const d=await r.json().catch(()=>({message:'Resposta inválida do servidor.'}));
  $('result').textContent=d.message||JSON.stringify(d);
  if(d.pending){btn.textContent='AGUARDANDO AUTORIZAÇÃO DEMO…';return;}
  if(!r.ok)throw new Error(d.message||'Falha ao iniciar');
  btn.textContent='PARAR ROBÔ DEMO'; btn.onclick=stopDemoFromSingleButton;
  refresh();
 }catch(e){$('result').textContent='Não iniciou: '+e.message;btn.textContent='INICIAR ROBÔ DEMO';}
 finally{btn.disabled=false;}
}
async function stopDemoFromSingleButton(){
 const btn=$('connectBtn');btn.disabled=true;
 try{const r=await fetch('/api/auto',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({enabled:false,duration_minutes:60})});$('result').textContent=await r.text();localStorage.removeItem('meuTraderAutoStart');btn.textContent='INICIAR ROBÔ DEMO';btn.onclick=startDemoFromSingleButton;refresh();}
 finally{btn.disabled=false;}
}
$('connectBtn').onclick=startDemoFromSingleButton;
const autoResume=localStorage.getItem('meuTraderAutoStart')==='1';
if(autoResume){
 const savedMinutes=localStorage.getItem('meuTraderRunMinutes')||'10080';$('runMinutes').value=savedMinutes;
 let resumeTries=0;
 const resumeTimer=setInterval(async()=>{
  resumeTries++;
  try{
   const sr=await fetch('/api/status',{cache:'no-store'});const st=await sr.json();const b=st.broker||{};
   if(st.oauth_authorized && b.connected && b.application_authorized){
    clearInterval(resumeTimer);localStorage.removeItem('meuTraderAutoStart');startDemoFromSingleButton();
   }else if(resumeTries>=20){
    clearInterval(resumeTimer);localStorage.removeItem('meuTraderAutoStart');
    $('result').textContent='Conexão/autorização ainda não confirmada. Toque em INICIAR ROBÔ DEMO para tentar novamente.';
   }
  }catch(_){if(resumeTries>=20){clearInterval(resumeTimer);localStorage.removeItem('meuTraderAutoStart');}}
 },1000);
}
$('autoToggle').onclick=async()=>{
 const active=($('autoToggle').textContent||'').startsWith('PARAR ROBÔ');
 if(active){const r=await fetch('/api/auto',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({enabled:false,duration_minutes:60})});$('result').textContent=await r.text();setTimeout(refresh,500);return;}
 const minutes=Math.floor(Number($('runMinutes').value)||10080);
 if(!Number.isFinite(minutes)||minutes<1||minutes>10080){$('result').textContent='Informe um tempo entre 1 e 10080 minutos (até 7 dias).';return;}
 if(!($('account').value)){ $('result').textContent='Aguardando a lista de contas DEMO. Atualize em alguns segundos.';return;}
 $('autoToggle').disabled=true;$('autoToggle').textContent='VALIDANDO CONTA DEMO…';
 try{
  const r=await fetch('/api/start-session',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({account_id:Number($('account').value),duration_minutes:minutes})});
  const d=await r.json().catch(async()=>({message:await r.text()}));
  $('result').textContent=d.message||JSON.stringify(d);
  if(d.connect_url){window.location.href=d.connect_url;return;}
  if(d.pending){$('autoToggle').textContent='AGUARDANDO AUTORIZAÇÃO DEMO…';let tries=0;const timer=setInterval(async()=>{tries++;try{const sr=await fetch('/api/status',{cache:'no-store'});const st=await sr.json();if(st.broker?.account_authorized){clearInterval(timer);const ar=await fetch('/api/auto',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({enabled:true,duration_minutes:minutes})});$('result').textContent=await ar.text();$('autoToggle').disabled=false;refresh();}else if(tries>=12){clearInterval(timer);$('result').textContent='A autorização ainda não foi confirmada. Não foi iniciada nenhuma ordem; confira o estado da conexão.';$('autoToggle').disabled=false;refresh();}}catch(_){if(tries>=12){clearInterval(timer);$('autoToggle').disabled=false;refresh();}}},1000);return;}
 }catch(e){$('result').textContent='Não foi possível iniciar: '+e.message;}
 $('autoToggle').disabled=false;refresh();
};
$('account').addEventListener('change',()=>{try{if($('account').value)localStorage.setItem('meuTraderDemoAccountId',$('account').value)}catch(_){}});
$('selectAccount').onclick=async()=>{if(!$('account').value){$('result').textContent='Nenhuma conta DEMO disponível ainda.';return}try{localStorage.setItem('meuTraderDemoAccountId',$('account').value)}catch(_){}const r=await fetch('/api/account',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({account_id:Number($('account').value)})});$('result').textContent=await r.text();setTimeout(refresh,800)};
document.querySelectorAll('.trade').forEach(btn=>btn.onclick=async()=>{if(!confirm('Enviar ordem '+btn.dataset.side+' de '+$('volume').value+' unidade(s) em '+$('symbol').value+' na conta DEMO?'))return;const r=await fetch('/api/order',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({symbol:$('symbol').value,side:btn.dataset.side,volume_units:Number($('volume').value)})});$('result').textContent=await r.text();setTimeout(refresh,1000)});
async function refreshMarketContext(){try{const r=await fetch('/api/market-context',{cache:'no-store'});const d=await r.json();$('contextStatus').textContent='Atualizado: '+(d.updated_at||'—')+' | Fontes com resposta: '+d.feeds_ok+'/'+d.feeds_total+' | Próximo refresh em cerca de 15 min.';const root=$('contextNews');root.replaceChildren();(d.headlines||[]).forEach(item=>{const p=document.createElement('p');p.className='tile';const a=document.createElement('a');a.href=item.url;a.target='_blank';a.rel='noopener';a.textContent=item.source+': '+item.title;p.appendChild(a);root.appendChild(p)});if(!(d.headlines||[]).length){root.textContent='Nenhuma manchete foi obtida agora. Use os calendários oficiais acima; isso não interfere no filtro de risco.'}}catch(_){$('contextStatus').textContent='Fontes externas temporariamente indisponíveis; consulte os calendários oficiais.'}}
async function refreshStrategyPolicy(){try{const r=await fetch('/api/strategy-policy',{cache:'no-store'});const d=await r.json();$('policyStatus').textContent=d.loaded?'Política carregada do arquivo '+d.path+' | Modo: DEMO | Arbitragem estatística: pesquisa desativada.':'Política não carregada: '+d.summary}catch(_){$('policyStatus').textContent='Não foi possível confirmar a política carregada.'}}
refresh();setInterval(refresh,3000);refreshMarketContext();setInterval(refreshMarketContext,900000);refreshStrategyPolicy();setInterval(refreshStrategyPolicy,30000);
</script></body></html>"""

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    sid = request.session.get("sid")
    connected = bool(sid and TOKENS.get(sid))
    status = "Autorização recebida; falta validar a lista de contas e confirmar qual é DEMO." if connected else "Ainda não conectado."
    return HTMLResponse(PAGE.replace("__STATUS__", status))

@app.get("/api/market-ai")
async def api_market_ai(request: Request):
    """Experimental live technical scoring; not a trained ML model or a trading recommendation."""
    import math
    sid = request.session.get("sid")
    bridge = BRIDGES.get(sid) if sid else None
    if not bridge:
        return {"mode": "aguardando conexão DEMO", "results": [], "message": "Conecte a conta DEMO para iniciar a análise."}
    histories = getattr(bridge, "_auto_history", {})
    results = []
    for symbol in ("XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "USDCAD"):
        raw = histories.get(symbol, [])
        prices = [float(v) for v in raw if isinstance(v, (int, float)) and v > 0]
        if len(prices) < 22:
            continue
        returns = [prices[i] / prices[i-1] - 1.0 for i in range(1, len(prices)) if prices[i-1] > 0]
        if len(returns) < 21:
            continue
        r3, r8, r14 = prices[-1] / prices[-4] - 1.0, prices[-1] / prices[-9] - 1.0, prices[-1] / prices[-15] - 1.0
        def ema(vals, period):
            alpha = 2.0 / (period + 1.0)
            value = vals[0]
            for item in vals[1:]:
                value = alpha * item + (1.0-alpha) * value
            return value
        gap = (ema(prices[-21:], 9) - ema(prices[-21:], 21)) / prices[-1]
        recent = returns[-14:]
        movement = sum(abs(v) for v in recent)
        efficiency = sum(recent) / movement if movement else 0.0
        # Heuristic scoring is explicitly experimental and is NOT trained/calibrated ML.
        score = max(-4.0, min(4.0, 900.0*r3 + 450.0*r8 + 250.0*r14 + 1800.0*gap + 1.4*efficiency))
        up = 1.0 / (1.0 + math.exp(-score))
        up_pct = round(100.0 * up)
        down_pct = 100 - up_pct
        signal = "OBSERVAR" if 40 <= up_pct <= 60 else ("POSSÍVEL ALTA" if up_pct > 60 else "POSSÍVEL BAIXA")
        results.append({"symbol": symbol, "up_pct": up_pct, "down_pct": down_pct, "signal": signal,
                        "reason": "momentum, médias curtas e eficiência direcional", "samples": len(prices)})
    return {"mode": "pontuação técnica experimental; sem modelo treinado e sem análise de notícias", "results": results,
            "message": "Aguardando pelo menos 22 ticks por ativo configurado." if not results else None}


@app.get("/diagnostico-ctrader")
async def diagnostico_ctrader():
    """Safe network probe: tests DNS/TCP reachability without using OAuth credentials."""
    from ctrader_open_api import EndPoints
    host = str(EndPoints.PROTOBUF_DEMO_HOST)
    port = int(EndPoints.PROTOBUF_PORT)
    result = {"host": host, "port": port, "dns_ok": False, "tcp_ok": False}
    try:
        addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        result["dns_ok"] = bool(addresses)
        result["resolved_addresses"] = sorted({row[4][0] for row in addresses})
    except Exception as exc:
        result["error_stage"] = "dns"
        result["error_type"] = type(exc).__name__
        return result
    started = time.monotonic()
    try:
        with socket.create_connection((host, port), timeout=5):
            result["tcp_ok"] = True
            result["latency_ms"] = round((time.monotonic() - started) * 1000, 1)
    except Exception as exc:
        result["error_stage"] = "tcp"
        result["error_type"] = type(exc).__name__
        result["latency_ms"] = round((time.monotonic() - started) * 1000, 1)
    return result


@app.get("/health")
async def health():
    return {"status":"online","app":APP_NAME,"oauth_configured":bool(CLIENT_ID and CLIENT_SECRET and REDIRECT_URI),"order_execution_available":True,"execution_mode":"demo_only_after_account_authorization","mode":"demo_only"}

@app.get("/api/status")
async def api_status(request: Request):
    sid = request.session.get("sid")
    bridge = BRIDGES.get(sid) if sid else None
    broker = bridge.snapshot() if bridge else {"connected":False,"application_authorized":False,"account_validated":False,"account_authorized":False,"accounts":[],"selected_account_id":None,"last_error":None}
    return {"status":"online","oauth_configured":bool(CLIENT_ID and CLIENT_SECRET and REDIRECT_URI),"oauth_authorized":bool(sid and TOKENS.get(sid)),"mode":"demo_only","order_execution":bool(broker.get("account_authorized")),"broker":broker,"next_step":"Selecione e autorize uma conta DEMO; ordens somente por confirmação manual."}

@app.get("/connect")
async def connect(request: Request):
    if not (CLIENT_ID and CLIENT_SECRET and REDIRECT_URI):
        return HTMLResponse("<h2>Configuração pendente</h2><p>Cadastre CTRADER_CLIENT_ID, CTRADER_CLIENT_SECRET e CTRADER_REDIRECT_URI nas variáveis secretas do servidor.</p><p>Depois, registre/aprove o aplicativo em <a href='https://openapi.ctrader.com/'>cTrader Open API</a> e cadastre o mesmo redirect URI.</p><p><a href='/'>Voltar</a></p>",status_code=503)
    state = secrets.token_urlsafe(24)
    request.session["oauth_state"] = state
    params = {"client_id":CLIENT_ID,"redirect_uri":REDIRECT_URI,"scope":"trading","product":"web","state":state}
    return RedirectResponse("https://id.ctrader.com/my/settings/openapi/grantingaccess/?"+urlencode(params),status_code=303)

@app.get("/auth/callback")
@app.get("/oauth/callback")
async def oauth_callback(request: Request, code: str = "", state: str = "", error: str = ""):
    expected = request.session.pop("oauth_state", None)
    if error:
        return HTMLResponse("<h2>Autorização não concluída</h2><p>O acesso não foi autorizado. Nenhuma ordem foi enviada.</p><a href='/'>Voltar</a>",status_code=400)
    if not code or not expected or not secrets.compare_digest(state,expected):
        return HTMLResponse("<h2>Retorno inválido ou expirado</h2><p>Tente conectar novamente.</p><a href='/'>Voltar</a>",status_code=400)
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get("https://openapi.ctrader.com/apps/token",params={"grant_type":"authorization_code","code":code,"redirect_uri":REDIRECT_URI,"client_id":CLIENT_ID,"client_secret":CLIENT_SECRET},headers={"Accept":"application/json"})
        response.raise_for_status()
        data = response.json()
        access_token = data.get("accessToken")
        if not access_token:
            log.warning("cTrader OAuth returned no token; errorCode=%s",data.get("errorCode"))
            return HTMLResponse("<h2>Autorização não concluída</h2><p>O cTrader não retornou um token válido. Confira a configuração do aplicativo.</p><a href='/'>Voltar</a>",status_code=502)
        sid = request.session.get("sid") or secrets.token_urlsafe(32)
        request.session["sid"] = sid
        TOKENS[sid] = {"access_token":access_token,"refresh_token":data.get("refreshToken"),"expires_in":data.get("expiresIn")}
        # OAuth callback can be repeated from mobile/browser history; close the old
        # cTrader TCP session before replacing its bridge to avoid duplicate app auth.
        previous_bridge = BRIDGES.get(sid)
        if previous_bridge is not None:
            previous_bridge.close_connection()
        bridge = CTraderDemoBridge(CLIENT_ID, CLIENT_SECRET)
        BRIDGES[sid] = bridge
        bridge.connect(access_token)
        return RedirectResponse("/",status_code=303)
    except Exception as exc:
        # Do not log exception details: HTTP errors can contain sensitive request URLs.
        log.error("cTrader OAuth token exchange failed (%s)", type(exc).__name__)
        return HTMLResponse("<h2>Falha na troca do código OAuth</h2><p>Confira os registros do servidor. Não envie códigos nem credenciais no chat.</p><a href='/'>Voltar</a>",status_code=502)

class AccountSelection(BaseModel):
    account_id: int


class AutoTradingToggle(BaseModel):
    enabled: bool
    duration_minutes: int = 60


class DemoOrder(BaseModel):
    symbol: str
    side: str
    volume_units: int


@app.post("/api/account")
async def select_demo_account(request: Request, selection: AccountSelection):
    sid = request.session.get("sid")
    bridge = BRIDGES.get(sid) if sid else None
    if not bridge:
        return HTMLResponse("Conecte a conta cTrader primeiro.", status_code=401)
    try:
        result = bridge.authorize_demo_account(selection.account_id)
        return {**result, "message":"Autorização da conta DEMO solicitada; consulte /api/status para confirmar."}
    except PermissionError:
        return HTMLResponse("Conta real bloqueada. Este painel aceita somente DEMO.", status_code=403)
    except (ValueError, RuntimeError) as exc:
        return HTMLResponse(str(exc), status_code=400)


@app.post("/api/start-session")
async def start_session(request: Request, payload: dict):
    """One-button DEMO startup: request account authorization, never bypass risk checks."""
    sid = request.session.get("sid")
    bridge = BRIDGES.get(sid) if sid else None
    account_id = payload.get("account_id")
    duration_minutes = int(payload.get("duration_minutes", 10080))
    if not 1 <= duration_minutes <= 10080:
        return HTMLResponse("Duração deve ser de 1 a 10080 minutos.", status_code=400)
    if not bridge:
        return {"pending": True, "connect_url": "/connect",
                "message": "Conecte e autorize o aplicativo cTrader primeiro; depois toque INICIAR ROBÔ DEMO."}
    if not account_id:
        return HTMLResponse("Selecione uma conta DEMO.", status_code=400)
    try:
        state = bridge.snapshot()
        account = next((a for a in state.get("accounts", []) if int(a["account_id"]) == int(account_id)), None)
        if not account:
            return HTMLResponse("A conta selecionada ainda não consta na lista autorizada.", status_code=400)
        if account.get("is_live"):
            return HTMLResponse("Conta REAL bloqueada. Somente DEMO.", status_code=403)
        if int(state.get("selected_account_id") or 0) != int(account_id) or not state.get("account_authorized"):
            bridge.authorize_demo_account(int(account_id))
            return {"pending": True, "message": "Solicitei autorização da conta DEMO selecionada. Aguardando confirmação antes de iniciar."}
        result = bridge.set_auto_trading(True, duration_minutes)
        return {**result, "message": "Conta DEMO validada e automação iniciada com os limites de segurança ativos."}
    except PermissionError as exc:
        return HTMLResponse(str(exc), status_code=403)
    except (ValueError, RuntimeError) as exc:
        return HTMLResponse(str(exc), status_code=400)


@app.post("/api/auto")
async def toggle_auto_trading(request: Request, toggle: AutoTradingToggle):
    sid = request.session.get("sid")
    bridge = BRIDGES.get(sid) if sid else None
    if not bridge:
        return HTMLResponse("Conecte a conta cTrader primeiro.", status_code=401)
    try:
        return bridge.set_auto_trading(toggle.enabled, toggle.duration_minutes)
    except PermissionError as exc:
        return HTMLResponse(str(exc), status_code=403)
    except RuntimeError as exc:
        return HTMLResponse(str(exc), status_code=400)


@app.get("/api/market-log")
async def market_event_log(request: Request, limit: int = 200):
    sid = request.session.get("sid")
    bridge = BRIDGES.get(sid) if sid else None
    if not bridge:
        return HTMLResponse("Conecte a conta cTrader primeiro.", status_code=401)
    events = bridge.read_recent_events(limit)
    return {"count": len(events), "events": events,
            "note": "Log estruturado para análise; no Render, o arquivo local pode ser apagado em reinicializações ou novos deploys."}


@app.post("/api/order")
async def place_demo_order(request: Request, order: DemoOrder):
    sid = request.session.get("sid")
    bridge = BRIDGES.get(sid) if sid else None
    if not bridge:
        return HTMLResponse("Conecte a conta cTrader primeiro.", status_code=401)
    try:
        result = bridge.place_demo_market_order(order.symbol, order.side, order.volume_units)
        return {**result, "message":"Ordem enviada à API DEMO; confirme a resposta em /api/status."}
    except PermissionError:
        return HTMLResponse("Conta real bloqueada. Somente DEMO.", status_code=403)
    except (ValueError, RuntimeError) as exc:
        return HTMLResponse(str(exc), status_code=400)


@app.post("/disconnect")
async def disconnect(request: Request):
    sid = request.session.get("sid")
    if sid: TOKENS.pop(sid,None)
    request.session.clear()
    return RedirectResponse("/",status_code=303)

# Market context: official news feeds and primary-source economic calendars.
# Cache responses to avoid polling external sites every time the dashboard refreshes.
import asyncio
import datetime
import xml.etree.ElementTree as ET

_MARKET_CONTEXT_CACHE = {"expires": 0, "data": None}
_MARKET_FEEDS = [
    ("Federal Reserve", "https://www.federalreserve.gov/feeds/press_all.xml"),
    ("BLS", "https://www.bls.gov/feed/bls_latest.rss"),
    ("BEA", "https://www.bea.gov/news/rss.xml"),
]


@app.get("/api/strategy-policy")
async def strategy_policy_status(request: Request):
    sid = request.session.get("sid")
    bridge = BRIDGES.get(sid) if sid else None
    if bridge is None:
        return {
            "loaded": False,
            "path": "ctrader-bot/strategy_spec.json",
            "mode": "DEMO",
            "statistical_arbitrage": "research_only_disabled",
            "summary": "Conecte e autorize uma conta DEMO para consultar a política ativa.",
            "critical_rules": {
                "one_open_position_per_symbol": True,
                "other_successful_entries_before_symbol_reuse": 5,
                "real_account_allowed": False,
                "statistical_arbitrage_enabled": False,
                "zscore_alone_authorizes_order": False
            }
        }
    state = bridge.snapshot()
    policy = state.get("strategy_policy", {})
    return {
        "loaded": bool(policy.get("loaded")),
        "path": policy.get("path", "AI_TRADING_POLICY.md"),
        "mode": "DEMO",
        "statistical_arbitrage": "research_only_disabled",
        "summary": policy.get("summary", "Estado da política indisponível."),
        "critical_rules": {
            "one_open_position_per_symbol": True,
            "other_successful_entries_before_symbol_reuse": 5,
            "real_account_allowed": False,
            "statistical_arbitrage_enabled": False,
            "zscore_alone_authorizes_order": False
        }
    }

@app.get("/api/market-context")
async def market_context():
    now = time.time()
    cached = _MARKET_CONTEXT_CACHE.get("data")
    if cached and now < _MARKET_CONTEXT_CACHE.get("expires", 0):
        return cached

    async def read_feed(source, url, client):
        try:
            response = await client.get(url, headers={"User-Agent": "MeuTraderMultimercado/1.0"}, timeout=6.0)
            response.raise_for_status()
            root = ET.fromstring(response.text)
            items = []
            for node in root.iter():
                tag = node.tag.rsplit("}", 1)[-1].lower()
                if tag not in {"item", "entry"}:
                    continue
                fields = {}
                for child in list(node):
                    name = child.tag.rsplit("}", 1)[-1].lower()
                    if name in {"title", "link", "published", "updated", "pubdate", "description"}:
                        fields[name] = (child.text or "").strip()
                        if name == "link" and not fields[name]:
                            fields[name] = child.attrib.get("href", "")
                link = fields.get("link", "")
                if link and link.startswith("http") and fields.get("title"):
                    items.append({"source": source, "title": fields["title"][:220],
                                  "url": link, "published": fields.get("published") or fields.get("updated") or fields.get("pubdate") or ""})
                if len(items) >= 4:
                    break
            return items
        except Exception as exc:
            log.info("Market context feed unavailable: source=%s error=%s", source, type(exc).__name__)
            return None

    async with httpx.AsyncClient(follow_redirects=True) as client:
        results = await asyncio.gather(*(read_feed(source, url, client) for source, url in _MARKET_FEEDS))
    headlines = [item for result in results if result for item in result]
    data = {
        "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "feeds_ok": sum(result is not None for result in results),
        "feeds_total": len(_MARKET_FEEDS),
        "headlines": headlines[:10],
        "calendar_sources": [
            {"name": "Federal Reserve / FOMC", "url": "https://www.federalreserve.gov/newsevents/calendar.htm"},
            {"name": "BLS releases", "url": "https://www.bls.gov/schedule/2026/"},
            {"name": "BEA releases", "url": "https://www.bea.gov/news/schedule/"},
        ],
        "notice": "Manchetes são contexto, não sinal operacional. Datas e horários devem ser confirmados nas fontes oficiais."
    }
    _MARKET_CONTEXT_CACHE.update(data=data, expires=now + 900)
    return data
