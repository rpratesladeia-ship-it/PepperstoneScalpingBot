# V8 OpenAI signal-filter bridge

This service is an intermediary between the V8 cBot and the OpenAI Responses API. It filters an existing candidate signal only; it never chooses direction, sends broker orders, or changes risk limits.

## Security model
- Never put an OpenAI API key or real client token in source control, cBot source, screenshots, or logs.
- Configure `OPENAI_API_KEY`, `OPENAI_MODEL`, `AI_CLIENT_TOKEN`, `TLS_CERT_PATH`, and `TLS_KEY_PATH` as server environment secrets.
- Configure the same random `AI_CLIENT_TOKEN` only in the V8 instance parameters. Use a WSS endpoint with a valid TLS certificate.
- The server requires TLS and listens on port 25345 by default. Do not expose a plaintext WebSocket endpoint.
- `store: false` is sent to the Responses API. No account ID, credentials, balance, or order identifiers are sent; only symbol, side candidate, timeframe and indicator values.
- If authentication, network, OpenAI, or response validation fails, the service rejects the signal (fail-closed).

## Deploy
1. Use a host/VPS that supports a public WSS endpoint on port 25345 and a valid TLS certificate. cTrader Cloud network support differs by API feature/version; verify WebSocket connectivity in a stopped/no-trading demo test before enabling it.
2. Install Node.js 20+ and run `npm install` inside this folder.
3. Configure the five required environment variables from `.env.example` in the hosting provider's secret settings. Never commit a populated .env file.
4. Run `npm test`, then `npm start`.
5. Set the V8 instance's AI filter enabled, WSS URL including port 25345, client token, and confidence threshold. Do this only after the service is deployed and its connectivity has been tested.

## Local tests
`npm test`

## Important
- cTrader Cloud documentation has differing statements about WebSocket support. The detailed API reference currently states WebSocketClient connect/send are unsupported in Cloud, while the Cloud requirements page mentions port 25345. Therefore this bridge is not considered Cloud-validated until a real no-trade connectivity test succeeds.
- The cBot contains an explicit `Account.IsLive` guard. Keep the AI branch separate from V7 and do not use it on a live account.
- The virtual ledger uses only net P&L from positions with the unique V8 label, not the account's full balance/equity. This remains a simulation based on demo execution results, not a separate broker account.
- The model is fallible; passing the filter is not a guarantee of a profitable trade.
