"""
双账户功能测试
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from decimal import Decimal

from src.gridbot.models import DualAccountConfig
from src.gridbot.dual_account_manager import DualAccountManager
from src.gridbot.dual_config import load_dual_config

class TestDualAccountConfig:
    """测试双账户配置"""
    
    def test_dual_config_creation(self):
        """测试双账户配置创建"""
        config = DualAccountConfig(
            name="TestDualBot",
            exchange="binance",
            sandbox_mode=True,
            long_api_key="long_key",
            long_api_secret="long_secret",
            short_api_key="short_key",
            short_api_secret="short_secret",
            pair="BTC/USDT",
            leverage=10,
            lower_price=Decimal("60000"),
            upper_price=Decimal("70000"),
            grids=10,
            order_amount_usdt=Decimal("100")
        )
        
        assert config.name == "TestDualBot"
        assert config.coin == "BTC"
        assert config.quote_coin == "USDT"
        assert config.grid_step == Decimal("1111.111111111111111111111111")
    
    def test_to_single_config(self):
        """测试转换为单账户配置"""
        dual_config = DualAccountConfig(
            name="TestDualBot",
            exchange="binance",
            sandbox_mode=True,
            long_api_key="long_key",
            long_api_secret="long_secret",
            short_api_key="short_key",
            short_api_secret="short_secret",
            pair="BTC/USDT",
            leverage=10,
            lower_price=Decimal("60000"),
            upper_price=Decimal("70000"),
            grids=10,
            order_amount_usdt=Decimal("100")
        )
        
        long_config = dual_config.to_single_config("long")
        short_config = dual_config.to_single_config("short")
        
        assert long_config.name == "TestDualBot-long"
        assert long_config.strategy_side == "long"
        assert long_config.api_key == "long_key"
        
        assert short_config.name == "TestDualBot-short"
        assert short_config.strategy_side == "short"
        assert short_config.api_key == "short_key"

class TestDualAccountManager:
    """测试双账户管理器"""
    
    @pytest.fixture
    def mock_config(self):
        """模拟配置"""
        return DualAccountConfig(
            name="TestDualBot",
            exchange="binance",
            sandbox_mode=True,
            long_api_key="long_key",
            long_api_secret="long_secret",
            short_api_key="short_key",
            short_api_secret="short_secret",
            pair="BTC/USDT",
            leverage=10,
            lower_price=Decimal("60000"),
            upper_price=Decimal("70000"),
            grids=10,
            order_amount_usdt=Decimal("100")
        )
    
    @pytest.mark.asyncio
    async def test_manager_creation(self, mock_config):
        """测试管理器创建"""
        manager = DualAccountManager(mock_config)
        
        assert manager.config == mock_config
        assert not manager.running
        assert not manager.initialization_complete
    
    @pytest.mark.asyncio
    @patch('src.gridbot.dual_account_manager.ExchangeInterface')
    @patch('src.gridbot.dual_account_manager.GridStrategy')
    async def test_initialization(self, mock_strategy, mock_exchange, mock_config):
        """测试初始化流程"""
        # 设置模拟对象
        mock_exchange_instance = AsyncMock()
        mock_exchange.return_value = mock_exchange_instance
        
        mock_strategy_instance = AsyncMock()
        mock_strategy.return_value = mock_strategy_instance
        
        # 模拟余额检查
        mock_exchange_instance.fetch_balance.return_value = {
            'free': {'USDT': 10000}
        }
        
        manager = DualAccountManager(mock_config)
        
        # 测试初始化
        await manager.initialize(fresh_start=True)
        
        assert manager.initialization_complete
        assert mock_exchange_instance.initialize.call_count == 2
        assert mock_strategy_instance.initialize_grid.call_count == 2

def test_config_loading():
    """测试配置加载"""
    # 这里可以添加配置文件加载的测试
    pass
