# strategy.py

import asyncio
import json
from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict
from .models import BotConfig, Trade, GridLevelState
from .exchange import ExchangeInterface

class GridStrategy:
    """
    实现永续合约
    使用状态机方法管理网格交易
    """

    def __init__(self, config: BotConfig, exchange: ExchangeInterface):
        self.config = config
        self.exchange = exchange
        self.grid_levels: Dict[str, GridLevelState] = {}  # 改为以ID为key
        self.price_to_id: Dict[Decimal, str] = {}  # 价格到ID的映射
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

        # --- 添加延时并主动检查立即成交的订单 ---
        delay_seconds = 5  # 增加到5秒
        print(f"初始订单已提交。等待 {delay_seconds} 秒以处理立即成交的交易...")
        await asyncio.sleep(delay_seconds)

        # 主动检查并处理应该立即成交的订单
        await self._process_immediate_fills()
        # --------------------------

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

            # 创建唯一ID
            grid_id = f"grid_{i:03d}"  # 格式：grid_000, grid_001, etc.
            level = GridLevelState(id=grid_id, price=price, status="AVAILABLE")

            self.grid_levels[grid_id] = level
            self.price_to_id[price] = grid_id

    async def _process_immediate_fills(self):
        """
        启动网格时，主动为应该立即成交的价格点创建平仓单
        交易所会将当前价上方的买入限价单瞬间以市价成交并合并为一个持仓
        但我们需要为每个应该成交的价格点创建对应的平仓单
        """
        print("正在处理启动时的立即成交逻辑...")

        # 获取当前市价
        ticker = await self.exchange.fetch_ticker()
        current_price = Decimal(str(ticker['last']))
        print(f"当前市价：{current_price}")

        immediate_fill_count = 0

        for grid_id, level in self.grid_levels.items():
            if level.status == "ORDER_PENDING":
                # 判断这个价格点是否应该立即成交
                should_fill_immediately = False

                if self.side == "long":
                    # 做多：买入价格高于等于当前市价的订单应该立即成交
                    should_fill_immediately = level.price >= current_price
                else:
                    # 做空：卖出价格低于等于当前市价的订单应该立即成交
                    # 修正：做空时，卖出价格低于等于当前市价才会立即成交
                    should_fill_immediately = level.price <= current_price

                if should_fill_immediately:
                    print(f"🎯 网格 {grid_id}（价格 {level.price}）应该立即成交，直接创建持仓和平仓单")

                    # 直接将状态转换为持仓状态
                    level.status = "POSITION_HELD"
                    level.open_order_id = None  # 清除订单ID，因为已经成交
                    level.position_amount = self.config.order_amount_usdt / level.price  # 计算持仓数量

                    # 为这个价格点创建平仓单
                    try:
                        close_price = level.price + self.grid_step if self.side == "long" else level.price - self.grid_step
                        params = {
                            'positionSide': 'LONG' if self.side == 'long' else 'SHORT'
                        }

                        if self.side == "long":
                            # 平多仓：卖出
                            order = await self.exchange.create_limit_sell_order(level.position_amount, close_price, params)
                        else:
                            # 平空仓：买入
                            order = await self.exchange.create_limit_buy_order(level.position_amount, close_price, params)

                        level.close_order_id = order['id']
                        print(f"✅ 为网格 {grid_id}（价格 {level.price}）创建平仓订单 {order['id']}，目标价格 {close_price}")
                        immediate_fill_count += 1

                    except Exception as e:
                        print(f"❌ 为网格 {grid_id}（价格 {level.price}）创建平仓订单时出错：{e}")

        print(f"✅ 启动时处理了 {immediate_fill_count} 个应该立即成交的价格点")

    async def _sync_order_states(self):
        """重启时同步本地状态与交易所状态"""
        print("正在与交易所同步订单状态...")
        open_orders = await self.exchange.fetch_open_orders()
        open_order_ids = {o['id'] for o in open_orders}

        for grid_id, level in self.grid_levels.items():
            # Case 1: We think an open order is pending
            if level.status == "ORDER_PENDING" and level.open_order_id:
                if level.open_order_id not in open_order_ids:
                    # The order is not open anymore, check if it was filled or cancelled
                    try:
                        order = await self.exchange.fetch_order(level.open_order_id)
                        if order['status'] == 'closed':
                            print(f"同步：发现已成交的开仓订单 {level.open_order_id}，网格 {grid_id}（价格 {level.price}）")
                            # Create a Trade object from the order
                            trade = Trade(
                                order_id=order['id'],
                                side=order['side'],
                                amount=order['amount'],
                                price=Decimal(str(order['price']))
                            )
                            await self._handle_open_order_fill(level, trade)
                        else: # cancelled or other states
                            print(f"发现已取消的订单 {level.open_order_id}，网格 {grid_id}（价格 {level.price}）")
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
                            print(f"同步：发现已成交的平仓订单 {level.close_order_id}，网格 {grid_id}（价格 {level.price}）")
                            trade = Trade(
                                order_id=order['id'],
                                side=order['side'],
                                amount=order['amount'],
                                price=Decimal(str(order['price']))
                            )
                            await self._handle_close_order_fill(level, trade)
                        else: # Close order was cancelled, we need to replace it
                            print(f"同步：网格 {grid_id}（价格 {level.price}）的平仓订单已被取消，正在重新放置")
                            await self._place_close_order_from_sync(level)
                    except Exception as e:
                        print(f"获取平仓订单 {level.close_order_id} 时出错：{e}")
                        # Can't fetch, assume it was cancelled and replace it
                        await self._place_close_order_from_sync(level)
                elif not level.close_order_id:
                    # We hold a position but have no record of a close order. This is a zombie position.
                    print(f"同步：发现网格 {grid_id}（价格 {level.price}）的僵尸持仓（无平仓订单），正在放置平仓订单")
                    await self._place_close_order_from_sync(level)

    async def _place_close_order_from_sync(self, level: GridLevelState):
        """同步期间为现有持仓放置平仓订单的辅助方法"""
        if not level.position_amount:
            print(f"错误：无法为网格 {level.id}（价格 {level.price}）放置平仓订单，持仓数量未知")
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
            print(f"同步：为网格 {level.id}（价格 {level.price}）的持仓放置平仓订单 {order['id']}，目标价格 {close_price}")
        except Exception as e:
            print(f"同步时为网格 {level.id}（价格 {level.price}）的持仓放置平仓订单出错：{e}")

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
        """
        为所有网格层级放置开仓订单
        高于当前市价的订单将立即成交，建立初始持仓
        """
        print("正在放置初始订单以建立网格持仓...")

        for grid_id, level in self.grid_levels.items():
            if level.status == "AVAILABLE":
                try:
                    order_amount_coin = self.config.order_amount_usdt / level.price

                    # --- 关键修改：移除 postOnly 和价格检查 ---
                    params = {
                        'positionSide': 'LONG' if self.side == 'long' else 'SHORT'
                    }

                    if self.side == "long":
                        order = await self.exchange.create_limit_buy_order(order_amount_coin, level.price, params)
                    else: # short strategy
                        order = await self.exchange.create_limit_sell_order(order_amount_coin, level.price, params)

                    # 假设订单处于挂单状态，watch_orders 循环将处理
                    # 立即成交的情况，将状态转换为 POSITION_HELD
                    level.open_order_id = order['id']
                    level.status = "ORDER_PENDING"
                    print(f"提交开仓{'多头' if self.side == 'long' else '空头'}订单 {order['id']}，网格ID {grid_id}，价格 {level.price}")

                except Exception as e:
                    # 价格保护错误仍可能发生，如果网格范围太宽
                    if 'limit price can\'t be higher' in str(e).lower() or 'limit price can\'t be lower' in str(e).lower():
                        print(f"跳过网格 {grid_id}（价格 {level.price}）的订单：价格超出交易所限制")
                    else:
                        print(f"在网格 {grid_id}（价格 {level.price}）放置初始订单时出错：{e}")

    async def handle_filled_order(self, trade: Trade):
        """处理已成交订单的核心状态机逻辑"""
        print(f"--- 处理已成交订单：ID {trade.order_id}，方向 {trade.side}，价格 {trade.price} ---")

        found_level = None
        found_grid_id = None

        # 1. 首先通过订单ID查找
        for grid_id, level in self.grid_levels.items():
            if level.open_order_id == trade.order_id:
                print(f"通过订单ID找到开仓订单：网格 {grid_id}")
                await self._handle_open_order_fill(level, trade)
                found_level = level
                found_grid_id = grid_id
                break
            elif level.close_order_id == trade.order_id:
                print(f"通过订单ID找到平仓订单：网格 {grid_id}")
                await self._handle_close_order_fill(level, trade)
                found_level = level
                found_grid_id = grid_id
                break

        # 2. 如果订单ID不匹配，通过价格匹配（容错处理）
        if found_level is None:
            print(f"未找到订单ID {trade.order_id}，尝试通过价格 {trade.price} 匹配")
            tolerance = Decimal('0.0001')  # 0.01% tolerance

            for grid_id, level in self.grid_levels.items():
                price_diff = abs(level.price - trade.price) / level.price
                if price_diff <= tolerance:
                    if level.status == "ORDER_PENDING":
                        print(f"通过价格找到匹配的开仓网格：{grid_id}（价格差异：{price_diff:.6f}）")
                        # 更新订单ID并处理成交
                        level.open_order_id = trade.order_id
                        await self._handle_open_order_fill(level, trade)
                        found_level = level
                        found_grid_id = grid_id
                        break
                    elif level.status == "POSITION_HELD" and level.close_order_id:
                        print(f"通过价格找到匹配的平仓网格：{grid_id}（价格差异：{price_diff:.6f}）")
                        # 更新订单ID并处理成交
                        level.close_order_id = trade.order_id
                        await self._handle_close_order_fill(level, trade)
                        found_level = level
                        found_grid_id = grid_id
                        break

        if found_level is None:
            print(f"警告：已成交订单 {trade.order_id}（价格 {trade.price}）不匹配任何已知网格层级，忽略处理")
            return

        await self._save_state()
        print(f"--- 网格 {found_grid_id} 订单处理完成 ---")

    async def _handle_open_order_fill(self, level: GridLevelState, trade: Trade):
        """处理开仓订单成交的逻辑"""
        print(f"网格 {level.id} 开仓订单在价格 {level.price} 成交，转换为持仓状态")

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
            print(f"✅ 为网格 {level.id}（价格 {level.price}）的持仓放置平仓订单 {order['id']}，目标价格 {close_price}")

        except Exception as e:
            print(f"❌ 为网格 {level.id}（价格 {level.price}）的持仓放置平仓订单时出错：{e}")
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

            # --- 关键修改：移除 postOnly ---
            params = {
                'positionSide': 'LONG' if self.side == 'long' else 'SHORT'
            }

            if self.side == "long":
                order = await self.exchange.create_limit_buy_order(order_amount_coin, level.price, params)
            else: # short
                order = await self.exchange.create_limit_sell_order(order_amount_coin, level.price, params)

            level.open_order_id = order['id']
            level.status = "ORDER_PENDING"
            print(f"在价格 {level.price} 重新放置开仓订单 {order['id']}")
        except Exception as e:
            # 价格保护错误仍可能发生
            if 'limit price can\'t be higher' in str(e).lower() or 'limit price can\'t be lower' in str(e).lower():
                print(f"跳过在价格 {level.price} 重新放置订单：价格超出交易所限制")
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
            # 保存网格状态和价格映射
            state_to_save = {
                'grid_levels': {grid_id: json.loads(level.json()) for grid_id, level in self.grid_levels.items()},
                'price_to_id': {str(price): grid_id for price, grid_id in self.price_to_id.items()}
            }
            with open(self.state_file_path, 'w') as f:
                json.dump(state_to_save, f, indent=4)
        except Exception as e:
            print(f"保存状态时出错：{e}")

    async def _load_state(self):
        """从文件加载网格状态"""
        try:
            with open(self.state_file_path, 'r') as f:
                loaded_state = json.load(f)

                # 加载网格层级
                self.grid_levels = {
                    grid_id: GridLevelState(**level_data)
                    for grid_id, level_data in loaded_state.get('grid_levels', {}).items()
                }

                # 加载价格映射
                self.price_to_id = {
                    Decimal(price_str): grid_id
                    for price_str, grid_id in loaded_state.get('price_to_id', {}).items()
                }

                print(f"成功加载 {len(self.grid_levels)} 个网格层级的状态")
        except FileNotFoundError:
            print("未找到状态文件，全新开始")
            self.grid_levels = {}
            self.price_to_id = {}
        except Exception as e:
            print(f"加载状态时出错：{e}")
            self.grid_levels = {}
            self.price_to_id = {}