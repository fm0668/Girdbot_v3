# 双账户对冲网格交易机器人

## 概述

双账户对冲功能是在现有单账户网格交易机器人基础上的升级，实现了多空双向对冲策略。该功能完全保持了现有的挂单和平仓逻辑不变，只是在上层添加了双账户协调管理。

## 核心特性

- 🔄 **双账户协调** - 一个账户做多，一个账户做空，实现完美对冲
- 🛡️ **故障联动** - 任一账户异常，另一账户也会停止，确保风险控制
- 📊 **统一监控** - 实时监控双账户运行状态和盈利情况
- ⚙️ **简单配置** - 通过单个配置文件管理双账户参数
- 🔧 **完全兼容** - 保持现有单账户功能不变，可独立使用

## 文件结构

```
src/gridbot/
├── dual_account_manager.py  # 双账户管理器
├── dual_bot.py             # 双账户机器人主程序
├── dual_main.py            # 双账户启动脚本
├── dual_config.py          # 双账户配置加载
└── models.py               # 包含DualAccountConfig模型

config/
├── dual_config.example.json # 双账户配置示例
└── dual_config_test.json    # 测试配置文件

scripts/
└── verify_dual_setup.py     # 双账户设置验证脚本

tests/
└── test_dual_account.py     # 双账户功能测试
```

## 快速开始

### 1. 配置环境变量

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑 .env 文件，设置双账户API密钥
BINANCE_LONG_API_KEY=your-long-account-api-key
BINANCE_LONG_API_SECRET=your-long-account-api-secret
BINANCE_SHORT_API_KEY=your-short-account-api-key
BINANCE_SHORT_API_SECRET=your-short-account-api-secret
```

### 2. 创建双账户配置

```bash
# 复制配置模板
cp config/dual_config.example.json config/dual_config.json

# 编辑配置文件，调整交易参数
```

### 3. 验证设置

```bash
# 运行验证脚本
python3 scripts/verify_dual_setup.py config/dual_config.json
```

### 4. 启动机器人

```bash
# 全新启动（清理所有现有持仓和订单）
python3 -m src.gridbot.dual_main --config config/dual_config.json --fresh

# 继续之前的状态启动
python3 -m src.gridbot.dual_main --config config/dual_config.json
```

## 配置说明

### 双账户配置文件示例

```json
{
    "name": "DualGridBot-DOGE-Hedge",
    "exchange": "binance",
    "sandbox_mode": true,

    "long_api_key": "${BINANCE_LONG_API_KEY}",
    "long_api_secret": "${BINANCE_LONG_API_SECRET}",
    "short_api_key": "${BINANCE_SHORT_API_KEY}",
    "short_api_secret": "${BINANCE_SHORT_API_SECRET}",

    "market_type": "future",
    "pair": "DOGE/USDC",

    "leverage": 10,
    "lower_price": "0.22500",
    "upper_price": "0.23500",
    "grids": 20,
    "order_amount_usdt": 10,

    "frontend": true,
    "frontend_host": "localhost:8080"
}
```

### 重要参数说明

- `long_api_key/long_api_secret`: 多头账户API密钥
- `short_api_key/short_api_secret`: 空头账户API密钥
- `pair`: 交易对（如 DOGE/USDC）
- `leverage`: 杠杆倍数
- `lower_price/upper_price`: 网格价格区间
- `grids`: 网格层数
- `order_amount_usdt`: 每个网格的订单金额

## 运行监控

机器人运行时会显示以下信息：

```
🔄 开始初始化双账户管理器...
✅ 双账户交易所连接初始化完成
✅ 双账户杠杆和保证金模式设置完成
💰 账户余额检查:
   多头账户 USDC: 1000.00
   空头账户 USDC: 1000.00
✅ 双账户策略实例创建完成
🚀 开始初始化双账户网格...
✅ 双账户网格初始化完成
🎉 双账户管理器初始化成功
🚀 双账户网格机器人启动成功

📊 === 双账户对冲状态报告 ===
运行时间: 运行中
多头账户: 网格20 | 挂单15 | 持仓5 | 利润12.34
空头账户: 网格20 | 挂单16 | 持仓4 | 利润11.78
对冲状态: ✅ 正常
===============================
```

## 测试

```bash
# 运行单元测试
python3 -m pytest tests/test_dual_account.py -v

# 验证双账户设置
python3 scripts/verify_dual_setup.py config/dual_config.json
```

## 注意事项

1. **API密钥要求**: 多头和空头账户必须使用不同的API密钥
2. **权限要求**: 两个账户都需要开启期货交易权限
3. **资金要求**: 每个账户需要足够的资金支持网格交易
4. **风险控制**: 任一账户异常都会触发双账户停止
5. **测试建议**: 建议先在沙盒模式下测试，确认无误后再切换到实盘

## 兼容性

- ✅ 完全兼容现有单账户功能
- ✅ 保持现有挂单和平仓逻辑不变
- ✅ 可以同时使用单账户和双账户模式
- ✅ 支持现有的所有交易对和参数配置
