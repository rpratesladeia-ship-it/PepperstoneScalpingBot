# Meu Trader Multimercado — início cTrader

Painel mobile-first do Meu Trader Multimercado para cTrader Open API, com conexão DEMO, sinais técnicos e execução limitada à conta DEMO.

## Current scope
- Portuguese responsive login/connect page.
- OAuth 2.0 authorization redirect with `scope=accounts` (read-only permission).
- OAuth `state` validation and authorization-code exchange.
- Health/status endpoints.
- Execução automática de ordens DEMO existe na versão atual, mas não deve ser considerada validada até concluir os testes de execução e fechamento.
- Filtro de Machine Learning experimental opcional; desativado por padrão e bloqueia entradas se ativado sem modelo válido.
- Testes automatizados de estratégia e filtro de IA via GitHub Actions.

## Setup
1. Create a cTrader ID and a demo account with a cTrader-affiliated broker. Confirm the broker accepts your residence and offers the instruments you want.
2. Register an Open API application at https://openapi.ctrader.com/ and wait for approval. Add the deployed callback URL exactly as a Redirect URI: `https://YOUR-SERVICE.onrender.com/oauth/callback`.
3. Set `CTRADER_CLIENT_ID`, `CTRADER_CLIENT_SECRET`, `CTRADER_REDIRECT_URI`, and a strong `SESSION_SECRET` in the host's secret environment settings. Never commit credentials.
4. Build command: `pip install -r ctrader-bot/requirements.txt`
5. Start command (from repository root): `uvicorn app:app --app-dir ctrader-bot --host 0.0.0.0 --port $PORT`
6. Open the service URL on Android and tap **Conectar conta cTrader**. Approve only the account access you intend to grant.

## Important limitations
- OAuth approval alone does not prove a working trading connection. Confirm the account is DEMO and inspect the execution result in the broker.
- Tokens are held in process memory only in this prototype and are lost on restart. Do not deploy as a production multi-user service.
- The current DMS14 is a tick-based approximation, not canonical OHLC ADX/DMS.
- SL/TP distances and financial trailing must be verified per broker symbol, account currency, and actual execution. A server-side trailing monitor is not a guaranteed broker-side stop.
- The ML filter is an experimental logistic-regression baseline, not proof of profitable AI. No model or market dataset is shipped; do not enable it until it is trained and validated.
- Very short intervals such as 3–5 seconds are not guaranteed; quotes, broker instruments, spread, latency, and API rate limits matter.

Official docs:
- https://help.ctrader.com/open-api/pt/
- https://help.ctrader.com/open-api/pt/account-authentication/
- https://help.ctrader.com/open-api/pt/api-application/
