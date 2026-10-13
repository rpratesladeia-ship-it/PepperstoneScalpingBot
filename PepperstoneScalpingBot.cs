// V5 - Multiativos: compra em correção dentro de tendência de alta.
// Instale em um gráfico M15. Use DEMO e faça backtest antes de operar ao vivo.
using System;
using System.Collections.Generic;
using cAlgo.API;
using cAlgo.API.Indicators;

namespace cAlgo.Robots
{
    [Robot(TimeZone = TimeZones.UTC, AccessRights = AccessRights.None)]
    public class PepperstoneScalpingBot : Robot
    {
        [Parameter("Ativos separados por vírgula", Group = "Ativos", DefaultValue = "GBPUSD,EURUSD,AUDUSD,NZDUSD,XAUUSD")]
        public string SymbolList { get; set; }
        [Parameter("Máx. posições abertas", Group = "Risco", DefaultValue = 3, MinValue = 1, MaxValue = 10)]
        public int MaxOpenPositions { get; set; }
        [Parameter("Risco por operação (%)", Group = "Risco", DefaultValue = 0.25, MinValue = 0.05, MaxValue = 1.0)]
        public double RiskPercent { get; set; }
        [Parameter("Perda diária máxima (%)", Group = "Risco", DefaultValue = 2.0, MinValue = 0.5, MaxValue = 5.0)]
        public double DailyLossLimitPercent { get; set; }
        [Parameter("Máx. entradas por dia", Group = "Risco", DefaultValue = 4, MinValue = 1, MaxValue = 20)]
        public int MaxTradesPerDay { get; set; }
        [Parameter("Máx. perdas seguidas", Group = "Risco", DefaultValue = 2, MinValue = 1, MaxValue = 8)]
        public int MaxConsecutiveLosses { get; set; }
        [Parameter("Teto por ordem (lotes)", Group = "Risco", DefaultValue = 0.10, MinValue = 0.01, MaxValue = 1.0)]
        public double MaxLotsPerTrade { get; set; }
        [Parameter("EMA H1 curta", Group = "Tendência", DefaultValue = 50, MinValue = 10)]
        public int FastEma { get; set; }
        [Parameter("EMA H1 longa", Group = "Tendência", DefaultValue = 200, MinValue = 50)]
        public int SlowEma { get; set; }
        [Parameter("Janela de queda (candles)", Group = "Entrada", DefaultValue = 12, MinValue = 3, MaxValue = 40)]
        public int DropBars { get; set; }
        [Parameter("Queda mínima (x ATR)", Group = "Entrada", DefaultValue = 1.5, MinValue = 0.8, MaxValue = 8)]
        public double DropAtr { get; set; }
        [Parameter("RSI período", Group = "Entrada", DefaultValue = 14, MinValue = 2)]
        public int RsiPeriod { get; set; }
        [Parameter("RSI sobrevendido", Group = "Entrada", DefaultValue = 45, MinValue = 15, MaxValue = 50)]
        public double RsiLow { get; set; }
        [Parameter("Hora inicial UTC", Group = "Filtro", DefaultValue = 7, MinValue = 0, MaxValue = 23)]
        public int StartHour { get; set; }
        [Parameter("Hora final UTC", Group = "Filtro", DefaultValue = 20, MinValue = 1, MaxValue = 24)]
        public int EndHour { get; set; }
        [Parameter("Spread máximo / stop", Group = "Filtro", DefaultValue = 0.10, MinValue = 0.02, MaxValue = 0.5)]
        public double MaxSpreadToStop { get; set; }
        [Parameter("ATR período", Group = "Saída", DefaultValue = 14, MinValue = 2)]
        public int AtrPeriod { get; set; }
        [Parameter("Folga stop (x ATR)", Group = "Saída", DefaultValue = 0.3, MinValue = 0, MaxValue = 1.5)]
        public double StopBufferAtr { get; set; }
        [Parameter("Stop mínimo (x ATR)", Group = "Saída", DefaultValue = 1.0, MinValue = 0.3)]
        public double MinStopAtr { get; set; }
        [Parameter("Stop máximo (x ATR)", Group = "Saída", DefaultValue = 3.5, MinValue = 1)]
        public double MaxStopAtr { get; set; }
        [Parameter("Alvo (R)", Group = "Saída", DefaultValue = 2.0, MinValue = 1, MaxValue = 6)]
        public double RewardRisk { get; set; }
        [Parameter("Trailing começa (x ATR)", Group = "Saída", DefaultValue = 1.5, MinValue = 0.5)]
        public double TrailStartAtr { get; set; }
        [Parameter("Trailing distância (x ATR)", Group = "Saída", DefaultValue = 1.5, MinValue = 0.5)]
        public double TrailDistanceAtr { get; set; }
        [Parameter("Tempo máximo (horas)", Group = "Saída", DefaultValue = 12, MinValue = 1, MaxValue = 72)]
        public int MaxHoldHours { get; set; }
        [Parameter("Etiqueta", DefaultValue = "PepperstoneScalpingBot")]
        public string BotLabel { get; set; }

