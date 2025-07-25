"""
网格管理器 - 负责网格层级的创建、状态管理和持久化
从 strategy.py 中分离出来，专门处理网格相关逻辑
"""

import json
import os
from datetime import datetime
from decimal import Decimal
from typing import Dict, Optional, List
from .models import BotConfig, GridLevelState

class GridManager:
    """网格层级管理器"""
    
    def __init__(self, config: BotConfig):
        self.config = config
        self.grid_levels: Dict[str, GridLevelState] = {}
        self.price_to_id: Dict[Decimal, str] = {}
        self.state_file_path = f"grid_state_{self.config.name.replace('/', '_')}.json"
        
        # 从配置中获取常用参数
        self.side = self.config.strategy_side
        self.grid_step = self.config.grid_step
        self.upper_price = self.config.upper_price
        self.lower_price = self.config.lower_price
    
    def create_grid_levels(self):
        """创建所有网格价格层级的初始状态"""
        print("正在创建新的网格层级...")
        for i in range(self.config.grids):
            price = self.lower_price + i * self.grid_step
            
            # 在上边界，做多策略不放置开仓单
            if self.side == "long" and price == self.upper_price:
                continue
            # 在下边界，做空策略不放置开仓单
            if self.side == "short" and price == self.lower_price:
                continue

            # 创建唯一ID
            grid_id = f"grid_{i:03d}"
            level = GridLevelState(id=grid_id, price=price, status="AVAILABLE")

            self.grid_levels[grid_id] = level
            self.price_to_id[price] = grid_id
        
        print(f"✅ 创建了 {len(self.grid_levels)} 个网格层级")
    
    async def load_state(self):
        """从文件加载网格状态"""
        try:
            with open(self.state_file_path, 'r') as f:
                loaded_state = json.load(f)

                # 加载网格层级
                self.grid_levels = {
                    grid_id: GridLevelState(**level_data)
                    for grid_id, level_data in loaded_state.get('grid_levels', {}).items()
                }

                # 加载价格映射
                self.price_to_id = {
                    Decimal(price_str): grid_id
                    for price_str, grid_id in loaded_state.get('price_to_id', {}).items()
                }

                print(f"成功加载 {len(self.grid_levels)} 个网格层级的状态")
        except FileNotFoundError:
            print("未找到状态文件，全新开始")
            self.grid_levels = {}
            self.price_to_id = {}
        except Exception as e:
            print(f"加载状态时出错：{e}")
            self.grid_levels = {}
            self.price_to_id = {}
    
    async def save_state(self):
        """保存网格状态到文件"""
        try:
            state_data = {
                'grid_levels': {
                    grid_id: level.dict() for grid_id, level in self.grid_levels.items()
                },
                'price_to_id': {
                    str(price): grid_id for price, grid_id in self.price_to_id.items()
                },
                'last_updated': datetime.now().isoformat()
            }
            
            with open(self.state_file_path, 'w') as f:
                json.dump(state_data, f, indent=2, default=str)
                
        except Exception as e:
            print(f"保存状态时出错：{e}")

    async def cleanup_local_state_files(self):
        """清理本地状态文件"""
        try:
            # 删除状态文件
            if os.path.exists(self.state_file_path):
                os.remove(self.state_file_path)
                print(f"✅ 已删除状态文件：{self.state_file_path}")
        except Exception as e:
            print(f"清理本地状态文件时出错：{e}")

    def get_grid_statistics(self) -> Dict:
        """获取网格统计信息"""
        stats = {
            'total_grids': len(self.grid_levels),
            'available_count': sum(1 for level in self.grid_levels.values() if level.status == "AVAILABLE"),
            'pending_count': sum(1 for level in self.grid_levels.values() if level.status == "ORDER_PENDING"),
            'position_count': sum(1 for level in self.grid_levels.values() if level.status == "POSITION_HELD"),
            'total_profit': sum(level.total_profit for level in self.grid_levels.values()),
            'total_trades': sum(level.trade_count for level in self.grid_levels.values())
        }
        return stats
    
    def find_grid_by_order_id(self, order_id: str) -> Optional[GridLevelState]:
        """通过订单ID查找网格"""
        for level in self.grid_levels.values():
            if level.open_order_id == order_id or level.close_order_id == order_id:
                return level
        return None
    
    def find_grid_by_price(self, price: Decimal, tolerance: Decimal = Decimal('0.0001')) -> Optional[GridLevelState]:
        """通过价格查找网格（支持容差匹配）"""
        # 精确匹配
        grid_id = self.price_to_id.get(price)
        if grid_id:
            return self.grid_levels[grid_id]
        
        # 容差匹配
        for level in self.grid_levels.values():
            if abs(level.price - price) / level.price <= tolerance:
                return level
        
        return None
