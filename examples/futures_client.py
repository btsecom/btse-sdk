from btse_sdk import BTSEFuturesClient, OrderSide, OrderType
import config
import time
import threading
from queue import Queue

api_key, api_secret = config.get_futures_credentials()
client = BTSEFuturesClient(
    api_key=api_key,
    api_secret=api_secret,
    testnet=config.USE_TESTNET
)


# --- WebSocket Thread Setup ---
print("=" * 60)
print("Setting up WebSocket feeds in separate thread...")
print("=" * 60)

# Message queue for thread-safe communication
ws_message_queue = Queue()
ws_running = threading.Event()
ws_running.set()


def handle_websocket_message(msg):
    """Handle all WebSocket messages - notifications and fills"""
    # Log authentication responses

    if msg['topic'] == 'notificationApiV3':
        print (f"Notification Received {msg['data']}")
    elif msg['topic'] == 'fills':
        print (f"Fills Recieved {msg['data']}")
    else:
        print (msg)


def websocket_thread_func():
    """WebSocket thread function - manages single websocket connection"""
    print("[WS THREAD] Starting WebSocket connection...")

    # Create a single private websocket stream (without auto_auth)
    ws_stream = client.ws.private_stream(
        on_message=handle_websocket_message,
        auto_auth=False  # Manual authentication
    )

    # Perform authentication explicitly
    print("[WS THREAD] Authenticating...")
    ws_stream.authenticate()
    time.sleep(1)  # Give time for auth response

    # Subscribe to both topics after authentication
    print("[WS THREAD] Subscribing to notificationApiV3, fills")

    ws_stream.subscribe_topics(['notificationApiV3', 'fills'])

    print("[WS THREAD] WebSocket connected, authenticated, and subscribed to both topics")

    # Keep the thread alive while ws_running is set
    try:
        while ws_running.is_set():
            time.sleep(1)
    except Exception as e:
        print(f"[WS THREAD] Error: {e}")
    finally:
        print("[WS THREAD] Closing stream...")
        ws_stream.close()
        print("[WS THREAD] Stream closed")


# Start WebSocket thread
ws_thread = threading.Thread(target=websocket_thread_func, daemon=False, name="WebSocketThread")
ws_thread.start()

print("WebSocket thread started!\n")
time.sleep(5)  # Give streams time to connect and authenticate

print("=" * 60)
print("Executing REST API calls...")
print("=" * 60)


# --- Public REST ---
print("Futures price:", client.price("BTC-PERP"))
print("Orderbook L2:", client.orderbook_l2("BTC-PERP", depth=5))

print ("\nPlace Order")
# --- Auth REST ---
order_response = client.create_order(
    symbol="BTC-PERP",
    side=OrderSide.BUY,
    order_type=OrderType.LIMIT,
    size=10,
    price=1000,
    reduce_only=False,
)
print("Created order response:", order_response)

# BTSE Futures API returns a list of orders
if isinstance(order_response, list) and len(order_response) > 0:
    order = order_response[0]
    order_id = order.get("orderID") or order.get("order_id")

    print(f"\nOrder created successfully!")
    print(f"Order ID: {order_id}")
    print(f"Full order: {order}")

    # Query
    print("\nQuerying order...")
    print("Order query:", client.query_order(order_id=order_id))

    # Cancel
    print(f"\nCancelling order...{order_id}")
    print("Cancel:", client.cancel_order("BTC-PERP", order_id=order_id))
else:
    print("Unexpected response format:", order_response)


# --- Keep listening for WebSocket messages ---
print("\n" + "=" * 60)
print("Listening for WebSocket messages...")
print("(Order notifications and fills will appear above)")
print("Waiting 10 seconds to capture any pending messages...")
print("=" * 60)

try:
    time.sleep(10)
except KeyboardInterrupt:
    print("\nInterrupted by user")

# Cleanup - Signal WebSocket thread to stop
print("\n" + "=" * 60)
print("Shutting down WebSocket thread...")
print("=" * 60)

ws_running.clear()  # Signal thread to stop
ws_thread.join(timeout=5)  # Wait for thread to finish

if ws_thread.is_alive():
    print("[MAIN] WebSocket thread did not stop cleanly")
else:
    print("[MAIN] WebSocket thread stopped successfully")

print("Done!")