        private class Ctx
        {
            public Symbol Symbol;
            public Bars Bars, H1;
            public ExponentialMovingAverage Fast, Slow;
            public RelativeStrengthIndex Rsi;
            public AverageTrueRange Atr;
        }
        private readonly Dictionary<string, Ctx> assets = new Dictionary<string, Ctx>();
        private DateTime day;
        private double dayStartEquity;
        private int tradesToday, lossesInRow;
        private bool dailyStopped;

        protected override void OnStart()
        {
            foreach (string raw in (SymbolList ?? "").Split(new[] { ',', ';', ' ' }, StringSplitOptions.RemoveEmptyEntries))
            {
                string name = raw.Trim();
                if (assets.ContainsKey(name)) continue;
                Symbol sym = Symbols.GetSymbol(name);
                if (sym == null) { Print("Ativo não encontrado e ignorado: {0}", name); continue; }
                var c = new Ctx { Symbol = sym, Bars = MarketData.GetBars(TimeFrame, name), H1 = MarketData.GetBars(TimeFrame.Hour, name) };
                c.Fast = Indicators.ExponentialMovingAverage(c.H1.ClosePrices, FastEma);
                c.Slow = Indicators.ExponentialMovingAverage(c.H1.ClosePrices, SlowEma);
                c.Rsi = Indicators.RelativeStrengthIndex(c.Bars.ClosePrices, RsiPeriod);
                c.Atr = Indicators.AverageTrueRange(c.Bars, AtrPeriod, MovingAverageType.Exponential);
                assets[name] = c;
            }
            day = Server.Time.Date; dayStartEquity = Account.Equity;
            Positions.Closed += OnPositionClosed;
            Print("V5 multiativos iniciado: {0} ativos carregados. Use somente DEMO.", assets.Count);
        }

        protected override void OnBar()
        {
            ResetDay();
            ManagePositions();
            if (dailyStopped || DailyLossLimitReached()) return;
            if (tradesToday >= MaxTradesPerDay || lossesInRow >= MaxConsecutiveLosses) return;
            int hour = Server.TimeInUtc.Hour;
            if (hour < StartHour || hour >= EndHour) return;

            foreach (var kv in assets)
            {
                if (CountPositions() >= MaxOpenPositions || tradesToday >= MaxTradesPerDay) break;
                Scan(kv.Key, kv.Value);
            }
        }

