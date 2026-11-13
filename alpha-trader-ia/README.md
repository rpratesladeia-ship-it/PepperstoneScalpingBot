# ALPHA TRADER IA — V1.0

Aplicação mobile-first para Android, com scanner multimercado, geração de sinais, histórico auditável e execução automática **somente em demonstração na V1**.

## Estado da V1
- [x] Branch isolada criada a partir de `ctrader-multimarket-demo`
- [ ] Painel web responsivo/PWA para Android
- [ ] API backend e armazenamento local de histórico
- [ ] Motor técnico (RSI, ADX, médias móveis, ATR)
- [ ] Pontuação explicável; não chamar score de probabilidade sem calibração
- [ ] Scanner por classe de ativo
- [ ] Adaptador cTrader demo
- [ ] Adaptador cripto em testnet
- [ ] Testes, backtest e paper trading
- [ ] Execução real bloqueada até aprovação explícita e validação

## Escopo de mercados
1. Forex e CFDs de moedas.
2. Metais e commodities (ex.: XAUUSD).
3. Índices e CFDs de índices.
4. Criptoativos via exchange/API oficial e ambiente testnet.
5. Ações/ETFs somente quando a corretora/API oferecer dados e negociação compatíveis.
6. OTC/digitais: somente pesquisa e sinais experimentais até existir feed e API oficiais verificáveis. Não automatizar por cliques, scraping ou APIs não autorizadas.

Cada classe de ativo terá um adaptador próprio. Não misturar candles OTC com candles de mercado aberto nem comparar seus resultados no mesmo grupo estatístico.

## Arquitetura
- `frontend/`: PWA responsiva, Android primeiro.
- `backend/api/`: API HTTP.
- `backend/market_data/`: conectores de dados por mercado.
- `backend/indicators/`: indicadores e normalização.
- `backend/strategy/`: regras, score explicável e filtros de entrada atrasada.
- `backend/risk/`: limites de exposição, perda diária e tamanho de posição.
- `backend/execution/`: adaptadores de execução em demo/testnet.
- `backend/journal/`: registro imutável de sinal, ordem e resultado.
- `tests/`: testes unitários e de integração simulada.

## Política de segurança inicial
- Ambiente padrão: DEMO/PAPER.
- Valor de referência informado pelo usuário: R$ 5 por entrada de teste; cada instrumento precisa converter isso corretamente para unidades/lotes e respeitar o mínimo da corretora. Se não for possível, não enviar ordem.
- Martingale: DESATIVADO e sem opção de recuperação automática.
- Nenhuma chave ou segredo no GitHub; usar variáveis de ambiente no provedor.
- Nenhuma ordem real na V1.
- Execução deve exigir feed atual, conta demo confirmada, limites de risco e confirmação de ordem.
- Um sinal não é uma promessa de lucro; scores serão validados por backtest e paper trading fora da amostra.

## Critérios para liberar execução em demo
- Feed e horário do candle confirmados.
- Sem candle incompleto quando a estratégia exigir fechamento.
- Stop/saída e tamanho válidos para o instrumento.
- Limite de perda e de posições respeitados.
- Idempotência para evitar ordens duplicadas.
- Registro de requisição, resposta, preço, spread, slippage e resultado.
- Botão global de emergência para bloquear novas ordens.

## Fases
### Fase 1 — Base segura
PWA Android, API, journal, indicadores, score explicável e modo simulado com dados de teste.

### Fase 2 — Dados reais e paper trading
Conectar fontes oficiais por classe de ativo, validar qualidade dos candles e executar simulações sem dinheiro.

### Fase 3 — Execução demo
Conectar cTrader demo e cripto testnet; sem credenciais reais e sem desbloquear live.

### Fase 4 — Validação
Backtest com custos, walk-forward, paper trading e relatório por ativo/timeframe/horário.

### Fase 5 — Revisão de segurança
Qualquer avaliação de execução real exige nova decisão explícita do usuário, revisão de corretora, API, risco e requisitos legais.

## Não objetivos da V1
- Prometer taxa de acerto ou rentabilidade.
- Copiar ou reproduzir sinais sem validar.
- Usar martingale para recuperar perdas.
- Operar Polarium ou qualquer plataforma sem API oficial autorizada e feed verificável.
