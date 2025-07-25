"""
双账户管理器 - 管理多空两个账户的交易所连接和策略实例
为对冲网格提供基础设施支持
"""

import asyncio
from typing import Dict, Optional
from .models import BotConfig
from .exchange import ExchangeInterface
from .strategy import GridStrategy

class DualAccountManager:
    """双账户管理器"""
    
    def __init__(self, long_config: BotConfig, short_config: BotConfig):
        self.long_config = long_config
        self.short_config = short_config
        
        # 创建双交易所连接
        self.long_exchange = ExchangeInterface(long_config)
        self.short_exchange = ExchangeInterface(short_config)
        
        # 创建双策略实例
        self.long_strategy = GridStrategy(long_config, self.long_exchange)
        self.short_strategy = GridStrategy(short_config, self.short_exchange)
        
        # 运行状态
        self.running = False
        self.sync_tasks = []
    
    async def initialize(self):
        """初始化双账户"""
        print("🔄 初始化双账户管理器...")
        
        # 并行初始化两个交易所
        await asyncio.gather(
            self.long_exchange.initialize(),
            self.short_exchange.initialize()
        )
        
        # 设置杠杆和保证金模式
        if self.long_config.market_type == 'future':
            await asyncio.gather(
                self.long_exchange.set_leverage_and_margin_mode(),
                self.short_exchange.set_leverage_and_margin_mode()
            )
        
        # 获取账户余额
        long_balance = await self.long_exchange.fetch_balance()
        short_balance = await self.short_exchange.fetch_balance()
        
        print(f"📊 多头账户余额: {long_balance.get('USDT', {}).get('free', 0)} USDT")
        print(f"📊 空头账户余额: {short_balance.get('USDT', {}).get('free', 0)} USDT")
        
        self.running = True
        print("✅ 双账户管理器初始化完成")
    
    async def start_strategies(self, fresh_start: bool = False):
        """启动双策略"""
        print("🚀 启动双边网格策略...")
        
        # 并行初始化双策略
        await asyncio.gather(
            self.long_strategy.initialize_grid(fresh_start),
            self.short_strategy.initialize_grid(fresh_start)
        )
        
        print("✅ 双边网格策略启动完成")
    
    async def start_monitoring(self):
        """启动监控任务"""
        print("👁️ 启动双账户监控...")
        
        # 创建监控任务
        self.sync_tasks = [
            asyncio.create_task(self._monitor_account_sync()),
            asyncio.create_task(self._monitor_balance_changes()),
            asyncio.create_task(self._monitor_position_drift())
        ]
        
        return self.sync_tasks
    
    async def _monitor_account_sync(self):
        """监控账户同步状态"""
        while self.running:
            try:
                # 获取双边持仓统计
                long_stats = self.long_strategy.grid_manager.get_grid_statistics()
                short_stats = self.short_strategy.grid_manager.get_grid_statistics()
                
                print(f"📊 账户同步监控:")
                print(f"   多头账户: {long_stats['position_count']} 个持仓")
                print(f"   空头账户: {short_stats['position_count']} 个持仓")
                
                # 检查持仓不平衡
                position_diff = abs(long_stats['position_count'] - short_stats['position_count'])
                if position_diff > 2:  # 允许2个网格的差异
                    print(f"⚠️ 持仓不平衡: 差异 {position_diff} 个网格")
                
                await asyncio.sleep(60)  # 每分钟检查一次
                
            except Exception as e:
                print(f"❌ 账户同步监控异常: {e}")
                await asyncio.sleep(60)
    
    async def _monitor_balance_changes(self):
        """监控余额变化"""
        while self.running:
            try:
                # 获取当前余额
                long_balance = await self.long_exchange.fetch_balance()
                short_balance = await self.short_exchange.fetch_balance()
                
                long_usdt = long_balance.get('USDT', {}).get('free', 0)
                short_usdt = short_balance.get('USDT', {}).get('free', 0)
                
                # 这里可以添加余额告警逻辑
                if long_usdt < 100 or short_usdt < 100:
                    print(f"⚠️ 账户余额不足: 多头 {long_usdt} USDT, 空头 {short_usdt} USDT")
                
                await asyncio.sleep(300)  # 每5分钟检查一次
                
            except Exception as e:
                print(f"❌ 余额监控异常: {e}")
                await asyncio.sleep(300)

    async def _monitor_position_drift(self):
        """监控持仓漂移"""
        while self.running:
            try:
                # 获取实际持仓
                long_positions = await self.long_exchange.fetch_positions([self.long_config.pair])
                short_positions = await self.short_exchange.fetch_positions([self.short_config.pair])

                # 计算净持仓
                net_position = self._calculate_net_position(long_positions, short_positions)

                if abs(net_position) > 0.1:  # 净持仓超过0.1个币
                    print(f"⚠️ 检测到持仓漂移: 净持仓 {net_position}")

                await asyncio.sleep(180)  # 每3分钟检查一次

            except Exception as e:
                print(f"❌ 持仓漂移监控异常: {e}")
                await asyncio.sleep(180)

    def _calculate_net_position(self, long_positions, short_positions) -> float:
        """计算净持仓"""
        long_size = 0
        short_size = 0

        for pos in long_positions:
            if pos.get('symbol') == self.long_config.pair and pos.get('side') == 'long':
                long_size += float(pos.get('contracts', 0))

        for pos in short_positions:
            if pos.get('symbol') == self.short_config.pair and pos.get('side') == 'short':
                short_size += float(pos.get('contracts', 0))

        return long_size - short_size

    async def cleanup(self):
        """清理资源"""
        print("🧹 清理双账户管理器...")

        self.running = False

        # 取消监控任务
        for task in self.sync_tasks:
            task.cancel()

        # 清理策略状态
        await asyncio.gather(
            self.long_strategy._cleanup_exchange_state(),
            self.short_strategy._cleanup_exchange_state(),
            return_exceptions=True
        )

        # 关闭交易所连接
        await asyncio.gather(
            self.long_exchange.close(),
            self.short_exchange.close(),
            return_exceptions=True
        )

        print("✅ 双账户管理器清理完成")
