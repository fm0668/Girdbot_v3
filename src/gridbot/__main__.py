#!/usr/bin/env python3
"""
网格交易机器人主入口
"""

import argparse
import asyncio
import sys
from pathlib import Path

from .bot import GridBot


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='永续合约网格交易机器人')
    parser.add_argument('--config', type=str, help='配置文件路径')
    parser.add_argument('--fresh', action='store_true', help='全新开始，清理所有现有持仓和订单')
    
    args = parser.parse_args()
    
    try:
        bot = GridBot(config_path=args.config, fresh_start=args.fresh)
        asyncio.run(bot.run())
    except KeyboardInterrupt:
        print("\n用户中断，正在退出...")
        sys.exit(0)
    except Exception as e:
        print(f"机器人运行错误：{e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
