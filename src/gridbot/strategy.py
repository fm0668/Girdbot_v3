# strategy.py

import asyncio
import json
import os
import time
from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, List, Any
from .models import BotConfig, Trade, GridLevelState, ProfitRecord
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

        # 验证边界设置的合理性
        if self.lower_price >= self.upper_price:
            raise ValueError(f"❌ 边界设置错误：下边界 {self.lower_price} 必须小于上边界 {self.upper_price}")

        print(f"📊 网格边界设置：{self.lower_price} - {self.upper_price}")
        print(f"🔍 边界突破检测已启用")

        # 利润追踪相关
        self.profit_records: List[ProfitRecord] = []
        self.total_realized_profit = Decimal('0')
        self.profit_file_path = f"profit_records_{self.config.name.replace('/', '_')}.json"

        # 边界突破控制
        self.boundary_breached = False
        self.emergency_stop_triggered = False

        # 手续费信息（将在初始化时获取实际费率）
        self.maker_fee_rate = Decimal('0')  # USDC期货默认maker费率为0
        self.taker_fee_rate = Decimal('0')  # USDC期货默认taker费率为0

    async def initialize_grid(self, fresh_start: bool = False):
        """初始化网格，清理旧状态，并放置初始订单"""
        # 首先获取交易所手续费信息
        await self._fetch_trading_fees()

        if fresh_start:
            print("请求全新开始。正在清理所有现有持仓和订单...")
            await self._cleanup_exchange_state()
            self.grid_levels = {}
            # 清理利润记录
            self.profit_records = []
            self.total_realized_profit = Decimal('0')
        else:
            await self._load_state()
            # 加载历史利润记录
            await self._load_profit_records()

        if not self.grid_levels:
            self._create_grid_levels()
        else:
            # 检查已加载状态中的订单实际状态
            await self._sync_order_states()

        await self._place_initial_orders()

        # --- 添加延时并主动检查立即成交的订单 ---
        delay_seconds = 3  # 优化为3秒，提高启动速度
        print(f"初始订单已提交。等待 {delay_seconds} 秒以处理立即成交的交易...")
        await asyncio.sleep(delay_seconds)

        # 主动检查并处理应该立即成交的订单
        await self._process_immediate_fills()
        # --------------------------

        await self._save_state()
        print("网格策略初始化成功。")

    async def _fetch_trading_fees(self):
        """获取交易所手续费信息"""
        try:
            fees = await self.exchange.fetch_trading_fees()

            if fees:
                self.maker_fee_rate = Decimal(str(fees.get('maker', 0)))
                self.taker_fee_rate = Decimal(str(fees.get('taker', 0)))

                print(f"📊 手续费信息：Maker {self.maker_fee_rate:.4f}%, Taker {self.taker_fee_rate:.4f}%")
            else:
                print("📊 手续费信息：使用默认值 (USDC期货通常为0%)")

        except Exception as e:
            print(f"⚠️ 获取手续费信息失败，使用默认值0%：{e}")
            # 保持默认值0%

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
                            # 使用更精确的字段创建Trade对象
                            trade_data = {
                                'order_id': order.get('id'),
                                'side': order.get('side'),
                                'symbol': order.get('symbol', self.config.pair),
                                'price': Decimal(str(order.get('average', order.get('price')))),  # average更精确
                                'amount': Decimal(str(order.get('filled', order.get('amount')))),  # filled更精确
                                'cost': Decimal(str(order.get('cost', '0'))),
                                'timestamp': int(order.get('timestamp') or datetime.now().timestamp() * 1000)
                            }
                            trade = Trade(**trade_data)
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
                            # 使用更精确的字段创建Trade对象
                            trade_data = {
                                'order_id': order.get('id'),
                                'side': order.get('side'),
                                'symbol': order.get('symbol', self.config.pair),
                                'price': Decimal(str(order.get('average', order.get('price')))),  # average更精确
                                'amount': Decimal(str(order.get('filled', order.get('amount')))),  # filled更精确
                                'cost': Decimal(str(order.get('cost', '0'))),
                                'timestamp': int(order.get('timestamp') or datetime.now().timestamp() * 1000)
                            }
                            trade = Trade(**trade_data)
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
        level.open_timestamp = trade.timestamp  # 记录开仓时间

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
        """处理平仓订单成交的逻辑，完成一个完整周期并计算利润"""
        print(f"价格 {level.price} 的平仓订单成交，周期完成，计算利润...")

        # 计算本次交易利润
        profit_usdt = self._calculate_grid_profit(level, trade)

        # 记录利润
        profit_record = ProfitRecord(
            grid_id=level.id,
            open_price=level.price,
            close_price=trade.price,
            amount=trade.amount,
            profit_usdt=profit_usdt,
            profit_percentage=(profit_usdt / (level.price * trade.amount)) * 100 if level.price * trade.amount > 0 else Decimal('0'),
            timestamp=trade.timestamp,
            side=self.side
        )

        self.profit_records.append(profit_record)
        self.total_realized_profit += profit_usdt

        # 更新网格层级统计
        level.total_profit += profit_usdt
        level.trade_count += 1

        # 根据利润正负显示不同的图标和颜色提示
        if profit_usdt >= 0:
            status_icon = "✅"
            profit_desc = "盈利"
        else:
            status_icon = "📉"
            profit_desc = "亏损"

        print(f"{status_icon} 网格 {level.id} 完成交易，{profit_desc}: {profit_usdt:.4f} USDT ({profit_record.profit_percentage:.2f}%)")

        # 保存利润记录
        await self._save_profit_records()

        # 1. Update state back to available
        level.status = "AVAILABLE"
        level.close_order_id = None
        level.position_amount = None
        level.open_timestamp = None

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
        pair = self.config.pair
        print(f"--- 开始清理 {pair} 的所有状态 ---")
        try:
            # 1. 首先取消所有挂单，防止新的成交
            print("正在取消所有挂单...")
            open_orders = await self.exchange.fetch_open_orders()
            print(f"获取到 {len(open_orders)} 个挂单")

            # 显示挂单详情（调试用）
            for order in open_orders:
                symbol = order.get('symbol', '')
                order_id = order.get('id', '')
                side = order.get('side', '')
                amount = order.get('amount', 0)
                price = order.get('price', 0)
                print(f"挂单详情：{symbol} | ID={order_id} | {side} | 数量={amount} | 价格={price}")

            for order in open_orders:
                await self.exchange.cancel_order(order['id'])
            print(f"已取消 {len(open_orders)} 个订单")

            # 2. 获取并平掉所有该交易对的持仓
            print("正在获取开放持仓...")
            positions = await self.exchange.fetch_positions([pair])
            print(f"获取到 {len(positions)} 个持仓记录")

            # 过滤出当前交易对的持仓
            target_positions = []
            for position in positions:
                symbol = position.get('symbol', '')
                contracts = Decimal(str(position.get('contracts', '0')))

                # 调试信息
                print(f"检查持仓：交易对={symbol}, 数量={contracts}")

                # 只处理当前交易对且数量大于0的持仓
                # 处理不同的symbol格式：DOGE/USDC 或 DOGE/USDC:USDC
                if (symbol == pair or symbol.startswith(pair)) and contracts > 0:
                    target_positions.append(position)

            print(f"找到 {len(target_positions)} 个需要平仓的 {pair} 持仓")

            for position in target_positions:
                contracts = Decimal(str(position.get('contracts', '0')))
                side = position.get('side')  # 'long' or 'short'
                print(f"发现开放的{side}持仓：{contracts} {self.config.coin}，正在平仓...")

                # 对冲模式下，必须指定要平掉哪一边的持仓
                params = {'positionSide': side.upper()}  # 'LONG' or 'SHORT'

                # 使用修复后的平仓方法
                await self.exchange.create_market_close_order(pair, side, contracts, params)
                print(f"已提交市价单平掉{side}持仓")

                # 等待平仓完成
                await asyncio.sleep(1)  # 给交易所时间处理平仓

            # 验证清理结果
            print("正在验证清理结果...")
            await asyncio.sleep(2)  # 等待交易所更新状态

            # 再次检查持仓
            final_positions = await self.exchange.fetch_positions([pair])
            remaining_positions = []
            for position in final_positions:
                symbol = position.get('symbol', '')
                contracts = Decimal(str(position.get('contracts', '0')))
                if (symbol == pair or symbol.startswith(pair)) and contracts > 0:
                    remaining_positions.append(position)

            if remaining_positions:
                print(f"⚠️ 警告：仍有 {len(remaining_positions)} 个持仓未完全清理")
                for pos in remaining_positions:
                    side = pos.get('side')
                    contracts = Decimal(str(pos.get('contracts', '0')))
                    print(f"  剩余持仓：{side} {contracts} {self.config.coin}")
            else:
                print("✅ 所有持仓已成功清理")

            # 🔧 关键修复：清理交易所状态后，删除本地状态文件确保下次启动干净
            print("�️ 删除本地状态文件，确保下次启动状态一致...")
            await self._cleanup_local_state_files()

            print(f"--- {pair} 状态清理完成 ---")
        except Exception as e:
            print(f"清理交易所状态时出错：{e}")

    async def _cleanup_local_state_files(self):
        """清理交易所状态后，删除本地状态文件"""
        try:
            import os

            # 删除状态文件
            if os.path.exists(self.state_file_path):
                os.remove(self.state_file_path)
                print(f"✅ 已删除状态文件：{self.state_file_path}")

            # 保留利润记录文件，因为它记录的是历史数据
            print("💰 保留利润记录文件，维持交易历史连续性")

        except Exception as e:
            print(f"清理本地状态文件时出错：{e}")

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

    def _calculate_grid_profit(self, level: GridLevelState, close_trade: Trade) -> Decimal:
        """
        计算单个网格的利润

        做空策略说明：
        - 开仓：在高价卖出（level.price）
        - 平仓：在低价买入（close_trade.price）
        - 盈利条件：平仓价格 < 开仓价格（价格下跌）
        - 亏损条件：平仓价格 > 开仓价格（价格上涨）

        这是正确的做空逻辑，负利润表示价格上涨导致的亏损
        """
        if self.side == "long":
            # 做多：买入价格低，卖出价格高，利润 = (卖出价 - 买入价) * 数量
            profit = (close_trade.price - level.price) * close_trade.amount
        else:
            # 做空：卖出价格高，买入价格低，利润 = (卖出价 - 买入价) * 数量
            # 当 level.price > close_trade.price 时盈利（价格下跌）
            # 当 level.price < close_trade.price 时亏损（价格上涨）
            profit = (level.price - close_trade.price) * close_trade.amount

        # 扣除手续费（使用实际交易所费率）
        # 开仓和平仓都可能产生手续费，这里使用taker费率（因为我们使用限价单但可能立即成交）
        # 对于USDC期货，通常maker和taker费率都是0%
        open_fee = level.price * close_trade.amount * self.taker_fee_rate
        close_fee = close_trade.price * close_trade.amount * self.taker_fee_rate
        total_fee = open_fee + close_fee

        return profit - total_fee

    async def _save_profit_records(self):
        """保存利润记录到文件"""
        try:
            profit_data = {
                'total_realized_profit': str(self.total_realized_profit),
                'records': [
                    {
                        'grid_id': record.grid_id,
                        'open_price': str(record.open_price),
                        'close_price': str(record.close_price),
                        'amount': str(record.amount),
                        'profit_usdt': str(record.profit_usdt),
                        'profit_percentage': str(record.profit_percentage),
                        'timestamp': record.timestamp,
                        'side': record.side
                    }
                    for record in self.profit_records
                ]
            }
            with open(self.profit_file_path, 'w') as f:
                json.dump(profit_data, f, indent=4)
        except Exception as e:
            print(f"保存利润记录时出错：{e}")

    async def _load_profit_records(self):
        """加载历史利润记录"""
        try:
            if os.path.exists(self.profit_file_path):
                with open(self.profit_file_path, 'r') as f:
                    data = json.load(f)
                    self.total_realized_profit = Decimal(data.get('total_realized_profit', '0'))

                    records_data = data.get('records', [])
                    self.profit_records = []
                    for record_data in records_data:
                        record = ProfitRecord(
                            grid_id=record_data['grid_id'],
                            open_price=Decimal(record_data['open_price']),
                            close_price=Decimal(record_data['close_price']),
                            amount=Decimal(record_data['amount']),
                            profit_usdt=Decimal(record_data['profit_usdt']),
                            profit_percentage=Decimal(record_data['profit_percentage']),
                            timestamp=record_data['timestamp'],
                            side=record_data['side']
                        )
                        self.profit_records.append(record)

                    print(f"加载了 {len(self.profit_records)} 条利润记录，总利润: {self.total_realized_profit} USDT")
        except Exception as e:
            print(f"加载利润记录时出错：{e}")

    async def watch_orders(self):
        """监控和处理已完成的订单"""
        # 添加运行状态标志
        self.running = True

        while self.running and not self.emergency_stop_triggered:
            try:
                # 定期检查边界突破（每10次循环检查一次，避免过于频繁）
                if hasattr(self, '_boundary_check_counter'):
                    self._boundary_check_counter += 1
                else:
                    self._boundary_check_counter = 0

                if self._boundary_check_counter % 10 == 0:
                    current_price = await self.get_current_market_price()
                    if current_price > 0:
                        boundary_breached = await self.check_boundary_breach(current_price)
                        if boundary_breached:
                            print(f"🚨 {self.side}账户因边界突破停止监控")
                            break

                orders = await self.exchange.watch_orders()
                if orders is None or len(orders) == 0:
                    await asyncio.sleep(0.01)
                    continue

                for order in orders:
                    # 只处理已成交的订单
                    if order.get('status') == 'closed' and order.get('filled', 0) > 0:
                        # 转换为Trade对象
                        timestamp = int(order['timestamp'] or 0)
                        if timestamp <= 0:
                            timestamp = int(time.time() * 1000)  # 使用当前时间戳

                        trade = Trade(
                            order_id=order['id'],
                            side=order['side'],
                            symbol=order['symbol'],
                            amount=Decimal(str(order['filled'])),
                            price=Decimal(str(order['average'] or order['price'])),
                            cost=Decimal(str(order['cost'] or 0)),
                            timestamp=timestamp
                        )

                        # 处理成交
                        await self.handle_filled_order(trade)

                await asyncio.sleep(0.1)

            except Exception as e:
                print(f"监控订单时出错：{e}")
                await asyncio.sleep(1)

                # 如果连续出错，可能需要停止
                if not self.running:
                    break

    def stop_watching(self):
        """停止监控订单"""
        self.running = False

    async def check_boundary_breach(self, current_price: Decimal) -> bool:
        """检查是否突破边界价格"""
        if self.boundary_breached or self.emergency_stop_triggered:
            return True

        # 检查是否突破上边界
        if current_price > self.upper_price:
            print(f"🚨 价格突破上边界！当前价格: {current_price}, 上边界: {self.upper_price}")
            self.boundary_breached = True
            await self._trigger_boundary_emergency_stop("价格突破上边界")
            return True

        # 检查是否突破下边界
        if current_price < self.lower_price:
            print(f"🚨 价格突破下边界！当前价格: {current_price}, 下边界: {self.lower_price}")
            self.boundary_breached = True
            await self._trigger_boundary_emergency_stop("价格突破下边界")
            return True

        return False

    async def _trigger_boundary_emergency_stop(self, reason: str):
        """触发边界突破紧急停止"""
        print(f"🚨 触发边界突破紧急停止: {reason}")
        self.emergency_stop_triggered = True
        self.running = False

        try:
            # 执行清理
            await self._cleanup_exchange_state()
            print(f"✅ {self.side}账户边界突破清理完成")

        except Exception as e:
            print(f"❌ 边界突破清理失败: {e}")

    async def get_current_market_price(self) -> Decimal:
        """获取当前市场价格"""
        try:
            ticker = await self.exchange.fetch_ticker(self.config.pair)
            return Decimal(str(ticker['last']))
        except Exception as e:
            print(f"获取市场价格失败: {e}")
            return Decimal('0')

    async def health_check(self):
        """订单健康检查机制"""
        print("🔍 开始订单健康检查...")

        try:
            # 1. 检查订单状态一致性
            await self._check_order_consistency()

            # 2. 检查孤儿订单
            await self._check_orphan_orders()

            print("✅ 订单健康检查完成")

        except Exception as e:
            print(f"❌ 健康检查时出错：{e}")

    async def _check_order_consistency(self):
        """检查订单状态一致性"""
        print("检查订单状态一致性...")

        inconsistent_count = 0

        for grid_id, level in self.grid_levels.items():
            try:
                # 检查开仓订单
                if level.open_order_id and level.status == "ORDER_PENDING":
                    order = await self.exchange.fetch_order(level.open_order_id)
                    if order['status'] == 'closed':
                        print(f"⚠️ 发现未同步的开仓订单：{grid_id} - {level.open_order_id}")
                        # 创建Trade对象并处理
                        trade_data = {
                            'order_id': order.get('id'),
                            'side': order.get('side'),
                            'symbol': order.get('symbol', self.config.pair),
                            'price': Decimal(str(order.get('average', order.get('price')))),
                            'amount': Decimal(str(order.get('filled', order.get('amount')))),
                            'cost': Decimal(str(order.get('cost', '0'))),
                            'timestamp': int(order.get('timestamp') or datetime.now().timestamp() * 1000)
                        }
                        trade = Trade(**trade_data)
                        await self._handle_open_order_fill(level, trade)
                        inconsistent_count += 1

                # 检查平仓订单
                if level.close_order_id and level.status == "POSITION_HELD":
                    order = await self.exchange.fetch_order(level.close_order_id)
                    if order['status'] == 'closed':
                        print(f"⚠️ 发现未同步的平仓订单：{grid_id} - {level.close_order_id}")
                        # 创建Trade对象并处理
                        trade_data = {
                            'order_id': order.get('id'),
                            'side': order.get('side'),
                            'symbol': order.get('symbol', self.config.pair),
                            'price': Decimal(str(order.get('average', order.get('price')))),
                            'amount': Decimal(str(order.get('filled', order.get('amount')))),
                            'cost': Decimal(str(order.get('cost', '0'))),
                            'timestamp': int(order.get('timestamp') or datetime.now().timestamp() * 1000)
                        }
                        trade = Trade(**trade_data)
                        await self._handle_close_order_fill(level, trade)
                        inconsistent_count += 1

            except Exception as e:
                print(f"检查网格 {grid_id} 时出错：{e}")

        if inconsistent_count > 0:
            print(f"🔧 修复了 {inconsistent_count} 个状态不一致的订单")
            await self._save_state()
        else:
            print("✅ 所有订单状态一致")



    async def _check_orphan_orders(self):
        """检查孤儿订单（交易所有但本地没有记录的订单）"""
        print("检查孤儿订单...")

        try:
            # 获取交易所所有开放订单
            exchange_orders = await self.exchange.fetch_open_orders()

            # 收集本地记录的所有订单ID
            local_order_ids = set()
            for level in self.grid_levels.values():
                if level.open_order_id:
                    local_order_ids.add(level.open_order_id)
                if level.close_order_id:
                    local_order_ids.add(level.close_order_id)

            # 查找孤儿订单
            orphan_orders = []
            for order in exchange_orders:
                if order['id'] not in local_order_ids:
                    orphan_orders.append(order)

            if orphan_orders:
                print(f"⚠️ 发现 {len(orphan_orders)} 个孤儿订单：")
                for order in orphan_orders:
                    print(f"  订单ID: {order['id']}, 价格: {order.get('price')}, 数量: {order.get('amount')}")
                print("建议手动检查这些订单是否需要取消")
            else:
                print("✅ 未发现孤儿订单")

        except Exception as e:
            print(f"检查孤儿订单时出错：{e}")