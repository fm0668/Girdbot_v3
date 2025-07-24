import asyncio
import json
import signal
import os
import re
from typing import Optional
from decimal import Decimal
from datetime import datetime, timedelta
from dotenv import load_dotenv

from .models import BotConfig, Trade
from .exchange import ExchangeInterface
from .strategy import GridStrategy
from .websocket import WebSocketManager


class GridBot:
    def __init__(self, config_path: Optional[str] = None, fresh_start: bool = False):
        self.config = self._load_config(config_path)
        self.fresh_start = fresh_start
        self.exchange = ExchangeInterface(self.config)
        self.strategy = GridStrategy(self.config, self.exchange)
        self.ws_manager = WebSocketManager(self.config)
        self.current_price = Decimal("0")
        self.last_price = Decimal("0")
        self.running = True
        self.tasks = []
        self._setup_signal_handlers()

    @staticmethod
    def _load_config(config_path: Optional[str] = None) -> BotConfig:
        """Load and validate configuration from JSON file with environment variable substitution"""
        load_dotenv()

        if not config_path:
            return BotConfig.from_env()

        with open(config_path, 'r') as f:
            config_content = f.read()

        def replace_env_vars(match):
            env_var = match.group(1)
            value = os.getenv(env_var)
            if value is None:
                raise ValueError(f"Environment variable {env_var} not found.")
            return value

        config_content = re.sub(r'\$\{([^}]+)\}', replace_env_vars, config_content)
        config_data = json.loads(config_content)

        # Let Pydantic handle all type conversions and validation
        return BotConfig(**config_data)

    def _setup_signal_handlers(self):
        """设置优雅关闭的信号处理器"""
        def handle_signal(signum, frame):
            print("\n收到关闭信号，正在清理...")
            self.running = False
            self._cancel_tasks()

        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)

    async def initialize(self):
        """Initialize bot components."""
        # Initialize exchange
        await self.exchange.initialize()

        # --- ADD THIS BLOCK ---
        if self.config.market_type == 'future':
            await self.exchange.set_leverage_and_margin_mode()
        # --------------------

        self.exchange.balance = await self.exchange.fetch_balance()
        # Note: Balance check might need to be more specific for futures (e.g., check USDT or BUSD)
        print(f"初始余额信息：{self.exchange.balance['info']}")

        # Initialize WebSocket connection
        if self.config.frontend:
            await self.ws_manager.connect()

        # Initialize grid strategy
        await self.strategy.initialize_grid(self.fresh_start)

    async def _handle_fee_coin(self):
        """Manage fee coin balance."""
        # Fee coin management disabled for perpetual futures strategy
        return

        while self.running:
            try:
                balance = await self.exchange.fetch_balance()
                ticker = await self.exchange.fetch_ticker(
                    f"{self.config.fee_coin.coin}/USDT"
                )

                fee_coin_balance = Decimal(str(balance['free'][self.config.fee_coin.coin]))
                fee_coin_price = Decimal(str(ticker['last']))
                fee_coin_value = fee_coin_balance * fee_coin_price

                if fee_coin_value < self.config.fee_coin.repurchase_balance:
                    amount = (self.config.fee_coin.repurchase_amount / fee_coin_price)

                    await self.exchange.create_market_buy_order(amount)
                    print(f"已充值 {self.config.fee_coin.coin}")

            except Exception as e:
                print(f"手续费币种管理错误：{e}")

            # Random delay to avoid multiple bots buying simultaneously
            await asyncio.sleep(60 + (hash(self.config.name) % 180))

    async def _watch_orders(self):
        """监控和处理已完成的订单"""
        while self.running:
            try:
                orders = await self.exchange.watch_orders()
                if orders is None or len(orders) == 0:
                    print("未返回订单")
                    await asyncio.sleep(0.01)
                    continue
                for order in orders:
                    # Check if the order is limit, and closed
                    print(f"订单 {order['id']} 状态：{order['status']}，成交量：{order['filled']}")
                    if order['status'] == 'closed' and order['type'] == 'limit':
                        this_trade = Trade(
                            order_id=order.get('id'),
                            side=order.get('side'),
                            symbol=order.get('symbol', self.config.pair), # 使用配置中的交易对作为默认值
                            price=Decimal(str(order.get('price'))),
                            amount=Decimal(str(order.get('amount'))),
                            cost=Decimal(str(order.get('cost', '0'))), # 默认成本为0
                            timestamp=int(order.get('timestamp') or datetime.now().timestamp() * 1000)
                        )
                        await self.strategy.handle_filled_order(this_trade)
                        self._update_stats()
            except Exception as e:
                print(f"订单监控错误：{e}")
                await asyncio.sleep(5)  # Add a delay before retrying

    async def _watch_ticker(self):
        """监控和处理价格更新"""
        while self.running:
            try:
                ticker = await self.exchange.watch_ticker()
                self.current_price = Decimal(str(ticker['last']))
                if self.current_price != self.last_price:
                    # print(f"Current price: {self.current_price}")
                    self.last_price = self.current_price
                    self.ws_manager.add_price(self.current_price)
                    self._update_stats()
            except Exception as e:
                print(f"价格监控错误：{e}")

    async def _monitor_health(self):
        """定期检查订单健康状态"""
        while self.running:
            await asyncio.sleep(60)
            try:
                await self.strategy.check_order_health()
            except Exception as e:
                print(f"健康检查错误：{e}")

    def _update_stats(self, trade: Optional[Trade] = None):
        """更新并发送统计信息到前端"""
        if not self.config.frontend:
            return

        stats = {
            'total_profit': self._calculate_total_profit(),
            'daily_profit': self._calculate_period_profit(hours=24),
            'weekly_profit': self._calculate_period_profit(hours=168),
            'monthly_profit': self._calculate_period_profit(hours=720),
        }

        if trade:
            self.ws_manager.add_price(trade.price)
            self.ws_manager.send_update('trade', trade.dict(), stats)
        else:
            self.ws_manager.send_update('stats', {}, stats)

    def _calculate_total_profit(self) -> float:
        """计算已完成交易的总利润。新永续合约策略尚未实现准确计算。"""
        print("警告：新永续合约策略的利润计算尚未实现")
        return 0.0 # Return 0 for now

    def _calculate_period_profit(self, hours: int) -> float:
        """计算特定时间段的利润。新永续合约策略尚未实现准确计算。"""
        return 0.0 # Return 0 for now

    async def run(self):
        """Main bot execution loop."""
        try:
            await self.initialize()

            self.tasks = [
                asyncio.create_task(self._watch_ticker()),
                asyncio.create_task(self._watch_orders()),
                asyncio.create_task(self._monitor_health()),
            ]

            # Fee coin management disabled for perpetual futures strategy
            # if self.config.fee_coin and self.config.fee_coin.enabled:
            #     self.tasks.append(asyncio.create_task(self._handle_fee_coin()))

            if self.config.frontend:
                self.tasks.extend([
                    asyncio.create_task(self.ws_manager.keep_alive()),
                    asyncio.create_task(self.ws_manager.process_messages()),
                ])

            try:
                # Wait for all tasks to complete or be cancelled
                await asyncio.gather(*self.tasks)
            except asyncio.CancelledError:
                print("任务已被取消")
        except Exception as e:
            print(f"机器人执行错误：{e}")
        finally:
            self.running = False
            await self._cleanup()

    def _cancel_tasks(self):
        """Cancel all running tasks."""
        for task in self.tasks:
            task.cancel()

    async def _cleanup(self):
        """Cleanup resources on shutdown."""
        if self.config.frontend:
            await self.ws_manager.close()
        await self.exchange.close()


def main():
    """Entry point for the bot."""
    import argparse

    parser = argparse.ArgumentParser(description="Grid Trading Bot")
    parser.add_argument('--config', type=str, required=False,
                        help='Path to configuration file')
    parser.add_argument('--fresh', action='store_true',
                        help='Start fresh by closing current position')

    args = parser.parse_args()

    bot = GridBot(args.config, args.fresh)
    asyncio.run(bot.run())


if __name__ == '__main__':
    main()
