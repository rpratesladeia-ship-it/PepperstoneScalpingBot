import os, secrets, logging
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
CLIENT_ID = os.getenv("CTRADER_CLIENT_ID", "").strip()
CLIENT_SECRET = os.getenv("CTRADER_CLIENT_SECRET", "").strip()
REDIRECT_URI = os.getenv("CTRADER_REDIRECT_URI", "").strip()
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
<a class="btn" href="/connect">Conectar conta cTrader</a>
<p class="muted"><small>* Os ativos dependem da corretora e da conta conectada. Cripto pode não estar disponível em todos os brokers cTrader.</small></p></div>
<div class="card"><h2>Estado da conexão</h2><p class="muted" id="status">__STATUS__</p><p class="muted" id="accountInfo">Consultando a API cTrader…</p><label for="account">Conta DEMO</label><select id="account" style="width:100%;padding:12px;margin:8px 0;background:#111925;color:#fff;border-radius:10px"></select><button id="selectAccount" style="padding:12px;width:100%;border:0;border-radius:10px;font-weight:700">Validar conta DEMO selecionada</button><h3>Cotações recebidas</h3><div id="quotes" class="muted">Aguardando cotações…</div><h3>Robô automático (somente DEMO)</h3><p id="autoStatus" class="muted">Automação desligada</p><p id="aiStatus" class="muted">Filtro IA experimental: desativado por padrão.</p><button id="autoToggle" style="padding:14px;width:100%;border:0;border-radius:10px;background:#f5c66b;color:#17202b;font-weight:800">ATIVAR ENTRADAS AUTOMÁTICAS DEMO</button><p class="muted"><small>Estratégia inicial: cruzamento de médias rápidas/lentas nos ticks. Volume mínimo de 1 unidade, intervalo de segurança de 5 minutos por ativo. Faça testes em DEMO; isso não garante lucro e não substitui stop-loss.</small></p><h3>Teste manual (somente DEMO)</h3><label>Ativo</label><select id="symbol" style="width:100%;padding:12px;margin:8px 0;background:#111925;color:#fff;border-radius:10px"><option>XAUUSD</option><option>EURUSD</option><option>GBPUSD</option><option>USDJPY</option><option>BTCUSD</option><option>US30</option></select><label>Volume em unidades</label><input id="volume" type="number" min="1" max="1000" value="1" style="width:100%;padding:12px;margin:8px 0;background:#111925;color:#fff;border-radius:10px;color:#fff"><div class="grid"><button class="trade" data-side="BUY" style="padding:14px;border:0;border-radius:10px;background:#75e0b0;font-weight:700">Comprar DEMO</button><button class="trade" data-side="SELL" style="padding:14px;border:0;border-radius:10px;background:#f5a3a3;font-weight:700">Vender DEMO</button></div><p id="result" class="muted"></p><p class="muted"><small>Uma ordem só será enviada após você tocar no botão e confirmar. Não é execução automática ainda.</small></p></div>
<div class="card"><h2>Segurança</h2><p class="muted">Não compartilhe senhas, códigos de autenticação, client secret ou tokens. As credenciais do aplicativo ficam somente nas variáveis secretas do servidor.</p></div>
</main><script>
const $=id=>document.getElementById(id);
async function refresh(){
 try{
  const r=await fetch('/api/status',{cache:'no-store'}); const d=await r.json(); const b=d.broker||{};
  $('status').textContent=!d.oauth_authorized?'Não conectado. Toque em Conectar conta cTrader.':!b.connected?'Autorização recebida; conectando à API cTrader…':!b.application_authorized?'Conectado; aguardando autorização do aplicativo…':!b.accounts?.length?'Aplicativo autorizado; aguardando lista de contas…':!b.account_authorized?'Contas carregadas. Selecione uma conta marcada DEMO e valide.': 'Conta DEMO autorizada. Verifique as cotações antes de testar.';
  $('accountInfo').textContent='Conexão: '+(b.connected?'online':'aguardando')+' | App autorizado: '+(b.application_authorized?'sim':'não')+' | Conta autorizada: '+(b.account_authorized?'sim':'não')+(b.last_error?' | Aviso: '+b.last_error:'');
  $('symbols').textContent=(b.symbols||[]).join(', ')||'Nenhum ativo ainda';
  $('execution').textContent=b.auto_trading?'AUTOMÁTICA DEMO ATIVA':(b.account_authorized?'TESTE MANUAL DEMO':'BLOQUEADA');
  $('autoStatus').textContent=b.auto_status|| (b.auto_trading?'Automação ativa':'Automação desligada');
  const ai=b.ai_filter||{}; $('aiStatus').textContent='Filtro IA: '+(ai.enabled?'ATIVO':'desativado')+' | Modelo treinado: '+(ai.model_loaded?'carregado':'não carregado')+' | '+(ai.status||'');\n  $('autoToggle').textContent=b.auto_trading?'DESATIVAR ROBÔ AUTOMÁTICO':'ATIVAR ENTRADAS AUTOMÁTICAS DEMO';
  const sel=$('account');
  const accountList=(b.accounts||[]).map(a=>({id:String(a.account_id),live:!!a.is_live}));
  const signature=JSON.stringify(accountList);
  if(sel.dataset.signature!==signature){
    const previous=sel.value;
    sel.replaceChildren();
    accountList.forEach(a=>{const o=document.createElement('option');o.value=a.id;o.textContent=a.id+' — '+(a.live?'REAL (bloqueada)':'DEMO');o.disabled=a.live;sel.appendChild(o)});
    sel.dataset.signature=signature;
    if(previous && accountList.some(a=>a.id===previous && !a.live)) sel.value=previous;
    else if(b.selected_account_id && accountList.some(a=>a.id===String(b.selected_account_id) && !a.live)) sel.value=String(b.selected_account_id);
  }
  const q=b.prices||{}; $('quotes').textContent=Object.keys(q).length?Object.entries(q).map(([n,p])=>n+': bid raw '+(p.bid_raw??'—')+' / ask raw '+(p.ask_raw??'—')).join(' | '):'Aguardando preços do servidor cTrader…';
  if(b.last_order)$('result').textContent='Última ordem: '+JSON.stringify(b.last_order);
 }catch(e){$('status').textContent='Não foi possível consultar o estado do servidor.'}
}
$('autoToggle').onclick=async()=>{const active=($('autoToggle').textContent||'').startsWith('DESATIVAR');const r=await fetch('/api/auto',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({enabled:!active})});const t=await r.text();$('result').textContent=t;setTimeout(refresh,500)};
$('selectAccount').onclick=async()=>{if(!$('account').value){$('result').textContent='Nenhuma conta DEMO disponível ainda.';return}const r=await fetch('/api/account',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({account_id:Number($('account').value)})});$('result').textContent=await r.text();setTimeout(refresh,800)};
document.querySelectorAll('.trade').forEach(btn=>btn.onclick=async()=>{if(!confirm('Enviar ordem '+btn.dataset.side+' de '+$('volume').value+' unidade(s) em '+$('symbol').value+' na conta DEMO?'))return;const r=await fetch('/api/order',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({symbol:$('symbol').value,side:btn.dataset.side,volume_units:Number($('volume').value)})});$('result').textContent=await r.text();setTimeout(refresh,1000)});
refresh();setInterval(refresh,3000);
</script></body></html>"""

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    sid = request.session.get("sid")
    connected = bool(sid and TOKENS.get(sid))
    status = "Autorização recebida; falta validar a lista de contas e confirmar qual é DEMO." if connected else "Ainda não conectado."
    return HTMLResponse(PAGE.replace("__STATUS__", status))

@app.get("/health")
async def health():
    return {"status":"online","app":APP_NAME,"oauth_configured":bool(CLIENT_ID and CLIENT_SECRET and REDIRECT_URI),"order_execution":False,"mode":"demo_only"}

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


@app.post("/api/auto")
async def toggle_auto_trading(request: Request, toggle: AutoTradingToggle):
    sid = request.session.get("sid")
    bridge = BRIDGES.get(sid) if sid else None
    if not bridge:
        return HTMLResponse("Conecte a conta cTrader primeiro.", status_code=401)
    try:
        return bridge.set_auto_trading(toggle.enabled)
    except PermissionError as exc:
        return HTMLResponse(str(exc), status_code=403)
    except RuntimeError as exc:
        return HTMLResponse(str(exc), status_code=400)


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
