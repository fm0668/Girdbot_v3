"""
利润追踪器 - 负责利润计算、记录和统计
从 strategy.py 中分离出来，专门处理利润相关逻辑
"""

import json
import os
from datetime import datetime
from decimal import Decimal
from typing import List, Dict, Optional
from .models import BotConfig, ProfitRecord, Trade, GridLevelState

class ProfitTracker:
    """利润追踪管理器"""
    
    def __init__(self, config: BotConfig):
        self.config = config
        self.profit_records: List[ProfitRecord] = []
        self.total_realized_profit = Decimal('0')
        self.profit_file_path = f"profit_records_{self.config.name.replace('/', '_')}.json"
        
        # 手续费信息
        self.maker_fee_rate = Decimal('0')
        self.taker_fee_rate = Decimal('0')
    
    def set_fee_rates(self, maker_rate: Decimal, taker_rate: Decimal):
        """设置手续费率"""
        self.maker_fee_rate = maker_rate
        self.taker_fee_rate = taker_rate
    
    def calculate_grid_profit(self, level: GridLevelState, close_trade: Trade) -> Decimal:
        """计算单个网格的利润"""
        if self.config.strategy_side == "long":
            # 做多：买入价格低，卖出价格高，利润 = (卖出价 - 买入价) * 数量
            profit = (close_trade.price - level.price) * close_trade.amount
        else:
            # 做空：卖出价格高，买入价格低，利润 = (卖出价 - 买入价) * 数量
            # 当 level.price > close_trade.price 时盈利（价格下跌）
            # 当 level.price < close_trade.price 时亏损（价格上涨）
            profit = (level.price - close_trade.price) * close_trade.amount
        
        # 扣除手续费（使用实际交易所费率）
        # 开仓和平仓都可能产生手续费，这里使用taker费率（因为我们使用限价单但可能立即成交）
        # 对于USDC期货，通常maker和taker费率都是0%
        open_fee = level.price * close_trade.amount * self.taker_fee_rate
        close_fee = close_trade.price * close_trade.amount * self.taker_fee_rate
        total_fee = open_fee + close_fee
        
        return profit - total_fee
    
    def record_profit(self, level: GridLevelState, close_trade: Trade) -> ProfitRecord:
        """记录利润"""
        profit_usdt = self.calculate_grid_profit(level, close_trade)
        
        profit_record = ProfitRecord(
            grid_id=level.id,
            open_price=level.price,
            close_price=close_trade.price,
            amount=close_trade.amount,
            profit_usdt=profit_usdt,
            profit_percentage=(profit_usdt / (level.price * close_trade.amount)) * 100 if level.price * close_trade.amount > 0 else Decimal('0'),
            timestamp=close_trade.timestamp,
            side=self.config.strategy_side
        )
        
        self.profit_records.append(profit_record)
        self.total_realized_profit += profit_usdt
        
        # 更新网格层级统计
        level.total_profit += profit_usdt
        level.trade_count += 1
        
        return profit_record
    
    async def load_profit_records(self):
        """加载历史利润记录"""
        try:
            if os.path.exists(self.profit_file_path):
                with open(self.profit_file_path, 'r') as f:
                    data = json.load(f)
                    self.total_realized_profit = Decimal(data.get('total_realized_profit', '0'))

                    records_data = data.get('records', [])
                    self.profit_records = []
                    for record_data in records_data:
                        record = ProfitRecord(
                            grid_id=record_data['grid_id'],
                            open_price=Decimal(record_data['open_price']),
                            close_price=Decimal(record_data['close_price']),
                            amount=Decimal(record_data['amount']),
                            profit_usdt=Decimal(record_data['profit_usdt']),
                            profit_percentage=Decimal(record_data['profit_percentage']),
                            timestamp=record_data['timestamp'],
                            side=record_data['side']
                        )
                        self.profit_records.append(record)

                    print(f"加载了 {len(self.profit_records)} 条利润记录，总利润: {self.total_realized_profit} USDT")
        except Exception as e:
            print(f"加载利润记录时出错：{e}")
    
    async def save_profit_records(self):
        """保存利润记录"""
        try:
            profit_data = {
                'total_realized_profit': str(self.total_realized_profit),
                'records': [
                    {
                        'grid_id': record.grid_id,
                        'open_price': str(record.open_price),
                        'close_price': str(record.close_price),
                        'amount': str(record.amount),
                        'profit_usdt': str(record.profit_usdt),
                        'profit_percentage': str(record.profit_percentage),
                        'timestamp': record.timestamp,
                        'side': record.side
                    }
                    for record in self.profit_records
                ]
            }
            with open(self.profit_file_path, 'w') as f:
                json.dump(profit_data, f, indent=4)
        except Exception as e:
            print(f"保存利润记录时出错：{e}")
    
    def get_profit_statistics(self, hours: Optional[int] = None) -> Dict:
        """获取利润统计"""
        if hours:
            # 计算特定时间段的利润
            current_time = datetime.now().timestamp() * 1000
            start_time = current_time - (hours * 60 * 60 * 1000)
            
            period_records = [
                record for record in self.profit_records 
                if record.timestamp >= start_time
            ]
            
            period_profit = sum(record.profit_usdt for record in period_records)
            
            return {
                'period_hours': hours,
                'period_profit': period_profit,
                'period_trades': len(period_records),
                'avg_profit_per_trade': period_profit / len(period_records) if period_records else Decimal('0')
            }
        else:
            # 总体统计
            return {
                'total_profit': self.total_realized_profit,
                'total_trades': len(self.profit_records),
                'avg_profit_per_trade': self.total_realized_profit / len(self.profit_records) if self.profit_records else Decimal('0'),
                'profitable_trades': len([r for r in self.profit_records if r.profit_usdt > 0]),
                'loss_trades': len([r for r in self.profit_records if r.profit_usdt < 0])
            }
