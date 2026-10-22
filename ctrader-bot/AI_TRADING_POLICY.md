# Política operacional da IA — Meu Trader Multimercado

Este documento é a especificação legível do mapa mental da IA. Deve orientar o código, mas não autoriza uma ordem por si só.

## Fluxo obrigatório
1. Validar conexão, autorização e conta DEMO.
2. Confirmar cotação atualizada, instrumento disponível, spread e liquidez.
3. Consultar sessão de mercado e eventos macroeconômicos.
4. Calcular sinais técnicos e estatísticos.
5. Aplicar filtros, rotação por ativo e verificações de risco.
6. Calcular volume com base no contrato e na margem.
7. Enviar ordem somente se todos os controles passarem.
8. Confirmar execução, SL/TP e gravar o resultado, custos e latência.
9. Monitorar posição e conexão; parar entradas diante de dados obsoletos ou erro crítico.
10. Avaliar resultados líquidos de custos com dados fora da amostra.

## Estratégia atual
Cruzamento de médias com confirmação DMS aproximada por ticks: experimental, não é modelo de IA treinado nem prova de vantagem estatística.

## Arbitragem estatística — pesquisa, ainda desativada
- Z-Score de +/-2 é candidato a sinal, nunca autorização isolada.
- Exigir pares econômicos definidos, dados sincronizados, pelo menos 300 observações iniciais, correlação mínima inicial de 0,70, teste de cointegração/estabilidade e validação walk-forward.
- Descontar spread, comissão, slippage, financiamento e custos de venda a descoberto quando aplicáveis.
- Não presumir acesso a iceberg, fluxo institucional ou volatilidade implícita se a API/broker não fornecer os dados.
- PPO e NLP ficam em pesquisa até existir simulador, dados adequados e validação fora da amostra.
- Fórmula de Kelly desativada; nunca usar Kelly integral sem estimativas robustas.

## Regras de risco e execução
- Conta DEMO apenas; conta REAL bloqueada.
- No máximo uma posição aberta por ativo.
- Depois de uma entrada bem-sucedida num ativo, exigir cinco entradas bem-sucedidas em outros ativos antes de reutilizá-lo.
- Cooldown inicial de 300 segundos por ativo.
- Sem limite global fixo de posições, mas cada ordem depende de margem livre e controles de exposição.
- SL e TP server-side obrigatórios e volume validado pelas especificações do instrumento.
- Antes de ampliar a automação: implementar e testar bloqueio por perda diária realizada, reconciliação de PnL, prevenção de ordem duplicada após timeout e pausa por cotação obsoleta.

## Portões para liberar uma estratégia
Testes unitários; backtest com custos; walk-forward; avaliação fora da amostra; teste DEMO do ciclo de ordens e reconexão; teste de bloqueio por perda diária; validação de volume e SL/TP por instrumento; liberação explícita do operador.
