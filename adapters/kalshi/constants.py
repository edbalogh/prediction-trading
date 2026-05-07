from nautilus_trader.model.identifiers import Venue

KALSHI_VENUE = Venue("KALSHI")

KALSHI_BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"
KALSHI_DEMO_URL = "https://demo-api.kalshi.co/trade-api/v2"

PRICE_PRECISION = 2      # Kalshi prices are cents: 0.01 to 1.00
SIZE_PRECISION = 0       # Contracts are whole numbers
PRICE_INCREMENT = 0.01
SIZE_INCREMENT = 1
