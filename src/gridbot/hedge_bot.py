"""
对冲网格机器人 - 集成所有对冲功能的主控制器
"""

import asyncio
import signal
from datetime import datetime
from typing import Optional
from .models import DualAccountConfig, Trade
from .dual_account_manager import DualAccountManager
from .hedge_pair_manager import HedgePairManager

class HedgeGridBot:
    """对冲网格机器人"""
    
    def __init__(self, config: DualAccountConfig, fresh_start: bool = False):
        self.config = config
        self.fresh_start = fresh_start
        
        # 创建双账户管理器
        long_config = config.create_long_config()
        short_config = config.create_short_config()
        self.dual_manager = DualAccountManager(long_config, short_config)
        
        # 创建对冲配对管理器
        self.hedge_manager = HedgePairManager(self.dual_manager, config)
        
        # 运行状态
        self.running = True
        self.tasks = []
        
        # 设置信号处理
        self._setup_signal_handlers()
    
    def _setup_signal_handlers(self):
        """设置信号处理器"""
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """信号处理器"""
        print(f"\n收到信号 {signum}，开始优雅退出...")
        self.running = False
    
    async def run(self):
        """运行对冲网格机器人"""
        try:
            print("🚀 启动对冲网格机器人...")
            
            # 1. 初始化双账户管理器
            await self.dual_manager.initialize()
            
            # 2. 启动双边策略
            await self.dual_manager.start_strategies(self.fresh_start)
            
            # 3. 初始化对冲配对
            pair_count = await self.hedge_manager.initialize_hedge_pairs()
            if pair_count == 0:
                print("❌ 未能创建任何对冲配对，退出")
                return
            
            # 4. 启动监控任务
            self.tasks.extend(await self.dual_manager.start_monitoring())
            self.tasks.extend(await self._start_hedge_monitoring())
            
            # 5. 启动交易监控
            self.tasks.extend([
                asyncio.create_task(self._watch_long_orders()),
                asyncio.create_task(self._watch_short_orders()),
                asyncio.create_task(self._periodic_status_report())
            ])
            
            print("✅ 对冲网格机器人启动完成")
            
            # 6. 等待任务完成或中断
            await asyncio.gather(*self.tasks, return_exceptions=True)
            
        except Exception as e:
            print(f"❌ 机器人运行异常: {e}")
        finally:
            await self._cleanup()
    
    async def _start_hedge_monitoring(self):
        """启动对冲监控任务"""
        return [
            asyncio.create_task(self._monitor_hedge_effectiveness()),
            asyncio.create_task(self._monitor_sync_delays())
        ]
    
    async def _watch_long_orders(self):
        """监控多头账户订单"""
        while self.running:
            try:
                # 监控多头账户的订单成交
                async for trade_data in self.dual_manager.long_exchange.watch_my_trades():
                    if not self.running:
                        break
                    
                    trade = Trade(**trade_data)
                    
                    # 处理策略逻辑
                    await self.dual_manager.long_strategy.handle_filled_order(trade)
                    
                    # 处理对冲逻辑
                    await self.hedge_manager.handle_trade_event(trade, 'long')
                    
            except Exception as e:
                print(f"❌ 多头订单监控异常: {e}")
                await asyncio.sleep(5)
    
    async def _watch_short_orders(self):
        """监控空头账户订单"""
        while self.running:
            try:
                # 监控空头账户的订单成交
                async for trade_data in self.dual_manager.short_exchange.watch_my_trades():
                    if not self.running:
                        break
                    
                    trade = Trade(**trade_data)
                    
                    # 处理策略逻辑
                    await self.dual_manager.short_strategy.handle_filled_order(trade)
                    
                    # 处理对冲逻辑
                    await self.hedge_manager.handle_trade_event(trade, 'short')
                    
            except Exception as e:
                print(f"❌ 空头订单监控异常: {e}")
                await asyncio.sleep(5)

    async def _monitor_hedge_effectiveness(self):
        """监控对冲有效性"""
        while self.running:
            try:
                stats = self.hedge_manager.get_hedge_statistics()

                print(f"🎯 对冲效果监控:")
                print(f"   总配对数: {stats['total_pairs']}")
                print(f"   平衡配对: {stats['balanced_pairs']}")
                print(f"   不平衡配对: {stats['imbalanced_pairs']}")
                print(f"   对冲有效性: {stats['hedge_effectiveness']:.2%}")
                print(f"   平衡比例: {stats['balance_ratio']:.2%}")

                await asyncio.sleep(300)  # 每5分钟报告一次

            except Exception as e:
                print(f"❌ 对冲效果监控异常: {e}")
                await asyncio.sleep(300)

    async def _monitor_sync_delays(self):
        """监控同步延迟"""
        while self.running:
            try:
                current_time = int(datetime.now().timestamp() * 1000)
                delayed_pairs = []

                for pair in self.hedge_manager.hedge_pairs.values():
                    sync_delay = current_time - pair.last_sync_timestamp
                    if sync_delay > self.config.sync_tolerance_seconds * 1000:
                        delayed_pairs.append((pair.pair_id, sync_delay / 1000))

                if delayed_pairs:
                    print(f"⏰ 发现 {len(delayed_pairs)} 个延迟同步的配对")
                    for pair_id, delay in delayed_pairs:
                        print(f"   {pair_id}: 延迟 {delay:.1f} 秒")

                await asyncio.sleep(60)  # 每分钟检查一次

            except Exception as e:
                print(f"❌ 同步延迟监控异常: {e}")
                await asyncio.sleep(60)

    async def _periodic_status_report(self):
        """定期状态报告"""
        while self.running:
            try:
                # 获取双边统计
                long_stats = self.dual_manager.long_strategy.grid_manager.get_grid_statistics()
                short_stats = self.dual_manager.short_strategy.grid_manager.get_grid_statistics()
                hedge_stats = self.hedge_manager.get_hedge_statistics()

                print(f"\n📊 === 对冲网格状态报告 ===")
                print(f"多头账户: {long_stats['position_count']} 持仓, {long_stats['pending_count']} 挂单")
                print(f"空头账户: {short_stats['position_count']} 持仓, {short_stats['pending_count']} 挂单")
                print(f"对冲状态: {hedge_stats['balanced_pairs']}/{hedge_stats['total_pairs']} 平衡")
                print(f"总利润: 多头 {long_stats['total_profit']:.2f} + 空头 {short_stats['total_profit']:.2f} USDT")
                print(f"=========================\n")

                await asyncio.sleep(600)  # 每10分钟报告一次

            except Exception as e:
                print(f"❌ 状态报告异常: {e}")
                await asyncio.sleep(600)

    async def _cleanup(self):
        """清理资源"""
        print("\n🛑 开始清理对冲网格机器人...")

        self.running = False

        # 取消所有任务
        for task in self.tasks:
            if not task.done():
                task.cancel()

        # 清理双账户管理器
        await self.dual_manager.cleanup()

        print("✅ 对冲网格机器人清理完成")
