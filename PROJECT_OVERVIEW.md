# GridBot v3 项目概览

## 项目简介

GridBot v3 是一个基于Python和CCXT Pro构建的加密货币网格交易机器人，支持现货和永续合约交易。

## 核心特性

- 🔄 **网格交易策略** - 可配置参数的网格交易
- 📊 **实时监控** - 实时交易监控和执行
- 🌐 **WebSocket支持** - 基于WebSocket的状态更新
- 💰 **盈利追踪** - 全面的盈利追踪系统
- ⚙️ **自动费用管理** - 自动手续费币种管理
- 📝 **JSON配置** - 通过JSON文件进行配置
- 🛡️ **错误处理** - 错误处理和恢复机制
- 📋 **详细日志** - 详细的日志记录

## 项目架构

```
src/gridbot/
├── bot.py           # 主机器人类，协调各组件
├── exchange.py      # 交易所接口，处理API交互
├── strategy.py      # 交易策略实现
├── models.py        # 数据模型和配置
└── websocket.py     # WebSocket通信管理
```

## 当前开发状态

### 已完成功能
- ✅ 基础网格交易策略（现货）
- ✅ 交易所API集成（CCXT）
- ✅ WebSocket实时通信
- ✅ 配置管理系统
- ✅ 单元测试框架
- ✅ 错误处理机制

### 正在开发
- 🔄 **永续合约支持** - 从现货迁移到永续合约
- 🔄 **状态机重构** - 基于状态机的"单兵接力网格"策略
- 🔄 **风险管理** - 增强的风险控制机制

### 计划功能
- 📋 利润计算优化
- 📋 手续费币种管理完善
- 📋 WebSocket订单追踪改进

## 技术栈

- **Python 3.8+** - 主要编程语言
- **CCXT Pro** - 加密货币交易所API库
- **Pydantic** - 数据验证和设置管理
- **WebSockets** - 实时通信
- **pytest** - 测试框架
- **asyncio** - 异步编程

## 配置示例

### 现货交易配置
```json
{
    "name": "MyGridBot",
    "exchange": "binance",
    "api_key": "your-api-key",
    "api_secret": "your-api-secret",
    "pair": "BTC/USDT",
    "investment": 1000,
    "grids": 10,
    "gridsize": 1.0,
    "sandbox_mode": true
}
```

### 永续合约配置（开发中）
```json
{
    "name": "PerpetualGridBot-Long",
    "exchange": "binance",
    "market_type": "future",
    "pair": "BTC/USDT",
    "strategy_side": "long",
    "leverage": 10,
    "lower_price": "60000",
    "upper_price": "70000",
    "grids": 10,
    "order_amount_usdt": 100,
    "max_position_count": 5
}
```

## 开发工作流

项目采用**测试驱动开发(TDD)**方法：

1. **编写失败测试** - 为新功能编写测试
2. **实现最小代码** - 编写使测试通过的最小代码
3. **重构优化** - 在保持测试通过的前提下重构
4. **重复循环** - 为下一个功能重复此过程

## 运行项目

### 安装依赖
```bash
pip install -r requirements.txt
```

### 配置设置
```bash
cp config/config.example.json config/config.json
# 编辑 config.json 填入您的API密钥和配置
```

### 运行机器人
```bash
python -m gridbot.bot --config config/config.json [--fresh]
```

### 运行测试
```bash
# 运行所有测试
pytest -v

# 运行单元测试
pytest tests/unit -v

# 运行特定测试
pytest -v -k "test_exchange"
```

## 重要文件说明

- **`config/config.example.json`** - 配置文件模板
- **`requirements.txt`** - Python依赖列表
- **`pytest.ini`** - 测试配置
- **`session_context.json`** - 项目状态和上下文
- **`单账户永续合约重构指南.md`** - 永续合约重构详细指南
- **`TODO.md`** - 待办事项列表

## Git仓库配置

- **origin**: `https://github.com/fm0668/Girdbot_v3.git` (您的仓库)
- **upstream**: `https://github.com/CaffeinatedTech/Girdbot_v3.git` (官方仓库)

## 下一步行动

1. **熟悉代码结构** - 查看各个模块的实现
2. **运行测试** - 确保环境配置正确
3. **阅读重构指南** - 了解永续合约迁移计划
4. **设置开发环境** - 配置API密钥和测试环境
5. **开始开发** - 根据需要进行功能开发或bug修复

## 联系和支持

- 查看 `TODO.md` 了解当前已知问题
- 查看 `单账户永续合约重构指南.md` 了解重构详情
- 参考 `GIT_WORKFLOW.md` 了解Git工作流程
