# strategy.py

from decimal import Decimal
from typing import Optional, Dict
from .models import BotConfig, Trade, GridLevelState
from .exchange import ExchangeInterface
import json

class GridStrategy:
    """
    实现永续合约的"单向接力网格"策略
    使用状态机方法管理网格交易
    """

    def __init__(self, config: BotConfig, exchange: ExchangeInterface):
        self.config = config
        self.exchange = exchange
        self.grid_levels: Dict[Decimal, GridLevelState] = {}
        self.state_file_path = f"grid_state_{self.config.name.replace('/', '_')}.json"
        
        # 从配置中获取常用参数，便于快速访问
        self.side = self.config.strategy_side
        self.grid_step = self.config.grid_step
        self.upper_price = self.config.upper_price
        self.lower_price = self.config.lower_price

    async def initialize_grid(self, fresh_start: bool = False):
        """初始化网格，清理旧状态，并放置初始订单"""
        if fresh_start:
            print("请求全新开始。正在清理所有现有持仓和订单...")
            await self._cleanup_exchange_state()
            self.grid_levels = {}
        else:
            await self._load_state()

        if not self.grid_levels:
            self._create_grid_levels()
        else:
            # 检查已加载状态中的订单实际状态
            await self._sync_order_states()

        await self._place_initial_orders()
        await self._save_state()
        print("网格策略初始化成功。")

    def _create_grid_levels(self):
        """创建所有网格价格层级的初始状态"""
        print("正在创建新的网格层级...")
        for i in range(self.config.grids):
            price = self.lower_price + i * self.grid_step
            # 在上边界，做多策略不放置开仓单
            if self.side == "long" and price == self.upper_price:
                continue
            # 在下边界，做空策略不放置开仓单
            if self.side == "short" and price == self.lower_price:
                continue

            self.grid_levels[price] = GridLevelState(price=price, status="AVAILABLE")

    async def _sync_order_states(self):
        """重启时同步本地状态与交易所状态"""
        print("正在与交易所同步订单状态...")
        open_orders = await self.exchange.fetch_open_orders()
        open_order_ids = {o['id'] for o in open_orders}

        for price, level in self.grid_levels.items():
            # Case 1: We think an open order is pending
            if level.status == "ORDER_PENDING" and level.open_order_id:
                if level.open_order_id not in open_order_ids:
                    # The order is not open anymore, check if it was filled or cancelled
                    try:
                        order = await self.exchange.fetch_order(level.open_order_id)
                        if order['status'] == 'closed':
                            print(f"同步：发现已成交的开仓订单 {level.open_order_id}，价格 {price}")
                            # Create a Trade object from the order
                            trade = Trade(
                                order_id=order['id'],
                                side=order['side'],
                                amount=order['amount'],
                                price=Decimal(str(order['price']))
                            )
                            await self._handle_open_order_fill(level, trade)
                        else: # cancelled or other states
                            print(f"发现已取消的订单 {level.open_order_id}，价格 {price}")
                            level.status = "AVAILABLE"
                            level.open_order_id = None
                    except Exception as e:
                        print(f"获取订单 {level.open_order_id} 时出错：{e}")
                        level.status = "AVAILABLE" # Can't fetch, assume it's gone
                        level.open_order_id = None

            # Case 2: We think we are holding a position
            elif level.status == "POSITION_HELD":
                if level.close_order_id and level.close_order_id not in open_order_ids:
                    # The close order is gone, check its status
                    try:
                        order = await self.exchange.fetch_order(level.close_order_id)
                        if order['status'] == 'closed':
                            print(f"同步：发现已成交的平仓订单 {level.close_order_id}，持仓价格 {price}")
                            trade = Trade(
                                order_id=order['id'],
                                side=order['side'],
                                amount=order['amount'],
                                price=Decimal(str(order['price']))
                            )
                            await self._handle_close_order_fill(level, trade)
                        else: # Close order was cancelled, we need to replace it
                            print(f"同步：价格 {price} 的平仓订单已被取消，正在重新放置")
                            await self._place_close_order_from_sync(level)
                    except Exception as e:
                        print(f"获取平仓订单 {level.close_order_id} 时出错：{e}")
                        # Can't fetch, assume it was cancelled and replace it
                        await self._place_close_order_from_sync(level)
                elif not level.close_order_id:
                    # We hold a position but have no record of a close order. This is a zombie position.
                    print(f"同步：发现价格 {price} 的僵尸持仓（无平仓订单），正在放置平仓订单")
                    await self._place_close_order_from_sync(level)

    async def _place_close_order_from_sync(self, level: GridLevelState):
        """同步期间为现有持仓放置平仓订单的辅助方法"""
        if not level.position_amount:
            print(f"错误：无法为价格 {level.price} 放置平仓订单，持仓数量未知")
            return # Or fetch position size from exchange

        close_price = level.price + self.grid_step if self.side == "long" else level.price - self.grid_step
        params = {'positionSide': 'LONG' if self.side == 'long' else 'SHORT'}

        try:
            if self.side == "long":
                # 平多仓：卖出
                order = await self.exchange.create_limit_sell_order(level.position_amount, close_price, params)
            else:
                # 平空仓：买入
                order = await self.exchange.create_limit_buy_order(level.position_amount, close_price, params)

            level.close_order_id = order['id']
            print(f"同步：为价格 {level.price} 的持仓放置平仓订单 {order['id']}，目标价格 {close_price}")
        except Exception as e:
            print(f"同步时为价格 {level.price} 的持仓放置平仓订单出错：{e}")

    async def _place_close_order(self, level, filled_order):
        """为已成交的订单放置平仓单"""
        try:
            close_price = level.price + self.grid_step if self.side == "long" else level.price - self.grid_step
            # 双向持仓模式：平仓通过positionSide和相反的side实现
            params = {
                'positionSide': 'LONG' if self.side == 'long' else 'SHORT'
            }

            # 平仓逻辑：
            # 平多仓：positionSide=LONG, side=SELL
            # 平空仓：positionSide=SHORT, side=BUY
            if self.side == "long":
                # 平多仓：卖出
                order = await self.exchange.create_limit_sell_order(level.position_amount, close_price, params)
            else:
                # 平空仓：买入
                order = await self.exchange.create_limit_buy_order(level.position_amount, close_price, params)

            level.close_order_id = order['id']
            print(f"为价格 {level.price} 的持仓放置平仓订单 {order['id']}，目标价格 {close_price}")
        except Exception as e:
            print(f"为价格 {level.price} 的持仓放置平仓订单时出错：{e}")

    async def _place_initial_orders(self):
        """为所有处于'AVAILABLE'状态的网格层级放置开仓订单"""
        print("正在放置初始订单...")

        # 获取当前市场价格
        ticker = await self.exchange.fetch_ticker()
        current_price = Decimal(str(ticker['last']))
        print(f"当前市场价格：{current_price}")

        for price, level in self.grid_levels.items():
            if level.status == "AVAILABLE":
                try:
                    order_amount_coin = self.config.order_amount_usdt / price

                    # --- KEY CHANGE HERE ---
                    params = {
                        'positionSide': 'LONG' if self.side == 'long' else 'SHORT',
                        'postOnly': True  # Ensure it's a MAKER order
                    }

                    # 做多策略：在所有网格价格都放置买入挂单
                    if self.side == "long":
                        # 跳过与当前价格太接近的层级，避免立即成交
                        price_diff = abs(price - current_price) / current_price
                        if price_diff < Decimal('0.001'):  # 0.1%以内跳过
                            print(f"跳过价格 {price} 的订单（与当前价格 {current_price} 太接近）")
                            continue

                        # 在所有其他价格放置买入挂单
                        order = await self.exchange.create_limit_buy_order(order_amount_coin, price, params)
                        level.open_order_id = order['id']
                        level.status = "ORDER_PENDING"
                        position = "低于" if price < current_price else "高于"
                        print(f"在价格 {price} 放置买入订单 {order['id']}（{position}当前价格）")

                    else: # short strategy
                        # 做空策略：在所有网格价格都放置卖出挂单
                        price_diff = abs(price - current_price) / current_price
                        if price_diff < Decimal('0.001'):  # 0.1%以内跳过
                            print(f"跳过价格 {price} 的订单（与当前价格 {current_price} 太接近）")
                            continue

                        order = await self.exchange.create_limit_sell_order(order_amount_coin, price, params)
                        level.open_order_id = order['id']
                        level.status = "ORDER_PENDING"
                        position = "低于" if price < current_price else "高于"
                        print(f"在价格 {price} 放置卖出订单 {order['id']}（{position}当前价格）")

                except Exception as e:
                    # postOnly订单如果会立即成交，会抛出 OrderImmediatelyFillable 或 Cancelled 错误，这是正常的
                    if ('postonly' in str(e).lower() or 'immediately' in str(e).lower() or
                        'would immediately match' in str(e).lower() or 'post only order will be rejected' in str(e).lower() or
                        'could not be executed as maker' in str(e).lower()):
                        print(f"跳过价格 {price} 的订单：会立即成交（高于当前市价的价格预期行为）")
                    elif 'limit price can\'t be higher' in str(e).lower() or 'limit price can\'t be lower' in str(e).lower():
                        print(f"跳过价格 {price} 的订单：价格超出交易所限制")
                    else:
                        print(f"在价格 {price} 放置初始订单时出错：{e}")

    async def handle_filled_order(self, trade: Trade):
        """处理已成交订单的核心状态机逻辑"""
        print(f"--- 处理已成交订单：ID {trade.order_id}，方向 {trade.side}，价格 {trade.price} ---")

        filled_level_price = None
        # First try to find by order ID
        for price, level in self.grid_levels.items():
            if level.open_order_id == trade.order_id:
                await self._handle_open_order_fill(level, trade)
                filled_level_price = price
                break
            elif level.close_order_id == trade.order_id:
                await self._handle_close_order_fill(level, trade)
                filled_level_price = price
                break

        # If not found by order ID, try to find by price (with tolerance)
        if filled_level_price is None:
            print(f"未找到订单ID {trade.order_id}，尝试通过价格 {trade.price} 匹配")
            tolerance = Decimal('0.0001')  # 0.01% tolerance
            for price, level in self.grid_levels.items():
                price_diff = abs(price - trade.price) / price
                if price_diff <= tolerance and level.status == "ORDER_PENDING":
                    print(f"通过价格找到匹配的网格层级：{price}（差异：{price_diff:.6f}）")
                    # Update the order ID and handle the fill
                    level.open_order_id = trade.order_id
                    await self._handle_open_order_fill(level, trade)
                    filled_level_price = price
                    break

        if filled_level_price is None:
            print(f"警告：已成交订单 {trade.order_id}（价格 {trade.price}）不匹配任何已知网格层级，忽略处理")
            return

        await self._save_state()
        print("--- 订单处理完成 ---")

    async def _handle_open_order_fill(self, level: GridLevelState, trade: Trade):
        """处理开仓订单成交的逻辑"""
        print(f"开仓订单在价格 {level.price} 成交，转换为持仓状态")

        # 1. Update state
        level.status = "POSITION_HELD"
        level.open_order_id = None
        level.position_amount = trade.amount

        # 2. Check risk management
        current_positions = sum(1 for lvl in self.grid_levels.values() if lvl.status == 'POSITION_HELD')
        if current_positions > self.config.max_position_count:
            print(f"严重警告：持仓数量（{current_positions}）超过最大限制（{self.config.max_position_count}）")
            # Here you could trigger a bot shutdown or other emergency action.
            # For now, we just print a warning.

        # 3. Place the corresponding 'close' order
        try:
            close_price = level.price + self.grid_step if self.side == "long" else level.price - self.grid_step
            # 双向持仓模式：平仓通过positionSide和相反的side实现
            params = {
                'positionSide': 'LONG' if self.side == 'long' else 'SHORT'
            }

            # 平仓逻辑：
            # 平多仓：positionSide=LONG, side=SELL
            # 平空仓：positionSide=SHORT, side=BUY
            if self.side == "long":
                # 平多仓：卖出
                order = await self.exchange.create_limit_sell_order(trade.amount, close_price, params)
            else: # short
                # 平空仓：买入
                order = await self.exchange.create_limit_buy_order(trade.amount, close_price, params)
                
            level.close_order_id = order['id']
            print(f"为价格 {level.price} 的持仓放置平仓订单 {order['id']}，目标价格 {close_price}")

        except Exception as e:
            print(f"为价格 {level.price} 的持仓放置平仓订单时出错：{e}")
            # In a real scenario, you'd need a retry mechanism or alert.

    async def _handle_close_order_fill(self, level: GridLevelState, trade: Trade):
        """处理平仓订单成交的逻辑，完成一个完整周期"""
        print(f"价格 {level.price} 的平仓订单成交，周期完成，重新放置开仓订单")

        # 1. Update state back to available
        level.status = "AVAILABLE"
        level.close_order_id = None
        level.position_amount = None

        # 2. Re-place the 'open' order to restart the cycle for this level
        try:
            order_amount_coin = self.config.order_amount_usdt / level.price

            # --- KEY CHANGE HERE ---
            params = {
                'positionSide': 'LONG' if self.side == 'long' else 'SHORT',
                'postOnly': True # Also for re-placing orders
            }

            if self.side == "long":
                order = await self.exchange.create_limit_buy_order(order_amount_coin, level.price, params)
            else: # short
                order = await self.exchange.create_limit_sell_order(order_amount_coin, level.price, params)

            level.open_order_id = order['id']
            level.status = "ORDER_PENDING"
            print(f"在价格 {level.price} 重新放置开仓订单 {order['id']}")
        except Exception as e:
            # postOnly订单如果会立即成交，会抛出异常，这是正常的
            if 'postonly' in str(e).lower() or 'immediately' in str(e).lower() or 'would immediately match' in str(e).lower():
                print(f"跳过在价格 {level.price} 重新放置订单：会立即成交")
            else:
                print(f"在价格 {level.price} 重新放置开仓订单时出错：{e}")

    async def _cleanup_exchange_state(self):
        """关闭所有持仓并取消该交易对的所有订单"""
        try:
            # This is a simplified cleanup. A robust version would fetch positions first.
            # For now, we assume we need to close a position if we have one.
            # A better implementation would be in exchange.py
            print("正在关闭所有开放持仓...")
            # This logic needs to be robust, check current position side and size
            # For now, let's just try to close both ways if needed, or implement in exchange.py

            print("正在取消所有挂单...")
            open_orders = await self.exchange.fetch_open_orders()
            for order in open_orders:
                await self.exchange.cancel_order(order['id'])
            print(f"已取消 {len(open_orders)} 个订单")
        except Exception as e:
            print(f"清理过程中出错：{e}")

    async def check_order_health(self):
        """定期与交易所同步状态"""
        # This is a complex but crucial method for a robust bot.
        # It should:
        # 1. Fetch all open orders from the exchange.
        # 2. Compare them with our `self.grid_levels` state.
        # 3. If an order in our state is not on the exchange, check its status (filled? cancelled?).
        # 4. If an order on the exchange is not in our state, something is wrong (cancel it?).
        # For this first refactoring step, we'll leave it as a placeholder.
        pass

    async def _save_state(self):
        """将当前网格状态保存到文件"""
        try:
            # Pydantic's built-in json() method handles Decimal serialization correctly
            state_to_save = {str(k): json.loads(v.json()) for k, v in self.grid_levels.items()}
            with open(self.state_file_path, 'w') as f:
                json.dump(state_to_save, f, indent=4)
        except Exception as e:
            print(f"保存状态时出错：{e}")

    async def _load_state(self):
        """从文件加载网格状态"""
        try:
            with open(self.state_file_path, 'r') as f:
                loaded_state = json.load(f)
                self.grid_levels = {
                    Decimal(k): GridLevelState(**v) for k, v in loaded_state.items()
                }
                print(f"成功加载 {len(self.grid_levels)} 个网格层级的状态")
        except FileNotFoundError:
            print("未找到状态文件，全新开始")
            self.grid_levels = {}
        except Exception as e:
            print(f"加载状态时出错：{e}")
            self.grid_levels = {}