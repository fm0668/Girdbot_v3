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
        """为交易对设置杠杆和保证金模式"""
        try:
            print(f"正在设置永续合约市场：{self.config.pair}")

            # 设置持仓模式为双向持仓
            try:
                await self.exchange.set_position_mode(True)  # True = 双向持仓模式
                print("持仓模式已设置为双向持仓")
            except Exception as e:
                print(f"持仓模式设置失败（可能已经设置）：{e}")

            # CCXT统一方法设置保证金模式为 ISOLATED (逐仓)
            await self.exchange.set_margin_mode('ISOLATED', self.config.pair)
            print(f"{self.config.pair} 的保证金模式已设置为逐仓")

            # CCXT统一方法设置杠杆
            await self.exchange.set_leverage(self.config.leverage, self.config.pair)
            print(f"{self.config.pair} 的杠杆已设置为 {self.config.leverage}x")

        except Exception as e:
            print(f"致命错误：设置杠杆或保证金模式失败。错误：{e}")
            # 在真实应用中，这里应该抛出异常，让程序停止
            raise e

    async def fetch_ticker(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """获取当前价格信息"""
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
            print(f"监控订单时出错：{e}")
            return []

    async def fetch_positions(self, symbols: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """获取所有开放持仓"""
        return await self.exchange.fetch_positions(symbols)

    async def create_market_close_order(self, symbol: str, position_side: str, amount: Decimal, params: Dict[str, Any] = {}):
        """创建市价单来平仓
        Args:
            symbol: 交易对
            position_side: 持仓方向 ('long' 或 'short')
            amount: 持仓数量
            params: 额外参数，应包含 positionSide
        """
        # 平仓时，我们在相反方向创建订单
        if position_side.lower() == 'long':
            # 平多仓：卖出
            return await self.exchange.create_market_sell_order(symbol, float(amount), params)
        else:
            # 平空仓：买入
            return await self.exchange.create_market_buy_order(symbol, float(amount), params)

    async def close(self):
        """Close exchange connection."""
        await self.exchange.close()
