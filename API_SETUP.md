# API密钥配置指南

## 🔐 安全配置API密钥

### 1. 创建环境变量文件

```bash
# 复制示例文件
cp .env.example .env
```

### 2. 编辑 .env 文件

打开 `.env` 文件并填入您的实际API密钥：

```bash
# 币安期货API配置
BINANCE_FUTURES_API_KEY=您的实际API密钥
BINANCE_FUTURES_API_SECRET=您的实际API密钥密码

# 交易模式 (建议先用sandbox测试)
TRADING_MODE=sandbox  # 改为 live 启用实盘模式

# 网格策略配置
STRATEGY_SIDE=long
LEVERAGE=10
LOWER_PRICE=60000
UPPER_PRICE=70000
GRIDS=10
ORDER_AMOUNT_USDT=100
MAX_POSITION_COUNT=5

# 前端配置
FRONTEND_ENABLED=true
FRONTEND_HOST=localhost:8080
```

## 🔑 获取币安API密钥

### 1. 登录币安账户
- 访问 [币安官网](https://www.binance.com)
- 登录您的账户

### 2. 创建API密钥
1. 进入 **账户管理** → **API管理**
2. 点击 **创建API**
3. 选择 **系统生成** 或 **自定义**
4. 完成安全验证（邮箱、短信、谷歌验证器）

### 3. 配置API权限
**重要：** 确保启用以下权限：
- ✅ **期货交易** (Futures Trading)
- ✅ **读取** (Read)
- ❌ **提现** (Withdraw) - 不建议启用

### 4. IP白名单（推荐）
- 添加您的服务器IP到白名单
- 提高API安全性

## ⚠️ 安全注意事项

### 🔒 API密钥安全
1. **永远不要**将API密钥提交到Git仓库
2. **定期更换**API密钥
3. **限制权限**，只启用必要的权限
4. **使用IP白名单**限制访问

### 🧪 测试建议
1. **先在沙盒环境测试**：
   ```bash
   TRADING_MODE=sandbox
   ```

2. **使用小金额测试**：
   ```bash
   ORDER_AMOUNT_USDT=10  # 从小金额开始
   ```

3. **监控运行状态**，确认策略正常工作

4. **确认无误后**切换到实盘：
   ```bash
   TRADING_MODE=live
   ```

## 🚀 启动机器人

```bash
# 安装依赖
pip install -r requirements.txt

# 启动机器人
python -m gridbot.bot --config config/config.json
```

## 📊 配置参数说明

| 参数 | 说明 | 示例值 |
|------|------|--------|
| `STRATEGY_SIDE` | 策略方向 | `long` (做多) / `short` (做空) |
| `LEVERAGE` | 杠杆倍数 | `10` (1-125倍) |
| `LOWER_PRICE` | 网格下边界 | `60000` |
| `UPPER_PRICE` | 网格上边界 | `70000` |
| `GRIDS` | 网格层数 | `10` |
| `ORDER_AMOUNT_USDT` | 每网格订单金额 | `100` |
| `MAX_POSITION_COUNT` | 最大持仓网格数 | `5` |

## 🔧 故障排除

### 常见错误
1. **API密钥错误**：检查密钥是否正确复制
2. **权限不足**：确保启用了期货交易权限
3. **IP限制**：检查IP白名单设置
4. **余额不足**：确保账户有足够的USDT余额

### 日志查看
机器人运行时会输出详细日志，帮助诊断问题。

## 📞 支持

如遇问题，请检查：
1. API密钥配置是否正确
2. 网络连接是否正常
3. 币安API服务是否正常
4. 账户余额是否充足
