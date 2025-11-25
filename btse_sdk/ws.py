# btse_sdk/ws.py
from __future__ import annotations

import json
import threading
import time
import hmac
import hashlib
from typing import Callable, Iterable, Optional, Dict, Any, List

import websocket  # pip install websocket-client

try:
    from ._version import __version__
except ImportError:
    __version__ = "unknown"

MessageHandler = Callable[[dict], None]
ErrorHandler = Callable[[Exception], None]


class BTSEWebSocketBase:
    """
    Thin wrapper around websocket-client's WebSocketApp.

    Supports:
    - subscribe/unsubscribe
    - ping
    - optional automatic authentication (login) for private topics.
    """

    def __init__(
        self,
        url: str,
        on_message: MessageHandler,
        on_error: Optional[ErrorHandler] = None,
        on_close: Optional[Callable[[], None]] = None,
        on_open: Optional[Callable[[], None]] = None,
        *,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        ws_path: Optional[str] = None,
        auto_auth: bool = False,
        auth_op: str = "login",
    ) -> None:
        """
        ws_path should match the *path* part used in signature generation:
          - Spot:    "/ws/spot"
          - Futures: "/ws/futures"
          - OTC:     "/ws/otc"
        Signature = HMAC-SHA384(secret, ws_path + nonce)  [oai_citation:0‡Btsecom](https://btsecom.github.io/docs/streaming/en/)

        auth_op: Authentication operation - "login" for legacy or "authKeyExpires" for Spot v3.3
        """
        self.url = url
        self._on_message_user = on_message
        self._on_error_user = on_error
        self._on_close_user = on_close
        self._on_open_user = on_open

        self._ws: Optional[websocket.WebSocketApp] = None
        self._thread: Optional[threading.Thread] = None
        self._connected = threading.Event()

        self.api_key = api_key
        self.api_secret = api_secret
        self.ws_path = ws_path
        self.auto_auth = auto_auth
        self.auth_op = auth_op

    # --- internal callbacks ---

    def _on_message(self, ws: websocket.WebSocketApp, message: str) -> None:
        try:
            data = json.loads(message)
        except Exception:
            data = {"raw": message}
        self._on_message_user(data)

    def _on_error(self, ws: websocket.WebSocketApp, error: Exception) -> None:
        if self._on_error_user:
            self._on_error_user(error)

    def _on_close(self, ws: websocket.WebSocketApp, *_) -> None:
        self._connected.clear()
        if self._on_close_user:
            self._on_close_user()

    def _on_open(self, ws: websocket.WebSocketApp) -> None:
        self._connected.set()
        # Auto-auth if enabled
        if self.auto_auth and self.api_key and self.api_secret and self.ws_path:
            try:
                self.authenticate()
            except Exception as e:
                if self._on_error_user:
                    self._on_error_user(e)
        if self._on_open_user:
            self._on_open_user()

    # --- auth helpers ---

    @staticmethod
    def _nonce() -> str:
        return str(int(time.time() * 1000))

    def _ws_signature(self, nonce: str) -> str:
        """
        Signature for WebSocket auth: HMAC-SHA384(secret, ws_path + nonce)
        Example for spot: echo -n "/ws/spot1624985375123" | openssl ...  [oai_citation:1‡Btsecom](https://btsecom.github.io/docs/spot/en/?utm_source=chatgpt.com)
        """
        if not (self.api_secret and self.ws_path):
            raise ValueError("api_secret and ws_path are required for WebSocket auth")
        msg = f"{self.ws_path}{nonce}".encode("utf-8")
        secret_bytes = self.api_secret.encode("utf-8")
        return hmac.new(secret_bytes, msg, hashlib.sha384).hexdigest()

    def authenticate(self) -> None:
        """
        Send an authentication message.

        For Spot v3.3:
          {"op": "authKeyExpires", "args": [apiKey, nonce, signature]}

        For legacy/futures:
          {"op": "login", "args": [apiKey, nonce, signature]}

        Signature: HMAC-SHA384(secret, ws_path + nonce)
        """
        if not (self.api_key and self.api_secret and self.ws_path):
            raise ValueError("api_key, api_secret and ws_path must be set to authenticate")

        nonce = self._nonce()
        sign = self._ws_signature(nonce)
        payload = {"op": self.auth_op, "args": [self.api_key, nonce, sign]}
        print(payload)
        self.send_json(payload)

    # --- public API ---

    def start(self) -> None:
        """
        Start the websocket in a background thread.
        """
        headers = {
            "User-Agent": f"btse-sdk-python/{__version__}"
        }
        self._ws = websocket.WebSocketApp(
            self.url,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
            on_open=self._on_open,
            header=headers,
        )
        self._thread = threading.Thread(target=self._ws.run_forever, daemon=True)
        self._thread.start()

    def send_json(self, payload: dict, timeout: float = 5.0) -> None:
        if not self._ws:
            raise RuntimeError("WebSocket is not started; call start() first")
        if not self._connected.wait(timeout=timeout):
            raise TimeoutError(f"WebSocket connection not established within {timeout}s")
        self._ws.send(json.dumps(payload))

    def subscribe(self, topics: Iterable[str]) -> None:
        """
        Generic subscription helper: {"op":"subscribe","args":[...]}  [oai_citation:3‡Btsecom](https://btsecom.github.io/docs/futures/en/)
        """
        self.send_json({"op": "subscribe", "args": list(topics)})

    def unsubscribe(self, topics: Iterable[str]) -> None:
        self.send_json({"op": "unsubscribe", "args": list(topics)})

    def ping(self, timeout: float = 5.0) -> None:
        """
        Send a 'ping' text frame. Server responds 'pong'.  [oai_citation:4‡Btsecom](https://btsecom.github.io/docs/streaming/en/)
        """
        if not self._ws:
            raise RuntimeError("WebSocket is not started; call start() first")
        if not self._connected.wait(timeout=timeout):
            raise TimeoutError(f"WebSocket connection not established within {timeout}s")
        self._ws.send("ping")

    def close(self) -> None:
        if self._ws:
            self._ws.close()
        self._ws = None
        self._thread = None


