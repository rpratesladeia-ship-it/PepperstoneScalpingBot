import tempfile
import unittest
from pathlib import Path
import strategy_telemetry as telemetry

class StrategyTelemetryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_dir, self.old_file = telemetry._DATA_DIR, telemetry._EVENTS
        telemetry._DATA_DIR = Path(self.temp.name)
        telemetry._EVENTS = telemetry._DATA_DIR / "events.jsonl"

    def tearDown(self):
        telemetry._DATA_DIR, telemetry._EVENTS = self.old_dir, self.old_file
        self.temp.cleanup()

    def test_counts_one_candidate_and_separate_filter_decisions(self):
        telemetry.record_event("signal_candidate", symbol="EURUSD", side="BUY")
        telemetry.record_event("filter_decision", symbol="EURUSD", side="BUY", decision="blocked_dms")
        telemetry.record_event("filter_decision", symbol="EURUSD", side="BUY", decision="blocked_ai")
        report = telemetry.analysis_report()
        self.assertEqual(report["signals_logged"], 1)
        self.assertEqual(report["filter_decisions"], 2)
        self.assertEqual(report["signal_decisions"]["blocked_dms"], 1)
        self.assertEqual(report["signal_decisions"]["blocked_ai"], 1)
        self.assertEqual(report["signals_by_symbol"]["EURUSD"], 1)

    def test_backup_has_events_and_analysis(self):
        telemetry.record_event("position_pnl", position_id=123, current_profit=0.12)
        backup = telemetry.export_backup()
        self.assertEqual(backup["mode"], "DEMO")
        self.assertEqual(len(backup["events"]), 1)
        self.assertEqual(backup["analysis"]["pnl_samples"], 1)
        self.assertEqual(backup["analysis"]["closed_trade_outcomes"], 0)

if __name__ == "__main__":
    unittest.main()
