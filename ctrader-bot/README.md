# Meu Trader Multimercado — início cTrader

Starter mobile-first for official cTrader Open API OAuth authorization. This is a connection scaffold, not a completed trading bot.

## Current scope
- Portuguese responsive login/connect page.
- OAuth 2.0 authorization redirect with `scope=accounts` (read-only permission).
- OAuth `state` validation and authorization-code exchange.
- Health/status endpoints.
- Order execution is hard-disabled; no orders are sent.

## Setup
1. Create a cTrader ID and a demo account with a cTrader-affiliated broker. Confirm the broker accepts your residence and offers the instruments you want.
2. Register an Open API application at https://openapi.ctrader.com/ and wait for approval. Add the deployed callback URL exactly as a Redirect URI: `https://meu-trader-multimercado.onrender.com/auth/callback` (also accepts `/oauth/callback`).
3. Set `CTRADER_CLIENT_ID`, `CTRADER_CLIENT_SECRET`, `CTRADER_REDIRECT_URI`, and a strong stable `SESSION_SECRET` in the host's secret environment settings. For compatibility with the ZIP, `CLIENT_ID`, `CLIENT_SECRET`, and `REDIRECT_URI` are also accepted. Use `CTRADER_REDIRECT_URI=https://meu-trader-multimercado.onrender.com/auth/callback` and register that exact URI in the cTrader app. Never commit credentials. The app must be approved by cTrader before OAuth can complete.
4. Build command: `pip install -r ctrader-bot/requirements.txt`
5. Start command (from repository root): `uvicorn app:app --app-dir ctrader-bot --host 0.0.0.0 --port $PORT`
6. Open the service URL on Android and tap **Conectar conta cTrader**. Approve only the account access you intend to grant.

## Safe DEMO test checklist
- Open `https://meu-trader-multimercado.onrender.com/health` and verify `oauth_configured` is `true`.
- Open `/diagnostico-ctrader` and verify `dns_ok` and `tcp_ok` are `true`.
- Connect through cTrader, select a row marked DEMO, and wait until status confirms account authorization and live quotes.
- Start with the manual test at volume `1` (the UI labels this as units); confirm each order only after verifying the selected account is DEMO. Do not enable automation until connection, quote scale, and SL/TP are validated on that broker symbol.
- The code blocks real accounts. The automatic strategy and its financial protections remain experimental; demo execution is not a guarantee of profit.

## Important limitations
- OAuth approval alone does not prove a trading connection or identify a demo account. Account-list validation and the official Open API protocol/SDK integration are still pending.
- This starter requests read-only `accounts` scope. Do not change to `trading` until demo-account validation and testing are complete.
- Tokens are held in process memory only in this prototype and are lost on restart. Do not deploy as a production multi-user service.
- Market scanning, backtesting, risk controls, trade history, and execution are not implemented yet.
- Very short intervals such as 3–5 seconds are not guaranteed; quotes, broker instruments, spread, latency, and API rate limits matter.

Official docs:
- https://help.ctrader.com/open-api/pt/
- https://help.ctrader.com/open-api/pt/account-authentication/
- https://help.ctrader.com/open-api/pt/api-application/
