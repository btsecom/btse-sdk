#!/usr/bin/env python3
"""
Live orderbook example for BTSE Futures.

This example:
1. Connects to BTSE OSS websocket for futures
2. Subscribes to orderbook updates (delta stream)
3. Receives initial snapshot
4. Processes incremental delta updates
5. Maintains a local orderbook cache
6. Displays best bid/ask continuously until Ctrl+C
"""

from btse_sdk import BTSEFuturesClient
import time
import sys
import config

def main():
    # Initialize client using centralized config
    api_key, api_secret = config.get_futures_credentials()
    client = BTSEFuturesClient(
        api_key=api_key,
        api_secret=api_secret,
        testnet=config.USE_TESTNET
    )

    symbol = "BTC-PERP"
    grouping = config.ORDERBOOK_GROUPING

    print(f"Environment: {config.get_environment_name()}")
    print(f"Connecting to BTSE Futures orderbook stream for {symbol}...")
    print(f"Grouping level: {grouping}")
    print("=" * 60)

    # Create orderbook stream with cache
    # - The first message will be a snapshot (type='snapshot')
    # - Subsequent messages will be deltas (type='delta')
    # - The cache automatically handles both types
    stream, cache = client.ws.orderbook_with_cache(symbol, grouping=grouping)

    print("Waiting for initial snapshot...")
    time.sleep(1)  # Give time for initial snapshot

    print("\nLive Futures Orderbook (Press Ctrl+C to stop)")
    print("-" * 60)

    update_count = 0
    last_bid = None
    last_ask = None

    try:
        while True:
            best_bid = cache.best_bid()
            best_ask = cache.best_ask()

            # Only print when data changes or every 10 iterations
            if best_bid and best_ask:
                bid_changed = last_bid is None or last_bid.price != best_bid.price
                ask_changed = last_ask is None or last_ask.price != best_ask.price

                if bid_changed or ask_changed or update_count % 10 == 0:
                    mid = cache.mid_price()
                    spread = best_ask.price - best_bid.price if mid else 0
                    spread_bps = (spread / mid * 10000) if mid else 0

                    print(f"\rBid: {best_bid.price:>10.2f} ({best_bid.size:>8.5f}) | "
                          f"Ask: {best_ask.price:>10.2f} ({best_ask.size:>8.5f}) | "
                          f"Mid: {mid:>10.2f} | "
                          f"Spread: {spread:.2f} ({spread_bps:.1f}bps)",
                          end='', flush=True)

                    last_bid = best_bid
                    last_ask = best_ask

                update_count += 1

            # Check if orderbook is out of sync
            if cache.out_of_sync:
                print("\n⚠️  WARNING: Orderbook out of sync! Consider reconnecting.")
                cache.reset()

            time.sleep(config.UPDATE_INTERVAL)

    except KeyboardInterrupt:
        print("\n\n" + "=" * 60)
        print("Shutting down...")

        # Show final orderbook state
        print(f"\nFinal orderbook depth (top 5 levels):")
        print("\nBIDS:")
        for level in cache.levels("bids", depth=5):
            print(f"  {level.price:>10.2f}  {level.size:>10.5f}")

        print("\nASKS:")
        for level in cache.levels("asks", depth=5):
            print(f"  {level.price:>10.2f}  {level.size:>10.5f}")

        print(f"\nTotal updates processed: {update_count}")
        stream.close()
        print("Connection closed.")
        sys.exit(0)

if __name__ == "__main__":
    main()