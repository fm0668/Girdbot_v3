# 对冲网格机器人设置指南

## 1. API密钥配置

### 步骤1：编辑.env文件
打开项目根目录下的`.env`文件，将以下占位符替换为您的真实API密钥：

```bash
# 多头账户 API 密钥
LONG_API_KEY=your-actual-long-account-api-key
LONG_API_SECRET=your-actual-long-account-api-secret

# 空头账户 API 密钥  
SHORT_API_KEY=your-actual-short-account-api-key
SHORT_API_SECRET=your-actual-short-account-api-secret
```

### 步骤2：API密钥要求
- **多头账户**：用于执行买入操作的账户
- **空头账户**：用于执行卖出操作的账户
- **权限要求**：期货交易权限、读取权限、交易权限
- **安全建议**：使用子账户或专门的交易账户

## 2. 配置文件设置

### 测试配置（推荐先使用）
使用 `config/hedge_config_test.json` 进行初始测试：
- 沙盒模式：`"sandbox_mode": true`
- 小额交易：`"order_amount_usdt": 10`
- 低杠杆：`"leverage": 3`

### 实盘配置
使用 `config/hedge_config.example.json` 作为模板：
- 实盘模式：`"sandbox_mode": false`
- 根据资金调整：`"order_amount_usdt"`
- 合理杠杆：建议3-10倍

## 3. 测试步骤

### 步骤1：环境测试
```bash
python3 test_exchange_connection.py
```

### 步骤2：配置验证
如果测试通过，您应该看到：
- ✅ 环境变量检查通过
- ✅ 配置加载成功
- ✅ ExchangeInterface创建成功
- ✅ 交易所连接初始化成功

### 步骤3：运行对冲机器人
```bash
# 测试模式
python -m src.gridbot.hedge_main --config config/hedge_config_test.json

# 实盘模式（确保已充分测试）
python -m src.gridbot.hedge_main --config config/hedge_config.example.json
```

## 4. 风险控制参数

### 关键参数说明
- `leverage`: 杠杆倍数，建议3-10倍
- `order_amount_usdt`: 单次订单金额
- `max_position_count`: 最大持仓数量
- `max_imbalance_ratio`: 最大不平衡比例（0.05-0.1）
- `sync_tolerance_seconds`: 同步容忍时间（15-30秒）

### 安全建议
1. **从小金额开始**：先用小额测试系统稳定性
2. **监控运行状态**：密切关注对冲效果和平衡状态
3. **设置止损**：根据风险承受能力设置合理参数
4. **定期检查**：定期检查账户余额和持仓状态

## 5. 故障排除

### 常见问题
1. **API密钥错误**：检查.env文件中的密钥是否正确
2. **权限不足**：确保API密钥有期货交易权限
3. **网络连接**：检查网络连接和防火墙设置
4. **余额不足**：确保账户有足够的保证金

### 错误日志
如果遇到问题，请查看详细的错误信息：
- ExchangeInterface创建失败
- 交易所连接超时
- API权限错误
- 余额不足警告

## 6. 监控指标

### 关键监控项
- 对冲效果：平衡配对比例
- 同步延迟：配对同步时间
- 持仓状态：多空持仓平衡
- 利润统计：总利润和收益率

### 报告频率
- 对冲效果：每5分钟
- 同步延迟：每1分钟
- 状态报告：每10分钟

## 7. 紧急停止

如需紧急停止机器人：
1. 按 `Ctrl+C` 触发优雅退出
2. 系统会自动清理资源和关闭连接
3. 检查账户状态和持仓情况
