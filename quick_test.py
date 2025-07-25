#!/usr/bin/env python3
"""
快速测试脚本 - 测试API密钥配置和ExchangeInterface创建
"""

import sys
import os
import asyncio
from pathlib import Path

# 添加项目路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def check_api_keys():
    """检查API密钥配置"""
    print("🔍 检查API密钥配置...")
    
    # 加载环境变量
    from dotenv import load_dotenv
    load_dotenv()
    
    keys = {
        "LONG_API_KEY": os.getenv("LONG_API_KEY"),
        "LONG_API_SECRET": os.getenv("LONG_API_SECRET"),
        "SHORT_API_KEY": os.getenv("SHORT_API_KEY"),
        "SHORT_API_SECRET": os.getenv("SHORT_API_SECRET")
    }
    
    all_set = True
    for key, value in keys.items():
        if not value or value.startswith("your-"):
            print(f"   ❌ {key}: 未设置或使用默认值")
            all_set = False
        else:
            print(f"   ✅ {key}: {value[:10]}...")
    
    return all_set

async def test_exchange_creation():
    """测试ExchangeInterface创建"""
    print("\n🧪 测试ExchangeInterface创建...")
    
    try:
        from src.gridbot.exchange import ExchangeInterface
        from src.gridbot.models import BotConfig
        from dotenv import load_dotenv
        load_dotenv()
        
        # 创建测试配置
        config = BotConfig(
            name="QuickTest",
            exchange="binance",
            api_key=os.getenv("LONG_API_KEY"),
            api_secret=os.getenv("LONG_API_SECRET"),
            sandbox_mode=True,  # 使用沙盒模式测试
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
        
        print(f"   配置信息:")
        print(f"   - 交易所: {config.exchange}")
        print(f"   - 沙盒模式: {config.sandbox_mode}")
        print(f"   - API密钥: {config.api_key[:10]}...")
        
        # 创建ExchangeInterface
        print("   正在创建ExchangeInterface...")
        exchange = ExchangeInterface(config)
        print("   ✅ ExchangeInterface创建成功")
        
        # 测试初始化
        print("   正在测试初始化...")
        await exchange.initialize()
        print("   ✅ 初始化成功")
        
        # 测试基本功能
        print("   正在测试基本功能...")
        
        # 获取账户余额
        balance = await exchange.fetch_balance()
        print(f"   ✅ 账户余额获取成功: {len(balance)} 个币种")
        
        # 获取市场信息
        ticker = await exchange.fetch_ticker(config.pair)
        print(f"   ✅ 市场信息获取成功: {config.pair} 价格 {ticker.get('last', 'N/A')}")
        
        # 清理
        await exchange.close()
        print("   ✅ 连接关闭成功")
        
        return True
        
    except Exception as e:
        print(f"   ❌ 测试失败: {e}")
        print(f"   错误类型: {type(e).__name__}")
        
        # 详细错误信息
        if "ws" in str(e).lower():
            print("   💡 提示: 这可能是WebSocket配置问题")
        elif "api" in str(e).lower():
            print("   💡 提示: 这可能是API密钥或权限问题")
        elif "network" in str(e).lower():
            print("   💡 提示: 这可能是网络连接问题")
        
        import traceback
        traceback.print_exc()
        return False

async def test_config_loading():
    """测试配置文件加载"""
    print("\n🧪 测试配置文件加载...")
    
    try:
        from src.gridbot.hedge_main import load_dual_config
        
        config_path = "config/hedge_config_test.json"
        if not Path(config_path).exists():
            print(f"   ❌ 配置文件不存在: {config_path}")
            return False
        
        config = load_dual_config(config_path)
        print(f"   ✅ 配置加载成功: {config.name}")
        print(f"   - 交易所: {config.exchange}")
        print(f"   - 沙盒模式: {config.sandbox_mode}")
        print(f"   - 交易对: {config.pair}")
        print(f"   - 多头API: {config.long_api_key[:10]}...")
        print(f"   - 空头API: {config.short_api_key[:10]}...")
        
        return True
        
    except Exception as e:
        print(f"   ❌ 配置加载失败: {e}")
        return False

async def main():
    """主测试函数"""
    print("🚀 快速API密钥和ExchangeInterface测试")
    print("=" * 50)
    
    # 1. 检查API密钥
    if not check_api_keys():
        print("\n❌ 请先在.env文件中设置正确的API密钥")
        print("📝 编辑.env文件，将以下占位符替换为真实密钥：")
        print("   LONG_API_KEY=your-actual-long-api-key")
        print("   LONG_API_SECRET=your-actual-long-api-secret")
        print("   SHORT_API_KEY=your-actual-short-api-key")
        print("   SHORT_API_SECRET=your-actual-short-api-secret")
        return
    
    # 2. 测试配置加载
    config_ok = await test_config_loading()
    if not config_ok:
        return
    
    # 3. 测试ExchangeInterface
    exchange_ok = await test_exchange_creation()
    
    print("\n" + "=" * 50)
    if exchange_ok:
        print("🎉 所有测试通过！ExchangeInterface工作正常")
        print("✅ 您现在可以运行完整的对冲网格机器人了")
        print("\n📋 下一步:")
        print("   python -m src.gridbot.hedge_main --config config/hedge_config_test.json")
    else:
        print("❌ ExchangeInterface测试失败")
        print("💡 请检查API密钥权限和网络连接")

if __name__ == "__main__":
    asyncio.run(main())
