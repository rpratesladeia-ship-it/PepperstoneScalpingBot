// PepperstoneScalpingBot.cs
// V8: scanner multiativos com capital virtual e limites adicionais de risco.
// Testar somente em conta DEMO; compilação não substitui backtest e validação de risco.

using System;
using System.Collections.Generic;
using cAlgo.API;
using cAlgo.API.Indicators;
using cAlgo.API.Internals;

namespace cAlgo.Robots
{
    [Robot(TimeZone = TimeZones.UTC, AccessRights = AccessRights.None)]
    public class PepperstoneScalpingBotV8 : Robot
    {
        [Parameter("Símbolos (separados por vírgula)", DefaultValue = "EURUSD,GBPUSD,USDJPY,AUDUSD,USDCAD,USDCHF,NZDUSD")]
        public string SymbolsToScan { get; set; }

        [Parameter("Período de sinal", DefaultValue = "Minute")]
        public TimeFrame SignalTimeFrame { get; set; }

        [Parameter("Intervalo de varredura (segundos)", DefaultValue = 15, MinValue = 5, MaxValue = 300)]
        public int ScanIntervalSeconds { get; set; }

        [Parameter("Capital virtual (moeda da conta)", DefaultValue = 19.80, MinValue = 1.0)]
        public double VirtualStartingCapital { get; set; }

        [Parameter("Máximo de posições simultâneas", DefaultValue = 2, MinValue = 1, MaxValue = 10)]
        public int MaxOpenPositions { get; set; }

        [Parameter("Máximo de entradas por dia", DefaultValue = 5, MinValue = 1, MaxValue = 100)]
        public int MaxEntriesPerDay { get; set; }

        [Parameter("Máximo de perdas consecutivas", DefaultValue = 3, MinValue = 1, MaxValue = 20)]
        public int MaxConsecutiveLosses { get; set; }

        [Parameter("Risco por operação (%)", DefaultValue = 0.5, MinValue = 0.1, MaxValue = 1.0)]
        public double RiskPercent { get; set; }

        [Parameter("Limite máximo por ordem (lotes)", DefaultValue = 0.01, MinValue = 0.01, MaxValue = 1.0)]
        public double MaxLotsPerTrade { get; set; }

        [Parameter("Limite de perda diária (%)", DefaultValue = 2.0, MinValue = 0.5, MaxValue = 2.0)]
        public double DailyLossLimitPercent { get; set; }

        [Parameter("EMA rápida", DefaultValue = 5, MinValue = 2)]
        public int FastEmaPeriod { get; set; }

        [Parameter("EMA lenta", DefaultValue = 13, MinValue = 3)]
        public int SlowEmaPeriod { get; set; }

        [Parameter("RSI período", DefaultValue = 14, MinValue = 2)]
        public int RsiPeriod { get; set; }

        [Parameter("RSI mínimo compra", DefaultValue = 50)]
        public double BuyRsiMin { get; set; }

        [Parameter("RSI máximo compra", DefaultValue = 70)]
        public double BuyRsiMax { get; set; }

        [Parameter("RSI mínimo venda", DefaultValue = 30)]
        public double SellRsiMin { get; set; }

        [Parameter("RSI máximo venda", DefaultValue = 50)]
        public double SellRsiMax { get; set; }

        [Parameter("ATR período", DefaultValue = 14, MinValue = 2)]
        public int AtrPeriod { get; set; }

        [Parameter("Stop ATR multiplicador", DefaultValue = 1.5, MinValue = 0.5)]
        public double StopAtrMultiplier { get; set; }

        [Parameter("Alvo ATR multiplicador", DefaultValue = 2.0, MinValue = 0.5)]
        public double TakeProfitAtrMultiplier { get; set; }

        [Parameter("Spread máximo (pips)", DefaultValue = 1.5, MinValue = 0.1)]
        public double MaxSpreadPips { get; set; }

        [Parameter("Etiqueta", DefaultValue = "PepperstoneScalpingBot")]
        public string BotLabel { get; set; }

