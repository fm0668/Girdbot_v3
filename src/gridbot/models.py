import os
from pydantic import BaseModel, Field
from typing import Optional, Literal
from decimal import Decimal, InvalidOperation


class FeeCoinConfig(BaseModel):
    enabled: bool = Field(alias="manage_fee_coin")
    coin: str = Field(alias="fee_coin")
    repurchase_balance: Decimal = Field(alias="fee_coin_repurchase_balance_USDT", gt=0)
    repurchase_amount: Decimal = Field(alias="fee_coin_repurchase_amount_USDT", gt=0)


class BotConfig(BaseModel):
    name: str
    exchange: str
    api_key: str
    api_secret: str
    sandbox_mode: bool

    # -- Market & Pair --
    market_type: Literal["spot", "future"] = "future"
    pair: str

    # -- Strategy Params --
    strategy_side: Literal["long", "short"]
    leverage: int = Field(gt=0)
    lower_price: Decimal = Field(gt=0)
    upper_price: Decimal = Field(gt=0)
    grids: int = Field(gt=0)
    order_amount_usdt: Decimal = Field(gt=0)

    # -- Risk Management --
    max_position_count: int = Field(gt=0)

    # -- Misc --
    frontend: bool
    frontend_host: str

    # -- Derived Properties --
    @property
    def coin(self) -> str:
        return self.pair.split('/')[0]

    @property
    def grid_step(self) -> Decimal:
        """Calculate the price difference between each grid level."""
        return (self.upper_price - self.lower_price) / (self.grids - 1)

    # from_env 方法需要完全重写或暂时移除，因为它基于旧的配置
    # 为简化起见，我们暂时依赖json文件加载
    @classmethod
    def from_env(cls):
        # This method needs a complete rewrite to support new env vars.
        # For now, we will rely on the JSON config file.
        raise NotImplementedError("from_env is not configured for the new perpetuals strategy.")


class OrderPair(BaseModel):
    """Represents a pair of buy and sell orders."""
    buy_order_id: Optional[str] = None
    sell_order_id: Optional[str] = None
    buy_price: Optional[Decimal] = None
    sell_price: Optional[Decimal] = None
    buy_type: Optional[Literal["limit", "market"]] = None
    amount: Decimal = Field(gt=0)
    timestamp: int = Field(gt=0)
    buy_order_status: Optional[Literal["open", "closed"]] = None

    def to_dict(self):
        return {
            "buy_order_id": self.buy_order_id,
            "sell_order_id": self.sell_order_id,
            "buy_price": str(self.buy_price) if self.buy_price else None,
            "sell_price": str(self.sell_price) if self.sell_price else None,
            "buy_type": self.buy_type,
            "amount": str(self.amount),
            "timestamp": self.timestamp
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            buy_order_id=data["buy_order_id"],
            sell_order_id=data["sell_order_id"],
            buy_price=Decimal(data["buy_price"]) if data["buy_price"] else None,
            sell_price=Decimal(data["sell_price"]) if data["sell_price"] else None,
            buy_type=data["buy_type"],
            amount=Decimal(data["amount"]),
            timestamp=data["timestamp"]
        )


class Trade(BaseModel):
    """Represents a completed trade."""
    order_id: str
    side: Literal["buy", "sell"]
    symbol: str
    amount: Decimal = Field(gt=0)
    price: Decimal = Field(gt=0)
    cost: Decimal = Field(gt=0)
    timestamp: int = Field(gt=0)


class ProfitRecord(BaseModel):
    """利润记录模型"""
    grid_id: str
    open_price: Decimal
    close_price: Decimal
    amount: Decimal
    profit_usdt: Decimal
    profit_percentage: Decimal
    timestamp: int
    side: Literal["long", "short"]


# 建议新增一个状态模型，用于新的策略逻辑
class GridLevelState(BaseModel):
    id: str  # 唯一标识符，格式如 "grid_001", "grid_002"
    price: Decimal
    status: Literal["AVAILABLE", "ORDER_PENDING", "POSITION_HELD"]
    open_order_id: Optional[str] = None
    close_order_id: Optional[str] = None
    position_amount: Optional[Decimal] = None
    # 新增利润追踪字段
    open_timestamp: Optional[int] = None
    total_profit: Decimal = Decimal('0')
    trade_count: int = 0


class DualAccountConfig(BaseModel):
    """双账户配置模型"""
    name: str
    exchange: str
    sandbox_mode: bool

    # 双账户API配置
    long_api_key: str
    long_api_secret: str
    short_api_key: str
    short_api_secret: str

    # 共享交易配置
    market_type: Literal["spot", "future"] = "future"
    pair: str
    leverage: int = Field(gt=0)
    lower_price: Decimal = Field(gt=0)
    upper_price: Decimal = Field(gt=0)
    grids: int = Field(gt=0)
    order_amount_usdt: Decimal = Field(gt=0)

    # 前端配置
    frontend: bool = False
    frontend_host: str = "localhost:8080"

    # 派生属性
    @property
    def coin(self) -> str:
        return self.pair.split('/')[0]

    @property
    def quote_coin(self) -> str:
        return self.pair.split('/')[1]

    @property
    def grid_step(self) -> Decimal:
        """计算网格步长"""
        return (self.upper_price - self.lower_price) / (self.grids - 1)

    def to_single_config(self, side: Literal["long", "short"]) -> BotConfig:
        """转换为单账号配置"""
        api_key = self.long_api_key if side == "long" else self.short_api_key
        api_secret = self.long_api_secret if side == "long" else self.short_api_secret

        return BotConfig(
            name=f"{self.name}-{side}",
            exchange=self.exchange,
            api_key=api_key,
            api_secret=api_secret,
            sandbox_mode=self.sandbox_mode,
            market_type=self.market_type,
            pair=self.pair,
            strategy_side=side,
            leverage=self.leverage,
            lower_price=self.lower_price,
            upper_price=self.upper_price,
            grids=self.grids,
            order_amount_usdt=self.order_amount_usdt,
            max_position_count=self.grids,  # 使用网格数作为最大持仓
            frontend=self.frontend,
            frontend_host=self.frontend_host
        )
