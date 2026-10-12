// PepperstoneScalpingBot.cs
// Scanner multiativos experimental para cTrader Automate.
// Testar somente em conta DEMO; compilação não substitui backtest e validação de risco.

using System;
using System.Collections.Generic;
using cAlgo.API;
using cAlgo.API.Indicators;
using cAlgo.API.Internals;

namespace cAlgo.Robots
{
    [Robot(TimeZone = TimeZones.UTC, AccessRights = AccessRights.None)]
    public class PepperstoneScalpingBot : Robot
    {
        [Parameter("Símbolos (separados por vírgula)", DefaultValue = "EURUSD,GBPUSD,USDJPY,AUDUSD,USDCAD,USDCHF,NZDUSD")]
        public string SymbolsToScan { get; set; }

        [Parameter("Período de sinal", DefaultValue = "Minute")]
        public TimeFrame SignalTimeFrame { get; set; }

        [Parameter("Intervalo de varredura (segundos)", DefaultValue = 15, MinValue = 5, MaxValue = 300)]
        public int ScanIntervalSeconds { get; set; }

        [Parameter("Máximo de posições simultâneas", DefaultValue = 3, MinValue = 1, MaxValue = 10)]
        public int MaxOpenPositions { get; set; }

        [Parameter("Risco por operação (%)", DefaultValue = 0.5, MinValue = 0.1, MaxValue = 1.0)]
        public double RiskPercent { get; set; }

        [Parameter("Limite máximo por ordem (lotes)", DefaultValue = 0.10, MinValue = 0.01, MaxValue = 1.0)]
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
        private double _dayStartEquity;
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

            _day = Server.Time.Date;
            _dayStartEquity = Account.Equity;
            _dailyStopTriggered = false;
            Timer.Start(ScanIntervalSeconds);
            Print("Scanner multiativos iniciado: {0} símbolos; máximo {1} posições; risco {2:F2}% por operação. Confirme que a conta é DEMO.",
                _states.Count, MaxOpenPositions, RiskPercent);
            Print("O limite diário bloqueia novas entradas, mas não fecha posições abertas nem garante perda máxima.");
        }

        protected override void OnTimer()
        {
            ResetDailyGuardIfNeeded();
            if (_dailyStopTriggered || DailyLossLimitReached())
                return;

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
            double unitsByRisk = symbol.VolumeForProportionalRisk(
                ProportionalAmountType.Equity, RiskPercent, stopLossPips, RoundingMode.Down);
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
                Print("{0}: ordem {1} aberta. Volume={2} unidades ({3:F2} lotes), SL={4:F1} pips, TP={5:F1} pips, RSI={6:F1}.",
                    symbolName, tradeType, volume, symbol.VolumeInUnitsToQuantity(volume), stopLossPips, takeProfitPips, _states[symbolName].Rsi.Result.Last(1));
            else
                Print("{0}: ordem não executada: {1}", symbolName, result.Error);
        }

        private bool DailyLossLimitReached()
        {
            if (_dayStartEquity <= 0)
                return false;

            double lossPercent = ((_dayStartEquity - Account.Equity) / _dayStartEquity) * 100.0;
            if (lossPercent >= DailyLossLimitPercent)
            {
                _dailyStopTriggered = true;
                Print("LIMITE DIÁRIO ATINGIDO ({0:F2}%). Nenhuma nova entrada será aberta hoje.", lossPercent);
                return true;
            }
            return false;
        }

        private void ResetDailyGuardIfNeeded()
        {
            if (Server.Time.Date == _day)
                return;

            _day = Server.Time.Date;
            _dayStartEquity = Account.Equity;
            _dailyStopTriggered = false;
            Print("Novo dia. Referência de equity diária reiniciada.");
        }

        protected override void OnStop()
        {
            Timer.Stop();
            Print("Scanner multiativos parado. Posições abertas não são fechadas automaticamente.");
        }
    }
}