"""
双账户管理器 - 管理多空两个账户的协调运行
"""

import asyncio
from typing import Dict, Optional
from decimal import Decimal
from .models import DualAccountConfig, BotConfig
from .exchange import ExchangeInterface
from .strategy import GridStrategy

class DualAccountManager:
    """双账户管理器"""
    
    def __init__(self, config: DualAccountConfig):
        self.config = config
        self.running = False
        
        # 创建双账户配置
        self.long_config = config.to_single_config("long")
        self.short_config = config.to_single_config("short")
        
        # 创建交易所接口
        self.long_exchange: Optional[ExchangeInterface] = None
        self.short_exchange: Optional[ExchangeInterface] = None
        
        # 创建策略实例
        self.long_strategy: Optional[GridStrategy] = None
        self.short_strategy: Optional[GridStrategy] = None
        
        # 状态跟踪
        self.long_running = False
        self.short_running = False
        self.initialization_complete = False
    
    async def initialize(self, fresh_start: bool = False):
        """初始化双账户"""
        print(f"🔄 开始初始化双账户管理器...")
        
        try:
            # 1. 创建交易所接口
            self.long_exchange = ExchangeInterface(self.long_config)
            self.short_exchange = ExchangeInterface(self.short_config)
            
            # 2. 初始化交易所连接
            await self.long_exchange.initialize()
            await self.short_exchange.initialize()
            print("✅ 双账户交易所连接初始化完成")
            
            # 3. 设置杠杆和保证金模式
            if self.config.market_type == 'future':
                await self.long_exchange.set_leverage_and_margin_mode()
                await self.short_exchange.set_leverage_and_margin_mode()
                print("✅ 双账户杠杆和保证金模式设置完成")
            
            # 4. 检查余额
            await self._check_balances()
            
            # 5. 创建策略实例
            self.long_strategy = GridStrategy(self.long_config, self.long_exchange)
            self.short_strategy = GridStrategy(self.short_config, self.short_exchange)
            print("✅ 双账户策略实例创建完成")
            
            # 6. 如果是全新开始，清理双账户状态
            if fresh_start:
                print("🧹 执行双账户清理...")
                await self._cleanup_both_accounts()
            
            # 7. 初始化双账户网格
            print("🚀 开始初始化双账户网格...")
            await asyncio.gather(
                self.long_strategy.initialize_grid(fresh_start),
                self.short_strategy.initialize_grid(fresh_start)
            )
            print("✅ 双账户网格初始化完成")
            
            self.initialization_complete = True
            print("🎉 双账户管理器初始化成功")
            
        except Exception as e:
            print(f"❌ 双账户初始化失败: {e}")
            await self._cleanup_on_error()
            raise
    
    async def _check_balances(self):
        """检查双账户余额"""
        try:
            long_balance = await self.long_exchange.fetch_balance()
            short_balance = await self.short_exchange.fetch_balance()
            
            quote_coin = self.config.quote_coin
            long_free = Decimal(str(long_balance['free'].get(quote_coin, 0)))
            short_free = Decimal(str(short_balance['free'].get(quote_coin, 0)))
            
            print(f"💰 账户余额检查:")
            print(f"   多头账户 {quote_coin}: {long_free}")
            print(f"   空头账户 {quote_coin}: {short_free}")
            
            # 计算所需资金
            required_per_account = self.config.order_amount_usdt * self.config.grids
            
            if long_free < required_per_account:
                print(f"⚠️ 多头账户余额不足，需要至少 {required_per_account} {quote_coin}")
            
            if short_free < required_per_account:
                print(f"⚠️ 空头账户余额不足，需要至少 {required_per_account} {quote_coin}")
            
        except Exception as e:
            print(f"❌ 检查余额时出错: {e}")
    
    async def _cleanup_both_accounts(self):
        """清理双账户状态"""
        print("🧹 开始清理双账户状态...")
        
        try:
            # 并行清理两个账户
            await asyncio.gather(
                self.long_strategy._cleanup_exchange_state(),
                self.short_strategy._cleanup_exchange_state()
            )
            print("✅ 双账户状态清理完成")
            
        except Exception as e:
            print(f"❌ 清理双账户状态时出错: {e}")
            raise

    async def start_monitoring(self):
        """开始监控双账户运行"""
        if not self.initialization_complete:
            raise RuntimeError("双账户管理器未完成初始化")

        self.running = True
        self.long_running = True
        self.short_running = True

        print("🔍 开始双账户监控...")

        # 创建监控任务
        tasks = [
            asyncio.create_task(self._monitor_long_account()),
            asyncio.create_task(self._monitor_short_account()),
            asyncio.create_task(self._monitor_coordination()),
            asyncio.create_task(self._periodic_status_report())
        ]

        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            print("🛑 监控任务被取消")
        except Exception as e:
            print(f"❌ 双账户监控异常: {e}")
        finally:
            # 不在这里调用stop()，让外部控制清理时机
            print("🔍 双账户监控结束")

    async def _monitor_long_account(self):
        """监控多头账户"""
        try:
            # 直接使用策略的watch_orders方法
            await self.long_strategy.watch_orders()
        except Exception as e:
            print(f"❌ 多头账户异常: {e}")
            self.long_running = False
            await self._trigger_emergency_stop("多头账户异常")

    async def _monitor_short_account(self):
        """监控空头账户"""
        try:
            # 直接使用策略的watch_orders方法
            await self.short_strategy.watch_orders()
        except Exception as e:
            print(f"❌ 空头账户异常: {e}")
            self.short_running = False
            await self._trigger_emergency_stop("空头账户异常")

    async def _monitor_coordination(self):
        """监控双账户协调"""
        while self.running:
            try:
                # 检查双账户运行状态
                if not self.long_running or not self.short_running:
                    print("⚠️ 检测到账户异常，触发协调停止")
                    await self._trigger_emergency_stop("账户协调异常")
                    break

                # 检查边界突破
                if (self.long_strategy and self.long_strategy.boundary_breached) or \
                   (self.short_strategy and self.short_strategy.boundary_breached):
                    print("🚨 检测到边界突破，触发双账户紧急停止")
                    await self._trigger_emergency_stop("边界突破")
                    break

                # 定期健康检查（降低频率）
                await asyncio.gather(
                    self.long_strategy.health_check(),
                    self.short_strategy.health_check()
                )

                await asyncio.sleep(300)  # 每5分钟检查一次

            except Exception as e:
                print(f"❌ 协调监控异常: {e}")
                await asyncio.sleep(30)

    async def _periodic_status_report(self):
        """定期状态报告"""
        while self.running:
            try:
                await asyncio.sleep(300)  # 每5分钟报告一次

                # 获取双账户统计
                long_stats = self._get_account_stats(self.long_strategy, "多头")
                short_stats = self._get_account_stats(self.short_strategy, "空头")

                print(f"\n📊 === 双账户对冲状态报告 ===")
                print(f"运行时间: {self._get_running_time()}")
                print(f"多头账户: {long_stats}")
                print(f"空头账户: {short_stats}")
                print(f"对冲状态: {'✅ 正常' if self.long_running and self.short_running else '❌ 异常'}")
                print(f"===============================\n")

            except Exception as e:
                print(f"❌ 状态报告异常: {e}")
                await asyncio.sleep(300)

    def _get_account_stats(self, strategy: GridStrategy, side: str) -> str:
        """获取账户统计信息"""
        try:
            total_grids = len(strategy.grid_levels)
            pending_orders = sum(1 for level in strategy.grid_levels.values()
                               if level.status == "ORDER_PENDING")
            held_positions = sum(1 for level in strategy.grid_levels.values()
                               if level.status == "POSITION_HELD")
            total_profit = strategy.total_realized_profit

            return f"网格{total_grids} | 挂单{pending_orders} | 持仓{held_positions} | 利润{total_profit}"

        except Exception:
            return "数据获取失败"

    def _get_running_time(self) -> str:
        """获取运行时间"""
        # 这里可以添加运行时间计算逻辑
        return "运行中"

    async def _trigger_emergency_stop(self, reason: str):
        """触发紧急停止"""
        print(f"🚨 触发紧急停止: {reason}")
        self.running = False
        self.long_running = False
        self.short_running = False

        # 执行紧急清理（使用成功验证的清理方法）
        await self._execute_successful_cleanup()

    async def _emergency_cleanup(self):
        """紧急清理"""
        print("🚨 执行紧急清理...")

        try:
            # 并行清理两个账户
            cleanup_tasks = []

            if self.long_strategy:
                cleanup_tasks.append(self.long_strategy._cleanup_exchange_state())

            if self.short_strategy:
                cleanup_tasks.append(self.short_strategy._cleanup_exchange_state())

            if cleanup_tasks:
                await asyncio.gather(*cleanup_tasks, return_exceptions=True)

            print("✅ 紧急清理完成")

        except Exception as e:
            print(f"❌ 紧急清理异常: {e}")

    async def stop(self):
        """停止双账户管理器"""
        print("🛑 开始停止双账户管理器...")

        self.running = False
        self.long_running = False
        self.short_running = False

        # 停止策略监控
        if self.long_strategy:
            self.long_strategy.stop_watching()

        if self.short_strategy:
            self.short_strategy.stop_watching()

        # 执行清理（使用成功验证的清理方法）
        await self._execute_successful_cleanup()

        # 关闭交易所连接
        if self.long_exchange:
            await self.long_exchange.close()

        if self.short_exchange:
            await self.short_exchange.close()

        print("✅ 双账户管理器已停止")

    async def _execute_successful_cleanup(self):
        """执行成功验证的清理方法"""
        print("🧹 开始执行双账户清理（使用成功验证的方法）...")

        try:
            # 使用策略的 _cleanup_exchange_state 方法，这是已验证成功的清理方法
            cleanup_tasks = []

            if self.long_strategy:
                print("🧹 清理多头账户...")
                cleanup_tasks.append(self.long_strategy._cleanup_exchange_state())

            if self.short_strategy:
                print("🧹 清理空头账户...")
                cleanup_tasks.append(self.short_strategy._cleanup_exchange_state())

            if cleanup_tasks:
                # 并行执行清理，但捕获异常确保不会因为一个账户失败而影响另一个
                results = await asyncio.gather(*cleanup_tasks, return_exceptions=True)

                for i, result in enumerate(results):
                    account_name = "多头" if i == 0 else "空头"
                    if isinstance(result, Exception):
                        print(f"❌ {account_name}账户清理异常: {result}")
                    else:
                        print(f"✅ {account_name}账户清理完成")

            print("✅ 双账户清理执行完成")

        except Exception as e:
            print(f"❌ 执行清理时出错: {e}")
            # 即使出错也要尝试基本清理
            await self._basic_cleanup()

    async def _basic_cleanup(self):
        """基本清理（关闭连接）"""
        try:
            if self.long_exchange:
                await self.long_exchange.close()
            if self.short_exchange:
                await self.short_exchange.close()
            print("✅ 基本清理完成")
        except Exception as e:
            print(f"❌ 基本清理异常: {e}")

    async def _cleanup_on_error(self):
        """错误时清理"""
        await self._basic_cleanup()
