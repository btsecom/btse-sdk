# btse_sdk/enums.py
from __future__ import annotations

from enum import Enum


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    """
    Common order types for BTSE.

    This is a subset of what BTSE supports; you can add more as needed,
    but the strings must match the API docs exactly.
    """

    LIMIT = "LIMIT"
    MARKET = "MARKET"

    # Advanced / conditional orders (check docs for availability & params)
    STOP_LIMIT = "STOP_LIMIT"
    STOP_MARKET = "STOP_MARKET"
    TAKE_PROFIT_LIMIT = "TAKE_PROFIT_LIMIT"
    TAKE_PROFIT_MARKET = "TAKE_PROFIT_MARKET"
    TRAILING_STOP_MARKET = "TRAILING_STOP_MARKET"
    TWAP = "TWAP"
    OCO = "OCO"
    INDEX = "INDEX"


class TimeInForce(str, Enum):
    """
    time_in_force values used by BTSE.

    Spot / futures docs mention the usual GTC/IOC/FOK plus HALFMIN.  [oai_citation:2‡Btsecom](https://btsecom.github.io/docs/spot/en/?utm_source=chatgpt.com)
    """

    GTC = "GTC"       # Good till cancel
    IOC = "IOC"       # Immediate or cancel
    FOK = "FOK"       # Fill or kill
    GTT = "GTT"       # Good till time (BTSE-specific behaviour, see docs)
    HALFMIN = "HALFMIN"