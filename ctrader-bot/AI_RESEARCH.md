# Filtro experimental de IA — Meu Trader Multimercado

## O que existe
- A estratégia atual é técnica: cruzamento de médias móveis em ticks e filtro direcional DMS14 aproximado por ticks. Isso não é ADX clássico nem um modelo de IA.
- Foi adicionado um filtro opcional de classificação logística. Ele calcula retornos em 3/8/14 passos, volatilidade, diferença EMA 9/21 e eficiência direcional.
- O filtro não cria nem inventa um modelo. Sem um arquivo treinado, o comportamento do filtro é **bloquear entradas quando ele estiver explicitamente ativado**.
- O treinador usa um CSV histórico cronológico com a coluna `close`, separa treino e validação por tempo e grava métricas de classificação. A acurácia não é rentabilidade.

## Como pesquisar
1. Obtenha dados históricos do mesmo ativo, feed e periodicidade que pretende usar. Não misture preços de brokers diferentes sem normalização.
2. Prepare um CSV cronológico com uma coluna `close`; não inclua dados futuros em nenhuma linha de entrada.
3. Rode, a partir da pasta `ctrader-bot`: `python train_ai_filter.py dados.csv --output ai_model.json`.
4. Avalie o holdout, e depois faça backtest walk-forward incluindo spread, comissão, swap e slippage.
5. Compare com a estratégia sem filtro em período separado e conta DEMO. Não use acurácia isolada para decidir.
6. Só depois de aprovação humana, configure `AI_FILTER_ENABLED=true` e `AI_MODEL_PATH` para um artefato treinado e disponível no servidor.

## Limitações
- O modelo é um baseline experimental, não uma IA generativa nem um sistema comprovadamente lucrativo.
- A saída é uma probabilidade de retorno futuro positivo acima de um limiar, não uma certeza.
- O treino usa preços de fechamento em sequência; a qualidade do conjunto de dados e a correspondência com a execução real são fundamentais.
- A proteção de risco continua independente do modelo. O modelo nunca deve aumentar volume nem remover SL/TP.
- A implantação atual não inclui dados históricos nem um modelo treinado; portanto, o filtro permanece desligado por padrão.
