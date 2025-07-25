#!/usr/bin/env python3
"""
紧急停止脚本 - 停止所有进程并清理双账户挂单
"""

import asyncio
import sys
import os
import signal
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.gridbot.dual_config import load_dual_config
from src.gridbot.exchange import ExchangeInterface

async def emergency_cleanup():
    """紧急清理双账户"""
    print("🚨 开始紧急清理...")
    
    try:
        # 1. 杀死所有相关Python进程
        print("🔪 停止所有相关进程...")
        os.system("pkill -f 'python.*dual_main' 2>/dev/null")
        os.system("pkill -f 'python.*gridbot' 2>/dev/null")
        
        # 2. 加载配置
        print("📋 加载配置...")
        config = load_dual_config('config/dual_config.json')
        
        # 3. 创建交易所接口
        long_config = config.to_single_config("long")
        short_config = config.to_single_config("short")
        
        long_exchange = ExchangeInterface(long_config)
        short_exchange = ExchangeInterface(short_config)
        
        # 4. 初始化连接
        await long_exchange.initialize()
        await short_exchange.initialize()
        
        print("✅ 交易所连接初始化完成")
        
        # 5. 清理多头账户
        print("🧹 清理多头账户...")
        await cleanup_account(long_exchange, "多头")
        
        # 6. 清理空头账户
        print("🧹 清理空头账户...")
        await cleanup_account(short_exchange, "空头")
        
        # 7. 关闭连接
        await long_exchange.close()
        await short_exchange.close()
        
        print("✅ 紧急清理完成！")
        
    except Exception as e:
        print(f"❌ 紧急清理失败: {e}")

async def cleanup_account(exchange, account_name):
    """清理单个账户"""
    try:
        # 取消所有挂单
        orders = await exchange.fetch_open_orders()
        if orders:
            print(f"📋 {account_name}账户发现 {len(orders)} 个挂单，开始取消...")
            for order in orders:
                try:
                    await exchange.cancel_order(order['id'])
                    print(f"✅ 已取消订单 {order['id']}")
                except Exception as e:
                    print(f"⚠️ 取消订单 {order['id']} 失败: {e}")
        else:
            print(f"✅ {account_name}账户无挂单")
        
        # 平仓所有持仓
        positions = await exchange.fetch_positions()
        for position in positions:
            if abs(float(position['contracts'])) > 0:
                side = 'sell' if float(position['contracts']) > 0 else 'buy'
                amount = abs(float(position['contracts']))
                print(f"📋 {account_name}账户发现持仓 {amount}，开始平仓...")
                
                try:
                    await exchange.create_market_order(
                        position['symbol'], 
                        side, 
                        amount
                    )
                    print(f"✅ 已平仓 {amount}")
                except Exception as e:
                    print(f"⚠️ 平仓失败: {e}")
        
        print(f"✅ {account_name}账户清理完成")
        
    except Exception as e:
        print(f"❌ 清理{account_name}账户失败: {e}")

def main():
    """主函数"""
    print("🚨 紧急停止和清理工具")
    print("这将停止所有网格机器人进程并清理所有挂单和持仓")
    
    try:
        asyncio.run(emergency_cleanup())
    except KeyboardInterrupt:
        print("\n用户中断")
    except Exception as e:
        print(f"❌ 执行失败: {e}")

if __name__ == "__main__":
    main()
