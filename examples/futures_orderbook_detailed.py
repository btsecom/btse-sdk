#!/usr/bin/env python3
"""
Detailed futures orderbook example showing snapshot vs delta processing.

This example demonstrates:
- How the initial SNAPSHOT message is received
- How subsequent DELTA messages update the orderbook
- The structure of each message type
- How the local orderbook cache is maintained
"""

from btse_sdk import BTSEFuturesClient
from btse_sdk.orderbook_cache import ThreadSafeOrderBookCache
import time
import json

# Track message types
message_count = {"snapshot": 0, "delta": 0, "other": 0}
shown_snapshot = False
shown_delta = False

def custom_message_handler(msg, cache):
    """Custom handler to show message details before processing."""
    global shown_snapshot, shown_delta

    topic = msg.get("topic", "")

    # Check if it's an orderbook update
    if "update:" in topic:
        data = msg.get("data", {})
        msg_type = data.get("type", "delta")

        if msg_type == "snapshot":
            message_count["snapshot"] += 1
            if not shown_snapshot:
                print("\n" + "=" * 60)
                print("SNAPSHOT MESSAGE RECEIVED (FUTURES)")
                print("=" * 60)
                print("This is the initial full orderbook state.")
                print(f"Symbol: {data.get('symbol')}")
                print(f"Sequence: {data.get('seqNum')}")
                print(f"Bids: {len(data.get('bids', []))} levels")
                print(f"Asks: {len(data.get('asks', []))} levels")
                print(f"\nTop 3 bids: {data.get('bids', [])[:3]}")
                print(f"Top 3 asks: {data.get('asks', [])[:3]}")
                print("=" * 60 + "\n")
                shown_snapshot = True

        elif msg_type == "delta":
            message_count["delta"] += 1
            if not shown_delta and message_count["delta"] == 1:
                print("\n" + "=" * 60)
                print("DELTA MESSAGE RECEIVED (FUTURES)")
                print("=" * 60)
                print("This is an incremental update to the orderbook.")
                print(f"Symbol: {data.get('symbol')}")
                print(f"Sequence: {data.get('seqNum')}")
                print(f"Previous Sequence: {data.get('prevSeqNum')}")
                print(f"Bid updates: {data.get('bids', [])}")
                print(f"Ask updates: {data.get('asks', [])}")
                print("Note: Size=0 means remove that price level")
                print("=" * 60 + "\n")
                shown_delta = True
    else:
        message_count["other"] += 1

    # Process the message in the cache
    cache.process_message(msg)

def main():
    import config

    api_key, api_secret = config.get_futures_credentials()
    client = BTSEFuturesClient(
        api_key=api_key,
        api_secret=api_secret,
        testnet=config.USE_TESTNET
    )

    symbol = "BTC-PERP"
    grouping = config.ORDERBOOK_GROUPING

    print("Detailed Futures Orderbook Processing Example")
    print("=" * 60)
    print(f"Environment: {config.get_environment_name()}")
    print(f"Symbol: {symbol}")
    print(f"Grouping: {grouping}")
    print("\nThis example will show you:")
    print("1. The initial SNAPSHOT message")
    print("2. Subsequent DELTA messages")
    print("3. How the local orderbook is updated")
    print("\nConnecting...\n")

    # Create cache manually
    cache = ThreadSafeOrderBookCache(symbol)

    # Create stream with custom message handler
    def on_msg(msg):
        custom_message_handler(msg, cache)

    stream = client.ws.orderbook_stream(on_message=on_msg)
    stream.start()
    stream.subscribe_delta(symbol, grouping=grouping)

    print("Waiting for messages...\n")

    try:
        start_time = time.time()
        while time.time() - start_time < 30:  # Run for 30 seconds
            time.sleep(1)

            # Show stats every 5 seconds
            if int(time.time() - start_time) % 5 == 0:
                best_bid = cache.best_bid()
                best_ask = cache.best_ask()

                print(f"\n--- Stats (t={int(time.time() - start_time)}s) ---")
                print(f"Snapshots: {message_count['snapshot']}")
                print(f"Deltas: {message_count['delta']}")
                print(f"Other messages: {message_count['other']}")

                if best_bid and best_ask:
                    print(f"Best Bid: {best_bid.price} ({best_bid.size})")
                    print(f"Best Ask: {best_ask.price} ({best_ask.size})")
                    print(f"Spread: {best_ask.price - best_bid.price:.2f}")

                bids_count = len(cache.levels("bids"))
                asks_count = len(cache.levels("asks"))
                print(f"Orderbook depth: {bids_count} bids, {asks_count} asks")
                print(f"Out of sync: {cache.out_of_sync}")
                print("-" * 40)

    except KeyboardInterrupt:
        pass

    print("\n\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total Snapshots: {message_count['snapshot']}")
    print(f"Total Deltas: {message_count['delta']}")
    print(f"Total Other: {message_count['other']}")
    print("\nThe futures orderbook cache maintained a local copy by:")
    print("1. Starting with the SNAPSHOT (full orderbook)")
    print("2. Applying each DELTA (incremental updates)")
    print("3. Tracking sequence numbers to detect gaps")
    print("=" * 60)

    stream.close()

if __name__ == "__main__":
    main()