"""
双账户网格机器人主程序
"""

import asyncio
import signal
from typing import Optional
from .models import DualAccountConfig
from .dual_account_manager import DualAccountManager
from .dual_config import load_dual_config

class DualGridBot:
    """双账户网格机器人"""
    
    def __init__(self, config_path: str, fresh_start: bool = False):
        self.config_path = config_path
        self.fresh_start = fresh_start
        self.config: Optional[DualAccountConfig] = None
        self.manager: Optional[DualAccountManager] = None
        self.running = False
        
        # 设置信号处理
        self._setup_signal_handlers()
    
    def _setup_signal_handlers(self):
        """设置信号处理器"""
        def signal_handler(signum, frame):
            print(f"\n收到信号 {signum}，开始优雅退出...")
            self.running = False
            # 设置停止标志，让主循环处理停止
            if self.manager:
                self.manager.running = False
                self.manager.long_running = False
                self.manager.short_running = False

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    async def run(self):
        """运行双账户机器人"""
        try:
            # 1. 加载配置
            print("📋 加载双账户配置...")
            self.config = load_dual_config(self.config_path)
            print(f"✅ 配置加载成功: {self.config.name}")

            # 2. 创建双账户管理器
            print("🔧 创建双账户管理器...")
            self.manager = DualAccountManager(self.config)

            # 3. 初始化双账户
            await self.manager.initialize(self.fresh_start)

            # 4. 开始运行
            self.running = True
            print("🚀 双账户网格机器人启动成功")
            print("按 Ctrl+C 优雅退出")

            # 5. 开始监控（使用新的监控方式）
            await self._run_with_signal_handling()

        except KeyboardInterrupt:
            print("\n用户中断，开始退出...")
        except Exception as e:
            print(f"❌ 机器人运行异常: {e}")
        finally:
            await self._cleanup()

    async def _run_with_signal_handling(self):
        """带信号处理的运行方法"""
        # 创建监控任务
        monitor_task = asyncio.create_task(self.manager.start_monitoring())

        try:
            # 主循环：检查停止信号
            while self.running:
                await asyncio.sleep(1)

                # 检查是否收到停止信号
                if not self.running:
                    print("🛑 收到停止信号，开始执行清理...")
                    break

            # 取消监控任务
            monitor_task.cancel()
            try:
                await monitor_task
            except asyncio.CancelledError:
                pass

        except Exception as e:
            print(f"❌ 监控过程异常: {e}")
            monitor_task.cancel()
    
    async def _cleanup(self):
        """清理资源（使用成功验证的清理方法）"""
        print("🧹 开始清理资源...")

        try:
            if self.manager:
                # 使用成功验证的清理方法
                await self.manager._execute_successful_cleanup()

                # 关闭连接
                if self.manager.long_exchange:
                    await self.manager.long_exchange.close()
                if self.manager.short_exchange:
                    await self.manager.short_exchange.close()

            print("✅ 资源清理完成")
        except Exception as e:
            print(f"❌ 清理资源时出错: {e}")
            # 即使出错也要尝试基本清理
            try:
                if self.manager:
                    await self.manager._basic_cleanup()
            except Exception:
                pass
