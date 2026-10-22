import unittest
from risk_policy_guard import DemoRiskGuard


class DemoRiskGuardTests(unittest.TestCase):
    def setUp(self):
        self.guard = DemoRiskGuard(max_positions=3, max_daily_loss_pct=2,
                                   max_operations_day=10, max_consecutive_losses=3,
                                   min_free_margin=25)

    def check(self, **overrides):
        values = dict(demo_account=True, account_match=True, connected=True,
                      quote_fresh=True, open_positions=0, equity=400,
                      free_margin=200)
        values.update(overrides)
        return self.guard.check(**values)

    def test_allows_valid_demo_state(self):
        self.assertTrue(self.check().allowed)

    def test_blocks_live_account(self):
        self.assertEqual(self.check(demo_account=False).reason, "demo_account_required")

    def test_blocks_account_mismatch(self):
        self.assertEqual(self.check(account_match=False).reason, "selected_account_mismatch")

    def test_blocks_disconnection_and_stale_quote(self):
        self.assertEqual(self.check(connected=False).reason, "connection_unavailable")
        self.assertEqual(self.check(quote_fresh=False).reason, "stale_quote")

    def test_blocks_global_position_limit(self):
        self.assertEqual(self.check(open_positions=3).reason, "global_position_limit")

    def test_blocks_low_margin(self):
        self.assertEqual(self.check(free_margin=10).reason, "insufficient_or_unknown_free_margin")

    def test_blocks_unknown_equity(self):
        self.assertEqual(self.check(equity=None).reason, "unknown_or_invalid_equity")

    def test_halts_after_consecutive_losses(self):
        for _ in range(3):
            self.guard.record_closed_trade(-1)
        self.assertEqual(self.check().reason, "consecutive_loss_limit")


if __name__ == "__main__":
    unittest.main()
