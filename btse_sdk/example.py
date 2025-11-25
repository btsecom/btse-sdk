from btse_sdk.spot import BTSESpotClient
from btse_sdk.enums import OrderSide, OrderType, TimeInForce

spot = BTSESpotClient(api_key, api_secret, testnet=True)

order = spot.create_order(
    symbol="BTC-USD",
    side=OrderSide.BUY,
    order_type=OrderType.LIMIT,
    size=0.001,
    price=30000,
    time_in_force=TimeInForce.GTC,
)
print(order)