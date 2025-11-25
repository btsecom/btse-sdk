# BTSE Python SDK

A Python SDK for BTSE Spot and Futures trading APIs with WebSocket support.

## Features

- **Spot Trading**: Full REST API support for BTSE Spot market
- **Futures Trading**: Complete REST API support for BTSE Futures market
- **WebSocket Streams**: Real-time orderbook, trades, and private account data
- **Orderbook Management**: Built-in orderbook cache with automatic snapshot/delta handling
- **Type Safety**: Full type hints and enums for better IDE support
- **Testnet Support**: Safe testing environment before going live
- **Authentication**: Secure HMAC-SHA384 request signing

## Installation

```bash
# Install from source
git clone https://github.com/btsecom/btse-sdk.git
cd btse-sdk
pip install -e .
```

## Quick Start

### Spot Market Example

```python
from btse_sdk import BTSESpotClient, OrderSide, OrderType

# Initialize client
client = BTSESpotClient(
    api_key="your_api_key",
    api_secret="your_api_secret",
    testnet=True  # Always start with testnet!
)

# Get current price
price = client.price("BTC-USD")
print(f"BTC-USD: {price}")

# Create an order
order = client.create_order(
    symbol="BTC-USD",
    side=OrderSide.BUY,
    order_type=OrderType.LIMIT,
    size=0.001,
    price=30000
)
```

### Futures Market Example

```python
from btse_sdk import BTSEFuturesClient, OrderSide, OrderType

client = BTSEFuturesClient(
    api_key="your_api_key",
    api_secret="your_api_secret",
    testnet=True
)

# Create perpetual futures order
order_response = client.create_order(
    symbol="BTC-PERP",
    side=OrderSide.BUY,
    order_type=OrderType.LIMIT,
    size=10,
    price=35000
)
```

### WebSocket Orderbook Example

```python
from btse_sdk import BTSESpotClient
import time

client = BTSESpotClient(testnet=True)

# Create orderbook stream with built-in cache
stream, cache = client.ws.orderbook_with_cache("BTC-USD")

time.sleep(2)  # Wait for snapshot

# Read orderbook data
best_bid = cache.best_bid()
best_ask = cache.best_ask()
mid_price = cache.mid_price()
spread = cache.spread()

print(f"Mid: {mid_price}, Spread: {spread}")
```

### WebSocket Private Feeds

```python
from btse_sdk import BTSESpotClient
import time

def handle_message(msg):
    print(f"Message: {msg}")

client = BTSESpotClient(
    api_key="your_key",
    api_secret="your_secret",
    testnet=True
)

stream = client.ws.private_stream(
    on_message=handle_message,
    auto_auth=False
)

stream.authenticate()
time.sleep(1)
stream.subscribe_topics(["notificationApiV3", "fills"])

while True:
    time.sleep(1)
```

## Examples

