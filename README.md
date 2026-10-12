# PepperstoneScalpingBot

cBot experimental para cTrader Automate (.NET 8), com cruzamento EMA 9/21, filtro RSI, stop e alvo por ATR, filtro de spread e limite diário de novas entradas.

## Compilar pelo celular
1. Abra a aba **Actions** neste repositório.
2. Selecione **Build cTrader cBot** e toque em **Run workflow**.
3. Aguarde a execução terminar.
4. Se ficar verde, abra a execução e baixe o artefato **PepperstoneScalpingBot-algo**.
5. Se falhar, abra o passo vermelho e envie a mensagem de erro para correção.

## Avisos importantes
- Use somente em conta DEMO e faça backtest antes de qualquer uso real.
- O limite diário impede novas entradas, mas não fecha automaticamente posições abertas nem garante perda máxima.
- O dimensionamento de volume depende das especificações do símbolo e da moeda da conta; confira no backtest/demo.
- Nunca salve senhas, tokens ou credenciais no repositório.
- O código ainda precisa compilar e passar por backtest e teste em DEMO antes de ser considerado utilizável.