        private sealed class SymbolState
        {
            public Symbol Symbol;
            public Bars Bars;
            public ExponentialMovingAverage FastEma;
            public ExponentialMovingAverage SlowEma;
            public RelativeStrengthIndex Rsi;
            public AverageTrueRange Atr;
            public DateTime LastProcessedBar;
        }

        private readonly Dictionary<string, SymbolState> _states = new Dictionary<string, SymbolState>(StringComparer.OrdinalIgnoreCase);
        private DateTime _day;
        private double _virtualEquity;
        private double _dayStartVirtualEquity;
        private int _entriesToday;
        private int _consecutiveLosses;
        private bool _dailyStopTriggered;

        protected override void OnStart()
        {
            if (FastEmaPeriod >= SlowEmaPeriod)
            {
                Print("ERRO: a EMA rápida precisa ser menor que a EMA lenta.");
                Stop();
                return;
            }

            string[] requested = (SymbolsToScan ?? string.Empty).Split(',');
            foreach (string raw in requested)
            {
                string name = raw.Trim();
                if (name.Length == 0 || _states.ContainsKey(name))
                    continue;

                try
                {
                    Symbol symbol = Symbols.GetSymbol(name);
                    if (symbol == null)
                    {
                        Print("Símbolo não encontrado na corretora: {0}. Confira o nome exato no cTrader.", name);
                        continue;
                    }

                    Bars bars = MarketData.GetBars(SignalTimeFrame, symbol.Name);
                    var state = new SymbolState
                    {
                        Symbol = symbol,
                        Bars = bars,
                        FastEma = Indicators.ExponentialMovingAverage(bars.ClosePrices, FastEmaPeriod),
                        SlowEma = Indicators.ExponentialMovingAverage(bars.ClosePrices, SlowEmaPeriod),
                        Rsi = Indicators.RelativeStrengthIndex(bars.ClosePrices, RsiPeriod),
                        Atr = Indicators.AverageTrueRange(bars, AtrPeriod, MovingAverageType.Exponential),
                        LastProcessedBar = DateTime.MinValue
                    };
                    _states[symbol.Name] = state;
                    Print("Monitorando {0} no período {1}; candles carregados: {2}.", symbol.Name, SignalTimeFrame, bars.Count);
                }
                catch (Exception ex)
                {
                    Print("Não foi possível preparar {0}: {1}", name, ex.Message);
                }
            }

            if (_states.Count == 0)
            {
                Print("ERRO: nenhum símbolo válido. Pare o cBot e confira os nomes dos ativos disponíveis na Pepperstone.");
                Stop();
                return;
            }

            if (!string.Equals(Account.Asset.Name, "USD", StringComparison.OrdinalIgnoreCase))
            {
                Print("ERRO: capital virtual 19,80 foi definido em USD; a moeda da conta é {0}. Para evitar cálculo incorreto, o cBot será parado.", Account.Asset.Name);
                Stop();
                return;
            }

            _day = Server.Time.Date;
            _virtualEquity = VirtualStartingCapital;
            _dayStartVirtualEquity = _virtualEquity;
            _entriesToday = 0;
            _consecutiveLosses = 0;
            _dailyStopTriggered = false;
            Positions.Closed += OnPositionClosed;
            Timer.Start(ScanIntervalSeconds);
            Print("V8 iniciado em modo DEMO: {0} símbolos; capital virtual US${1:F2}; risco {2:F2}%; até {3} posições, {4} entradas/dia, {5} perdas seguidas; teto {6:F2} lote.",
                _states.Count, _virtualEquity, RiskPercent, MaxOpenPositions, MaxEntriesPerDay, MaxConsecutiveLosses, MaxLotsPerTrade);
            Print("ATENÇÃO: capital virtual só controla dimensionamento e limites internos; margem, execução e P&L da corretora continuam ligados à conta demo real.");
        }

