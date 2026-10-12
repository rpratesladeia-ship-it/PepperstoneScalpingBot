// PepperstoneScalpingBot.cs
// Código-fonte inicial para um cBot próprio do cTrader.
// ATENÇÃO: arquivo-fonte ainda NÃO compilado nem testado no cTrader.
// Use primeiro em conta DEMO e faça backtest antes de qualquer uso real.

using System;
using cAlgo.API;
using cAlgo.API.Indicators;
using cAlgo.API.Internals;

namespace cAlgo.Robots
{
    [Robot(TimeZone = TimeZones.UTC, AccessRights = AccessRights.None)]
    public class PepperstoneScalpingBot : Robot
    {
        [Parameter("Risco por operação (%)", DefaultValue = 0.5, MinValue = 0.1, MaxValue = 1.0)]
        public double RiskPercent { get; set; }

        [Parameter("Limite de perda diária (%)", DefaultValue = 2.0, MinValue = 0.5, MaxValue = 2.0)]
        public double DailyLossLimitPercent { get; set; }

        [Parameter("EMA rápida", DefaultValue = 9, MinValue = 2)]
        public int FastEmaPeriod { get; set; }

        [Parameter("EMA lenta", DefaultValue = 21, MinValue = 3)]
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

        [Parameter("Stop ATR multiplicador", DefaultValue = 2.0, MinValue = 0.5)]
        public double StopAtrMultiplier { get; set; }

        [Parameter("Alvo ATR multiplicador", DefaultValue = 3.0, MinValue = 0.5)]
        public double TakeProfitAtrMultiplier { get; set; }

        [Parameter("Spread máximo (pips)", DefaultValue = 1.5, MinValue = 0.1)]
        public double MaxSpreadPips { get; set; }

        [Parameter("Etiqueta", DefaultValue = "PepperstoneScalpingBot")]
        public string BotLabel { get; set; }

        private ExponentialMovingAverage _fastEma;
        private ExponentialMovingAverage _slowEma;
        private RelativeStrengthIndex _rsi;
        private AverageTrueRange _atr;

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

            _fastEma = Indicators.ExponentialMovingAverage(Bars.ClosePrices, FastEmaPeriod);
            _slowEma = Indicators.ExponentialMovingAverage(Bars.ClosePrices, SlowEmaPeriod);
            _rsi = Indicators.RelativeStrengthIndex(Bars.ClosePrices, RsiPeriod);
            _atr = Indicators.AverageTrueRange(AtrPeriod, MovingAverageType.Exponential);

            _day = Server.Time.Date;
            _dayStartEquity = Account.Equity;
            _dailyStopTriggered = false;

            Print("Bot iniciado em {0}, timeframe {1}. Confirme que a conta é DEMO.", SymbolName, TimeFrame);
            Print("Este cBot não usa Martingale e permite no máximo uma posição própria por símbolo.");
        }

        protected override void OnBar()
        {
            ResetDailyGuardIfNeeded();

            if (_dailyStopTriggered || DailyLossLimitReached())
                return;

            if (Bars.Count < Math.Max(SlowEmaPeriod, AtrPeriod) + 3)
                return;

            if (Symbol.Spread / Symbol.PipSize > MaxSpreadPips)
                return;

            if (Positions.FindAll(BotLabel, SymbolName).Length > 0)
                return;

            double fastNow = _fastEma.Result.Last(1);
            double fastPrevious = _fastEma.Result.Last(2);
            double slowNow = _slowEma.Result.Last(1);
            double slowPrevious = _slowEma.Result.Last(2);
            double rsi = _rsi.Result.Last(1);
            double atrPips = _atr.Result.Last(1) / Symbol.PipSize;

            if (atrPips <= 0)
                return;

            bool bullishCross = fastPrevious <= slowPrevious && fastNow > slowNow;
            bool bearishCross = fastPrevious >= slowPrevious && fastNow < slowNow;

            double stopLossPips = atrPips * StopAtrMultiplier;
            double takeProfitPips = atrPips * TakeProfitAtrMultiplier;

            if (bullishCross && rsi >= BuyRsiMin && rsi <= BuyRsiMax)
                OpenPosition(TradeType.Buy, stopLossPips, takeProfitPips);

            else if (bearishCross && rsi >= SellRsiMin && rsi <= SellRsiMax)
                OpenPosition(TradeType.Sell, stopLossPips, takeProfitPips);
        }

        private void OpenPosition(TradeType tradeType, double stopLossPips, double takeProfitPips)
        {
            // Estimativa de volume baseada no risco monetário e no valor do pip.
            // Deve ser validada no backtest para o símbolo e as condições da corretora.
            double riskMoney = Account.Equity * (RiskPercent / 100.0);
            double lots = riskMoney / (stopLossPips * Symbol.PipValue);

            if (double.IsNaN(lots) || double.IsInfinity(lots) || lots <= 0)
                return;

            double volume = Symbol.QuantityToVolumeInUnits(lots);
            volume = Symbol.NormalizeVolumeInUnits(volume, RoundingMode.Down);

            if (volume < Symbol.VolumeInUnitsMin)
            {
                Print("Sinal ignorado: volume calculado menor que o mínimo permitido.");
                return;
            }

            if (volume > Symbol.VolumeInUnitsMax)
                volume = Symbol.NormalizeVolumeInUnits(Symbol.VolumeInUnitsMax, RoundingMode.Down);

            var result = ExecuteMarketOrder(
                tradeType,
                SymbolName,
                volume,
                BotLabel,
                stopLossPips,
                takeProfitPips
            );

            if (result.IsSuccessful)
                Print("{0} aberto. Volume={1}, SL={2:F1} pips, TP={3:F1} pips",
                    tradeType, volume, stopLossPips, takeProfitPips);
            else
                Print("Ordem não executada: {0}", result.Error);
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
    }
}
