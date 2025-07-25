"""
双账户通用工具
"""

import asyncio
from typing import List, Tuple, Any, Callable, Optional
from decimal import Decimal

class DualAccountUtils:
    """双账户通用工具类"""
    
    @staticmethod
    async def execute_on_both(
        long_obj: Any, 
        short_obj: Any, 
        method_name: str, 
        *args, **kwargs
    ) -> Tuple[Any, Any]:
        """在双账户对象上执行相同方法"""
        long_method = getattr(long_obj, method_name)
        short_method = getattr(short_obj, method_name)
        
        results = await asyncio.gather(
            long_method(*args, **kwargs),
            short_method(*args, **kwargs),
            return_exceptions=True
        )
        
        return results[0], results[1]
    
    @staticmethod
    async def parallel_cleanup(strategies: List[Any]) -> bool:
        """并行清理多个策略"""
        cleanup_tasks = []
        for strategy in strategies:
            if strategy and hasattr(strategy, '_cleanup_exchange_state'):
                cleanup_tasks.append(strategy._cleanup_exchange_state())
        
        if cleanup_tasks:
            results = await asyncio.gather(*cleanup_tasks, return_exceptions=True)
            # 检查是否有异常
            success = True
            for i, result in enumerate(results):
                account_name = "多头" if i == 0 else "空头"
                if isinstance(result, Exception):
                    print(f"❌ {account_name}账户清理异常: {result}")
                    success = False
                else:
                    print(f"✅ {account_name}账户清理完成")
            return success
        
        return True
    
    @staticmethod
    async def initialize_exchange_pair(long_exchange, short_exchange, market_type: str):
        """初始化交易所对"""
        print("🔗 开始初始化双账户交易所连接...")
        
        # 并行初始化
        await asyncio.gather(
            long_exchange.initialize(),
            short_exchange.initialize()
        )
        
        # 设置杠杆和保证金模式
        if market_type == 'future':
            await asyncio.gather(
                long_exchange.set_leverage_and_margin_mode(),
                short_exchange.set_leverage_and_margin_mode()
            )
            print("✅ 双账户杠杆和保证金模式设置完成")
        
        print("✅ 双账户交易所连接初始化完成")
    
    @staticmethod
    async def check_balances_pair(long_exchange, short_exchange, config) -> Tuple[Decimal, Decimal]:
        """检查双账户余额对"""
        balances = await asyncio.gather(
            long_exchange.fetch_balance(),
            short_exchange.fetch_balance()
        )
        
        quote_coin = config.quote_coin
        long_free = Decimal(str(balances[0]['free'].get(quote_coin, 0)))
        short_free = Decimal(str(balances[1]['free'].get(quote_coin, 0)))
        
        print(f"💰 账户余额检查:")
        print(f"   多头账户 {quote_coin}: {long_free}")
        print(f"   空头账户 {quote_coin}: {short_free}")
        
        # 计算所需资金
        required_per_account = config.order_amount_usdt * config.grids
        
        if long_free < required_per_account:
            print(f"⚠️ 多头账户余额不足，需要至少 {required_per_account} {quote_coin}")
        
        if short_free < required_per_account:
            print(f"⚠️ 空头账户余额不足，需要至少 {required_per_account} {quote_coin}")
        
        return long_free, short_free
    
    @staticmethod
    def format_account_stats(strategy: Any, side: str) -> str:
        """格式化账户统计信息"""
        try:
            if not strategy or not hasattr(strategy, 'grid_levels'):
                return f"{side}: 数据不可用"
            
            total_grids = len(strategy.grid_levels)
            pending_orders = sum(1 for level in strategy.grid_levels.values() 
                               if level.status == "ORDER_PENDING")
            held_positions = sum(1 for level in strategy.grid_levels.values() 
                               if level.status == "POSITION_HELD")
            total_profit = getattr(strategy, 'total_realized_profit', 0)
            
            return f"网格{total_grids} | 挂单{pending_orders} | 持仓{held_positions} | 利润{total_profit}"
            
        except Exception as e:
            return f"{side}: 统计异常 {e}"
    
    @staticmethod
    def validate_dual_config(config) -> List[str]:
        """验证双账户配置"""
        errors = []
        
        # 检查API密钥
        if not config.long_api_key or not config.long_api_secret:
            errors.append("多头账户API密钥不能为空")
        
        if not config.short_api_key or not config.short_api_secret:
            errors.append("空头账户API密钥不能为空")
        
        # 检查API密钥是否相同
        if (config.long_api_key == config.short_api_key and 
            config.long_api_secret == config.short_api_secret):
            errors.append("多头和空头账户不能使用相同的API密钥")
        
        # 检查价格区间
        if config.lower_price >= config.upper_price:
            errors.append("价格区间设置错误：下限价格必须小于上限价格")
        
        # 检查网格数量
        if config.grids < 2:
            errors.append("网格数量至少为2")
        
        return errors
    
    @staticmethod
    async def cleanup_single_account_safe(exchange, account_name: str) -> bool:
        """安全清理单个账户"""
        try:
            print(f"🧹 开始清理{account_name}账户...")
            
            # 1. 取消所有挂单
            orders = await exchange.fetch_open_orders()
            cancel_failed = 0
            if orders:
                print(f"📋 {account_name}账户发现 {len(orders)} 个挂单，开始取消...")
                for order in orders:
                    try:
                        await exchange.cancel_order(order['id'])
                        print(f"✅ 已取消{account_name}订单 {order['id']}")
                    except Exception as e:
                        print(f"⚠️ 取消{account_name}订单 {order['id']} 失败: {e}")
                        cancel_failed += 1
            else:
                print(f"✅ {account_name}账户无挂单")
            
            # 2. 平掉所有持仓
            positions = await exchange.fetch_positions()
            close_failed = 0
            position_count = 0
            
            for position in positions:
                contracts = float(position.get('contracts', 0))
                if abs(contracts) > 0:
                    position_count += 1
                    symbol = position.get('symbol', '')
                    print(f"📋 {account_name}账户发现持仓: {contracts} {symbol}")
                    
                    try:
                        # 使用市价单平仓
                        if contracts > 0:  # 多头持仓
                            await exchange.create_market_sell_order(abs(contracts))
                            print(f"✅ {account_name}账户已平掉多头持仓 {abs(contracts)}")
                        else:  # 空头持仓
                            await exchange.create_market_buy_order(abs(contracts))
                            print(f"✅ {account_name}账户已平掉空头持仓 {abs(contracts)}")
                    except Exception as e:
                        print(f"⚠️ {account_name}账户平仓失败: {e}")
                        close_failed += 1
            
            if position_count == 0:
                print(f"✅ {account_name}账户无持仓")
            
            # 判断清理是否成功
            success = (cancel_failed == 0 and close_failed == 0)
            if success:
                print(f"✅ {account_name}账户清理完成")
            else:
                print(f"⚠️ {account_name}账户清理有问题：{cancel_failed}个挂单取消失败，{close_failed}个持仓平仓失败")
            
            return success
            
        except Exception as e:
            print(f"❌ 清理{account_name}账户失败: {e}")
            return False
