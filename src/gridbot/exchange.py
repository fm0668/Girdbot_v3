from decimal import Decimal
import ccxt.pro as ccxtpro
from typing import Optional, List, Dict, Any
from .models import BotConfig, Trade


class ExchangeInterface:
    def __init__(self, config: BotConfig):
        self.config = config
        self.exchange = self._initialize_exchange()
        self.markets = {}
        self.current_price: Optional[Decimal] = None
        self.balance: Optional[Dict[str, Any]] = None

    def _initialize_exchange(self) -> ccxtpro.Exchange:
        """Initialize the exchange with configuration settings."""
        exchange_class = getattr(ccxtpro, self.config.exchange)
        exchange = exchange_class({
            'apiKey': self.config.api_key,
            'secret': self.config.api_secret,
            # --- THIS IS THE KEY CHANGE ---
            'options': {'defaultType': self.config.market_type}
        })
        exchange.options['ws']['useMessageQueue'] = True

        if self.config.sandbox_mode:
            exchange.set_sandbox_mode(True)

        exchange.new_updates = True

        return exchange

    async def initialize(self):
        """Load markets and other initialization tasks."""
        self.markets = await self.exchange.fetch_markets()

    async def set_leverage_and_margin_mode(self):
        """Set leverage and margin mode for the trading pair."""
        try:
            print(f"Setting up for perpetuals market: {self.config.pair}")

            # 设置持仓模式为双向持仓
            try:
                await self.exchange.set_position_mode(True)  # True = 双向持仓模式
                print("Position mode set to Hedge (Two-way).")
            except Exception as e:
                print(f"Position mode setting failed (may already be set): {e}")

            # CCXT统一方法设置保证金模式为 ISOLATED (逐仓)
            await self.exchange.set_margin_mode('ISOLATED', self.config.pair)
            print(f"Margin mode for {self.config.pair} set to ISOLATED.")

            # CCXT统一方法设置杠杆
            await self.exchange.set_leverage(self.config.leverage, self.config.pair)
            print(f"Leverage for {self.config.pair} set to {self.config.leverage}x.")

        except Exception as e:
            print(f"FATAL: Failed to set leverage or margin mode. Error: {e}")
            # 在真实应用中，这里应该抛出异常，让程序停止
            raise e

    async def fetch_ticker(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """Fetch current ticker information."""
        symbol = symbol or self.config.pair
        ticker = await self.exchange.fetch_ticker(symbol)
        self.current_price = Decimal(str(ticker['last']))
        return ticker

    async def watch_ticker(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """Watch for ticker updates."""
        symbol = symbol or self.config.pair
        return await self.exchange.watch_ticker(symbol)

    async def create_limit_buy_order(self, amount: Decimal, price: Decimal, params: Dict[str, Any] = {}) -> Dict[str, Any]:
        """Create a limit buy order."""
        return await self.exchange.create_limit_buy_order(
            self.config.pair,
            float(amount),
            float(price),
            params  # Pass extra params here
        )

    async def create_limit_sell_order(self, amount: Decimal, price: Decimal, params: Dict[str, Any] = {}) -> Dict[str, Any]:
        """Create a limit sell order."""
        return await self.exchange.create_limit_sell_order(
            self.config.pair,
            float(amount),
            float(price),
            params  # Pass extra params here
        )

    async def create_market_buy_order(self, amount: Decimal) -> Dict[str, Any]:
        """Create a market buy order."""
        return await self.exchange.create_market_buy_order(
            self.config.pair,
            float(amount)
        )

    async def create_market_sell_order(self, amount: Decimal) -> Dict[str, Any]:
        """Create a market sell order."""
        return await self.exchange.create_market_sell_order(
            self.config.pair,
            float(amount)
        )

    async def fetch_open_orders(self) -> List[Dict[str, Any]]:
        """Fetch all open orders."""
        return await self.exchange.fetch_open_orders(self.config.pair)

    async def fetch_order(self, order_id: str) -> Dict[str, Any]:
        """Fetch a specific order by ID."""
        return await self.exchange.fetch_order(order_id, self.config.pair)

    async def cancel_order(self, order_id: str) -> Dict[str, Any]:
        """Cancel a specific order by ID."""
        return await self.exchange.cancel_order(order_id, self.config.pair)

    async def fetch_balance(self) -> Dict[str, Any]:
        """Fetch account balance."""
        return await self.exchange.fetch_balance()

    async def watch_orders(self) -> List[Dict[str, Any]]:
        """Watch for completed order updates."""
        try:
            orders = await self.exchange.watch_orders(self.config.pair)
            return orders

        except Exception as e:
            print(f"Error in watch_orders: {e}")
            return []

    async def close(self):
        """Close exchange connection."""
        await self.exchange.close()
