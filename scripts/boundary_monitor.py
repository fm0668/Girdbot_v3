#!/usr/bin/env python3
"""
独立的边界监控程序
实时监控价格，一旦突破边界就立即清理双账户并停止策略
"""

import asyncio
import sys
import signal
import os
from pathlib import Path
from decimal import Decimal

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.gridbot.dual_config import load_dual_config
from src.gridbot.exchange import ExchangeInterface

class BoundaryMonitor:
    """边界监控器"""
    
    def __init__(self, config_path: str):
        self.config_path = config_path
        self.config = None
        self.running = True
        self.boundary_breached = False
        
        # 设置信号处理
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """信号处理器"""
        print(f"\n收到停止信号 {signum}，边界监控器退出...")
        self.running = False
    
    async def start_monitoring(self):
        """开始边界监控"""
        try:
            # 1. 加载配置
            print("📋 加载双账户配置...")
            self.config = load_dual_config(self.config_path)
            print(f"✅ 配置加载成功: {self.config.name}")
            
            # 2. 显示监控信息
            print(f"📊 监控边界：{self.config.lower_price} - {self.config.upper_price}")
            print(f"💱 监控交易对: {self.config.pair}")
            print("🔍 开始实时边界监控...")
            print("按 Ctrl+C 停止监控")
            
            # 3. 创建交易所接口（用于获取价格）
            temp_config = self.config.to_single_config("long")
            exchange = ExchangeInterface(temp_config)
            await exchange.initialize()
            
            # 4. 开始监控循环
            check_count = 0
            while self.running and not self.boundary_breached:
                try:
                    # 获取当前价格
                    current_price = await self._get_current_price(exchange)
                    check_count += 1
                    
                    if current_price > 0:
                        # 每10次检查显示一次价格
                        if check_count % 10 == 0:
                            print(f"💹 当前价格: {current_price} | 边界: {self.config.lower_price} - {self.config.upper_price}")
                        
                        # 检查边界突破
                        if await self._check_boundary_breach(current_price):
                            print("🚨 检测到边界突破，开始执行紧急清理...")
                            await self._execute_emergency_cleanup()
                            break
                    
                    # 每秒检查一次
                    await asyncio.sleep(1)
                    
                except Exception as e:
                    print(f"❌ 监控过程中出错: {e}")
                    await asyncio.sleep(5)
            
            await exchange.close()
            
        except Exception as e:
            print(f"❌ 边界监控启动失败: {e}")
    
    async def _get_current_price(self, exchange) -> Decimal:
        """获取当前市场价格"""
        try:
            ticker = await exchange.fetch_ticker(self.config.pair)
            return Decimal(str(ticker['last']))
        except Exception as e:
            print(f"获取价格失败: {e}")
            return Decimal('0')
    
    async def _check_boundary_breach(self, current_price: Decimal) -> bool:
        """检查边界突破"""
        # 检查上边界突破
        if current_price > self.config.upper_price:
            print(f"🚨 价格突破上边界！")
            print(f"   当前价格: {current_price}")
            print(f"   上边界: {self.config.upper_price}")
            print(f"   突破幅度: {current_price - self.config.upper_price}")
            self.boundary_breached = True
            return True
        
        # 检查下边界突破
        if current_price < self.config.lower_price:
            print(f"🚨 价格突破下边界！")
            print(f"   当前价格: {current_price}")
            print(f"   下边界: {self.config.lower_price}")
            print(f"   突破幅度: {self.config.lower_price - current_price}")
            self.boundary_breached = True
            return True
        
        return False
    
    async def _execute_emergency_cleanup(self):
        """执行紧急清理"""
        print("🚨 开始执行边界突破紧急清理...")

        try:
            # 1. 先执行双账户清理（最重要）
            print("🧹 开始清理双账户...")
            cleanup_success = await self._cleanup_dual_accounts()

            if cleanup_success:
                # 2. 验证清理结果
                print("🔍 验证清理结果...")
                verification_success = await self._verify_cleanup_results()

                if verification_success:
                    print("✅ 清理验证通过")

                    # 3. 清理成功后才停止进程
                    print("🔪 停止所有网格机器人进程...")
                    os.system("pkill -f 'dual_main' 2>/dev/null")
                    os.system("pkill -f 'python.*gridbot' 2>/dev/null")

                    print("✅ 边界突破紧急清理完成！")
                    print("🛑 所有网格策略已停止")
                else:
                    print("⚠️ 清理验证失败，可能有遗漏，请手动检查")
            else:
                print("❌ 双账户清理失败")

        except Exception as e:
            print(f"❌ 紧急清理失败: {e}")
            print("🚨 建议立即手动检查账户状态")
    
    async def _cleanup_dual_accounts(self) -> bool:
        """清理双账户，使用已验证的策略清理方法"""
        try:
            # 创建双账户配置
            long_config = self.config.to_single_config("long")
            short_config = self.config.to_single_config("short")

            # 创建交易所接口
            long_exchange = ExchangeInterface(long_config)
            short_exchange = ExchangeInterface(short_config)

            # 初始化连接
            await long_exchange.initialize()
            await short_exchange.initialize()

            # 设置杠杆和保证金模式
            if self.config.market_type == 'future':
                await long_exchange.set_leverage_and_margin_mode()
                await short_exchange.set_leverage_and_margin_mode()

            # 创建策略实例以使用已验证的清理方法
            from src.gridbot.strategy import GridStrategy

            long_strategy = GridStrategy(long_config, long_exchange)
            short_strategy = GridStrategy(short_config, short_exchange)

            print("🧹 使用已验证的策略清理方法...")

            # 并行清理两个账户（最多重试3次）
            success = False
            for attempt in range(3):
                print(f"🧹 第{attempt + 1}次尝试清理双账户...")

                cleanup_tasks = [
                    long_strategy._cleanup_exchange_state(),
                    short_strategy._cleanup_exchange_state()
                ]

                results = await asyncio.gather(*cleanup_tasks, return_exceptions=True)

                # 检查清理结果
                all_success = True
                for i, result in enumerate(results):
                    account_name = "多头" if i == 0 else "空头"
                    if isinstance(result, Exception):
                        print(f"❌ {account_name}账户清理异常: {result}")
                        all_success = False
                    else:
                        print(f"✅ {account_name}账户清理完成")

                if all_success:
                    success = True
                    break
                else:
                    if attempt < 2:  # 不是最后一次尝试
                        print(f"⚠️ 第{attempt + 1}次清理有问题，等待3秒后重试...")
                        await asyncio.sleep(3)

            # 关闭连接
            await long_exchange.close()
            await short_exchange.close()

            return success

        except Exception as e:
            print(f"❌ 双账户清理失败: {e}")
            return False
    


    async def _verify_cleanup_results(self) -> bool:
        """验证清理结果，确保所有挂单和持仓都已清理"""
        try:
            print("🔍 开始验证清理结果...")

            # 创建双账户配置
            long_config = self.config.to_single_config("long")
            short_config = self.config.to_single_config("short")

            # 创建交易所接口
            long_exchange = ExchangeInterface(long_config)
            short_exchange = ExchangeInterface(short_config)

            # 初始化连接
            await long_exchange.initialize()
            await short_exchange.initialize()

            # 设置杠杆和保证金模式
            if self.config.market_type == 'future':
                await long_exchange.set_leverage_and_margin_mode()
                await short_exchange.set_leverage_and_margin_mode()

            # 验证两个账户
            verification_tasks = [
                self._verify_single_account(long_exchange, "多头"),
                self._verify_single_account(short_exchange, "空头")
            ]

            results = await asyncio.gather(*verification_tasks, return_exceptions=True)

            # 检查验证结果
            all_clean = True
            for i, result in enumerate(results):
                account_name = "多头" if i == 0 else "空头"
                if isinstance(result, Exception):
                    print(f"❌ {account_name}账户验证异常: {result}")
                    all_clean = False
                elif not result:
                    print(f"❌ {account_name}账户验证失败：仍有未清理的订单或持仓")
                    all_clean = False
                else:
                    print(f"✅ {account_name}账户验证通过：无挂单无持仓")

            # 关闭连接
            await long_exchange.close()
            await short_exchange.close()

            return all_clean

        except Exception as e:
            print(f"❌ 验证清理结果失败: {e}")
            return False

    async def _verify_single_account(self, exchange, account_name) -> bool:
        """验证单个账户是否清理干净"""
        try:
            # 检查挂单
            orders = await exchange.fetch_open_orders()
            if orders:
                print(f"⚠️ {account_name}账户仍有 {len(orders)} 个挂单未清理：")
                for order in orders:
                    print(f"   订单ID: {order['id']}, 方向: {order['side']}, 价格: {order['price']}")
                return False

            # 检查持仓
            positions = await exchange.fetch_positions()
            active_positions = []
            for position in positions:
                contracts = float(position.get('contracts', 0))
                if abs(contracts) > 0:
                    active_positions.append(position)

            if active_positions:
                print(f"⚠️ {account_name}账户仍有 {len(active_positions)} 个持仓未清理：")
                for position in active_positions:
                    contracts = position.get('contracts', 0)
                    symbol = position.get('symbol', '')
                    print(f"   持仓: {contracts} {symbol}")
                return False

            return True

        except Exception as e:
            print(f"❌ 验证{account_name}账户失败: {e}")
            return False

async def main():
    """主函数"""
    if len(sys.argv) != 2:
        print("用法: python scripts/boundary_monitor.py <config_path>")
        print("示例: python scripts/boundary_monitor.py config/dual_config.json")
        sys.exit(1)
    
    config_path = sys.argv[1]
    
    if not Path(config_path).exists():
        print(f"❌ 配置文件不存在: {config_path}")
        sys.exit(1)
    
    monitor = BoundaryMonitor(config_path)
    await monitor.start_monitoring()

if __name__ == "__main__":
    asyncio.run(main())
