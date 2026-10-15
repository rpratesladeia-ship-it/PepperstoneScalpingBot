# PepperstoneScalpingBot V8

cBot experimental para cTrader Automate (.NET 6 / cTrader.Automate 1.0.21), com cruzamento de EMAs, filtro RSI, stop e alvo por ATR, filtro de spread e controles de risco.

## Configuração inicial V8 (conta DEMO)
- Capital virtual inicial: US$ 19,80 (referência aproximada para simular R$ 100; confirme a conversão antes do teste).
- Risco por operação: 0,5% do capital virtual atual (inicialmente cerca de US$ 0,10).
- Limite de perda diária: 2% do capital virtual de referência no início do dia.
- Máximo de posições simultâneas: 2.
- Máximo de entradas por dia: 5.
- Máximo de perdas consecutivas: 3.
- Limite máximo por ordem: 0,01 lote.
- Stop Loss e Take Profit baseados no ATR.
- O cBot recusa sinais quando o volume calculado fica abaixo do mínimo do símbolo.
- Para evitar erro de conversão, a versão atual exige que a moeda da conta demo seja USD.

## Como compilar
1. Abra a aba **Actions** neste repositório.
2. Selecione **Build cTrader cBot** e execute **Run workflow**, ou aguarde a execução disparada pelo commit.
3. Aguarde o resultado. Se ficar verde, abra a execução e baixe o artefato **PepperstoneScalpingBot-algo**.
4. Importe o arquivo .algo no cTrader e teste em demo/backtest antes de usar.

## Limitações e avisos
- Esta V8 está em uma branch separada chamada `v8-risk-guards`; a branch `main` (V7) não foi alterada.
- O capital virtual é usado para dimensionar o volume e controlar os limites internos. A margem, a execução e o P&L da corretora continuam vinculados à conta demo real; isso não cria uma conta real de US$ 19,80.
- O limite de perda bloqueia novas entradas, mas não fecha posições abertas e não garante que a perda final fique exatamente no limite, pois gaps, spread, slippage e comissões podem alterar o resultado.
- O histórico do capital virtual é reiniciado quando o cBot é reiniciado; não reinicie o robô durante uma sessão de teste se quiser manter a continuidade do cálculo.
- Faça backtest e teste em DEMO. Não use em conta real sem validação independente.
- Nunca salve senhas, tokens ou credenciais no repositório.
