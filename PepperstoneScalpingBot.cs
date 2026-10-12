// PepperstoneScalpingBot.cs (v2)
// cBot para cTrader. Estratégia: cruzamento de EMAs a favor da tendência do H1,
// com filtros de sessão, volatilidade, força de tendência (ADX) e spread.
// ATENÇÃO: use SOMENTE em conta DEMO e faça backtest antes. Sem garantia de lucro.
// Pensado para pares de forex (EURUSD, GBPUSD, USDJPY, AUDUSD...). Não use em índices/cripto.

using System;
using cAlgo.API;
using cAlgo.API.Indicators;
using cAlgo.API.Internals;

namespace cAlgo.Robots
{
    [Robot(TimeZone = TimeZones.UTC, AccessRights = AccessRights.None)]
    public class PepperstoneScalpingBot : Robot
    {
        // ---------- Risco ----------
        [Parameter("Risco por operação (%)", Group = "Risco", DefaultValue = 0.25, MinValue = 0.05, MaxValue = 1.0)]
        public double RiskPercent { get; set; }

        [Parameter("Limite máximo por ordem (lotes)", Group = "Risco", DefaultValue = 0.10, MinValue = 0.01, MaxValue = 1.0)]
        public double MaxLotsPerTrade { get; set; }

        [Parameter("Limite de perda diária (%)", Group = "Risco", DefaultValue = 1.5, MinValue = 0.5, MaxValue = 2.0)]
        public double DailyLossLimitPercent { get; set; }

        [Parameter("Máx. operações por dia", Group = "Risco", DefaultValue = 4, MinValue = 1, MaxValue = 20)]
        public int MaxTradesPerDay { get; set; }

        [Parameter("Parar após X perdas seguidas (no dia)", Group = "Risco", DefaultValue = 2, MinValue = 1, MaxValue = 10)]
        public int MaxConsecutiveLosses { get; set; }

        // ---------- Sinal ----------
        [Parameter("EMA rápida", Group = "Sinal", DefaultValue = 9, MinValue = 2)]
        public int FastEmaPeriod { get; set; }

        [Parameter("EMA lenta", Group = "Sinal", DefaultValue = 21, MinValue = 3)]
        public int SlowEmaPeriod { get; set; }

        [Parameter("RSI período", Group = "Sinal", DefaultValue = 14, MinValue = 2)]
        public int RsiPeriod { get; set; }

        [Parameter("RSI mínimo compra", Group = "Sinal", DefaultValue = 50)]
        public double BuyRsiMin { get; set; }

        [Parameter("RSI máximo compra", Group = "Sinal", DefaultValue = 68)]
        public double BuyRsiMax { get; set; }

        [Parameter("RSI mínimo venda", Group = "Sinal", DefaultValue = 32)]
        public double SellRsiMin { get; set; }

        [Parameter("RSI máximo venda", Group = "Sinal", DefaultValue = 50)]
        public double SellRsiMax { get; set; }

        // ---------- Filtros ----------
        [Parameter("EMA de tendência (H1)", Group = "Filtros", DefaultValue = 200, MinValue = 20)]
        public int TrendEmaPeriod { get; set; }

        [Parameter("ADX período", Group = "Filtros", DefaultValue = 14, MinValue = 5)]
        public int AdxPeriod { get; set; }

        [Parameter("ADX mínimo", Group = "Filtros", DefaultValue = 20, MinValue = 5)]
        public double MinAdx { get; set; }

        [Parameter("Hora inicial UTC", Group = "Filtros", DefaultValue = 7, MinValue = 0, MaxValue = 23)]
        public int StartHourUtc { get; set; }

        [Parameter("Hora final UTC", Group = "Filtros", DefaultValue = 16, MinValue = 1, MaxValue = 24)]
        public int EndHourUtc { get; set; }

        [Parameter("ATR mínimo (pips)", Group = "Filtros", DefaultValue = 3.0, MinValue = 0.5)]
        public double MinAtrPips { get; set; }

        [Parameter("Spread máx. (pips)", Group = "Filtros", DefaultValue = 1.2, MinValue = 0.1)]
        public double MaxSpreadPips { get; set; }

        [Parameter("Spread máx. como fração do stop", Group = "Filtros", DefaultValue = 0.15, MinValue = 0.02, MaxValue = 0.5)]
        public double MaxSpreadToStop { get; set; }

        // ---------- Saída ----------
        [Parameter("ATR período", Group = "Saída", DefaultValue = 14, MinValue = 2)]
        public int AtrPeriod { get; set; }

        [Parameter("Stop ATR multiplicador", Group = "Saída", DefaultValue = 1.5, MinValue = 0.5)]
        public double StopAtrMultiplier { get; set; }

