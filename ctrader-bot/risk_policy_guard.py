"""Fail-closed demo risk policy helpers. These helpers do not submit orders."""
from dataclasses import dataclass
from datetime import date
from threading import RLock


@dataclass(frozen=True)
class RiskDecision:
    allowed: bool
    reason: str


class DemoRiskGuard:
    """In-memory pre-trade guard; production use requires persistent reconciliation."""
    def __init__(self, max_positions=None, max_daily_loss_pct=2.0,
                 max_operations_day=10, max_consecutive_losses=3,
                 min_free_margin=25.0):
        self.max_positions = None if max_positions is None else int(max_positions)
        self.max_daily_loss_pct = float(max_daily_loss_pct)
        self.max_operations_day = int(max_operations_day)
        self.max_consecutive_losses = int(max_consecutive_losses)
        self.min_free_margin = float(min_free_margin)
        self._lock = RLock()
        self._day = date.today()
        self._day_start_equity = None
        self._operations = 0
        self._consecutive_losses = 0
        self._halt_reason = None

    def _roll_day(self):
        today = date.today()
        if today != self._day:
            self._day = today
            self._day_start_equity = None
            self._operations = 0
            self._consecutive_losses = 0
            self._halt_reason = None

    def check(self, *, demo_account, account_match, connected, quote_fresh,
              open_positions, equity, free_margin):
        with self._lock:
            self._roll_day()
            if not demo_account:
                return RiskDecision(False, "demo_account_required")
            if not account_match:
                return RiskDecision(False, "selected_account_mismatch")
            if not connected:
                return RiskDecision(False, "connection_unavailable")
            if not quote_fresh:
                return RiskDecision(False, "stale_quote")
            if self._halt_reason:
                return RiskDecision(False, self._halt_reason)
            if self.max_positions is not None and int(open_positions) >= self.max_positions:
                return RiskDecision(False, "global_position_limit")
            if free_margin is None or float(free_margin) < self.min_free_margin:
                return RiskDecision(False, "insufficient_or_unknown_free_margin")
            if equity is None or float(equity) <= 0:
                return RiskDecision(False, "unknown_or_invalid_equity")
            if self._day_start_equity is None:
                self._day_start_equity = float(equity)
            loss_pct = max(0.0, (self._day_start_equity - float(equity)) /
                           self._day_start_equity * 100.0)
            if loss_pct >= self.max_daily_loss_pct:
                self._halt_reason = "daily_loss_limit"
                return RiskDecision(False, self._halt_reason)
            if self._operations >= self.max_operations_day:
                return RiskDecision(False, "daily_operation_limit")
            if self._consecutive_losses >= self.max_consecutive_losses:
                self._halt_reason = "consecutive_loss_limit"
                return RiskDecision(False, self._halt_reason)
            return RiskDecision(True, "risk_checks_passed")

    def record_closed_trade(self, realized_pnl):
        with self._lock:
            self._roll_day()
            self._operations += 1
            if float(realized_pnl) < 0:
                self._consecutive_losses += 1
                if self._consecutive_losses >= self.max_consecutive_losses:
                    self._halt_reason = "consecutive_loss_limit"
            else:
                self._consecutive_losses = 0

    def reset_halt(self):
        """Explicit operator action only; caller must reconcile account first."""
        with self._lock:
            self._halt_reason = None