        private void Scan(string name, Ctx c)
        {
            if (c.Bars.Count < Math.Max(DropBars, AtrPeriod) + 6 || c.H1.Count < SlowEma + 5) return;
            if (Positions.FindAll(BotLabel, name).Length > 0) return;
            double atr = c.Atr.Result.Last(1);
            if (atr <= 0 || c.Fast.Result.Last(1) <= c.Slow.Result.Last(1)) return;

            double highest = double.MinValue, lowest = double.MaxValue, minRsi = 100;
            int highIndex = 0, lowIndex = 0;
            for (int i = 1; i <= DropBars; i++)
            {
                if (c.Bars.HighPrices.Last(i) > highest) { highest = c.Bars.HighPrices.Last(i); highIndex = i; }
                if (c.Bars.LowPrices.Last(i) < lowest) { lowest = c.Bars.LowPrices.Last(i); lowIndex = i; }
            }
            for (int i = 1; i <= 5; i++) minRsi = Math.Min(minRsi, c.Rsi.Result.Last(i));
            if (!(highIndex > lowIndex && lowIndex <= 5 && highest - lowest >= DropAtr * atr && minRsi <= RsiLow)) return;

            double open = c.Bars.OpenPrices.Last(1), close = c.Bars.ClosePrices.Last(1);
            if (!(close > open && close > c.Bars.ClosePrices.Last(2) && c.Rsi.Result.Last(1) > c.Rsi.Result.Last(2))) return;
            if (lowest < c.Slow.Result.Last(1)) return;

            Symbol s = c.Symbol;
            double atrPips = atr / s.PipSize;
            double stopPips = (s.Ask - (lowest - StopBufferAtr * atr)) / s.PipSize;
            if (stopPips > atrPips * MaxStopAtr) return;
            stopPips = Math.Max(stopPips, atrPips * MinStopAtr);
            double spreadPips = s.Spread / s.PipSize;
            if (spreadPips > stopPips * MaxSpreadToStop) return;
            double tpPips = stopPips * RewardRisk;

            // Calcula o volume pelo risco percentual e limita a ordem a MaxLotsPerTrade.
            double volume = s.VolumeForProportionalRisk(ProportionalAmountType.Equity, RiskPercent, stopPips, RoundingMode.Down);
            double maxVolume = s.QuantityToVolumeInUnits(MaxLotsPerTrade);
            volume = s.NormalizeVolumeInUnits(Math.Min(volume, maxVolume), RoundingMode.Down);
            if (double.IsNaN(volume) || double.IsInfinity(volume) || volume < s.VolumeInUnitsMin)
            {
                Print("[{0}] Sinal ignorado: volume seguro abaixo do mínimo da corretora.", name);
                return;
            }
            var result = ExecuteMarketOrder(TradeType.Buy, name, volume, BotLabel, stopPips, tpPips);
            if (result.IsSuccessful)
            {
                tradesToday++;
                Print("[{0}] COMPRA aberta | volume {1} unidades | SL {2:F1} pips | TP {3:F1} pips", name, volume, stopPips, tpPips);
            }
            else Print("[{0}] Ordem rejeitada: {1}", name, result.Error);
        }

        private int CountPositions() { return Positions.FindAll(BotLabel).Length; }

        private void ManagePositions()
        {
            foreach (var p in Positions.FindAll(BotLabel))
            {
                Ctx c;
                if (!assets.TryGetValue(p.SymbolName, out c)) continue;
                double atr = c.Atr.Result.Last(1);
                if (atr <= 0) continue;
                if ((Server.Time - p.EntryTime).TotalHours >= MaxHoldHours) { ClosePosition(p); continue; }
                if (p.Pips >= (atr / c.Symbol.PipSize) * TrailStartAtr)
                {
                    double stop = Math.Max(c.Symbol.Bid - TrailDistanceAtr * atr, p.EntryPrice + c.Symbol.PipSize * 0.5);
                    if (p.StopLoss == null || stop > p.StopLoss.Value + c.Symbol.PipSize * 0.2)
                    {
                        var modify = ModifyPosition(p, stop, p.TakeProfit);
                        if (!modify.IsSuccessful) Print("[{0}] Falha ao ajustar trailing: {1}", p.SymbolName, modify.Error);
                    }
                }
            }
        }

        private void OnPositionClosed(PositionClosedEventArgs e)
        {
            if (e.Position.Label != BotLabel) return;
            lossesInRow = e.Position.NetProfit < 0 ? lossesInRow + 1 : 0;
        }

        private bool DailyLossLimitReached()
        {
            if (dayStartEquity <= 0) return false;
            double loss = (dayStartEquity - Account.Equity) / dayStartEquity * 100.0;
            if (loss >= DailyLossLimitPercent) { dailyStopped = true; Print("Limite diário atingido: {0:F2}%. Entradas suspensas.", loss); return true; }
            return false;
        }

        private void ResetDay()
        {
            if (Server.Time.Date == day) return;
            day = Server.Time.Date; dayStartEquity = Account.Equity;
            tradesToday = 0; lossesInRow = 0; dailyStopped = false;
            Print("Novo dia: limites diários reiniciados.");
        }

        protected override void OnStop()
        {
            Positions.Closed -= OnPositionClosed;
        }
    }
}