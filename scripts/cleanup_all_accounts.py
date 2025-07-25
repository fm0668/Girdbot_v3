#!/usr/bin/env python3
"""
清理所有账户的挂单和持仓
"""

import asyncio
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.gridbot.dual_config import load_dual_config
from src.gridbot.dual_account_manager import DualAccountManager

async def cleanup_all_accounts():
    """清理所有账户"""
    try:
        print("🧹 开始清理所有账户...")
        
        # 1. 加载配置
        print("📋 加载配置...")
        config = load_dual_config('config/dual_config.json')
        print(f"✅ 配置加载成功: {config.name}")
        
        # 2. 创建双账户管理器
        print("🔧 创建双账户管理器...")
        manager = DualAccountManager(config)
        
        # 3. 初始化交易所连接
        print("🌐 初始化交易所连接...")
        from src.gridbot.exchange import ExchangeInterface
        from src.gridbot.strategy import GridStrategy
        
        # 创建配置
        long_config = config.to_single_config("long")
        short_config = config.to_single_config("short")
        
        # 创建交易所接口
        long_exchange = ExchangeInterface(long_config)
        short_exchange = ExchangeInterface(short_config)
        
        # 初始化连接
        await long_exchange.initialize()
        await short_exchange.initialize()
        
        # 设置杠杆和保证金模式
        if config.market_type == 'future':
            await long_exchange.set_leverage_and_margin_mode()
            await short_exchange.set_leverage_and_margin_mode()
        
        print("✅ 交易所连接初始化完成")
        
        # 4. 创建策略实例
        long_strategy = GridStrategy(long_config, long_exchange)
        short_strategy = GridStrategy(short_config, short_exchange)
        
        # 5. 使用策略的清理方法
        print("🧹 开始清理双账户状态...")
        
        await asyncio.gather(
            long_strategy._cleanup_exchange_state(),
            short_strategy._cleanup_exchange_state()
        )
        
        print("✅ 双账户状态清理完成")
        
        # 6. 关闭连接
        await long_exchange.close()
        await short_exchange.close()
        
        print("🎉 所有账户清理完成！")
        
    except Exception as e:
        print(f"❌ 清理失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(cleanup_all_accounts())
