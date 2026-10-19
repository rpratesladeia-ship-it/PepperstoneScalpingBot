"""Minimal cTrader Open API session bridge. Demo-only; order submission is intentionally not exposed yet."""
import threading
import logging
from typing import Any

log = logging.getLogger("trader-ctrader")

from ctrader_open_api import Client, TcpProtocol, EndPoints, Protobuf
from ctrader_open_api.messages.OpenApiCommonMessages_pb2 import *
from ctrader_open_api.messages.OpenApiMessages_pb2 import *
from ctrader_open_api.messages.OpenApiModelMessages_pb2 import *
from twisted.internet import reactor


class CTraderDemoBridge:
    """One demo connection, account validation, and account authorization."""

    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self._lock = threading.RLock()
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
            "balance": None, "open_positions": 0, "order_execution": False, "last_order": None,
        }
        self._thread = None
        self._auto_enabled = False
        self._auto_last_signal = {}
        self._auto_history = {}
        self._auto_cooldown_seconds = 300
        self._auto_last_trade_at = {}
        self._auto_max_positions = 1
        # Initial DEMO protection distances in absolute price units; review per broker/symbol.
        self._protection_distances = {
            "XAUUSD": (2.0, 3.0),
            "EURUSD": (0.0010, 0.0015),
            "GBPUSD": (0.0010, 0.0015),
            "USDJPY": (0.10, 0.15),
            "BTCUSD": (100.0, 150.0),
            "US30": (10.0, 15.0),
        }

    def snapshot(self):
        with self._lock:
            return dict(self._state)

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
        client = Client(EndPoints.PROTOBUF_DEMO_HOST, EndPoints.PROTOBUF_PORT, TcpProtocol)
        self._client = client
        client.setConnectedCallback(self._on_connected)
        client.setDisconnectedCallback(self._on_disconnected)
        client.setMessageReceivedCallback(self._on_message)
        client.startService()

    def _on_connected(self, client):
        with self._lock:
            self._state["connected"] = True
        req = ProtoOAApplicationAuthReq()
        req.clientId = self.client_id
        req.clientSecret = self.client_secret
        client.send(req).addErrback(self._on_error)

    def _on_disconnected(self, _client, reason):
        with self._lock:
            self._state.update(connected=False, application_authorized=False,
                               account_authorized=False, last_error="Conexão cTrader interrompida")

    def _on_error(self, failure):
        try:
            error_type = failure.type.__name__
        except Exception:
            error_type = "ErroDeTransporte"
        log.warning("cTrader transport failure: %s", error_type)
        with self._lock:
            self._state["last_error"] = "Falha de comunicação (" + error_type + "). Reconecte pelo botão cTrader."
            self._state["application_authorized"] = False
            self._state["account_authorized"] = False
        return None

    def _on_message(self, client, message):
        if message.payloadType == ProtoHeartbeatEvent().payloadType:
            return
        payload = Protobuf.extract(message)
        if message.payloadType == ProtoOAErrorRes().payloadType:
            code = str(getattr(payload, "errorCode", "erro cTrader"))
            # cTrader may answer ALREADY_LOGGED_IN if app auth was already accepted
            # on this transport/session. Treat it as authenticated and continue account discovery.
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
                self._state["last_error"] = "cTrader recusou uma solicitação: " + code
                self._state["account_authorized"] = False
            log.warning("cTrader API error code: %s", code[:100])
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
        elif message.payloadType == ProtoOAAccountAuthRes().payloadType:
            with self._lock:
                self._state["account_authorized"] = True

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
            with self._lock:
                self._state["open_positions"] = len(getattr(payload, "position", []))
        elif message.payloadType == ProtoOASymbolsListRes().payloadType:
            wanted = {"XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "BTCUSD", "US30"}
            found = {}
            for symbol in getattr(payload, "symbol", []):
                name = str(getattr(symbol, "symbolName", "")).upper()
                if name in wanted:
                    found[name] = int(symbol.symbolId)
            with self._lock:
                self._state["symbol_ids"] = found
                self._state["symbols"] = sorted(found.keys())
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
                        self._evaluate_auto_entry(name, history)
        elif message.payloadType == ProtoOAExecutionEvent().payloadType:
            with self._lock:
                order = getattr(payload, "order", None)
                self._state["last_order"] = {"accepted": True, "order_id": int(order.orderId) if order else None, "status": "resposta recebida"}


    def set_auto_trading(self, enabled: bool):
        """Enable only guarded demo entries; never permits a live account."""
        with self._lock:
            if enabled:
                account = next((a for a in self._state["accounts"]
                                if a["account_id"] == self._state["selected_account_id"]), None)
                if not self._state["connected"] or not self._state["application_authorized"] or not self._state["account_authorized"]:
                    raise RuntimeError("Conecte e autorize uma conta DEMO antes de ativar.")
                if not account or account["is_live"]:
                    raise PermissionError("Automação bloqueada: somente conta DEMO.")
                if not self._state["symbols"]:
                    raise RuntimeError("Nenhum ativo disponível para a automação.")
            self._auto_enabled = bool(enabled)
            self._state["auto_trading"] = self._auto_enabled
            self._state["auto_status"] = "Ativo: aguardando cruzamento de médias" if enabled else "Desativado"
        return {"auto_trading": self._auto_enabled, "demo_only": True}

    def _evaluate_auto_entry(self, symbol: str, history):
        # EMA crossover on incoming ticks. Guarded, one position at a time, cooldown.
        if not self._auto_enabled or len(history) < 22:
            return
        import time
        now = time.time()
        with self._lock:
            if not self._state["account_authorized"] or self._state["open_positions"] >= self._auto_max_positions:
                return
            if now - self._auto_last_trade_at.get(symbol, 0) < self._auto_cooldown_seconds:
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
            if not side:
                return
            self._auto_last_trade_at[symbol] = now
            self._state["auto_status"] = "Sinal " + side + " em " + symbol + "; enviando ordem demo"
        try:
            # One minimal unit; this is demo-only and intentionally throttled.
            self.place_demo_market_order(symbol, side, 1)
            with self._lock:
                self._state["auto_status"] = "Ordem DEMO enviada para confirmação: " + side + " " + symbol
        except Exception as exc:
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
        def send_auth():
            req = ProtoOAAccountAuthReq()
            req.ctidTraderAccountId = int(account_id)
            req.accessToken = token
            client.send(req).addErrback(self._on_error)
            with self._lock:
                self._state["selected_account_id"] = int(account_id)
                self._state["account_authorized"] = False
        reactor.callFromThread(send_auth)
        return {"queued": True, "account_id": int(account_id), "demo_only": True}

    def place_demo_market_order(self, symbol: str, side: str, volume_units: int):
        symbol = symbol.upper().strip()
        side = side.upper().strip()
        if side not in {"BUY", "SELL"}:
            raise ValueError("Lado deve ser BUY ou SELL")
        if not isinstance(volume_units, int) or volume_units < 1 or volume_units > 1000:
            raise ValueError("Volume permitido nesta etapa: 1 a 1000 unidades")
        with self._lock:
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
        entry_price = float(raw) / 100000.0
        sl_distance, tp_distance = self._protection_distances.get(symbol, (None, None))
        if sl_distance is None or tp_distance is None or sl_distance <= 0 or tp_distance <= 0:
            raise RuntimeError("SL/TP não configurados para este ativo; entrada bloqueada.")
        if side == "BUY":
            req.stopLoss = round(entry_price - sl_distance, 5)
            req.takeProfit = round(entry_price + tp_distance, 5)
        else:
            req.stopLoss = round(entry_price + sl_distance, 5)
            req.takeProfit = round(entry_price - tp_distance, 5)
        with self._lock:
            self._state["last_order"] = {"accepted": False, "status": "enviando ordem DEMO com SL/TP", "symbol": symbol, "side": side, "volume_units": volume_units, "stop_loss": req.stopLoss, "take_profit": req.takeProfit}
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
        return message