# ---------- Spot orderbook (OSS) ----------

class SpotOrderBookStream(BTSEWebSocketBase):
    """
    Spot orderbook incremental updates via OSS.

    Endpoints:
      - Prod:    wss://ws.btse.com/ws/oss/spot
      - Testnet: wss://testws.btse.io/ws/oss/spot  [oai_citation:5‡Btsecom](https://btsecom.github.io/docs/futures/en/?utm_source=chatgpt.com)
    """

    def __init__(
        self,
        *,
        testnet: bool = False,
        on_message: MessageHandler,
        on_error: Optional[ErrorHandler] = None,
        on_close: Optional[Callable[[], None]] = None,
        on_open: Optional[Callable[[], None]] = None,
    ) -> None:
        url = "wss://testws.btse.io/ws/oss/spot" if testnet else "wss://ws.btse.com/ws/oss/spot"
        super().__init__(
            url=url,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
            on_open=on_open,
        )

    def subscribe_l1(self, symbol: str) -> None:
        topic = f"snapshotL1:{symbol}"
        self.subscribe([topic])

    def subscribe_delta(self, symbol: str, grouping: int = 0) -> None:
        """
        Incremental updates:
          update:<symbol>_<grouping> (first msg is snapshot, then delta)  [oai_citation:6‡Btsecom](https://btsecom.github.io/docs/futures/en/?utm_source=chatgpt.com)
        """
        topic = f"update:{symbol}_{grouping}"
        self.subscribe([topic])


# ---------- Futures orderbook (OSS) ----------