For comprehensive examples and usage patterns, see the [btse-sdk-examples](https://github.com/yourname/btse-sdk-examples) repository.

## API Overview

### Spot Client Methods

**Public endpoints:**
- `market_summary(symbol)` - Market statistics
- `price(symbol)` - Current price
- `orderbook(symbol, group, limit_bids, limit_asks)` - Orderbook snapshot
- `trades(symbol, start_time, end_time, count)` - Recent trades

**Authenticated endpoints:**
- `create_order(symbol, side, order_type, size, price, ...)` - Place order
- `query_order(order_id, cl_order_id)` - Get order status
- `cancel_order(symbol, order_id, cl_order_id)` - Cancel order
- `open_orders(symbol)` - List open orders
- `trade_history(symbol, start_time, end_time, ...)` - User trade history
- `fees(symbol)` - Account fee rates

### Futures Client Methods

**Public endpoints:**
- `market_summary(symbol)` - Market statistics
- `price(symbol)` - Current price
- `orderbook(symbol, depth)` - Orderbook snapshot
- `trades(symbol, start_time, end_time, count)` - Recent trades
- `funding_history(symbol, start_time, end_time)` - Funding rates

**Authenticated endpoints:**
- `create_order(symbol, side, order_type, size, price, ...)` - Place order
- `query_order(order_id, cl_order_id)` - Get order status
- `cancel_order(symbol, order_id, cl_order_id)` - Cancel order
- `cancel_all_orders(symbol)` - Cancel all orders for symbol
- `open_orders(symbol)` - List open orders
- `wallet(currency)` - Get wallet balance
- `positions(symbol)` - Get open positions

### WebSocket Methods

**Public streams:**
- `ws.orderbook_with_cache(symbol, grouping)` - Orderbook with auto cache
- `ws.orderbook_stream(on_message)` - Raw orderbook stream
- `ws.trade_stream(symbol, on_message)` - Public trades

**Private streams (authenticated):**
- `ws.private_stream(on_message, auto_auth)` - Authenticated stream
  - `.subscribe_notifications(version)` - Order updates
  - `.subscribe_fills()` - Trade execution notifications
  - `.subscribe_topics(topics)` - Subscribe to multiple topics at once

## Authentication

BTSE uses HMAC-SHA384 for request signing. The SDK handles all authentication automatically.

### Quick Authentication Test

```python
from btse_sdk import BTSEFuturesClient, OrderSide, OrderType

client = BTSEFuturesClient(
    api_key="your_key",
    api_secret="your_secret",
    testnet=True
)

try:
    result = client.create_order(
        symbol="BTC-PERP",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        size=10,
        price=1000,  # Far below market
    )
    print("✅ Authentication successful!")
except Exception as e:
    if "signature" in str(e).lower():
        print("❌ Signature error - authentication failed")
    else:
        print(f"✅ Authentication passed (other error: {e})")
```

## Orderbook Cache

The `ThreadSafeOrderBookCache` handles snapshot/delta updates automatically:

```python
# Access orderbook data
best_bid = cache.best_bid()        # (price, size)
best_ask = cache.best_ask()        # (price, size)
mid_price = cache.mid_price()      # float
spread_abs = cache.spread()        # float
spread_bps = cache.spread_bps()    # float (basis points)

# Get multiple levels
top_10_bids = cache.levels("bids", depth=10)
top_10_asks = cache.levels("asks", depth=10)

# Check sync status
if cache.out_of_sync:
    cache.reset()
```

## Security Best Practices

### ✅ DO:

- Use environment variables for API keys
- Start with testnet (`testnet=True`)
- Use separate API keys for testnet and production
- Restrict API key permissions
- Set IP whitelist in BTSE account settings
- Rotate API keys periodically

### ❌ DON'T:

- Hardcode API keys in source code
- Commit credentials to version control
- Share API secrets
- Grant unnecessary permissions
- Use production keys in testnet mode
- Log API secrets

## Troubleshooting

### Authentication Errors

**"Invalid signature"**
- Ensure you're using the correct API key and secret
- Check that your system clock is synchronized

**"Nonce too old" or "Nonce too new"**
- Synchronize your system time:
  ```bash
  # Linux
  sudo ntpdate -s time.nist.gov

  # macOS
  sudo sntp -sS time.apple.com
  ```

### WebSocket Issues

**Empty orderbook**
- Wait 1-2 seconds after subscribing for the initial snapshot

**Out of sync orderbook**
- Check `cache.out_of_sync`
- Call `cache.reset()` or reconnect

## API Reference

- [BTSE Spot API Documentation](https://btsecom.github.io/docs/spotV3_3/en/)
- [BTSE Futures API Documentation](https://btsecom.github.io/docs/futures/en/)
- [BTSE WebSocket Documentation](https://btsecom.github.io/docs/streaming/en/)

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

See [LICENSE](LICENSE) file for details.

## Support

- **Examples**: See [btse-sdk-examples](https://github.com/btsecom/btse-sdk/tree/main/examples)
- **Issues**: Open an issue on GitHub
- **Documentation**: Check the API reference links above
- **BTSE Support**: [support@btse.com](mailto:support@btse.com)

## Changelog

### v0.1.0 (2024-11-25)

- ✅ Initial release
- ✅ Spot and Futures REST API support
- ✅ WebSocket streams (public and private)
- ✅ Orderbook cache with snapshot/delta handling
- ✅ Full type hints and enums
- ✅ Testnet support