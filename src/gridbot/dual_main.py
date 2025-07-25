#!/usr/bin/env python3
"""
双账户网格机器人启动脚本
"""

import argparse
import asyncio
import sys
from pathlib import Path
from .dual_bot import DualGridBot

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='双账户对冲网格交易机器人')
    parser.add_argument('--config', type=str, required=True, help='双账户配置文件路径')
    parser.add_argument('--fresh', action='store_true', help='全新开始，清理所有现有持仓和订单')
    parser.add_argument('--no-boundary-monitor', action='store_true', help='禁用自动边界监控')

    args = parser.parse_args()
    
    # 检查配置文件是否存在
    if not Path(args.config).exists():
        print(f"❌ 配置文件不存在: {args.config}")
        sys.exit(1)
    
    try:
        # 创建并运行机器人
        enable_boundary_monitor = not args.no_boundary_monitor
        bot = DualGridBot(args.config, fresh_start=args.fresh, enable_boundary_monitor=enable_boundary_monitor)

        if enable_boundary_monitor:
            print("🛡️ 边界监控已启用（自动启动）")
        else:
            print("⚠️ 边界监控已禁用")

        asyncio.run(bot.run())
        
    except KeyboardInterrupt:
        print("\n用户中断，正在退出...")
        sys.exit(0)
    except Exception as e:
        print(f"❌ 机器人运行错误: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