class FuturesOrderBookStream(BTSEWebSocketBase):
    """
    Futures orderbook incremental updates via OSS.

    Endpoints:
      - Prod:    wss://ws.btse.com/ws/oss/futures
      - Testnet: wss://testws.btse.io/ws/oss/futures  [oai_citation:7‡Btsecom](https://btsecom.github.io/docs/futures/en/)
    """

    def __init__(
        self,
        *,
        testnet: bool = False,
        on_message: MessageHandler,
        on_error: Optional[ErrorHandler] = None,
        on_close: Optional[Callable[[], None]] = None,
        on_open: Optional[Callable[[], None]] = None,
    ) -> None:
        url = "wss://testws.btse.io/ws/oss/futures" if testnet else "wss://ws.btse.com/ws/oss/futures"
        super().__init__(
            url=url,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
            on_open=on_open,
        )

    def subscribe_l1(self, symbol: str, grouping: int = 0) -> None:
        topic = f"snapshotL1:{symbol}_{grouping}"
        self.subscribe([topic])

    def subscribe_delta(self, symbol: str, grouping: int = 0) -> None:
        topic = f"update:{symbol}_{grouping}"
        self.subscribe([topic])


# ---------- Spot public trade stream ----------

class SpotTradeStream(BTSEWebSocketBase):
    """
    Spot public trade fills.

    Endpoint:
      - Prod:    wss://ws.btse.com/ws/spot
      - Testnet: wss://testws.btse.io/ws/spot

    Topic:
      tradeHistoryApi:<symbol> (e.g. tradeHistoryApi:BTC-USD)  [oai_citation:8‡Btsecom](https://btsecom.github.io/docs/spot/en/?utm_source=chatgpt.com)
    """

    def __init__(
        self,
        *,
        testnet: bool = False,
        on_message: MessageHandler,
        on_error: Optional[ErrorHandler] = None,
        on_close: Optional[Callable[[], None]] = None,
        on_open: Optional[Callable[[], None]] = None,
    ) -> None:
        url = "wss://testws.btse.io/ws/spot" if testnet else "wss://ws.btse.com/ws/spot"
        super().__init__(
            url=url,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
            on_open=on_open,
        )

    def subscribe_trades(self, symbol: str) -> None:
        topic = f"tradeHistoryApi:{symbol}"
        self.subscribe([topic])


# ---------- Futures public trade stream ----------

class FuturesTradeStream(BTSEWebSocketBase):
    """
    Futures public trade fills.

    Endpoint:
      - Prod:    wss://ws.btse.com/ws/futures
      - Testnet: wss://testws.btse.io/ws/futures

    Topic:
      tradeHistoryApiV2:<symbol> (e.g. tradeHistoryApiV2:BTC-PERP)  [oai_citation:9‡Btsecom](https://btsecom.github.io/docs/futures/en/)
    """

    def __init__(
        self,
        *,
        testnet: bool = False,
        on_message: MessageHandler,
        on_error: Optional[ErrorHandler] = None,
        on_close: Optional[Callable[[], None]] = None,
        on_open: Optional[Callable[[], None]] = None,
    ) -> None:
        url = "wss://testws.btse.io/ws/futures" if testnet else "wss://ws.btse.com/ws/futures"
        super().__init__(
            url=url,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
            on_open=on_open,
        )

    def subscribe_trades(self, symbol: str) -> None:
        topic = f"tradeHistoryApiV2:{symbol}"
        self.subscribe([topic])


# ---------- AUTHENTICATED STREAMS ----------

