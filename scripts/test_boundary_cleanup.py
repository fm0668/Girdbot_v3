#!/usr/bin/env python3
"""
测试边界监控的清理功能
"""

import asyncio
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.gridbot.dual_config import load_dual_config
from scripts.boundary_monitor import BoundaryMonitor

async def test_boundary_cleanup():
    """测试边界监控的清理功能"""
    print("🧪 开始测试边界监控的清理功能...")
    
    try:
        # 创建边界监控实例
        monitor = BoundaryMonitor('config/dual_config.json')
        
        # 加载配置
        monitor.config = load_dual_config('config/dual_config.json')
        
        print(f"📊 监控边界：{monitor.config.lower_price} - {monitor.config.upper_price}")
        
        # 模拟边界突破
        print("🚨 模拟边界突破，触发紧急清理...")
        monitor.boundary_breached = True
        
        # 执行紧急清理
        await monitor._execute_emergency_cleanup()
        
        print("✅ 边界监控清理功能测试完成")
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_boundary_cleanup())