        protected override void OnTimer()
        {
            ResetDailyGuardIfNeeded();
            if (_dailyStopTriggered || DailyLossLimitReached())
                return;

            if (_entriesToday >= MaxEntriesPerDay)
            {
                Print("LIMITE DE ENTRADAS: {0}/{1}. Novas entradas bloqueadas até o próximo dia.", _entriesToday, MaxEntriesPerDay);
                return;
            }

            if (_consecutiveLosses >= MaxConsecutiveLosses)
            {
                Print("LIMITE DE PERDAS CONSECUTIVAS: {0}. Novas entradas bloqueadas até o próximo dia.", _consecutiveLosses);
                return;
            }

            foreach (KeyValuePair<string, SymbolState> pair in _states)
            {
                if (Positions.FindAll(BotLabel, pair.Key).Length > 0)
                    continue;

                if (Positions.FindAll(BotLabel).Length >= MaxOpenPositions)
                    return;

                ScanSymbol(pair.Key, pair.Value);
            }
        }

        private void ScanSymbol(string symbolName, SymbolState state)
        {
            if (state.Bars.Count < Math.Max(SlowEmaPeriod, AtrPeriod) + 3)
            {
                Print("{0}: aguardando histórico suficiente ({1} candles).", symbolName, state.Bars.Count);
                return;
            }

            DateTime closedBarTime = state.Bars.OpenTimes.Last(1);
            if (closedBarTime == state.LastProcessedBar)
                return;
            state.LastProcessedBar = closedBarTime;

            double spreadPips = (state.Symbol.Ask - state.Symbol.Bid) / state.Symbol.PipSize;
            if (spreadPips > MaxSpreadPips)
            {
                Print("{0}: sinal ignorado, spread {1:F2} pips acima do limite.", symbolName, spreadPips);
                return;
            }

            double fastNow = state.FastEma.Result.Last(1);
            double fastPrevious = state.FastEma.Result.Last(2);
            double slowNow = state.SlowEma.Result.Last(1);
            double slowPrevious = state.SlowEma.Result.Last(2);
            double rsi = state.Rsi.Result.Last(1);
            double atrPips = state.Atr.Result.Last(1) / state.Symbol.PipSize;
            if (atrPips <= 0)
            {
                Print("{0}: ATR inválido; sinal ignorado.", symbolName);
                return;
            }

            bool bullishCross = fastPrevious <= slowPrevious && fastNow > slowNow;
            bool bearishCross = fastPrevious >= slowPrevious && fastNow < slowNow;
            double stopLossPips = atrPips * StopAtrMultiplier;
            double takeProfitPips = atrPips * TakeProfitAtrMultiplier;

            if (bullishCross && rsi >= BuyRsiMin && rsi <= BuyRsiMax)
                OpenPosition(symbolName, state.Symbol, TradeType.Buy, stopLossPips, takeProfitPips);
            else if (bearishCross && rsi >= SellRsiMin && rsi <= SellRsiMax)
                OpenPosition(symbolName, state.Symbol, TradeType.Sell, stopLossPips, takeProfitPips);
            else
                Print("{0}: sem entrada em {1}; EMA9/EMA21={2:F5}/{3:F5}; RSI={4:F1}; spread={5:F2} pips.",
                    symbolName, SignalTimeFrame, fastNow, slowNow, rsi, spreadPips);
        }

