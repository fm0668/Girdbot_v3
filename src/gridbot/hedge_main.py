#!/usr/bin/env python3
"""
对冲网格机器人启动脚本
"""

import argparse
import asyncio
import json
import os
import re
import sys
from pathlib import Path
from .models import DualAccountConfig
from .hedge_bot import HedgeGridBot

def load_env_variables():
    """加载环境变量"""
    from dotenv import load_dotenv
    load_dotenv()

def substitute_env_variables(config_str: str) -> str:
    """替换配置文件中的环境变量"""
    def replace_var(match):
        var_name = match.group(1)
        env_value = os.getenv(var_name)
        if env_value is None:
            print(f"⚠️ 环境变量 {var_name} 未设置")
            return match.group(0)  # 保持原样
        return env_value

    # 替换 ${VAR_NAME} 格式的环境变量
    return re.sub(r'\$\{([^}]+)\}', replace_var, config_str)

def load_dual_config(config_path: str) -> DualAccountConfig:
    """加载双账户配置"""
    try:
        # 加载环境变量
        load_env_variables()

        # 读取配置文件
        with open(config_path, 'r') as f:
            config_str = f.read()

        # 替换环境变量
        config_str = substitute_env_variables(config_str)

        # 解析JSON
        config_data = json.loads(config_str)

        # 移除注释字段
        config_data = {k: v for k, v in config_data.items() if not k.startswith('_')}

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
