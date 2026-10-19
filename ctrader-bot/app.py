import os, secrets, logging
from urllib.parse import urlencode
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("trader-ctrader")
APP_NAME = "Meu Trader Multimercado"
CLIENT_ID = os.getenv("CTRADER_CLIENT_ID", "").strip()
CLIENT_SECRET = os.getenv("CTRADER_CLIENT_SECRET", "").strip()
REDIRECT_URI = os.getenv("CTRADER_REDIRECT_URI", "").strip()
SESSION_SECRET = os.getenv("SESSION_SECRET", "").strip()
# Prototype: tokens remain in memory only and are cleared when the service restarts.
TOKENS = {}
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
<div class="grid"><div class="tile"><small>Mercados planejados</small><br><b>Forex, ouro, índices e cripto*</b></div><div class="tile"><small>Execução de ordens</small><br><b>DESATIVADA</b></div></div>
<a class="btn" href="/connect">Conectar conta cTrader</a>
<p class="muted"><small>* Os ativos dependem da corretora e da conta conectada. Cripto pode não estar disponível em todos os brokers cTrader.</small></p></div>
<div class="card"><h2>Estado da conexão</h2><p class="muted">__STATUS__</p><p class="muted">Próximas etapas: autorizar o aplicativo, validar as contas retornadas pela API, identificar a conta demo e testar a leitura de cotações. Nenhuma ordem será enviada nesta versão.</p></div>
<div class="card"><h2>Segurança</h2><p class="muted">Não compartilhe senhas, códigos de autenticação, client secret ou tokens. As credenciais do aplicativo ficam somente nas variáveis secretas do servidor.</p></div>
</main></body></html>"""

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
    return {"status":"online","oauth_configured":bool(CLIENT_ID and CLIENT_SECRET and REDIRECT_URI),"oauth_authorized":bool(sid and TOKENS.get(sid)),"account_validated":False,"mode":"demo_only","order_execution":False,"next_step":"Validate cTrader account list and explicitly select a demo account."}

@app.get("/connect")
async def connect(request: Request):
    if not (CLIENT_ID and CLIENT_SECRET and REDIRECT_URI):
        return HTMLResponse("<h2>Configuração pendente</h2><p>Cadastre CTRADER_CLIENT_ID, CTRADER_CLIENT_SECRET e CTRADER_REDIRECT_URI nas variáveis secretas do servidor.</p><p>Depois, registre/aprove o aplicativo em <a href='https://openapi.ctrader.com/'>cTrader Open API</a> e cadastre o mesmo redirect URI.</p><p><a href='/'>Voltar</a></p>",status_code=503)
    state = secrets.token_urlsafe(24)
    request.session["oauth_state"] = state
    params = {"client_id":CLIENT_ID,"redirect_uri":REDIRECT_URI,"scope":"accounts","product":"web","state":state}
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
        return RedirectResponse("/",status_code=303)
    except Exception:
        log.exception("cTrader OAuth token exchange failed")
        return HTMLResponse("<h2>Falha na troca do código OAuth</h2><p>Confira os registros do servidor. Não envie códigos nem credenciais no chat.</p><a href='/'>Voltar</a>",status_code=502)

@app.post("/disconnect")
async def disconnect(request: Request):
    sid = request.session.get("sid")
    if sid: TOKENS.pop(sid,None)
    request.session.clear()
    return RedirectResponse("/",status_code=303)
