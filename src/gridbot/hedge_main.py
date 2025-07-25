#!/usr/bin/env python3
"""
对冲网格机器人启动脚本
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from .models import DualAccountConfig
from .hedge_bot import HedgeGridBot

def load_dual_config(config_path: str) -> DualAccountConfig:
    """加载双账户配置"""
    try:
        with open(config_path, 'r') as f:
            config_data = json.load(f)
        
        return DualAccountConfig(**config_data)
    except Exception as e:
        print(f"❌ 加载配置文件失败: {e}")
        sys.exit(1)

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='对冲网格交易机器人')
    parser.add_argument('--config', type=str, required=True, help='双账户配置文件路径')
    parser.add_argument('--fresh', action='store_true', help='全新开始，清理所有现有持仓和订单')
    
    args = parser.parse_args()
    
    # 检查配置文件是否存在
    if not Path(args.config).exists():
        print(f"❌ 配置文件不存在: {args.config}")
        sys.exit(1)
    
    try:
        # 加载配置
        config = load_dual_config(args.config)
        print(f"✅ 成功加载配置: {config.name}")
        
        # 创建并运行机器人
        bot = HedgeGridBot(config, fresh_start=args.fresh)
        asyncio.run(bot.run())
        
    except KeyboardInterrupt:
        print("\n用户中断，正在退出...")
        sys.exit(0)
    except Exception as e:
        print(f"❌ 机器人运行错误: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
