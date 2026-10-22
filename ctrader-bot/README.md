# Meu Trader Multimercado — início cTrader

Starter mobile-first for official cTrader Open API OAuth authorization. This is a connection scaffold, not a completed trading bot.

## Current scope
- Portuguese responsive login/connect page.
- OAuth 2.0 authorization redirect with `scope=accounts` (read-only permission).
- OAuth `state` validation and authorization-code exchange.
- Health/status endpoints.
- cTrader account selection is DEMO-only; manual/automatic order paths exist in the bridge, so keep automatic entries disabled until validated.
- Automatic entries fail closed when the trained ML model is missing; automatic mode cannot be enabled in that state.
- Market context panel shows cached official RSS headlines from Federal Reserve/BLS/BEA plus links to official economic-release calendars.

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
- The current asset universe scans symbols available from the connected broker, using a configured candidate list. The technical strategy and SL/TP distances remain experimental and must be validated per symbol.
- The panel now includes a market-context endpoint cached for 15 minutes. RSS headlines are not a full economic calendar and are not used as trade signals.
- The concurrent-position cap is currently 2. This is a safety limit, not a guarantee of bounded monetary loss.
- The event log is local and may be lost on Render restarts; durable storage, daily realized-loss reconciliation, comprehensive backtesting, and per-symbol contract-size validation are still pending.
- Very short intervals such as 3–5 seconds are not guaranteed; quotes, broker instruments, spread, latency, and API rate limits matter.

Official docs:
- https://help.ctrader.com/open-api/pt/
- https://help.ctrader.com/open-api/pt/account-authentication/
- https://help.ctrader.com/open-api/pt/api-application/


## Modelo de IA supervisionado (treino offline)
- O filtro de IA agora bloqueia entradas automáticas quando não existe um modelo treinado válido; a pontuação heurística não é mais usada como substituto silencioso de IA.
- O script `ctrader-bot/train_ai_model.py` treina um classificador direcional simples com CSV histórico. Exemplo:
  `python ctrader-bot/train_ai_model.py historico.csv --close Close --horizon 3`
- Use um arquivo por ativo, com candles em ordem cronológica e coluna `Close`. O treino exige pelo menos 600 candles e mantém os 20% finais para avaliação temporal. O modelo só é salvo se superar a previsão de classe majoritária no trecho de teste.
- O arquivo de saída padrão é `ctrader-bot/ai_model.json`; no Render, configure `AI_MODEL_PATH` para um caminho persistente/disponível no deploy ou inclua um modelo validado no artefato de deploy. Render free pode perder arquivos locais ao reiniciar.
- Este script é uma primeira base de treinamento, não uma prova de rentabilidade. Faça validação walk-forward, custos, spread, slippage e teste DEMO antes de qualquer uso. Não ative conta REAL.


## Market context and safe operating state
- Dashboard endpoint: `/api/market-context`. It reads public RSS feeds from the Federal Reserve, Bureau of Labor Statistics (BLS), and Bureau of Economic Analysis (BEA), caches the result for 15 minutes, and reports unavailable feeds instead of treating them as empty market news.
- Official calendars linked in the panel: Federal Reserve/FOMC, BLS releases, and BEA releases. Check the published time zone and convert to Brasília time yourself before building a session plan.
- Headlines are contextual information only. The current code does not automatically parse calendar events into a high-impact news blackout; this must be added and tested before relying on it to block trades.
- Automatic trading now refuses to start if `AI_FILTER_ENABLED=true` and no valid trained model is loaded. The concurrent-position ceiling was reduced from 15 to 2.
- Do not treat the experimental ML trainer as proof of edge. Evaluate spread, commission, slippage, out-of-sample/walk-forward performance, and each instrument's contract specifications before considering any release from the safety block.


## Próxima política operacional da IA
O mapa mental deve ser mantido como especificação versionada no projeto e refletido em regras verificáveis no código: dados, análise, entrada, execução, risco, rotação de ativos, filtros macro, recuperação de erros e relatórios. A estratégia atual de médias+DMS continua experimental e não equivale a IA treinada.

A arbitragem estatística é uma linha de pesquisa separada, desativada até existirem pares configurados e validados, dados sincronizados suficientes, análise de estabilidade/cointegração, custos de spread/comissão/slippage/financiamento e validação walk-forward fora da amostra. Z-Score de ±2 é apenas um candidato a sinal, nunca autorização isolada para ordem. Order book, iceberg, volatilidade implícita, PPO e NLP só podem ser usados quando houver dados/infraestrutura comprovados; Kelly permanece desativada.

O plano de risco conserva uma posição aberta por ativo e exige cinco entradas bem-sucedidas em outros ativos antes de reutilizar um ativo, com cooldown por símbolo. Não há limite global fixo de posições, mas todas as entradas continuam sujeitas à margem, SL/TP, limites de perda e qualidade dos dados. Antes de ampliar a automação, implementar e testar reconciliação de PnL realizado e bloqueio de perda diária, prevenção de ordens duplicadas em timeout, validação por contrato e monitoramento de cotações obsoletas. Conta REAL permanece bloqueada.