class SpotPrivateStream(BTSEWebSocketBase):
    """
    Authenticated Spot WebSocket (private topics).

    Endpoint:
      - Prod:    wss://ws.btse.com/ws/spot (ws_path="/ws/spot")
      - Testnet: wss://testws.btse.io/ws/spot  [oai_citation:10‡BTSE Exchange Demo](https://exchangedemo-docs.btse.co/pages/ws.html?utm_source=chatgpt.com)
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        *,
        testnet: bool = False,
        on_message: MessageHandler,
        on_error: Optional[ErrorHandler] = None,
        on_close: Optional[Callable[[], None]] = None,
        on_open: Optional[Callable[[], None]] = None,
        auto_auth: bool = True,
    ) -> None:
        url = "wss://testws.btse.io/ws/spot" if testnet else "wss://ws.btse.com/ws/spot"
        super().__init__(
            url=url,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
            on_open=on_open,
            api_key=api_key,
            api_secret=api_secret,
            ws_path="/ws/spot",
            auto_auth=auto_auth,
            auth_op="authKeyExpires",  # Spot v3.3 uses authKeyExpires
        )


    def subscribe_topics(self, topics: List[str]) -> None:
        """
        Subscribe to multiple topics at once.

        Args:
            topics: List of topic names to subscribe to
                   e.g., ["notificationApiV3", "fills"]
        """
        self.subscribe(topics)

    def subscribe_notifications(self, version: int = 3) -> None:
        """
        Subscribe to spot trade/order notifications.

        Docs mention notificationApiV2, and newer streaming docs prefer V3.  [oai_citation:11‡Btsecom](https://btsecom.github.io/docs/spot/en/?utm_source=chatgpt.com)
        """
        topic = f"notificationApiV{version}" if version >= 3 else "notificationApiV2"
        self.subscribe([topic])

    def subscribe_fills(self) -> None:
        """
        Subscribe to user trade fills (execution notifications).

        When a trade has been transacted, this topic will send the trade information
        including orderId, clOrderId, symbol, side, price, size, feeAmount, maker status, etc.

        Topic: 'fills'
        """
        self.subscribe(["fills"])


class FuturesPrivateStream(BTSEWebSocketBase):
    """
    Authenticated Futures WebSocket (private topics).

    Endpoint:
      - Prod:    wss://ws.btse.com/ws/futures (ws_path="/ws/futures")
      - Testnet: wss://testws.btse.io/ws/futures  [oai_citation:12‡Btsecom](https://btsecom.github.io/docs/futures/en/)
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        *,
        testnet: bool = False,
        on_message: MessageHandler,
        on_error: Optional[ErrorHandler] = None,
        on_close: Optional[Callable[[], None]] = None,
        on_open: Optional[Callable[[], None]] = None,
        auto_auth: bool = True,
    ) -> None:
        url = "wss://testws.btse.io/ws/futures" if testnet else "wss://ws.btse.com/ws/futures"
        super().__init__(
            url=url,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
            on_open=on_open,
            api_key=api_key,
            api_secret=api_secret,
            ws_path="/ws/futures",
            auto_auth=auto_auth,
        )

    def subscribe_topics(self, topics: List[str]) -> None:
        """
        Subscribe to multiple topics at once.

        Args:
            topics: List of topic names to subscribe to
                   e.g., ["notificationApiV3", "fills", "allPositionV2"]
        """
        self.subscribe(topics)

    def subscribe_notifications(self, version: int = 3) -> None:
        """
        Futures notifications; futures docs map notificationApiV2 -> notificationApiV3 for new symbols.  [oai_citation:13‡Btsecom](https://btsecom.github.io/docs/futures/en/)
        """
        topic = f"notificationApiV{version}" if version >= 3 else "notificationApiV2"
        self.subscribe([topic])

    def subscribe_fills(self, use_v2: bool = True) -> None:
        """
        User trade fills:
          - legacy: 'fills'
          - new naming: 'fillsV2'  [oai_citation:14‡Btsecom](https://btsecom.github.io/docs/futures/en/)
        """
        topic = "fillsV2" if use_v2 else "fills"
        self.subscribe([topic])

    def subscribe_all_positions(self, use_v2: bool = True) -> None:
        """
        All positions:
          - legacy: 'allPosition'
          - new naming: 'allPositionV2'  [oai_citation:15‡Btsecom](https://btsecom.github.io/docs/futures/en/)
        """
        topic = "allPositionV2" if use_v2 else "allPosition"
        self.subscribe([topic])