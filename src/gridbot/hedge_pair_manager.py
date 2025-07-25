"""
对冲配对管理器 - 管理多空网格的配对关系和同步逻辑
实现真正的市场中性对冲策略
"""

import asyncio
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from .models import Trade, GridLevelState, DualAccountConfig
from .dual_account_manager import DualAccountManager

@dataclass
class HedgePair:
    """对冲配对数据结构"""
    pair_id: str
    price: Decimal
    long_grid_id: str
    short_grid_id: str
    hedge_status: str  # 'BALANCED', 'LONG_AHEAD', 'SHORT_AHEAD', 'IMBALANCED'
    created_timestamp: int
    last_sync_timestamp: int
    sync_count: int = 0

class HedgePairManager:
    """对冲配对管理器"""
    
    def __init__(self, dual_manager: DualAccountManager, config: DualAccountConfig):
        self.dual_manager = dual_manager
        self.config = config
        self.hedge_pairs: Dict[str, HedgePair] = {}
        self.price_to_pair_id: Dict[Decimal, str] = {}
        
        # 对冲控制参数
        self.max_imbalance_ratio = config.max_imbalance_ratio
        self.sync_tolerance_seconds = config.sync_tolerance_seconds
        
        # 统计信息
        self.total_hedge_trades = 0
        self.successful_hedges = 0
        self.failed_hedges = 0
    
    async def initialize_hedge_pairs(self):
        """初始化对冲配对关系"""
        print("🎯 初始化对冲配对关系...")
        
        # 获取双边网格
        long_grids = self.dual_manager.long_strategy.grid_manager.grid_levels
        short_grids = self.dual_manager.short_strategy.grid_manager.grid_levels
        
        # 创建配对关系
        pair_count = 0
        for long_id, long_grid in long_grids.items():
            # 寻找相同价格的空头网格
            matching_short_grid = None
            for short_id, short_grid in short_grids.items():
                if abs(long_grid.price - short_grid.price) < Decimal('0.01'):
                    matching_short_grid = short_grid
                    break
            
            if matching_short_grid:
                pair_id = f"hedge_{pair_count:03d}"
                
                hedge_pair = HedgePair(
                    pair_id=pair_id,
                    price=long_grid.price,
                    long_grid_id=long_grid.id,
                    short_grid_id=matching_short_grid.id,
                    hedge_status='BALANCED',
                    created_timestamp=int(datetime.now().timestamp() * 1000),
                    last_sync_timestamp=int(datetime.now().timestamp() * 1000)
                )
                
                self.hedge_pairs[pair_id] = hedge_pair
                self.price_to_pair_id[long_grid.price] = pair_id
                pair_count += 1
        
        print(f"✅ 创建了 {len(self.hedge_pairs)} 个对冲配对")
        return len(self.hedge_pairs)
    
    async def handle_trade_event(self, trade: Trade, account_side: str):
        """处理交易事件，执行对冲逻辑"""
        print(f"🎯 处理对冲交易事件: {account_side} 账户，价格 {trade.price}")
        
        # 1. 找到对应的对冲配对
        hedge_pair = self._find_hedge_pair_by_price(trade.price)
        if not hedge_pair:
            print(f"⚠️ 未找到价格 {trade.price} 对应的对冲配对")
            return
        
        # 2. 更新对冲配对状态
        await self._update_hedge_pair_status(hedge_pair, trade, account_side)
        
        # 3. 检查对冲平衡
        balance_status = await self._check_hedge_balance(hedge_pair)
        
        # 4. 执行对冲同步逻辑
        if balance_status != 'BALANCED':
            await self._execute_hedge_sync(hedge_pair, account_side)
        
        # 5. 更新统计
        self.total_hedge_trades += 1
        if balance_status == 'BALANCED':
            self.successful_hedges += 1
        else:
            self.failed_hedges += 1
    
    def _find_hedge_pair_by_price(self, price: Decimal) -> Optional[HedgePair]:
        """通过价格查找对冲配对"""
        # 精确匹配
        pair_id = self.price_to_pair_id.get(price)
        if pair_id:
            return self.hedge_pairs[pair_id]
        
        # 容差匹配
        tolerance = Decimal('0.0001')
        for pair in self.hedge_pairs.values():
            if abs(pair.price - price) / pair.price <= tolerance:
                return pair
        
        return None
    
    async def _update_hedge_pair_status(self, hedge_pair: HedgePair, trade: Trade, account_side: str):
        """更新对冲配对状态"""
        current_time = int(datetime.now().timestamp() * 1000)
        
        # 获取对应的网格状态
        if account_side == 'long':
            grid = self.dual_manager.long_strategy.grid_manager.grid_levels.get(hedge_pair.long_grid_id)
        else:
            grid = self.dual_manager.short_strategy.grid_manager.grid_levels.get(hedge_pair.short_grid_id)
        
        if grid:
            # 记录交易事件
            print(f"📝 记录 {account_side} 账户交易: 网格 {grid.id}, 价格 {trade.price}")
        
        hedge_pair.last_sync_timestamp = current_time
        hedge_pair.sync_count += 1

    async def _check_hedge_balance(self, hedge_pair: HedgePair) -> str:
        """检查对冲平衡状态"""
        # 获取多空网格状态
        long_grid = self.dual_manager.long_strategy.grid_manager.grid_levels.get(hedge_pair.long_grid_id)
        short_grid = self.dual_manager.short_strategy.grid_manager.grid_levels.get(hedge_pair.short_grid_id)

        if not long_grid or not short_grid:
            return 'ERROR'

        long_has_position = long_grid.status == "POSITION_HELD"
        short_has_position = short_grid.status == "POSITION_HELD"

        if long_has_position and short_has_position:
            # 检查持仓数量是否平衡
            long_amount = long_grid.position_amount or Decimal('0')
            short_amount = short_grid.position_amount or Decimal('0')

            if abs(long_amount - short_amount) / max(long_amount, short_amount) <= self.max_imbalance_ratio:
                hedge_pair.hedge_status = 'BALANCED'
                return 'BALANCED'
            else:
                hedge_pair.hedge_status = 'IMBALANCED'
                print(f"⚠️ 对冲配对 {hedge_pair.pair_id} 持仓不平衡: 多头 {long_amount}, 空头 {short_amount}")
                return 'IMBALANCED'

        elif long_has_position and not short_has_position:
            hedge_pair.hedge_status = 'LONG_AHEAD'
            print(f"📈 对冲配对 {hedge_pair.pair_id} 多头领先")
            return 'LONG_AHEAD'

        elif not long_has_position and short_has_position:
            hedge_pair.hedge_status = 'SHORT_AHEAD'
            print(f"📉 对冲配对 {hedge_pair.pair_id} 空头领先")
            return 'SHORT_AHEAD'

        else:
            hedge_pair.hedge_status = 'BALANCED'
            return 'BALANCED'

    async def _execute_hedge_sync(self, hedge_pair: HedgePair, leading_side: str):
        """执行对冲同步逻辑"""
        print(f"🔄 执行对冲同步: 配对 {hedge_pair.pair_id}, 领先方 {leading_side}")

        # 这里可以实现更复杂的同步逻辑
        # 例如：调整订单价格、增加订单数量、使用市价单等

        if hedge_pair.hedge_status == 'LONG_AHEAD':
            await self._accelerate_short_side(hedge_pair)
        elif hedge_pair.hedge_status == 'SHORT_AHEAD':
            await self._accelerate_long_side(hedge_pair)
        elif hedge_pair.hedge_status == 'IMBALANCED':
            await self._rebalance_positions(hedge_pair)

    async def _accelerate_short_side(self, hedge_pair: HedgePair):
        """加速空头方建仓"""
        print(f"⚡ 加速空头建仓: 配对 {hedge_pair.pair_id}")

        short_grid = self.dual_manager.short_strategy.grid_manager.grid_levels.get(hedge_pair.short_grid_id)
        if short_grid and short_grid.status == "ORDER_PENDING":
            # 这里可以实现加速逻辑，比如：
            # 1. 提高订单价格优先级
            # 2. 增加订单数量
            # 3. 使用市价单
            print(f"   空头网格 {short_grid.id} 当前状态: {short_grid.status}")

    async def _accelerate_long_side(self, hedge_pair: HedgePair):
        """加速多头方建仓"""
        print(f"⚡ 加速多头建仓: 配对 {hedge_pair.pair_id}")

        long_grid = self.dual_manager.long_strategy.grid_manager.grid_levels.get(hedge_pair.long_grid_id)
        if long_grid and long_grid.status == "ORDER_PENDING":
            print(f"   多头网格 {long_grid.id} 当前状态: {long_grid.status}")

    async def _rebalance_positions(self, hedge_pair: HedgePair):
        """重平衡持仓"""
        print(f"⚖️ 重平衡持仓: 配对 {hedge_pair.pair_id}")

        # 获取持仓信息
        long_grid = self.dual_manager.long_strategy.grid_manager.grid_levels.get(hedge_pair.long_grid_id)
        short_grid = self.dual_manager.short_strategy.grid_manager.grid_levels.get(hedge_pair.short_grid_id)

        if long_grid and short_grid:
            long_amount = long_grid.position_amount or Decimal('0')
            short_amount = short_grid.position_amount or Decimal('0')
            print(f"   当前持仓: 多头 {long_amount}, 空头 {short_amount}")

    def get_hedge_statistics(self) -> Dict:
        """获取对冲统计信息"""
        balanced_count = sum(1 for pair in self.hedge_pairs.values() if pair.hedge_status == 'BALANCED')
        imbalanced_count = len(self.hedge_pairs) - balanced_count

        hedge_effectiveness = self.successful_hedges / self.total_hedge_trades if self.total_hedge_trades > 0 else 0

        return {
            'total_pairs': len(self.hedge_pairs),
            'balanced_pairs': balanced_count,
            'imbalanced_pairs': imbalanced_count,
            'total_trades': self.total_hedge_trades,
            'successful_hedges': self.successful_hedges,
            'failed_hedges': self.failed_hedges,
            'hedge_effectiveness': hedge_effectiveness,
            'balance_ratio': balanced_count / len(self.hedge_pairs) if self.hedge_pairs else 0
        }
