#!/usr/bin/env python3
"""
交易所连接测试脚本
测试配置加载和ExchangeInterface创建是否正常
"""

import sys
import os
import asyncio
from pathlib import Path

# 添加项目路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.gridbot.hedge_main import load_dual_config
from src.gridbot.dual_account_manager import DualAccountManager
from src.gridbot.hedge_bot import HedgeGridBot

async def test_config_loading():
    """测试配置加载"""
    print("🧪 测试配置加载...")
    
    config_path = "config/hedge_config_test.json"
    if not Path(config_path).exists():
        print(f"❌ 配置文件不存在: {config_path}")
        return None
    
    try:
        config = load_dual_config(config_path)
        print(f"✅ 配置加载成功: {config.name}")
        print(f"   交易所: {config.exchange}")
        print(f"   沙盒模式: {config.sandbox_mode}")
        print(f"   交易对: {config.pair}")
        print(f"   多头API密钥: {config.long_api_key[:10]}...")
        print(f"   空头API密钥: {config.short_api_key[:10]}...")
        return config
    except Exception as e:
        print(f"❌ 配置加载失败: {e}")
        return None

async def test_dual_account_manager(config):
    """测试双账户管理器创建"""
    print("\n🧪 测试双账户管理器创建...")
    
    try:
        # 创建双账户配置
        long_config = config.create_long_config()
        short_config = config.create_short_config()
        
        print(f"   多头配置: {long_config.name} ({long_config.strategy_side})")
        print(f"   空头配置: {short_config.name} ({short_config.strategy_side})")
        
        # 创建双账户管理器
        dual_manager = DualAccountManager(long_config, short_config)
        print("✅ 双账户管理器创建成功")
        
        # 测试初始化（这里可能会遇到ExchangeInterface问题）
        print("   正在测试交易所连接初始化...")
        await dual_manager.initialize()
        print("✅ 交易所连接初始化成功")
        
        return dual_manager
        
    except Exception as e:
        print(f"❌ 双账户管理器创建失败: {e}")
        print(f"   错误类型: {type(e).__name__}")
        import traceback
        traceback.print_exc()
        return None

async def test_hedge_bot(config):
    """测试对冲机器人创建"""
    print("\n🧪 测试对冲机器人创建...")
    
    try:
        # 创建对冲机器人
        bot = HedgeGridBot(config, fresh_start=False)
        print("✅ 对冲机器人创建成功")
        
        # 注意：这里不运行bot.run()，只测试创建
        print("   机器人配置验证通过")
        return bot
        
    except Exception as e:
        print(f"❌ 对冲机器人创建失败: {e}")
        print(f"   错误类型: {type(e).__name__}")
        import traceback
        traceback.print_exc()
        return None

async def test_exchange_interface_directly():
    """直接测试ExchangeInterface"""
    print("\n🧪 直接测试ExchangeInterface...")
    
    try:
        from src.gridbot.exchange import ExchangeInterface
        from src.gridbot.models import BotConfig
        
        # 创建测试配置
        test_config = BotConfig(
            name="TestBot",
            exchange="binance",
            api_key=os.getenv("LONG_API_KEY", "test-key"),
            api_secret=os.getenv("LONG_API_SECRET", "test-secret"),
            sandbox_mode=True,
            market_type="future",
            pair="BTC/USDT",
            strategy_side="long",
            leverage=3,
            lower_price=65000,
            upper_price=75000,
            grids=10,
            order_amount_usdt=10,
            max_position_count=5,
            frontend=False,
            frontend_host="localhost:8080"
        )
        
        print(f"   使用API密钥: {test_config.api_key[:10]}...")
        
        # 创建ExchangeInterface
        exchange = ExchangeInterface(test_config)
        print("✅ ExchangeInterface创建成功")
        
        # 测试初始化
        await exchange.initialize()
        print("✅ ExchangeInterface初始化成功")
        
        # 测试基本功能
        balance = await exchange.fetch_balance()
        print(f"✅ 账户余额获取成功: {len(balance)} 个币种")
        
        return exchange
        
    except Exception as e:
        print(f"❌ ExchangeInterface测试失败: {e}")
        print(f"   错误类型: {type(e).__name__}")
        import traceback
        traceback.print_exc()
        return None

def check_env_variables():
    """检查环境变量"""
    print("🔍 检查环境变量...")
    
    required_vars = ["LONG_API_KEY", "LONG_API_SECRET", "SHORT_API_KEY", "SHORT_API_SECRET"]
    missing_vars = []
    
    for var in required_vars:
        value = os.getenv(var)
        if not value or value.startswith("your-"):
            missing_vars.append(var)
        else:
            print(f"   ✅ {var}: {value[:10]}...")
    
    if missing_vars:
        print(f"   ❌ 缺少环境变量: {', '.join(missing_vars)}")
        print("   请在.env文件中设置正确的API密钥")
        return False
    
    print("   ✅ 所有环境变量已设置")
    return True

async def main():
    """主测试函数"""
    print("🚀 开始交易所连接测试")
    print("=" * 50)
    
    # 1. 检查环境变量
    if not check_env_variables():
        print("\n❌ 环境变量检查失败，请先在.env文件中设置正确的API密钥")
        return
    
    # 2. 测试配置加载
    config = await test_config_loading()
    if not config:
        return
    
    # 3. 直接测试ExchangeInterface
    exchange = await test_exchange_interface_directly()
    if exchange:
        await exchange.close()
    
    # 4. 测试双账户管理器
    dual_manager = await test_dual_account_manager(config)
    if dual_manager:
        await dual_manager.cleanup()
    
    # 5. 测试对冲机器人
    bot = await test_hedge_bot(config)
    
    print("\n" + "=" * 50)
    print("🎉 交易所连接测试完成")

if __name__ == "__main__":
    asyncio.run(main())
