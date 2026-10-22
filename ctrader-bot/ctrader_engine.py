"""Minimal cTrader Open API session bridge. Demo-only; order submission is intentionally not exposed yet."""
import threading
import logging
import os
import json
import time
from pathlib import Path
from typing import Any

log = logging.getLogger("trader-ctrader")

from ctrader_open_api import Client, TcpProtocol, EndPoints, Protobuf
from ctrader_open_api.messages.OpenApiCommonMessages_pb2 import *
from ctrader_open_api.messages.OpenApiMessages_pb2 import *
from ctrader_open_api.messages.OpenApiModelMessages_pb2 import *
from twisted.internet import reactor
from ai_filter import load_model, evaluate_ml_gate


class CTraderDemoBridge:
    """One demo connection, account validation, and account authorization."""

    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self._lock = threading.RLock()
        # Audit trail for later strategy/AI analysis. Render's local filesystem may be ephemeral.
        self._event_log_path = Path(os.getenv("TRADING_EVENT_LOG", "/tmp/meu-trader-events.jsonl"))
        self._event_log_path.parent.mkdir(parents=True, exist_ok=True)
        self._event_log_lock = threading.Lock()
        self._client = None
        self._token = None
        self._state: dict[str, Any] = {
            "connected": False,
            "application_authorized": False,
            "account_validated": False,
            "account_authorized": False,
            "demo_only": True,
            "accounts": [],
            "selected_account_id": None,
            "last_error": None,
            "symbols": [], "symbol_ids": {}, "prices": {}, "equity": None,
            "balance": None, "equity": None, "margin": None, "free_margin": None,
            "open_positions": 0, "order_execution": False, "last_order": None,
            "risk_limits": {"max_positions": 2, "min_free_margin": 25.0},
            "auto_started_at": None, "auto_deadline": None,
            "last_auto_started_at": None, "last_auto_stopped_at": None,
            "last_auto_stop_reason": None,
            "last_manual_order_at": None, "last_manual_order_result_at": None,
        }
        self._thread = None
        self._auto_enabled = False
        self._auto_last_signal = {}
        self._auto_history = {}
        self._auto_cooldown_seconds = 300
        self._auto_last_trade_at = {}
        # Rotation guard: max 3 consecutive successful entries per symbol, then 5 other-symbol entries before reuse.
        self._auto_last_entry_symbol = None
        self._auto_same_symbol_entries = 0
        self._auto_rotation_wait = {}
        self._auto_rotation_other_entries = {}
        self._auto_max_consecutive_per_symbol = 3
        self._auto_other_entries_before_reuse = 5
        self._auto_max_positions = 2
        # Financial trailing protection per open position, account deposit currency.
        self._profit_arm_usd = 0.20
        self._profit_retrace_usd = 0.05
        self._tracked_positions = {}
        self._trail_peak_by_position = {}
        self._trail_closing_positions = set()
        self._pnl_poll_scheduled = False
        self._reconnect_attempt = 0
        self._reconnect_scheduled = False
        # DMS(14) tick-based prototype; not canonical OHLC ADX.
        self._dms_period = 14
        self._dms_min_strength = 20.0
        self._ai_enabled = os.getenv("AI_FILTER_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}
        self._ai_model = load_model()
        self._state["ai_filter"] = {"enabled": self._ai_enabled, "model_loaded": self._ai_model is not None,
                                    "status": ("Modelo ML treinado ativo" if self._ai_enabled and self._ai_model else
                                               "Filtro técnico experimental ativo; modelo ML ainda não treinado" if self._ai_enabled else
                                               "Filtro IA desligado")}
        self._state["dms_filter"] = {"enabled": True, "period": 14, "min_strength": 20.0, "method": "tick approximation", "last": {}}
        # Initial DEMO protection distances in absolute price units; review per broker/symbol.
        # Absolute price distances; DEMO-only until each broker symbol is validated.
        # DEMO experiment: stop-loss distance is 40% of the configured take-profit
        # distance. Monetary P&L still depends on each broker symbol's contract specs.
        # XAUUSD usa alvo mais amplo (swing intraday); demais ativos mantêm perfil scalping.
        # Distâncias em preço, não em dólares de P&L: validar especificações de cada símbolo.
        # Em todos os perfis o SL configurado é 40% da distância do TP.
        # Universo DEMO por classe. Os nomes são candidatos; só os símbolos
        # realmente publicados pela corretora cTrader serão encontrados/assinados.
        # Distâncias em preço, não em dinheiro; SL = 40% do TP configurado.
        self._protection_distances = {
            # Metais e energia
            "XAUUSD": (4.0, 10.0), "XAGUSD": (0.06, 0.15),
            "XPTUSD": (4.0, 10.0), "XPDUSD": (4.0, 10.0),
            "USOIL": (0.08, 0.20), "UKOIL": (0.08, 0.20), "NATGAS": (0.02, 0.05),
            # Forex majors
            "EURUSD": (0.0006, 0.0015), "GBPUSD": (0.0006, 0.0015),
            "USDJPY": (0.06, 0.15), "USDCHF": (0.0006, 0.0015),
            "USDCAD": (0.0006, 0.0015), "AUDUSD": (0.0006, 0.0015),
            "NZDUSD": (0.0006, 0.0015),
            # Forex crosses
            "EURGBP": (0.0006, 0.0015), "EURJPY": (0.06, 0.15),
            "GBPJPY": (0.06, 0.15), "AUDJPY": (0.06, 0.15),
            "EURAUD": (0.0008, 0.0020), "AUDCAD": (0.0006, 0.0015),
            "AUDCHF": (0.0006, 0.0015), "AUDNZD": (0.0006, 0.0015),
            "CADCHF": (0.0006, 0.0015), "CADJPY": (0.06, 0.15),
            "CHFJPY": (0.06, 0.15), "EURNZD": (0.0008, 0.0020),
            "EURCAD": (0.0008, 0.0020), "GBPAUD": (0.0008, 0.0020),
            "GBPCAD": (0.0008, 0.0020), "GBPCHF": (0.0008, 0.0020),
            "GBPNZD": (0.0008, 0.0020), "NZDCAD": (0.0006, 0.0015),
            "NZDCHF": (0.0006, 0.0015), "NZDJPY": (0.06, 0.15),
            "EURCHF": (0.0006, 0.0015),
            # Índices de bolsas
            "US30": (6.0, 15.0), "NAS100": (10.0, 25.0),
            "SPX500": (3.2, 8.0), "GER40": (10.0, 25.0),
            "UK100": (6.0, 15.0), "JPN225": (32.0, 80.0),
            "AUS200": (10.0, 25.0), "FRA40": (10.0, 25.0),
            "EU50": (10.0, 25.0), "HK50": (20.0, 50.0),
            # Criptomoedas
            "BTCUSD": (60.0, 150.0), "ETHUSD": (6.0, 15.0),
            "LTCUSD": (3.2, 8.0), "BCHUSD": (6.0, 15.0),
            "ADAUSD": (0.012, 0.03), "DOTUSD": (0.08, 0.20),
            "SOLUSD": (0.8, 2.0), "XRPUSD": (0.004, 0.01),
            "LINKUSD": (0.2, 0.5), "AVAXUSD": (0.4, 1.0),
            "DOGEUSD": (0.002, 0.005),
            # Ações/CFDs de ações — disponibilidade depende do broker/conta
            "AAPL": (0.4, 1.0), "MSFT": (0.4, 1.0), "NVDA": (0.8, 2.0),
            "TSLA": (1.0, 2.5), "AMZN": (0.6, 1.5), "GOOGL": (0.6, 1.5),
            "META": (0.8, 2.0), "NFLX": (1.0, 2.5),
        }
        self._state["configured_auto_symbols"] = sorted(self._protection_distances)
        self._state["symbol_digits"] = {}

    def _record_event(self, event_type: str, **fields):
        """Append one structured market/trading event for later analysis."""
        record = {"ts": time.time(), "type": event_type, **fields}
        try:
            with self._event_log_lock:
                with self._event_log_path.open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(record, ensure_ascii=False, separators=(",", ":"), default=str) + "\n")
        except OSError:
            log.exception("Could not persist trading audit event")

    def read_recent_events(self, limit: int = 200):
        limit = max(1, min(int(limit), 1000))
        try:
            with self._event_log_lock:
                if not self._event_log_path.exists():
                    return []
                lines = self._event_log_path.read_text(encoding="utf-8").splitlines()[-limit:]
            events = []
            for line in lines:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
            return events
        except OSError:
            log.exception("Could not read trading audit events")
            return []

    def snapshot(self):
        with self._lock:
            return dict(self._state)

    def close_connection(self):
        """Stop this bridge cleanly before replacing a cTrader session."""
        with self._lock:
            client = self._client
            self._client = None
            self._token = None
            self._auto_enabled = False
            self._state.update(connected=False, application_authorized=False,
                               account_authorized=False, auto_trading=False,
                               auto_status="Conexão encerrada para reinicialização")
        if client is not None:
            try:
                client.stopService()
            except Exception as exc:
                log.info("cTrader client cleanup finished (%s)", type(exc).__name__)

    def connect(self, access_token: str):
        if not access_token:
            raise ValueError("Token cTrader ausente")
        with self._lock:
            if self._client and self._state["connected"]:
                raise RuntimeError("Já existe uma conexão cTrader ativa")
            self._token = access_token
            self._state.update(connected=False, application_authorized=False,
                               account_validated=False, account_authorized=False,
                               accounts=[], selected_account_id=None, last_error=None)
        if not reactor.running:
            self._thread = threading.Thread(target=reactor.run, kwargs={"installSignalHandlers": False}, daemon=True)
            self._thread.start()
        reactor.callFromThread(self._start_client)
        return {"queued": True, "demo_only": True}

    def _start_client(self):
        # Do not leave two TCP clients alive for one browser session.
        existing = self._client
        if existing is not None:
            try:
                existing.stopService()
            except Exception:
                pass
        client = Client(EndPoints.PROTOBUF_DEMO_HOST, EndPoints.PROTOBUF_PORT, TcpProtocol)
        self._client = client
        client.setConnectedCallback(self._on_connected)
        client.setDisconnectedCallback(self._on_disconnected)
        client.setMessageReceivedCallback(self._on_message)
        client.startService()

    def _on_connected(self, client):
        with self._lock:
            self._state["connected"] = True
            self._reconnect_attempt = 0
            self._reconnect_scheduled = False
            self._state["last_error"] = None
        req = ProtoOAApplicationAuthReq()
        req.clientId = self.client_id
        req.clientSecret = self.client_secret
        client.send(req).addErrback(self._on_error)

    def _on_disconnected(self, _client, reason):
        with self._lock:
            self._state.update(connected=False, application_authorized=False,
                               account_authorized=False, last_error="Conexão cTrader interrompida; tentando reconectar")
            self._schedule_reconnect_locked()

    def _schedule_reconnect_locked(self):
        if self._reconnect_scheduled or not self._token:
            return
        self._reconnect_attempt += 1
        delay = min(60, 2 ** min(self._reconnect_attempt, 6))
        self._reconnect_scheduled = True
        self._state["reconnect_attempt"] = self._reconnect_attempt
        self._state["reconnect_in_seconds"] = delay
        reactor.callLater(delay, self._restart_client_after_disconnect)

    def _restart_client_after_disconnect(self):
        with self._lock:
            self._reconnect_scheduled = False
            if self._state.get("connected"):
                return
        try:
            self._start_client()
        except Exception as exc:
            log.warning("cTrader reconnect attempt failed: %s", type(exc).__name__)
            with self._lock:
                self._state["last_error"] = "Falha ao reconectar; nova tentativa programada"
                self._schedule_reconnect_locked()

    def _on_error(self, failure):
        try:
            error_type = failure.type.__name__
            error_text = str(failure.value)[:240]
        except Exception:
            error_type = "ErroDeTransporte"
            error_text = ""
        # Twisted Deferred timeouts can be request/response timeouts even while
        # the TCP socket is reachable; keep the wording precise for diagnosis.
        log.warning("cTrader request/deferred failure: type=%s detail=%s", error_type, error_text)
        with self._lock:
            # A timeout on an individual request (for example a market-data or
            # reconciliation request) does not revoke OAuth/application/account
            # authorization. Clearing these flags here caused the UI to show
            # "App autorizado: não" even after AuthRes had arrived successfully.
            self._state["last_error"] = "Uma solicitação cTrader expirou (" + error_type + "); a autorização será mantida se já foi confirmada."
        return None

    def _on_message(self, client, message):
        if message.payloadType == ProtoHeartbeatEvent().payloadType:
            return
        payload = Protobuf.extract(message)
        log.info("cTrader message received: payloadType=%s class=%s",
                 getattr(message, "payloadType", None), type(payload).__name__)
        if message.payloadType == ProtoOAErrorRes().payloadType:
            code = str(getattr(payload, "errorCode", "erro cTrader"))
            description = str(getattr(payload, "description", "") or "")[:240]
            log.warning("cTrader API response: code=%s description=%s", code[:100], description)
            # Restore the previous flow: cTrader may report ALREADY_LOGGED_IN
            # when application auth is already established on this session.
            # Continue account discovery, then require explicit DEMO account auth.
            if code.upper() == "ALREADY_LOGGED_IN":
                with self._lock:
                    self._state["application_authorized"] = True
                    self._state["last_error"] = None
                req = ProtoOAGetAccountListByAccessTokenReq()
                req.accessToken = self._token
                client.send(req).addErrback(self._on_error)
                log.info("cTrader reported ALREADY_LOGGED_IN; continuing account discovery")
                return
            with self._lock:
                self._state["account_authorized"] = False
                if code.upper() == "UNSUPPORTED_MESSAGE" and "account is not authorized" in description.lower():
                    self._state["account_validated"] = False
                    self._state["last_error"] = (
                        "A cTrader recusou a autorização da conta. Toque em 'Conectar conta cTrader' "
                        "e aprove novamente o acesso; contas adicionadas depois da autorização inicial "
                        "podem exigir nova aprovação. Depois selecione novamente uma conta DEMO."
                    )
                else:
                    self._state["last_error"] = "cTrader recusou uma solicitação: " + code + ((" — " + description) if description else "")
            log.warning("cTrader API request rejected: code=%s description=%s", code[:100], description)
            return
        if message.payloadType == ProtoOAApplicationAuthRes().payloadType:
            with self._lock:
                self._state["application_authorized"] = True
                self._state["last_error"] = None
            req = ProtoOAGetAccountListByAccessTokenReq()
            req.accessToken = self._token
            client.send(req).addErrback(self._on_error)
        elif message.payloadType == ProtoOAGetAccountListByAccessTokenRes().payloadType:
            accounts = []
            for account in getattr(payload, "ctidTraderAccount", []):
                accounts.append({
                    "account_id": int(account.ctidTraderAccountId),
                    "is_live": bool(account.isLive),
                })
            with self._lock:
                self._state["accounts"] = accounts
                self._state["account_validated"] = any(not a["is_live"] for a in accounts)
                self._state["last_error"] = None if accounts else "API autorizada, mas nenhuma conta foi retornada; verifique a permissão de acesso a contas no aplicativo cTrader"
                selected_id = self._state.get("selected_account_id")
                selected_demo = next((a for a in accounts if a["account_id"] == selected_id and not a["is_live"]), None)
                timer_deadline = self._state.get("auto_deadline")
                resume_auto = bool(self._auto_enabled and selected_demo and timer_deadline)
                if selected_id is not None and not selected_demo:
                    self._state["account_authorized"] = False
                    self._auto_enabled = False
                    self._state["auto_trading"] = False
                    self._state["auto_status"] = "Automação parada: conta DEMO não confirmada após reconexão"
                elif resume_auto:
                    import time
                    if time.time() >= timer_deadline:
                        self._auto_enabled = False
                        self._state["auto_trading"] = False
                        self._state["auto_status"] = "Temporizador expirou durante a desconexão; automação não retomada"
                        resume_auto = False
            if selected_demo and selected_id is not None:
                if resume_auto:
                    log.info("Reconnecting: reauthorizing the previously selected DEMO account")
                reactor.callFromThread(self._send_account_auth, int(selected_id))
        elif message.payloadType == ProtoOAAccountAuthRes().payloadType:
            with self._lock:
                self._state["account_authorized"] = True
                self._state["last_error"] = None
                if self._auto_enabled:
                    self._state["auto_trading"] = True
                    self._state["auto_status"] = "Conexão restaurada; automação DEMO retomada após revalidar a conta"

            trader = ProtoOATraderReq()
            trader.ctidTraderAccountId = int(payload.ctidTraderAccountId)
            client.send(trader).addErrback(self._on_error)
            reconcile = ProtoOAReconcileReq()
            reconcile.ctidTraderAccountId = int(payload.ctidTraderAccountId)
            client.send(reconcile).addErrback(self._on_error)
            symbols = ProtoOASymbolsListReq()
            symbols.ctidTraderAccountId = int(payload.ctidTraderAccountId)
            symbols.includeArchivedSymbols = False
            client.send(symbols).addErrback(self._on_error)
        elif message.payloadType == ProtoOATraderRes().payloadType:
            with self._lock:
                self._state["balance"] = float(payload.trader.balance) / 100.0
                self._state["equity"] = float(payload.trader.balance) / 100.0
        elif message.payloadType == ProtoOAReconcileRes().payloadType:
            positions = {}
            for position in getattr(payload, "position", []):
                trade_data = getattr(position, "tradeData", None)
                position_id = int(getattr(position, "positionId", 0) or getattr(trade_data, "positionId", 0))
                volume = int(getattr(trade_data, "volume", 0)) if trade_data else 0
                if position_id and volume > 0:
                    positions[position_id] = {"volume": volume}
            with self._lock:
                self._tracked_positions = positions
                self._state["open_positions"] = len(positions)
                live_ids = set(positions)
                self._trail_peak_by_position = {pid: peak for pid, peak in self._trail_peak_by_position.items() if pid in live_ids}
                self._trail_closing_positions.intersection_update(live_ids)
            self._schedule_position_pnl_poll()
        elif message.payloadType == ProtoOAGetPositionUnrealizedPnLRes().payloadType:
            self._handle_position_pnl(payload)
            self._schedule_position_pnl_poll()
        elif message.payloadType == ProtoOASymbolsListRes().payloadType:
            wanted = set(self._protection_distances)
            found = {}
            digits = {}
            for symbol in getattr(payload, "symbol", []):
                name = str(getattr(symbol, "symbolName", "")).upper()
                if name in wanted:
                    found[name] = int(symbol.symbolId)
                    digits[name] = int(getattr(symbol, "digits", 5))
            with self._lock:
                self._state["symbol_ids"] = found
                self._state["symbol_digits"] = digits
                self._state["symbols"] = sorted(found.keys())
                self._state["unavailable_symbols"] = sorted(wanted - set(found.keys()))
            for symbol_id in found.values():
                req = ProtoOASubscribeSpotsReq()
                req.ctidTraderAccountId = int(self._state["selected_account_id"])
                req.symbolId.append(int(symbol_id))
                client.send(req).addErrback(self._on_error)
        elif message.payloadType == ProtoOASpotEvent().payloadType:
            with self._lock:
                symbol_id = int(getattr(payload, "symbolId", 0))
                name = next((key for key, value in self._state["symbol_ids"].items() if value == symbol_id), None)
                if name:
                    prices = self._state["prices"].setdefault(name, {})
                    if getattr(payload, "bid", 0):
                        prices["bid_raw"] = int(payload.bid)
                    if getattr(payload, "ask", 0):
                        prices["ask_raw"] = int(payload.ask)
                    current = int(getattr(payload, "bid", 0) or getattr(payload, "ask", 0) or 0)
                    if current:
                        history = self._auto_history.setdefault(name, [])
                        history.append(current)
                        del history[:-30]
                        self._record_event("quote", symbol=name,
                            bid_raw=int(getattr(payload, "bid", 0) or 0),
                            ask_raw=int(getattr(payload, "ask", 0) or 0),
                            price_raw=current, digits=self._state["symbol_digits"].get(name, 5),
                            auto_enabled=self._auto_enabled)
                        self._evaluate_auto_entry(name, history)
        elif message.payloadType == ProtoOAExecutionEvent().payloadType:
            with self._lock:
                order = getattr(payload, "order", None)
                self._state["last_order"] = {"accepted": True, "order_id": int(order.orderId) if order else None, "status": "resposta recebida"}
            account_id = self._state.get("selected_account_id")
            if account_id:
                reconcile = ProtoOAReconcileReq()
                reconcile.ctidTraderAccountId = int(account_id)
                client.send(reconcile).addErrback(self._on_error)

    def _schedule_position_pnl_poll(self):
        with self._lock:
            if self._pnl_poll_scheduled or not self._state.get("account_authorized"):
                return
            self._pnl_poll_scheduled = True
        reactor.callLater(1.0, self._request_position_pnl)

    def _request_position_pnl(self):
        with self._lock:
            self._pnl_poll_scheduled = False
            client = self._client
            account_id = self._state.get("selected_account_id")
            ready = bool(client and self._state.get("connected") and self._state.get("account_authorized") and account_id)
        if not ready:
            return
        req = ProtoOAGetPositionUnrealizedPnLReq()
        req.ctidTraderAccountId = int(account_id)
        client.send(req).addErrback(self._on_error)

    @staticmethod
    def _trail_should_close(peak_profit: float, current_profit: float, activation: float = 0.20, retrace: float = 0.05) -> bool:
        return peak_profit >= activation and (peak_profit - current_profit) >= retrace

    def _handle_position_pnl(self, payload):
        money_digits = int(getattr(payload, "moneyDigits", 2))
        divisor = float(10 ** money_digits)
        for item in getattr(payload, "positionUnrealizedPnL", []):
            position_id = int(getattr(item, "positionId", 0))
            current_profit = float(getattr(item, "netUnrealizedPnL", 0)) / divisor
            self._record_event("position_pnl", position_id=position_id, net_unrealized_pnl=current_profit)
            with self._lock:
                if position_id not in self._tracked_positions or position_id in self._trail_closing_positions:
                    continue
                peak = max(self._trail_peak_by_position.get(position_id, current_profit), current_profit)
                self._trail_peak_by_position[position_id] = peak
                armed = peak >= self._profit_arm_usd
                self._state["profit_trailing"] = {
                    "enabled": True, "activation_usd": self._profit_arm_usd, "retrace_usd": self._profit_retrace_usd,
                    "positions": len(self._tracked_positions),
                    "armed_positions": sum(1 for p in self._trail_peak_by_position.values() if p >= self._profit_arm_usd),
                    "last_position_id": position_id, "last_profit_usd": round(current_profit, 4),
                    "peak_profit_usd": round(peak, 4), "armed": armed,
                }
                should_close = self._trail_should_close(peak, current_profit, self._profit_arm_usd, self._profit_retrace_usd)
                if should_close:
                    self._trail_closing_positions.add(position_id)
                    volume = self._tracked_positions[position_id]["volume"]
                    account_id = self._state.get("selected_account_id")
                    client = self._client
                    self._state["auto_status"] = "Trailing financeiro: solicitando fechamento DEMO da posição " + str(position_id)
            if should_close:
                if not client or not account_id or not volume:
                    with self._lock:
                        self._trail_closing_positions.discard(position_id)
                        self._state["last_error"] = "Trailing acionado, mas não foi possível confirmar volume/conta para fechar."
                    continue
                req = ProtoOAClosePositionReq()
                req.ctidTraderAccountId = int(account_id)
                req.positionId = int(position_id)
                req.volume = int(volume)
                def record_close_response(message, pid=position_id, peak_value=peak, current_value=current_profit):
                    with self._lock:
                        self._state["last_order"] = {
                            "accepted": message.payloadType == ProtoOAExecutionEvent().payloadType,
                            "action": "trailing_close", "position_id": pid,
                            "peak_profit_usd": round(peak_value, 4), "profit_at_request_usd": round(current_value, 4),
                            "status": "resposta de fechamento recebida",
                        }
                        self._trail_closing_positions.discard(pid)
                    return message
                def close_failed(failure, pid=position_id):
                    with self._lock:
                        self._trail_closing_positions.discard(pid)
                        self._state["last_error"] = "Falha ao solicitar fechamento pelo trailing financeiro."
                    return self._on_error(failure)
                client.send(req).addCallbacks(record_close_response, close_failed)
                log.info("Financial trailing requested DEMO close position=%s peak=%.4f current=%.4f", position_id, peak, current_profit)

    def set_auto_trading(self, enabled: bool, duration_minutes: int = 60):
        """Enable guarded DEMO entries with an automatic stop timer."""
        import time
        duration_minutes = int(duration_minutes)
        if enabled and not 1 <= duration_minutes <= 1440:
            raise ValueError("O temporizador deve ficar entre 1 e 1440 minutos.")
        with self._lock:
            if enabled:
                account = next((a for a in self._state["accounts"]
                                if a["account_id"] == self._state["selected_account_id"]), None)
                if not self._state["connected"] or not self._state["application_authorized"] or not self._state["account_authorized"]:
                    raise RuntimeError("Conecte e autorize uma conta DEMO antes de ativar.")
                if not account or account["is_live"]:
                    raise PermissionError("Automação bloqueada: somente conta DEMO.")
                if self._ai_enabled and self._ai_model is None:
                    raise RuntimeError(
                        "Automação bloqueada por segurança: o filtro IA está ligado, mas ainda não existe "
                        "modelo treinado válido. O painel continuará em DEMO; treine e valide o modelo antes de liberar entradas."
                    )
                if not self._state["symbols"]:
                    raise RuntimeError("Nenhum ativo disponível para a automação.")
                self._auto_enabled = True
                started = time.time()
                deadline = started + duration_minutes * 60
                self._state.update(auto_trading=True, auto_started_at=started,
                                   auto_duration_seconds=duration_minutes * 60,
                                   auto_deadline=deadline,
                                   auto_status="Ativo: temporizador iniciado")
            else:
                self._auto_enabled = False
                self._state.update(auto_trading=False, auto_started_at=None,
                                   auto_duration_seconds=0, auto_deadline=None,
                                   auto_status="Desativado pelo operador")
                return {"auto_trading": False, "demo_only": True, "timer_active": False}
        reactor.callFromThread(self._schedule_auto_shutdown, duration_minutes * 60)
        if self._state.get("account_authorized"):
            self._schedule_position_pnl_poll()
        return {"auto_trading": True, "demo_only": True, "timer_active": True,
                "duration_minutes": duration_minutes}

    def _schedule_auto_shutdown(self, delay_seconds: int):
        reactor.callLater(delay_seconds, self._auto_timer_expired)

    def _auto_timer_expired(self):
        with self._lock:
            if not self._auto_enabled:
                return
            deadline = self._state.get("auto_deadline")
            import time
            if deadline is not None and time.time() < deadline:
                reactor.callLater(max(1, deadline - time.time()), self._auto_timer_expired)
                return
            self._auto_enabled = False
            self._state.update(auto_trading=False, auto_started_at=None,
                               auto_duration_seconds=0, auto_deadline=None,
                               auto_status="Temporizador encerrado: novas entradas automáticas desligadas")
        log.info("Automatic DEMO entries stopped by runtime timer")

    def _calculate_dms14_tick(self, prices):
        """Approximate directional movement from ticks; not canonical OHLC ADX."""
        period = self._dms_period
        if len(prices) < period + 1:
            return None
        moves = [float(prices[i]) - float(prices[i - 1]) for i in range(len(prices) - period, len(prices))]
        plus = sum(move for move in moves if move > 0)
        minus = sum(-move for move in moves if move < 0)
        total = plus + minus
        if total <= 0:
            return {"di_plus": 0.0, "di_minus": 0.0, "adx": 0.0, "direction": "NEUTRAL"}
        di_plus = 100.0 * plus / total
        di_minus = 100.0 * minus / total
        strength = 100.0 * abs(plus - minus) / total
        direction = "BUY" if di_plus > di_minus else "SELL" if di_minus > di_plus else "NEUTRAL"
        return {"di_plus": round(di_plus, 2), "di_minus": round(di_minus, 2),
                "adx": round(strength, 2), "direction": direction}

    def _evaluate_auto_entry(self, symbol: str, history):
        # Preserve existing crossover, adding DMS(14) directional confirmation.
        if not self._auto_enabled or len(history) < max(22, self._dms_period + 1):
            return
        import time
        now = time.time()
        with self._lock:
            if not self._state["account_authorized"] or self._state["open_positions"] >= self._state["risk_limits"]["max_positions"]:
                self._state["auto_status"] = "Entrada bloqueada: limite de posições atingido ou conta não autorizada"
                return
            free_margin = self._state.get("free_margin")
            if free_margin is not None and free_margin < self._state["risk_limits"]["min_free_margin"]:
                self._state["auto_status"] = "Entrada bloqueada: margem livre abaixo do mínimo de segurança"
                return
            if now - self._auto_last_trade_at.get(symbol, 0) < self._auto_cooldown_seconds:
                return
            if self._auto_rotation_wait.get(symbol, False):
                waited = self._auto_rotation_other_entries.get(symbol, 0)
                if waited < self._auto_other_entries_before_reuse:
                    self._state["auto_status"] = (
                        "Rotação de ativos: " + symbol + " aguardando "
                        + str(self._auto_other_entries_before_reuse - waited)
                        + " entrada(s) em outros ativos antes de liberar novamente"
                    )
                    return
            prices = list(history)
            previous = prices[:-1]
            fast_prev = sum(previous[-10:-1]) / 9
            slow_prev = sum(previous[-22:-1]) / 21
            fast_now = sum(prices[-9:]) / 9
            slow_now = sum(prices[-21:]) / 21
            side = None
            if fast_prev <= slow_prev and fast_now > slow_now:
                side = "BUY"
            elif fast_prev >= slow_prev and fast_now < slow_now:
                side = "SELL"
            dms = self._calculate_dms14_tick(prices)
            if dms:
                self._state["dms_filter"]["last"][symbol] = dms
            if not side:
                return
            self._record_event("signal", symbol=symbol, side=side,
                price_raw=prices[-1], dms=dms, ai_enabled=self._ai_enabled)
            if not dms or dms["direction"] != side or dms["adx"] < self._dms_min_strength:
                self._state["auto_status"] = (
                    "Entrada " + side + " bloqueada pelo DMS 14 em " + symbol
                    + " (DI+ " + str(dms["di_plus"] if dms else "—")
                    + " / DI− " + str(dms["di_minus"] if dms else "—")
                    + " / força " + str(dms["adx"] if dms else "—") + ")"
                )
                return
            if self._ai_enabled:
                # Fail closed: do not label a heuristic score as trained AI.
                # Automatic entries stay blocked until a valid, trained model is installed.
                if self._ai_model is None:
                    allowed, probability, reason = False, None, (
                        "Entrada bloqueada: modelo de IA treinado não instalado. "
                        "A análise técnica pode gerar sinais, mas não autoriza ordens automáticas."
                    )
                else:
                    try:
                        allowed, probability, reason = evaluate_ml_gate(prices, side, self._ai_model)
                    except (ValueError, TypeError, ZeroDivisionError, OverflowError):
                        allowed, probability, reason = False, None, "IA não conseguiu avaliar os preços; entrada bloqueada"
                self._state["ai_filter"]["last"] = {"symbol": symbol, "side": side,
                    "probability_up": round(probability, 4) if probability is not None else None,
                    "reason": reason, "mode": "ml" if self._ai_model is not None else "experimental"}
                self._record_event("ai_decision", symbol=symbol, side=side,
                    probability_up=round(probability, 6) if probability is not None else None,
                    allowed=bool(allowed), reason=reason,
                    mode="ml" if self._ai_model is not None else "experimental")
                if not allowed:
                    self._state["auto_status"] = "Entrada " + side + " bloqueada pelo filtro IA experimental em " + symbol + ": " + reason
                    return
            self._auto_last_trade_at[symbol] = now
            self._state["auto_status"] = "Sinal " + side + " confirmado pelos filtros em " + symbol + "; enviando ordem demo"
        try:
            # One minimal unit; this is demo-only and intentionally throttled.
            order_result = self.place_demo_market_order(symbol, side, 1)
            self._record_event("entry_requested", symbol=symbol, side=side,
                volume_units=1, result=order_result)
            with self._lock:
                # Update rotation only after the order call succeeds.
                if self._auto_last_entry_symbol == symbol:
                    self._auto_same_symbol_entries += 1
                else:
                    previous_symbol = self._auto_last_entry_symbol
                    self._auto_last_entry_symbol = symbol
                    self._auto_same_symbol_entries = 1
                    # Every successful entry on a different asset advances all pending rotation counters.
                    for waiting_symbol in list(self._auto_rotation_wait):
                        if waiting_symbol != symbol and self._auto_rotation_wait.get(waiting_symbol, False):
                            self._auto_rotation_other_entries[waiting_symbol] = self._auto_rotation_other_entries.get(waiting_symbol, 0) + 1
                            if self._auto_rotation_other_entries[waiting_symbol] >= self._auto_other_entries_before_reuse:
                                self._auto_rotation_wait[waiting_symbol] = False
                                self._auto_rotation_other_entries[waiting_symbol] = 0
                if self._auto_same_symbol_entries >= self._auto_max_consecutive_per_symbol:
                    self._auto_rotation_wait[symbol] = True
                    self._auto_rotation_other_entries[symbol] = 0
                self._state["auto_status"] = "Ordem DEMO enviada: " + side + " " + symbol + " | rotação de ativos aplicada"
        except Exception as exc:
            self._record_event("entry_error", symbol=symbol, side=side, error=str(exc)[:300])
            with self._lock:
                self._state["auto_status"] = "Entrada bloqueada: " + str(exc)[:140]
            log.warning("Automatic demo entry blocked for %s: %s", symbol, type(exc).__name__)

    def authorize_demo_account(self, account_id: int):
        with self._lock:
            accounts = list(self._state["accounts"])
            client = self._client
            token = self._token
        match = next((a for a in accounts if a["account_id"] == int(account_id)), None)
        if not match:
            raise ValueError("Conta não encontrada na lista autorizada")
        if match["is_live"]:
            raise PermissionError("Conta REAL bloqueada: este robô só permite DEMO")
        if not client or not self._state["application_authorized"] or not token:
            raise RuntimeError("Conexão cTrader ainda não está autorizada")
        with self._lock:
            self._state["selected_account_id"] = int(account_id)
            self._state["account_authorized"] = False
        reactor.callFromThread(self._send_account_auth, int(account_id))
        return {"queued": True, "account_id": int(account_id), "demo_only": True}

    def _send_account_auth(self, account_id: int):
        with self._lock:
            client = self._client
            token = self._token
            ready = bool(self._state.get("connected") and self._state.get("application_authorized"))
        if not client or not token or not ready:
            with self._lock:
                self._state["last_error"] = "Reconexão pendente; conta DEMO será revalidada quando a API voltar"
            return
        req = ProtoOAAccountAuthReq()
        req.ctidTraderAccountId = int(account_id)
        req.accessToken = token
        client.send(req).addErrback(self._on_error)

    def place_demo_market_order(self, symbol: str, side: str, volume_units: int):
        symbol = symbol.upper().strip()
        side = side.upper().strip()
        if side not in {"BUY", "SELL"}:
            raise ValueError("Lado deve ser BUY ou SELL")
        if not isinstance(volume_units, int) or volume_units < 1 or volume_units > 1000:
            raise ValueError("Volume permitido nesta etapa: 1 a 1000 unidades")
        import time
        with self._lock:
            self._state["last_manual_order_at"] = time.time()
            state = dict(self._state)
            client = self._client
            symbol_id = state["symbol_ids"].get(symbol)
        if not client or not state["connected"] or not state["application_authorized"]:
            raise RuntimeError("API cTrader não conectada/autorizada")
        if not state["account_authorized"] or not state["selected_account_id"]:
            raise RuntimeError("Selecione e autorize uma conta DEMO antes da ordem")
        account = next((a for a in state["accounts"] if a["account_id"] == state["selected_account_id"]), None)
        if not account or account["is_live"]:
            raise PermissionError("Somente conta DEMO permitida")
        if not symbol_id:
            raise ValueError("Ativo não encontrado na conta")
        if not state["prices"].get(symbol):
            raise RuntimeError("Aguardando cotação do ativo")
        if int(state.get("open_positions", 0)) >= int(state.get("risk_limits", {}).get("max_positions", 2)):
            raise RuntimeError("Limite de segurança: máximo de 2 posições simultâneas.")
        free_margin = state.get("free_margin")
        min_free_margin = float(state.get("risk_limits", {}).get("min_free_margin", 25.0))
        if free_margin is not None and free_margin < min_free_margin:
            raise RuntimeError("Margem livre abaixo do mínimo de segurança de US$ %.2f." % min_free_margin)
        req = ProtoOANewOrderReq()
        req.ctidTraderAccountId = int(state["selected_account_id"])
        req.symbolId = int(symbol_id)
        req.orderType = ProtoOAOrderType.MARKET
        req.tradeSide = ProtoOATradeSide.BUY if side == "BUY" else ProtoOATradeSide.SELL
        req.volume = int(volume_units) * 100
        # Attach server-side SL/TP to entry request. cTrader expects absolute prices.
        # Open API spot quotes are integer prices scaled by 1e5.
        quote = state["prices"].get(symbol, {})
        raw = quote.get("ask_raw" if side == "BUY" else "bid_raw")
        if not raw:
            raise RuntimeError("Sem cotação válida para calcular SL/TP; entrada bloqueada.")
        digits = int(state.get("symbol_digits", {}).get(symbol, 5))
        # cTrader Open API spot prices use a fixed 1e5 scale, independent of symbol digits.
        entry_price = float(raw) / 100000.0
        sl_distance, tp_distance = self._protection_distances.get(symbol, (None, None))
        if sl_distance is None or tp_distance is None or sl_distance <= 0 or tp_distance <= 0:
            raise RuntimeError("SL/TP não configurados para este ativo; entrada bloqueada.")
        if side == "BUY":
            req.stopLoss = round(entry_price - sl_distance, digits)
            req.takeProfit = round(entry_price + tp_distance, digits)
        else:
            req.stopLoss = round(entry_price + sl_distance, digits)
            req.takeProfit = round(entry_price - tp_distance, digits)
        with self._lock:
            self._state["last_order"] = {"accepted": False, "status": "enviando ordem DEMO com SL/TP", "symbol": symbol, "side": side, "volume_units": volume_units, "stop_loss": req.stopLoss, "take_profit": req.takeProfit}
        self._record_event("order_request", symbol=symbol, side=side, volume_units=volume_units,
            entry_price=entry_price, stop_loss=req.stopLoss, take_profit=req.takeProfit,
            order_source="automatic" if self._auto_enabled else "manual")
        def send():
            client.send(req).addCallbacks(
                lambda msg: self._record_order_response(msg, symbol, side, volume_units),
                self._on_error,
            )
        reactor.callFromThread(send)
        return {"queued": True, "demo_only": True, "symbol": symbol, "side": side, "volume_units": volume_units}

    def _record_order_response(self, message, symbol, side, volume_units):
        payload = Protobuf.extract(message)
        with self._lock:
            order = getattr(payload, "order", None)
            self._state["last_order"] = {
                "accepted": message.payloadType == ProtoOAExecutionEvent().payloadType,
                "symbol": symbol, "side": side, "volume_units": volume_units,
                "order_id": int(order.orderId) if order else None,
                "status": "resposta recebida",
            }
        self._record_event("order_response", symbol=symbol, side=side, volume_units=volume_units,
            accepted=message.payloadType == ProtoOAExecutionEvent().payloadType,
            order_id=int(order.orderId) if order else None)
        return message
