#!/usr/bin/env python3
"""
清理空头账户挂单
"""

import asyncio
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.gridbot.dual_config import load_dual_config
from src.gridbot.exchange import ExchangeInterface

async def cleanup_short_account():
    """清理空头账户"""
    try:
        print("📋 加载配置...")
        config = load_dual_config('config/dual_config.json')
        
        # 创建空头账户配置
        short_config = config.to_single_config("short")
        short_exchange = ExchangeInterface(short_config)
        
        # 初始化连接
        await short_exchange.initialize()
        print("✅ 空头账户连接成功")
        
        # 获取所有挂单
        orders = await short_exchange.fetch_open_orders()
        
        if orders:
            print(f"📋 发现 {len(orders)} 个挂单，开始清理...")
            
            for order in orders:
                try:
                    await short_exchange.cancel_order(order['id'])
                    print(f"✅ 已取消订单 {order['id']} | {order['side']} | 价格: {order['price']}")
                except Exception as e:
                    print(f"⚠️ 取消订单 {order['id']} 失败: {e}")
        else:
            print("✅ 空头账户无挂单")
        
        # 检查持仓
        positions = await short_exchange.fetch_positions()
        for position in positions:
            if abs(float(position['contracts'])) > 0:
                print(f"📋 发现持仓: {position['contracts']} {position['symbol']}")
                
                # 询问是否平仓
                response = input("是否平仓？(y/n): ")
                if response.lower() == 'y':
                    side = 'sell' if float(position['contracts']) > 0 else 'buy'
                    amount = abs(float(position['contracts']))
                    
                    try:
                        # 使用市价单平仓
                        if side == 'sell':
                            await short_exchange.create_market_sell_order(amount)
                        else:
                            await short_exchange.create_market_buy_order(amount)

                        print(f"✅ 已平仓 {amount} ({side})")
                    except Exception as e:
                        print(f"⚠️ 平仓失败: {e}")
        
        await short_exchange.close()
        print("✅ 空头账户清理完成")
        
    except Exception as e:
        print(f"❌ 清理失败: {e}")

if __name__ == "__main__":
    asyncio.run(cleanup_short_account())
