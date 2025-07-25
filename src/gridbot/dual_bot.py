"""
双账户网格机器人主程序
"""

import asyncio
import signal
import subprocess
import os
from typing import Optional
from .models import DualAccountConfig
from .dual_account_manager import DualAccountManager
from .dual_config import load_dual_config

class DualGridBot:
    """双账户网格机器人"""
    
    def __init__(self, config_path: str, fresh_start: bool = False, enable_boundary_monitor: bool = True):
        self.config_path = config_path
        self.fresh_start = fresh_start
        self.enable_boundary_monitor = enable_boundary_monitor
        self.config: Optional[DualAccountConfig] = None
        self.manager: Optional[DualAccountManager] = None
        self.running = False
        self.boundary_monitor_process = None

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
            # 停止边界监控进程
            self._stop_boundary_monitor()

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

            # 4. 启动边界监控（如果启用）
            if self.enable_boundary_monitor:
                self._start_boundary_monitor()

            # 5. 开始运行
            self.running = True
            print("🚀 双账户网格机器人启动成功")
            print("按 Ctrl+C 优雅退出")

            # 6. 开始监控（使用新的监控方式）
            await self._run_with_signal_handling()

        except KeyboardInterrupt:
            print("\n用户中断，开始退出...")
        except Exception as e:
            print(f"❌ 机器人运行异常: {e}")
        finally:
            await self._cleanup()

    def _start_boundary_monitor(self):
        """启动边界监控进程"""
        try:
            print("🛡️ 启动边界监控程序...")

            # 获取当前脚本的目录
            current_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.dirname(os.path.dirname(current_dir))
            boundary_script = os.path.join(project_root, "scripts", "boundary_monitor.py")

            # 启动边界监控进程
            self.boundary_monitor_process = subprocess.Popen([
                "python3", boundary_script, self.config_path
            ], cwd=project_root, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            print(f"✅ 边界监控程序已启动 (PID: {self.boundary_monitor_process.pid})")

        except Exception as e:
            print(f"⚠️ 启动边界监控程序失败: {e}")
            print("💡 您可以手动启动: python3 scripts/boundary_monitor.py config/dual_config.json")

    def _stop_boundary_monitor(self):
        """停止边界监控进程"""
        if self.boundary_monitor_process:
            try:
                print("🛑 停止边界监控程序...")
                self.boundary_monitor_process.terminate()
                self.boundary_monitor_process.wait(timeout=5)
                print("✅ 边界监控程序已停止")
            except subprocess.TimeoutExpired:
                print("⚠️ 边界监控程序未响应，强制终止...")
                self.boundary_monitor_process.kill()
                self.boundary_monitor_process.wait()
            except Exception as e:
                print(f"⚠️ 停止边界监控程序时出错: {e}")
            finally:
                self.boundary_monitor_process = None

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
            # 1. 停止边界监控程序
            self._stop_boundary_monitor()

            # 2. 清理双账户
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