        private void OpenPosition(string symbolName, Symbol symbol, TradeType tradeType, double stopLossPips, double takeProfitPips)
        {
            // API oficial calcula o volume diretamente em unidades para o risco percentual.
            // Não converter o volume retornado novamente de lotes para unidades.
            double virtualRiskMoney = _virtualEquity * (RiskPercent / 100.0);
            if (virtualRiskMoney <= 0 || stopLossPips <= 0)
            {
                Print("{0}: risco monetário ou stop inválido; ordem cancelada.", symbolName);
                return;
            }

            // O risco monetário é calculado na moeda da conta; a verificação USD impede conversão incorreta.
            double unitsByRisk = symbol.VolumeForFixedRisk(virtualRiskMoney, stopLossPips, RoundingMode.Down);
            double maxUnits = symbol.QuantityToVolumeInUnits(MaxLotsPerTrade);
            if (double.IsNaN(unitsByRisk) || double.IsInfinity(unitsByRisk) || unitsByRisk <= 0 ||
                double.IsNaN(maxUnits) || double.IsInfinity(maxUnits) || maxUnits <= 0)
            {
                Print("{0}: volume inválido calculado; ordem cancelada por segurança.", symbolName);
                return;
            }

            double units = Math.Min(unitsByRisk, maxUnits);
            double volume = symbol.NormalizeVolumeInUnits(units, RoundingMode.Down);
            Print("{0}: risco alvo {1:F2}% | volume por risco {2} unidades | teto {3} unidades | volume final {4} unidades ({5:F2} lotes).",
                symbolName, RiskPercent, unitsByRisk, maxUnits, volume, symbol.VolumeInUnitsToQuantity(volume));
            if (volume < symbol.VolumeInUnitsMin)
            {
                Print("{0}: sinal ignorado; volume calculado menor que o mínimo permitido.", symbolName);
                return;
            }

            if (volume > symbol.VolumeInUnitsMax)
                volume = symbol.NormalizeVolumeInUnits(symbol.VolumeInUnitsMax, RoundingMode.Down);

            var result = ExecuteMarketOrder(tradeType, symbolName, volume, BotLabel, stopLossPips, takeProfitPips);
            if (result.IsSuccessful)
            {
                _entriesToday++;
                Print("{0}: ordem {1} aberta. Volume={2} unidades ({3:F3} lotes), risco virtual alvo=${4:F2}, SL={5:F1} pips, TP={6:F1} pips. Entrada {7}/{8}.",
                    symbolName, tradeType, volume, symbol.VolumeInUnitsToQuantity(volume), virtualRiskMoney, stopLossPips, takeProfitPips, _entriesToday, MaxEntriesPerDay);
            }
            else
                Print("{0}: ordem não executada: {1}", symbolName, result.Error);
        }

        private bool DailyLossLimitReached()
        {
            if (_dayStartVirtualEquity <= 0)
                return false;

            double floatingBotPnl = 0;
            foreach (Position position in Positions.FindAll(BotLabel))
                floatingBotPnl += position.NetProfit;

            double virtualCurrentEquity = _virtualEquity + floatingBotPnl;
            double lossPercent = ((_dayStartVirtualEquity - virtualCurrentEquity) / _dayStartVirtualEquity) * 100.0;
            if (lossPercent >= DailyLossLimitPercent)
            {
                _dailyStopTriggered = true;
                Print("LIMITE DIÁRIO VIRTUAL ATINGIDO ({0:F2}%). Capital inicial=${1:F2}; valor atual estimado=${2:F2}. Novas entradas bloqueadas.", lossPercent, _dayStartVirtualEquity, virtualCurrentEquity);
                return true;
            }
            return false;
        }

        private void ResetDailyGuardIfNeeded()
        {
            if (Server.Time.Date == _day)
                return;

            _day = Server.Time.Date;
            _dayStartVirtualEquity = _virtualEquity;
            _entriesToday = 0;
            _consecutiveLosses = 0;
            _dailyStopTriggered = false;
            Print("Novo dia. Capital virtual de referência=${0:F2}; contadores diários reiniciados.", _dayStartVirtualEquity);
        }

        private void OnPositionClosed(PositionClosedEventArgs args)
        {
            Position position = args.Position;
            if (position.Label != BotLabel)
                return;

            _virtualEquity += position.NetProfit;
            if (position.NetProfit < 0)
                _consecutiveLosses++;
            else if (position.NetProfit > 0)
                _consecutiveLosses = 0;

            Print("Fechamento {0}: resultado líquido ${1:F2}; capital virtual=${2:F2}; perdas consecutivas={3}.",
                position.SymbolName, position.NetProfit, _virtualEquity, _consecutiveLosses);
        }

        protected override void OnStop()
        {
            Positions.Closed -= OnPositionClosed;
            Timer.Stop();
            Print("Scanner multiativos parado. Posições abertas não são fechadas automaticamente.");
        }
    }
}