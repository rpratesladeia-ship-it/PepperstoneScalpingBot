# Meu Pocket AI Trader — Python

Telegram bot em Python/FastAPI, modo demo e sinais. Configurações por Telegram: `/periodo`, `/valor`, `/expiracao`, `/ia`, `/start`, `/scan`, `/parar`.

Variáveis de ambiente: `TELEGRAM_BOT_TOKEN` obrigatório para o Telegram; `OPENAI_API_KEY` opcional para o filtro IA.

Importante: a versão atual gera sinais a partir de candles públicos da Binance Spot, não de cotações Pocket Option/OTC. Ela não executa ordens. Não inserir credenciais da corretora até haver uma integração autorizada e validada.
