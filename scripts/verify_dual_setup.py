#!/usr/bin/env python3
"""
双账户设置验证脚本
"""

import asyncio
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.gridbot.dual_config import load_dual_config
from src.gridbot.exchange import ExchangeInterface

async def verify_dual_setup(config_path: str):
    """验证双账户设置"""
    print("🔍 开始验证双账户设置...")
    
    try:
        # 1. 加载配置
        print("📋 加载配置文件...")
        config = load_dual_config(config_path)
        print(f"✅ 配置加载成功: {config.name}")
        
        # 2. 验证配置参数
        print("🔧 验证配置参数...")
        
        # 检查API密钥
        if config.long_api_key == config.short_api_key:
            print("❌ 多头和空头账户使用了相同的API密钥")
            return False
        
        # 检查价格区间
        if config.lower_price >= config.upper_price:
            print("❌ 价格区间设置错误")
            return False
        
        print("✅ 配置参数验证通过")
        
        # 3. 测试API连接
        print("🌐 测试API连接...")
        
        # 创建单账户配置
        long_config = config.to_single_config("long")
        short_config = config.to_single_config("short")
        
        # 创建交易所接口
        long_exchange = ExchangeInterface(long_config)
        short_exchange = ExchangeInterface(short_config)
        
        # 测试连接
        await long_exchange.initialize()
        await short_exchange.initialize()
        
        print("✅ 双账户API连接成功")
        
        # 4. 检查余额
        print("💰 检查账户余额...")
        
        long_balance = await long_exchange.fetch_balance()
        short_balance = await short_exchange.fetch_balance()
        
        quote_coin = config.quote_coin
        long_free = float(long_balance['free'].get(quote_coin, 0))
        short_free = float(short_balance['free'].get(quote_coin, 0))
        
        print(f"多头账户 {quote_coin} 余额: {long_free}")
        print(f"空头账户 {quote_coin} 余额: {short_free}")
        
        # 计算名义价值（可用余额 × 杠杆倍数）
        long_nominal_value = long_free * config.leverage
        short_nominal_value = short_free * config.leverage

        print(f"多头账户名义价值: {long_nominal_value} {quote_coin}")
        print(f"空头账户名义价值: {short_nominal_value} {quote_coin}")

        # 计算所需名义价值（每个网格的名义价值 × 网格数）
        required_nominal_per_account = float(config.order_amount_usdt * config.grids)

        print(f"每个账户需要名义价值: {required_nominal_per_account} {quote_coin}")

        if long_nominal_value < required_nominal_per_account:
            print(f"⚠️ 多头账户名义价值不足，需要至少 {required_nominal_per_account} {quote_coin}")
            print(f"   建议保证金: {required_nominal_per_account / config.leverage:.2f} {quote_coin}")
        else:
            print(f"✅ 多头账户名义价值充足")

        if short_nominal_value < required_nominal_per_account:
            print(f"⚠️ 空头账户名义价值不足，需要至少 {required_nominal_per_account} {quote_coin}")
            print(f"   建议保证金: {required_nominal_per_account / config.leverage:.2f} {quote_coin}")
        else:
            print(f"✅ 空头账户名义价值充足")
        
        # 5. 测试杠杆设置
        if config.market_type == 'future':
            print("⚙️ 测试杠杆设置...")
            try:
                await long_exchange.set_leverage_and_margin_mode()
                await short_exchange.set_leverage_and_margin_mode()
                print("✅ 杠杆设置测试通过")
            except Exception as e:
                print(f"⚠️ 杠杆设置测试失败: {e}")
        
        # 关闭连接
        await long_exchange.close()
        await short_exchange.close()
        
        print("\n🎉 双账户设置验证完成！")
        print("可以使用以下命令启动机器人：")
        print(f"python -m src.gridbot.dual_main --config {config_path} --fresh")
        
        return True
        
    except Exception as e:
        print(f"❌ 验证失败: {e}")
        return False

def main():
    """主函数"""
    if len(sys.argv) != 2:
        print("用法: python scripts/verify_dual_setup.py <config_path>")
        sys.exit(1)
    
    config_path = sys.argv[1]
    
    if not Path(config_path).exists():
        print(f"❌ 配置文件不存在: {config_path}")
        sys.exit(1)
    
    success = asyncio.run(verify_dual_setup(config_path))
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
