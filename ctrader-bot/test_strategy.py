import unittest
from strategy import analyze_closes, risk_allows_trade


class SignalEngineTests(unittest.TestCase):
    def test_requires_enough_candles(self):
        with self.assertRaises(ValueError):
            analyze_closes("XAUUSD", [100.0] * 20)

    def test_flat_market_returns_no_trade(self):
        signal = analyze_closes("XAUUSD", [100.0] * 30)
        self.assertEqual(signal.direction, "NO_TRADE")

    def test_signal_does_not_claim_ai_approval(self):
        signal = analyze_closes("BTCUSD", [100 + i * 0.5 for i in range(30)])
        self.assertEqual(signal.confidence, "technical_only")

    def test_real_mode_is_blocked(self):
        allowed, _ = risk_allows_trade(demo_mode=False, daily_loss=0,
                                       max_daily_loss=5, open_positions=0,
                                       max_open_positions=2)
        self.assertFalse(allowed)

    def test_daily_loss_limit_blocks(self):
        allowed, _ = risk_allows_trade(demo_mode=True, daily_loss=5,
                                       max_daily_loss=5, open_positions=0,
                                       max_open_positions=2)
        self.assertFalse(allowed)

    def test_position_limit_blocks(self):
        allowed, _ = risk_allows_trade(demo_mode=True, daily_loss=0,
                                       max_daily_loss=5, open_positions=2,
                                       max_open_positions=2)
        self.assertFalse(allowed)


if __name__ == "__main__":
    unittest.main()