        [Parameter("Alvo ATR multiplicador", Group = "Saída", DefaultValue = 2.25, MinValue = 0.5)]
        public double TakeProfitAtrMultiplier { get; set; }

        [Parameter("Breakeven ao atingir (x stop)", Group = "Saída", DefaultValue = 0.8, MinValue = 0.2, MaxValue = 2.0)]
        public double BreakEvenTriggerR { get; set; }

        [Parameter("Etiqueta", DefaultValue = "PepperstoneScalpingBot")]
        public string BotLabel { get; set; }

        private ExponentialMovingAverage _fastEma;
        private ExponentialMovingAverage _slowEma;
        private ExponentialMovingAverage _trendEma;
        private RelativeStrengthIndex _rsi;
        private AverageTrueRange _atr;
        private DirectionalMovementSystem _adx;
        private Bars _trendBars;

        private DateTime _day;
        private double _dayStartEquity;
        private bool _dailyStopTriggered;
        private int _tradesToday;
        private int _consecutiveLosses;

        protected override void OnStart()
        {
            if (FastEmaPeriod >= SlowEmaPeriod)
            {
                Print("ERRO: a EMA rápida precisa ser menor que a EMA lenta.");
                Stop();
                return;
            }

            if (StartHourUtc >= EndHourUtc)
            {
                Print("ERRO: hora inicial UTC precisa ser menor que a hora final UTC.");
                Stop();
                return;
            }

            _trendBars = MarketData.GetBars(TimeFrame.Hour);
            _fastEma = Indicators.ExponentialMovingAverage(Bars.ClosePrices, FastEmaPeriod);
            _slowEma = Indicators.ExponentialMovingAverage(Bars.ClosePrices, SlowEmaPeriod);
            _trendEma = Indicators.ExponentialMovingAverage(_trendBars.ClosePrices, TrendEmaPeriod);
            _rsi = Indicators.RelativeStrengthIndex(Bars.ClosePrices, RsiPeriod);
            _atr = Indicators.AverageTrueRange(AtrPeriod, MovingAverageType.Exponential);
            _adx = Indicators.DirectionalMovementSystem(AdxPeriod);

            _day = Server.Time.Date;
            _dayStartEquity = Account.Equity;
            _dailyStopTriggered = false;
            _tradesToday = 0;
            _consecutiveLosses = 0;

            Positions.Closed += OnPositionClosed;

            Print("Bot v2 iniciado em {0}, timeframe {1}. Confirme que a conta é DEMO.", SymbolName, TimeFrame);
            Print("Risco {0:F2}% por operação; teto {1:F2} lote(s); máximo {2} operações/dia; pare após {3} perdas seguidas.",
                RiskPercent, MaxLotsPerTrade, MaxTradesPerDay, MaxConsecutiveLosses);
        }

        protected override void OnTick()
        {
            ManageBreakEven();
        }

        protected override void OnBar()
        {
            ResetDailyGuardIfNeeded();

            if (_dailyStopTriggered || DailyLossLimitReached())
                return;

            if (_tradesToday >= MaxTradesPerDay || _consecutiveLosses >= MaxConsecutiveLosses)
                return;

            if (Bars.Count < Math.Max(SlowEmaPeriod, AtrPeriod) + 3 || _trendBars.Count < TrendEmaPeriod + 2)
                return;

            int hour = Server.TimeInUtc.Hour;
            if (hour < StartHourUtc || hour >= EndHourUtc)
                return;

            if (Positions.FindAll(BotLabel, SymbolName).Length > 0)
                return;

            double spreadPips = Symbol.Spread / Symbol.PipSize;
            if (spreadPips > MaxSpreadPips)
                return;

            double atrPips = _atr.Result.Last(1) / Symbol.PipSize;
            if (atrPips < MinAtrPips)
                return;

            double stopLossPips = atrPips * StopAtrMultiplier;
            double takeProfitPips = atrPips * TakeProfitAtrMultiplier;

            if (stopLossPips <= 0 || spreadPips > stopLossPips * MaxSpreadToStop)
                return;

            if (_adx.ADX.Last(1) < MinAdx)
                return;

            double fastNow = _fastEma.Result.Last(1);
            double fastPrevious = _fastEma.Result.Last(2);
            double slowNow = _slowEma.Result.Last(1);
            double slowPrevious = _slowEma.Result.Last(2);
            double rsi = _rsi.Result.Last(1);

            double price = Bars.ClosePrices.Last(1);
            double trendEma = _trendEma.Result.Last(1);

            bool bullishCross = fastPrevious <= slowPrevious && fastNow > slowNow;
            bool bearishCross = fastPrevious >= slowPrevious && fastNow < slowNow;

            bool uptrend = price > trendEma;
            bool downtrend = price < trendEma;

            if (bullishCross && uptrend && rsi >= BuyRsiMin && rsi <= BuyRsiMax)
                OpenPosition(TradeType.Buy, stopLossPips, takeProfitPips);
            else if (bearishCross && downtrend && rsi >= SellRsiMin && rsi <= SellRsiMax)
                OpenPosition(TradeType.Sell, stopLossPips, takeProfitPips);
        }

