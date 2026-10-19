"""Minimal cTrader Open API session bridge. Demo-only; order submission is intentionally not exposed yet."""
import threading
from typing import Any

from ctrader_open_api import Client, TcpProtocol, EndPoints, Protobuf
from ctrader_open_api.messages.OpenApiMessages_pb2 import (
    ProtoOAApplicationAuthReq,
    ProtoOAApplicationAuthRes,
    ProtoOAGetAccountListByAccessTokenReq,
    ProtoOAGetAccountListByAccessTokenRes,
    ProtoOAAccountAuthReq,
    ProtoOAAccountAuthRes,
    ProtoHeartbeatEvent,
)
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
        }
        self._thread = None

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

    def _on_error(self, _failure):
        with self._lock:
            self._state["last_error"] = "Falha na comunicação com a API cTrader"
        return None

    def _on_message(self, client, message):
        if message.payloadType == ProtoHeartbeatEvent().payloadType:
            return
        payload = Protobuf.extract(message)
        if message.payloadType == ProtoOAApplicationAuthRes().payloadType:
            with self._lock:
                self._state["application_authorized"] = True
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
                self._state["account_validated"] = bool(accounts) and all(not a["is_live"] for a in accounts)
                self._state["last_error"] = None if accounts else "Nenhuma conta retornada pelo cTrader"
        elif message.payloadType == ProtoOAAccountAuthRes().payloadType:
            with self._lock:
                self._state["account_authorized"] = True

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
