# Git 工作流指南

## 仓库配置

您的Git仓库已经配置了以下远程仓库：

- **origin**: `https://github.com/fm0668/Girdbot_v3.git` (您的个人仓库)
- **upstream**: `https://github.com/CaffeinatedTech/Girdbot_v3.git` (原始官方仓库)

## 日常开发工作流

### 1. 开始新功能开发

```bash
# 确保在主分支上
git checkout main

# 从upstream拉取最新更改
git fetch upstream
git merge upstream/main

# 推送更新到您的仓库
git push origin main

# 创建新的功能分支
git checkout -b feature/your-feature-name
```

### 2. 进行开发工作

```bash
# 进行代码修改...

# 添加更改
git add .

# 提交更改（使用规范的提交信息格式）
git commit -m "feat(component): add new feature description"
```

### 3. 推送到您的仓库

```bash
# 推送功能分支到您的仓库
git push origin feature/your-feature-name
```

### 4. 合并到主分支

```bash
# 切换到主分支
git checkout main

# 合并功能分支
git merge feature/your-feature-name

# 推送到您的仓库
git push origin main

# 删除功能分支（可选）
git branch -d feature/your-feature-name
git push origin --delete feature/your-feature-name
```

## 同步官方更新

### 定期同步官方仓库的更新

```bash
# 获取官方仓库的最新更改
git fetch upstream

# 切换到主分支
git checkout main

# 合并官方更新
git merge upstream/main

# 推送到您的仓库
git push origin main
```

### 处理冲突

如果在合并时出现冲突：

```bash
# 查看冲突文件
git status

# 手动解决冲突后
git add .
git commit -m "fix: resolve merge conflicts with upstream"
git push origin main
```

## 提交信息规范

使用以下格式：`type(scope): description`

**类型 (type):**
- `feat`: 新功能
- `fix`: 修复bug
- `refactor`: 重构代码
- `test`: 添加或修改测试
- `docs`: 文档更改
- `chore`: 构建过程或辅助工具的变动

**范围 (scope):**
- `bot`: 主机器人逻辑
- `exchange`: 交易所接口
- `strategy`: 交易策略
- `websocket`: WebSocket通信
- `config`: 配置相关
- `tests`: 测试相关

**示例:**
```bash
git commit -m "feat(strategy): implement perpetual futures grid strategy"
git commit -m "fix(exchange): handle order cancellation errors"
git commit -m "refactor(bot): improve error handling"
```

## 分支策略

- **main**: 主开发分支，保持稳定
- **feature/**: 功能开发分支
- **fix/**: 修复bug分支
- **develop**: 开发分支（如果需要）

## 测试驱动开发 (TDD)

在提交前确保：

```bash
# 运行所有测试
pytest -v

# 运行特定类型的测试
pytest tests/unit -v
pytest -v -k "test_exchange"
```

## 快速命令参考

```bash
# 查看当前状态
git status
git branch -a
git remote -v

# 同步官方更新
git fetch upstream && git merge upstream/main && git push origin main

# 创建并切换到新分支
git checkout -b feature/new-feature

# 查看提交历史
git log --oneline -10

# 撤销最后一次提交（保留更改）
git reset --soft HEAD~1
```

## 注意事项

1. **始终在功能分支上开发**，不要直接在main分支上进行大的更改
2. **定期同步官方仓库**，避免分歧过大
3. **遵循提交信息规范**，便于追踪更改历史
4. **提交前运行测试**，确保代码质量
5. **小步提交**，每个提交应该是一个逻辑完整的更改

这样的工作流确保您可以：
- ✅ 在您的仓库中自由开发和修改
- ✅ 保持与官方仓库的同步
- ✅ 维护清晰的开发历史
- ✅ 方便地推送更改到您的仓库
