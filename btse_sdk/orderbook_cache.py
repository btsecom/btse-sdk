# btse_sdk/orderbook_cache.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional, Literal, Any
import threading


Side = Literal["bids", "asks"]


@dataclass
class Level:
    price: float
    size: float


class OSSOrderBookCache:
    """
    In-memory L2 orderbook built from BTSE OSS messages (spot or futures).
    (Same as before – unchanged, just included here for context.)
    """

    def __init__(self, symbol: str) -> None:
        self.symbol = symbol
        self.bids: Dict[float, float] = {}
        self.asks: Dict[float, float] = {}
        self.seq_num: Optional[int] = None
        self.prev_seq_num: Optional[int] = None
        self.out_of_sync: bool = False

    @staticmethod
    def _apply_levels(side_book: Dict[float, float], levels: List[List[str]]) -> None:
        for price_str, size_str in levels:
            price = float(price_str)
            size = float(size_str)
            if size == 0.0:
                side_book.pop(price, None)
            else:
                side_book[price] = size

    def _update_seq(self, seq: Optional[int], prev_seq: Optional[int]) -> None:
        if seq is None:
            return
        if self.seq_num is not None and prev_seq is not None:
            if prev_seq != self.seq_num:
                self.out_of_sync = True
        self.prev_seq_num = prev_seq
        self.seq_num = seq

    def reset(self) -> None:
        self.bids.clear()
        self.asks.clear()
        self.seq_num = None
        self.prev_seq_num = None
        self.out_of_sync = False

    def process_message(self, msg: Dict[str, Any]) -> None:
        topic = msg.get("topic", "")
        if "update:" not in topic and "snapshotL1:" not in topic:
            return

        data = msg.get("data")
        if not isinstance(data, dict):
            return

        symbol = data.get("symbol")
        if symbol and symbol != self.symbol:
            return

        ob_type = data.get("type", "delta")
        bids = data.get("bids") or []
        asks = data.get("asks") or []
        seq = data.get("seqNum")
        prev_seq = data.get("prevSeqNum")

        if ob_type in ("snapshot", "snapshotL1"):
            self.reset()
            self._apply_levels(self.bids, bids)
            self._apply_levels(self.asks, asks)
        elif ob_type == "delta":
            self._apply_levels(self.bids, bids)
            self._apply_levels(self.asks, asks)
        else:
            return

        self._update_seq(seq, prev_seq)

    def _sorted_side(self, side: Side) -> List[Level]:
        book = self.bids if side == "bids" else self.asks
        reverse = side == "bids"
        return [Level(price=p, size=book[p]) for p in sorted(book.keys(), reverse=reverse)]

    def levels(self, side: Side, depth: Optional[int] = None) -> List[Level]:
        lvls = self._sorted_side(side)
        return lvls if depth is None else lvls[:depth]

    def best_bid(self) -> Optional[Level]:
        lvls = self.levels("bids", depth=1)
        return lvls[0] if lvls else None

    def best_ask(self) -> Optional[Level]:
        lvls = self.levels("asks", depth=1)
        return lvls[0] if lvls else None

    def mid_price(self) -> Optional[float]:
        bid = self.best_bid()
        ask = self.best_ask()
        if not bid or not ask:
            return None
        return (bid.price + ask.price) / 2.0


class ThreadSafeOrderBookCache:
    """
    Thread-safe wrapper around OSSOrderBookCache.

    - All reads/writes protected by an RLock.
    - You can safely feed messages from a websocket thread
      and read from another thread (e.g. your trading loop).
    """

    def __init__(self, symbol: str) -> None:
        self._cache = OSSOrderBookCache(symbol)
        self._lock = threading.RLock()

    @property
    def symbol(self) -> str:
        return self._cache.symbol

    @property
    def out_of_sync(self) -> bool:
        with self._lock:
            return self._cache.out_of_sync

    def reset(self) -> None:
        with self._lock:
            self._cache.reset()

    def process_message(self, msg: Dict[str, Any]) -> None:
        with self._lock:
            self._cache.process_message(msg)

    def levels(self, side: Side, depth: Optional[int] = None) -> List[Level]:
        with self._lock:
            return self._cache.levels(side, depth)

    def best_bid(self) -> Optional[Level]:
        with self._lock:
            return self._cache.best_bid()

    def best_ask(self) -> Optional[Level]:
        with self._lock:
            return self._cache.best_ask()

    def mid_price(self) -> Optional[float]:
        with self._lock:
            return self._cache.mid_price()

    def snapshot(self, depth: Optional[int] = None) -> Dict[str, List[Level]]:
        """
        Convenience method to grab both sides at once.
        """
        with self._lock:
            return {
                "bids": self._cache.levels("bids", depth),
                "asks": self._cache.levels("asks", depth),
            }