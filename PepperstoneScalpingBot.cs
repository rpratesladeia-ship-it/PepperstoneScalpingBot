// PepperstoneScalpingBot.cs  (v4 - Compra na queda dentro da alta, posições de horas)
// Lógica: o H1 está em ALTA -> o preço sofre uma queda rápida -> aparece reversão -> COMPRA.
// A posição é mantida por horas, com stop, alvo, trailing e tempo máximo.
// Só compra (não vende). Sem martingale, sem aumentar posição perdedora.
// USE SOMENTE EM CONTA DEMO. Nenhum robô garante lucro. Faça backtest antes.
// Recomendado: GBPUSD, EURUSD, AUDUSD, NZDUSD em M15.

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
        [Parameter("Risco por operação (%)", Group = "Risco", DefaultValue = 0.5, MinValue = 0.05, MaxValue = 2.0)]
        public double RiskPercent { get; set; }

        [Parameter("Limite de perda diária (%)", Group = "Risco", DefaultValue = 2.0, MinValue = 0.5, MaxValue = 5.0)]
        public double DailyLossLimitPercent { get; set; }

        [Parameter("Máx. operações por dia", Group = "Risco", DefaultValue = 2, MinValue = 1, MaxValue = 10)]
        public int MaxTradesPerDay { get; set; }

        [Parameter("Parar após X perdas seguidas (no dia)", Group = "Risco", DefaultValue = 2, MinValue = 1, MaxValue = 10)]
        public int MaxConsecutiveLosses { get; set; }

        // ---------- Tendência de alta (H1) ----------
        [Parameter("EMA curta (H1)", Group = "Tendência", DefaultValue = 50, MinValue = 10)]
        public int HtfFastPeriod { get; set; }

        [Parameter("EMA longa (H1)", Group = "Tendência", DefaultValue = 200, MinValue = 50)]
        public int HtfSlowPeriod { get; set; }

        // ---------- Queda repentina ----------
        [Parameter("Janela da queda (barras)", Group = "Queda", DefaultValue = 8, MinValue = 3, MaxValue = 40)]
        public int DropBars { get; set; }

        [Parameter("Queda mínima (x ATR)", Group = "Queda", DefaultValue = 2.0, MinValue = 0.8, MaxValue = 8.0)]
        public double DropAtrMultiplier { get; set; }

        [Parameter("RSI período", Group = "Queda", DefaultValue = 14, MinValue = 2)]
        public int RsiPeriod { get; set; }

        [Parameter("RSI deve ter ficado abaixo de", Group = "Queda", DefaultValue = 40, MinValue = 15, MaxValue = 50)]
        public double RsiOversold { get; set; }

        // ---------- Reversão ----------
        [Parameter("Corpo mínimo do candle de reversão (x ATR)", Group = "Reversão", DefaultValue = 0.3, MinValue = 0.0, MaxValue = 2.0)]
        public double ReversalBodyAtr { get; set; }

        // ---------- Filtros ----------
        [Parameter("Hora inicial UTC", Group = "Filtros", DefaultValue = 6, MinValue = 0, MaxValue = 23)]
        public int StartHourUtc { get; set; }

        [Parameter("Hora final UTC", Group = "Filtros", DefaultValue = 20, MinValue = 1, MaxValue = 24)]
        public int EndHourUtc { get; set; }

        [Parameter("Spread máx. (pips)", Group = "Filtros", DefaultValue = 1.5, MinValue = 0.1)]
        public double MaxSpreadPips { get; set; }

        [Parameter("Spread máx. como fração do stop", Group = "Filtros", DefaultValue = 0.1, MinValue = 0.02, MaxValue = 0.5)]
        public double MaxSpreadToStop { get; set; }

        // ---------- Saída ----------
        [Parameter("ATR período", Group = "Saída", DefaultValue = 14, MinValue = 2)]
        public int AtrPeriod { get; set; }

        [Parameter("Folga do stop abaixo do fundo (x ATR)", Group = "Saída", DefaultValue = 0.3, MinValue = 0.0, MaxValue = 1.5)]
        public double StopBufferAtr { get; set; }

        [Parameter("Stop mínimo (x ATR)", Group = "Saída", DefaultValue = 1.0, MinValue = 0.3)]
        public double MinStopAtr { get; set; }

        [Parameter("Stop máximo (x ATR)", Group = "Saída", DefaultValue = 3.5, MinValue = 1.0)]
        public double MaxStopAtr { get; set; }

        [Parameter("Alvo (x o stop)", Group = "Saída", DefaultValue = 2.0, MinValue = 1.0, MaxValue = 6.0)]
        public double RewardRisk { get; set; }

        [Parameter("Trailing começa em (x ATR de lucro)", Group = "Saída", DefaultValue = 1.5, MinValue = 0.5)]
        public double TrailStartAtr { get; set; }

        [Parameter("Distância do trailing (x ATR)", Group = "Saída", DefaultValue = 1.5, MinValue = 0.5)]
        public double TrailDistanceAtr { get; set; }

        [Parameter("Tempo máximo da operação (horas)", Group = "Saída", DefaultValue = 12, MinValue = 1, MaxValue = 72)]
        public int MaxHoldHours { get; set; }

        [Parameter("Etiqueta", DefaultValue = "PepperstoneScalpingBot")]
        public string BotLabel { get; set; }

        private ExponentialMovingAverage _htfFast;
        private ExponentialMovingAverage _htfSlow;
        private RelativeStrengthIndex _rsi;
        private AverageTrueRange _atr;
        private Bars _htfBars;

        private DateTime _day;
        private double _dayStartEquity;
        private bool _dailyStopTriggered;
        private int _tradesToday;
        private int _consecutiveLosses;

        protected override void OnStart()
        {
            _htfBars = MarketData.GetBars(TimeFrame.Hour);

            _htfFast = Indicators.ExponentialMovingAverage(_htfBars.ClosePrices, HtfFastPeriod);
            _htfSlow = Indicators.ExponentialMovingAverage(_htfBars.ClosePrices, HtfSlowPeriod);
            _rsi = Indicators.RelativeStrengthIndex(Bars.ClosePrices, RsiPeriod);
            _atr = Indicators.AverageTrueRange(AtrPeriod, MovingAverageType.Exponential);

            _day = Server.Time.Date;
            _dayStartEquity = Account.Equity;
            _dailyStopTriggered = false;
            _tradesToday = 0;
            _consecutiveLosses = 0;

            Positions.Closed += OnPositionClosed;

            Print("Bot v4 (compra na queda) iniciado em {0}, {1}. Confirme que a conta é DEMO.", SymbolName, TimeFrame);
        }

        protected override void OnBar()
        {
            ResetDailyGuardIfNeeded();

            if (Bars.Count < Math.Max(AtrPeriod, DropBars) + 6 || _htfBars.Count < HtfSlowPeriod + 5)
                return;

            double atr = _atr.Result.Last(1);
            if (atr <= 0)
                return;

            ManagePositions(atr);

            if (_dailyStopTriggered || DailyLossLimitReached())
                return;

            if (_tradesToday >= MaxTradesPerDay || _consecutiveLosses >= MaxConsecutiveLosses)
                return;

            int hour = Server.TimeInUtc.Hour;
            if (hour < StartHourUtc || hour >= EndHourUtc)
                return;

            if (Positions.FindAll(BotLabel, SymbolName).Length > 0)
                return;

            double spreadPips = Symbol.Spread / Symbol.PipSize;
            if (spreadPips > MaxSpreadPips)
                return;

            // 1) Tendência de ALTA no H1.
            double htfFast = _htfFast.Result.Last(1);
            double htfSlow = _htfSlow.Result.Last(1);
            double htfPrice = _htfBars.ClosePrices.Last(1);
            bool htfUp = htfFast > htfSlow && htfPrice > htfSlow;
            if (!htfUp)
                return;

            // 2) Queda repentina: topo mais antigo, fundo recente, tamanho >= X ATR.
            double highestHigh = double.MinValue;
            double lowestLow = double.MaxValue;
            int highIdx = 0;
            int lowIdx = 0;
            double minRsi = 100;

            for (int i = 1; i <= DropBars; i++)
            {
                double h = Bars.HighPrices.Last(i);
                double l = Bars.LowPrices.Last(i);
                if (h > highestHigh) { highestHigh = h; highIdx = i; }
                if (l < lowestLow) { lowestLow = l; lowIdx = i; }
            }

            for (int i = 1; i <= 5; i++)
                minRsi = Math.Min(minRsi, _rsi.Result.Last(i));

            double drop = highestHigh - lowestLow;
            bool suddenDrop = highIdx > lowIdx && lowIdx <= 5 && drop >= DropAtrMultiplier * atr;
            if (!suddenDrop)
                return;

            if (minRsi > RsiOversold)
                return;

            // 3) Reversão: candle de alta forte que rompe a máxima do anterior, RSI virando para cima.
            double open1 = Bars.OpenPrices.Last(1);
            double close1 = Bars.ClosePrices.Last(1);
            double high2 = Bars.HighPrices.Last(2);
            bool reversal = close1 > open1
                && (close1 - open1) >= ReversalBodyAtr * atr
                && close1 > high2
                && _rsi.Result.Last(1) > _rsi.Result.Last(2);
            if (!reversal)
                return;

            // 4) Fundo da queda não pode ter perdido a EMA longa do H1 (tendência intacta).
            if (lowestLow < htfSlow)
            {
                Print("Setup ignorado: a queda perdeu a EMA longa do H1.");
                return;
            }

            double atrPips = atr / Symbol.PipSize;
            double stopPrice = lowestLow - StopBufferAtr * atr;
            double stopLossPips = (Symbol.Ask - stopPrice) / Symbol.PipSize;

            if (stopLossPips > atrPips * MaxStopAtr)
            {
                Print("Setup ignorado: stop ficaria grande demais ({0:F1} pips).", stopLossPips);
                return;
            }

            if (stopLossPips < atrPips * MinStopAtr)
                stopLossPips = atrPips * MinStopAtr;

            if (spreadPips > stopLossPips * MaxSpreadToStop)
            {
                Print("Setup ignorado: spread alto para este stop ({0:F1} pips).", spreadPips);
                return;
            }

            double takeProfitPips = stopLossPips * RewardRisk;

            Print("SINAL COMPRA: queda de {0:F1} pips ({1:F1}x ATR), RSI mín {2:F0}, H1 em alta | SL={3:F1} TP={4:F1} pips",
                drop / Symbol.PipSize, drop / atr, minRsi, stopLossPips, takeProfitPips);

            OpenBuy(stopLossPips, takeProfitPips);
        }

        private void OpenBuy(double stopLossPips, double takeProfitPips)
        {
            // Volume em UNIDADES = dinheiro arriscado / (stop em pips * valor do pip por unidade).
            double riskMoney = Account.Equity * (RiskPercent / 100.0);
            double units = riskMoney / (stopLossPips * Symbol.PipValue);

            if (double.IsNaN(units) || double.IsInfinity(units) || units <= 0)
                return;

            double volume = Symbol.NormalizeVolumeInUnits(units, RoundingMode.Down);

            if (volume < Symbol.VolumeInUnitsMin)
            {
                Print("Sinal ignorado: volume calculado menor que o mínimo permitido.");
                return;
            }

            if (volume > Symbol.VolumeInUnitsMax)
                volume = Symbol.NormalizeVolumeInUnits(Symbol.VolumeInUnitsMax, RoundingMode.Down);

            var result = ExecuteMarketOrder(TradeType.Buy, SymbolName, volume, BotLabel, stopLossPips, takeProfitPips);

            if (result.IsSuccessful)
            {
                _tradesToday++;
                Print("Compra aberta. Volume={0} unidades ({1:F2} lotes)", volume, volume / 100000.0);
            }
            else
                Print("Ordem não executada: {0}", result.Error);
        }

        private void ManagePositions(double atr)
        {
            double atrPips = atr / Symbol.PipSize;

            foreach (var position in Positions.FindAll(BotLabel, SymbolName))
            {
                // Tempo máximo.
                if ((Server.Time - position.EntryTime).TotalHours >= MaxHoldHours)
                {
                    Print("Tempo máximo atingido. Fechando posição.");
                    ClosePosition(position);
                    continue;
                }

                // Trailing: só depois de lucro mínimo; nunca recua o stop.
                if (position.Pips >= atrPips * TrailStartAtr)
                {
                    double newStop = Symbol.Bid - TrailDistanceAtr * atr;
                    double minStop = position.EntryPrice + Symbol.PipSize * 0.5;
                    if (newStop < minStop)
                        newStop = minStop;

                    if (position.StopLoss == null || newStop > position.StopLoss.Value + Symbol.PipSize * 0.2)
                        ModifyPosition(position, newStop, position.TakeProfit);
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
    }
}