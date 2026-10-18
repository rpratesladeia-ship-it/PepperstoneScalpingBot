# Pocket AI Demo — hospedagem Render

Este subprojeto é um painel web de análise para uso educativo. **Não envia ordens à Pocket Option** e não é um robô autônomo de negociação.

## Deploy
No Render, crie um Web Service apontando para este repositório e a branch `pocket-option-demo-cloud`.
- Build command: `cd pocket-option-demo && npm install`
- Start command: `cd pocket-option-demo && npm start`
- Health check path: `/health`
- Opcional: configure `OPENAI_API_KEY` como variável secreta no Render. Não a coloque no GitHub nem no chat.

O serviço analisa candles OHLC fornecidos pelo usuário. Sem a chave de IA, os sinais ficam bloqueados. A IA não garante resultados.

Não foi implementada integração de execução da Pocket Option porque não foi confirmada uma API oficial documentada e autorizada para enviar operações. Não use scraping, cookies de sessão ou credenciais para contornar isso.
