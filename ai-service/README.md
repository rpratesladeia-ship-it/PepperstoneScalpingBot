# V8 OpenAI signal-filter bridge

This service is an intermediary between the V8 cBot and the OpenAI Responses API. It filters an existing candidate signal only; it never chooses direction, sends broker orders, or changes risk limits.

## Render deployment (recommended for this repository)

Create a **Web Service** connected to this repository and select branch `v8-openai-ai-filter`.

- **Root Directory:** `ai-service`
- **Runtime:** Node
- **Build Command:** `npm install`
- **Start Command:** `npm start`
- **Health Check Path:** `/health` (optional but recommended)
- Let Render provide the `PORT` environment variable. Do not set `TLS_CERT_PATH` or `TLS_KEY_PATH` on Render: Render terminates public TLS and forwards traffic to the service internally. External clients must use `wss://`.

Add these three environment variables in Render → service → Environment. Use secret values and never put them in GitHub or this chat:

- `OPENAI_API_KEY`: your OpenAI API key.
- `OPENAI_MODEL`: a model available to your API project.
- `AI_CLIENT_TOKEN`: a long, randomly generated token; use the exact same token only in the V8 instance parameter.

After saving environment variables, deploy the service. The health check should return JSON with `"status":"ok"` at `https://YOUR-SERVICE.onrender.com/health`. This checks that the process is running, not that OpenAI credentials or cTrader connectivity work.

The cBot endpoint will be `wss://YOUR-SERVICE.onrender.com` (no port number). Render supports public WebSocket connections over the service URL; its TLS certificate is managed by Render. Do not use `ws://` or append port `25345` for a Render Web Service.

## Security model

- Never put an OpenAI API key or real client token in source control, cBot source, screenshots, or logs.
- The service validates the client token, validates the signal schema, limits each connection to 30 requests/minute, and fails closed on authentication, network, OpenAI, or response-validation errors.
- `store: false` is sent to the OpenAI Responses API. No account ID, credentials, balance, or order identifiers are sent; only symbol, candidate side, timeframe and indicator values.
- The AI only filters an existing candidate signal; it cannot create an order, change the side, or override risk limits.

## Local tests

Use Node.js 20+:
```sh
npm install
npm test
npm start
``

For a self-hosted deployment outside Render, set `TLS_CERT_PATH` and `TLS_KEY_PATH` and expose only TLS/WSS. On Render, do not set those two variables.

## Important cTrader Cloud limitation

The official cTrader documentation has conflicting statements about WebSocket support in Cloud: the detailed `WebSocketClient` reference says connect/send are unsupported in Cloud, while the Cloud requirements page mentions port 25345. Therefore, a successful Render deployment **does not prove** that cTrader Cloud can connect to it. Keep AI blocked and perform a no-trade connectivity test first. If Cloud does not support `WebSocketClient`, the integration will need a different cTrader execution environment or supported architecture.

The cBot has an explicit `Account.IsLive` guard. Keep this branch separate from V7 and do not use it on a live account. The virtual ledger uses only net P&L from positions with the unique V8 label, not the account's full balance/equity. This is a simulation based on demo execution results, not a separate broker account. The model is fallible and does not guarantee profitable trades.
