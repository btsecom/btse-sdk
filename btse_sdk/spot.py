# btse_sdk/spot.py
from __future__ import annotations

from typing import Any, Dict, Optional, Union, Callable, Tuple

from .core import BTSEClientBase
from .enums import OrderSide, OrderType, TimeInForce
from .ws import SpotOrderBookStream, SpotTradeStream, SpotPrivateStream
from .orderbook_cache import ThreadSafeOrderBookCache

StrOrSide = Union[str, OrderSide]
StrOrOrderType = Union[str, OrderType]
StrOrTIF = Union[str, TimeInForce]

WebSocketMessageHandler = Callable[[dict], None]


class BTSESpotClient(BTSEClientBase):
    """
    BTSE Spot v3.3 client.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        *,
        testnet: bool = False,
        timeout: float = 10.0,
    ) -> None:
        self.testnet = testnet  # <-- store for WS facade
        base_url = "https://testapi.btse.io/spot" if testnet else "https://api.btse.com/spot"
        super().__init__(
            api_key=api_key,
            api_secret=api_secret,
            base_url=base_url,
            api_prefix="/api/v3.3",
            timeout=timeout,
        )

        # High-level websocket facade
        self.ws = SpotWebSocketFacade(self)

    # ---------- Public endpoints (unchanged) ----------

    def market_summary(self, symbol: Optional[str] = None) -> Any:
        params: Dict[str, Any] = {}
        if symbol:
            params["symbol"] = symbol
        return self._request("GET", "/market_summary", params=params)

    def price(self, symbol: Optional[str] = None) -> Any:
        params: Dict[str, Any] = {}
        if symbol:
            params["symbol"] = symbol
        return self._request("GET", "/price", params=params)

    def orderbook(
        self,
        symbol: str,
        group: Optional[int] = None,
        limit_bids: Optional[int] = None,
        limit_asks: Optional[int] = None,
    ) -> Any:
        params: Dict[str, Any] = {"symbol": symbol}
        if group is not None:
            params["group"] = group
        if limit_bids is not None:
            params["limit_bids"] = limit_bids
        if limit_asks is not None:
            params["limit_asks"] = limit_asks
        return self._request("GET", "/orderbook", params=params)

    def trades(
        self,
        symbol: str,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        count: Optional[int] = None,
    ) -> Any:
        params: Dict[str, Any] = {"symbol": symbol}
        if start_time is not None:
            params["startTime"] = start_time
        if end_time is not None:
            params["endTime"] = end_time
        if count is not None:
            params["count"] = count
        return self._request("GET", "/trades", params=params)

    # ---------- Authenticated trade endpoints (unchanged) ----------

    def create_order(
        self,
        symbol: str,
        side: StrOrSide,
        order_type: StrOrOrderType,
        size: Optional[float] = None,
        price: Optional[float] = None,
        time_in_force: Optional[StrOrTIF] = None,
        **extra_fields: Any,
    ) -> Any:
        side_str = side.value if isinstance(side, OrderSide) else side
        type_str = order_type.value if isinstance(order_type, OrderType) else order_type

        payload: Dict[str, Any] = {
            "symbol": symbol,
            "side": side_str,
            "type": type_str,
        }
        if size is not None:
            payload["size"] = size
        if price is not None:
            payload["price"] = price
        if time_in_force is not None:
            payload["time_in_force"] = (
                time_in_force.value if isinstance(time_in_force, TimeInForce) else time_in_force
            )

        payload.update(extra_fields)
        return self._request("POST", "/order", data=payload, auth=True)

    def query_order(
        self,
        order_id: Optional[str] = None,
        cl_order_id: Optional[str] = None,
    ) -> Any:
        params: Dict[str, Any] = {}
        if order_id:
            params["orderID"] = order_id
        if cl_order_id:
            params["clOrderID"] = cl_order_id
        return self._request("GET", "/order", params=params, auth=True)

    def cancel_order(
        self,
        symbol: str,
        order_id: Optional[str] = None,
        cl_order_id: Optional[str] = None,
    ) -> Any:
        # BTSE API expects parameters in query string for DELETE
        params: Dict[str, Any] = {"symbol": symbol}
        if order_id:
            params["orderID"] = order_id
        if cl_order_id:
            params["clOrderID"] = cl_order_id
        return self._request("DELETE", "/order", params=params, auth=True)

    def open_orders(self, symbol: Optional[str] = None) -> Any:
        params: Dict[str, Any] = {}
        if symbol:
            params["symbol"] = symbol
        return self._request("GET", "/open_orders", params=params, auth=True)

    def trade_history(
        self,
        symbol: str,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        count: Optional[int] = None,
        cl_order_id: Optional[str] = None,
        order_id: Optional[str] = None,
        is_match_symbol: Optional[bool] = None,
    ) -> Any:
        """
        Query user trade history (fills).

        Args:
            symbol: Market symbol (required)
            start_time: Starting time in milliseconds
            end_time: Ending time in milliseconds
            count: Number of records to return
            cl_order_id: Query by custom order ID
            order_id: Query by order ID
            is_match_symbol: Exact match on symbol

        Note: Maximum 7 days within specified interval
        """
        params: Dict[str, Any] = {"symbol": symbol}
        if start_time is not None:
            params["startTime"] = start_time
        if end_time is not None:
            params["endTime"] = end_time
        if count is not None:
            params["count"] = count
        if cl_order_id:
            params["clOrderID"] = cl_order_id
        if order_id:
            params["orderID"] = order_id
        if is_match_symbol is not None:
            params["isMatchSymbol"] = is_match_symbol
        return self._request("GET", "/user/trade_history", params=params, auth=True)

    def fees(self, symbol: Optional[str] = None) -> Any:
        """
        Query account fees.

        Args:
            symbol: Market symbol to filter for specific market (optional)

        Returns:
            Object containing makerFee, takerFee, and symbol
        """
        params: Dict[str, Any] = {}
        if symbol:
            params["symbol"] = symbol
        return self._request("GET", "/user/fees", params=params, auth=True)


class SpotWebSocketFacade:
    """
    High-level websocket helpers attached to BTSESpotClient via `client.ws`.

    Typical usage:

        spot = BTSESpotClient(api_key, api_secret, testnet=True)
        stream, cache = spot.ws.orderbook_with_cache("BTC-USD")
    """

    def __init__(self, client: BTSESpotClient) -> None:
        self._client = client

    # --- Orderbook + cache ---

    def orderbook_with_cache(
        self,
        symbol: str,
        grouping: int = 0,
    ) -> Tuple[SpotOrderBookStream, ThreadSafeOrderBookCache]:
        """
        Convenience helper:
          - creates a ThreadSafeOrderBookCache
          - starts a SpotOrderBookStream
          - wires the stream to feed the cache
          - subscribes to the OSS delta topic for the symbol

        Returns: (stream, cache)
        """
        cache = ThreadSafeOrderBookCache(symbol)

        def on_msg(msg: dict) -> None:
            cache.process_message(msg)

        stream = SpotOrderBookStream(
            testnet=self._client.testnet,
            on_message=on_msg,
        )
        stream.start()
        stream.subscribe_delta(symbol, grouping=grouping)
        return stream, cache

    # --- Raw orderbook stream (no cache) ---

    def orderbook_stream(
        self,
        on_message: WebSocketMessageHandler,
        *,
        testnet: Optional[bool] = None,
    ) -> SpotOrderBookStream:
        """
        Create a raw SpotOrderBookStream, caller manages subscriptions.
        """
        stream = SpotOrderBookStream(
            testnet=self._client.testnet if testnet is None else testnet,
            on_message=on_message,
        )
        stream.start()
        return stream

    # --- Public trades ---

    def trade_stream(
        self,
        symbol: str,
        on_message: WebSocketMessageHandler,
        *,
        testnet: Optional[bool] = None,
    ) -> SpotTradeStream:
        """
        Create & start a SpotTradeStream for a single symbol.
        """
        stream = SpotTradeStream(
            testnet=self._client.testnet if testnet is None else testnet,
            on_message=on_message,
        )
        stream.start()
        stream.subscribe_trades(symbol)
        return stream

    # --- Private / authenticated ---

    def private_stream(
        self,
        on_message: WebSocketMessageHandler,
        *,
        testnet: Optional[bool] = None,
        auto_auth: bool = True,
    ) -> SpotPrivateStream:
        """
        Create & start an authenticated SpotPrivateStream.

        You can then:
          - subscribe to order notifications: stream.subscribe_notifications()
          - subscribe to trade fills: stream.subscribe_fills()
        """
        if not (self._client.api_key and self._client.api_secret):
            raise ValueError("BTSESpotClient must be initialized with api_key and api_secret")

        stream = SpotPrivateStream(
            api_key=self._client.api_key,
            api_secret=self._client.api_secret,
            testnet=self._client.testnet if testnet is None else testnet,
            on_message=on_message,
            auto_auth=auto_auth,
        )
        stream.start()
        return stream