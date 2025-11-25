# btse_sdk/futures.py
from __future__ import annotations

from typing import Any, Dict, Optional, Union, Callable, Tuple

from .core import BTSEClientBase
from .enums import OrderSide, OrderType, TimeInForce
from .ws import (
    FuturesOrderBookStream,
    FuturesTradeStream,
    FuturesPrivateStream,
)
from .orderbook_cache import ThreadSafeOrderBookCache

StrOrSide = Union[str, OrderSide]
StrOrOrderType = Union[str, OrderType]
StrOrTIF = Union[str, TimeInForce]

WebSocketMessageHandler = Callable[[dict], None]


class BTSEFuturesClient(BTSEClientBase):
    """
    BTSE Futures v2.3 client.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        *,
        testnet: bool = False,
        timeout: float = 10.0,
    ) -> None:
        self.testnet = testnet
        base_url = "https://testapi.btse.io/futures" if testnet else "https://api.btse.com/futures"
        super().__init__(
            api_key=api_key,
            api_secret=api_secret,
            base_url=base_url,
            api_prefix="/api/v2.3",
            timeout=timeout,
        )

        self.ws = FuturesWebSocketFacade(self)

    # ---------- Public REST (unchanged) ----------

    def price(self, symbol: Optional[str] = None) -> Any:
        params: Dict[str, Any] = {}
        if symbol:
            params["symbol"] = symbol
        return self._request("GET", "/price", params=params)

    def orderbook(
        self,
        symbol: str,
        group: Optional[int] = None,
    ) -> Any:
        params: Dict[str, Any] = {"symbol": symbol}
        if group is not None:
            params["group"] = group
        return self._request("GET", "/orderbook", params=params)

    def orderbook_l2(self, symbol: str, depth: Optional[int] = None) -> Any:
        params: Dict[str, Any] = {"symbol": symbol}
        if depth is not None:
            params["depth"] = depth
        return self._request("GET", "/orderbook/L2", params=params)

    def trades(
        self,
        symbol: str,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        before_serial_id: Optional[int] = None,
    ) -> Any:
        params: Dict[str, Any] = {"symbol": symbol}
        if start_time is not None:
            params["startTime"] = start_time
        if end_time is not None:
            params["endTime"] = end_time
        if before_serial_id is not None:
            params["beforeSerialId"] = before_serial_id
        return self._request("GET", "/trades", params=params)

    # ---------- Auth REST (unchanged) ----------

    def wallet(self) -> Any:
        return self._request("GET", "/user/wallet", auth=True)

    def create_order(
        self,
        symbol: str,
        side: StrOrSide,
        order_type: StrOrOrderType,
        size: float,
        price: Optional[float] = None,
        reduce_only: bool = False,
        time_in_force: Optional[StrOrTIF] = None,
        **extra_fields: Any,
    ) -> Any:
        side_str = side.value if isinstance(side, OrderSide) else side
        type_str = order_type.value if isinstance(order_type, OrderType) else order_type

        payload: Dict[str, Any] = {
            "symbol": symbol,
            "side": side_str,
            "type": type_str,
            "size": size,
            "reduceOnly": reduce_only,
        }
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


class FuturesWebSocketFacade:
    """
    High-level websocket helpers attached to BTSEFuturesClient via `client.ws`.
    """

    def __init__(self, client: BTSEFuturesClient) -> None:
        self._client = client

    # --- Orderbook + cache ---

    def orderbook_with_cache(
        self,
        symbol: str,
        grouping: int = 0,
    ) -> Tuple[FuturesOrderBookStream, ThreadSafeOrderBookCache]:
        """
        Convenience helper wired to OSS futures orderbook.
        """
        cache = ThreadSafeOrderBookCache(symbol)

        def on_msg(msg: dict) -> None:
            cache.process_message(msg)

        stream = FuturesOrderBookStream(
            testnet=self._client.testnet,
            on_message=on_msg,
        )
        stream.start()
        stream.subscribe_delta(symbol, grouping=grouping)
        return stream, cache

    def orderbook_stream(
        self,
        on_message: WebSocketMessageHandler,
        *,
        testnet: Optional[bool] = None,
    ) -> FuturesOrderBookStream:
        stream = FuturesOrderBookStream(
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
    ) -> FuturesTradeStream:
        stream = FuturesTradeStream(
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
    ) -> FuturesPrivateStream:
        if not (self._client.api_key and self._client.api_secret):
            raise ValueError("BTSEFuturesClient must be initialized with api_key and api_secret")

        stream = FuturesPrivateStream(
            api_key=self._client.api_key,
            api_secret=self._client.api_secret,
            testnet=self._client.testnet if testnet is None else testnet,
            on_message=on_message,
            auto_auth=auto_auth,
        )
        stream.start()
        return stream