        private void OpenPosition(TradeType tradeType, double stopLossPips, double takeProfitPips)
        {
            double unitsByRisk = Symbol.VolumeForProportionalRisk(
                ProportionalAmountType.Equity, RiskPercent, stopLossPips, RoundingMode.Down);
            double maxUnits = Symbol.QuantityToVolumeInUnits(MaxLotsPerTrade);

            if (double.IsNaN(unitsByRisk) || double.IsInfinity(unitsByRisk) || unitsByRisk <= 0 ||
                double.IsNaN(maxUnits) || double.IsInfinity(maxUnits) || maxUnits <= 0)
            {
                Print("Sinal ignorado: volume calculado inválido; ordem cancelada por segurança.");
                return;
            }

            double volume = Symbol.NormalizeVolumeInUnits(Math.Min(unitsByRisk, maxUnits), RoundingMode.Down);

            if (volume < Symbol.VolumeInUnitsMin)
            {
                Print("Sinal ignorado: volume calculado menor que o mínimo permitido.");
                return;
            }

            if (volume > Symbol.VolumeInUnitsMax)
                volume = Symbol.NormalizeVolumeInUnits(Symbol.VolumeInUnitsMax, RoundingMode.Down);

            Print("Volume calculado={0} unidades ({1:F2} lote(s)); teto por ordem={2:F2} lote(s).",
                volume, Symbol.VolumeInUnitsToQuantity(volume), MaxLotsPerTrade);

            var result = ExecuteMarketOrder(tradeType, SymbolName, volume, BotLabel, stopLossPips, takeProfitPips);

            if (result.IsSuccessful)
            {
                _tradesToday++;
                Print("{0} aberto. Volume={1} unidades ({2:F2} lotes), SL={3:F1} pips, TP={4:F1} pips",
                    tradeType, volume, Symbol.VolumeInUnitsToQuantity(volume), stopLossPips, takeProfitPips);
            }
            else
                Print("Ordem não executada: {0}", result.Error);
        }

        private void ManageBreakEven()
        {
            foreach (var position in Positions.FindAll(BotLabel, SymbolName))
            {
                if (position.StopLoss == null)
                    continue;

                double riskPips = Math.Abs(position.EntryPrice - position.StopLoss.Value) / Symbol.PipSize;
                if (riskPips <= 0)
                    continue;

                bool stillBelowEntry = position.TradeType == TradeType.Buy
                    ? position.StopLoss.Value < position.EntryPrice
                    : position.StopLoss.Value > position.EntryPrice;

                if (!stillBelowEntry)
                    continue;

                if (position.Pips >= riskPips * BreakEvenTriggerR)
                {
                    double buffer = Symbol.PipSize * 0.5;
                    double newStop = position.TradeType == TradeType.Buy
                        ? position.EntryPrice + buffer
                        : position.EntryPrice - buffer;

                    var modifyResult = ModifyPosition(position, newStop, position.TakeProfit);
                    if (!modifyResult.IsSuccessful)
                        Print("Não foi possível mover o stop para breakeven na posição {0}: {1}", position.Id, modifyResult.Error);
                    else
                        Print("Breakeven ajustado na posição {0}. Novo stop={1}", position.Id, newStop);
                }
            }
        }

        private void OnPositionClosed(PositionClosedEventArgs args)
        {
            var position = args.Position;
            if (position.Label != BotLabel || position.SymbolName != SymbolName)
                return;

            if (position.NetProfit < 0)
                _consecutiveLosses++;
            else
                _consecutiveLosses = 0;

            Print("Posição encerrada. Resultado líquido={0:F2}; perdas consecutivas hoje={1}.", position.NetProfit, _consecutiveLosses);
        }

        private bool DailyLossLimitReached()
        {
            if (_dayStartEquity <= 0)
                return false;

            double lossPercent = ((_dayStartEquity - Account.Equity) / _dayStartEquity) * 100.0;

            if (lossPercent >= DailyLossLimitPercent)
            {
                _dailyStopTriggered = true;
                Print("LIMITE DIÁRIO ATINGIDO ({0:F2}%). Nenhuma nova entrada hoje.", lossPercent);
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
            _tradesToday = 0;
            _consecutiveLosses = 0;
            Print("Novo dia. Contadores diários reiniciados.");
        }

        protected override void OnStop()
        {
            Positions.Closed -= OnPositionClosed;
            Print("Bot v2 parado. Posições abertas não são fechadas automaticamente.");
        }
    }
}