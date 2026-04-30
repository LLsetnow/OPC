# agents.md — AI Agent 项目规则文件

## 项目概述

- 项目名称：{{项目名称}}
- 技术栈：{{技术栈}}
- 包管理器：uv / pip
- Python 环境：`qwen3-tts-venv`（WSL 内的虚拟环境）
- 命令执行环境：WSL（Windows Subsystem for Linux），默认 Shell：zsh

---

## 环境与执行规范

### 命令执行

所有命令默认在 **WSL zsh** 中执行，不要使用 Windows CMD / PowerShell。

```bash
# ✅ 正确：直接在 WSL 中执行
wsl --cd ~/project pnpm dev

# 或在 WSL 终端内执行（AI 应优先进入 WSL）
cd ~/project && source qwen3-tts-venv/bin/activate && python main.py
```

### Python 虚拟环境

- 虚拟环境名：`qwen3-tts-venv`
- 激活方式：`source qwen3-tts-venv/bin/activate`
- 依赖管理：激活环境后使用 `pip install -r requirements.txt`
- 路径示例：`~/qwen3-tts-venv/` 或 `./qwen3-tts-venv/`

```bash
# 激活虚拟环境
source qwen3-tts-venv/bin/activate

# 验证已激活
which python    # 应显示路径中包含 qwen3-tts-venv
python --version

# 安装依赖
pip install -r requirements.txt

# 运行项目
python main.py

# 退出虚拟环境
deactivate
```

---

## 工作流

### 核心流程

每个功能严格执行五步流程：

```
方案设计 → 编码实现 → 自测验证 → 沉淀文档 → 提交 Git
```

### 步骤详解

**1. 方案设计**
- 阅读 `docs/` 目录下的相关文档，了解全局
- 在 `docs/` 中输出技术方案（包含实现思路、接口设计、影响范围）
- 等待人工确认后再开始编码

**2. 编码实现**
- 遵循项目的编码规范
- 保持代码简洁，避免过度抽象
- 保持现有代码风格一致

**3. 自测验证**
- 激活虚拟环境后运行测试
- 修复所有失败用例
- 确保不破坏已有功能

**4. 沉淀文档**
- 更新 `docs/` 目录下的相关文档
- 记录关键决策和注意事项

**5. 提交 Git**

```bash
# 查看变更
git status
git diff --stat

# 按功能模块分次提交（不要一次性提交所有改动）
git add <相关文件>
git commit -m "feat: 完成 xxx 功能"

# 推送到远程
git push
```

### 提交规范

- 每个独立功能完成后立即提交一次 Git
- 提交后立即更新本 `agents.md` 中的进度记录
- 语义化 commit：

| 类型 | 说明 |
|:-----|:------|
| `feat:` | 新功能 |
| `fix:` | Bug 修复 |
| `refactor:` | 代码重构 |
| `docs:` | 文档更新 |
| `chore:` | 杂项（配置、依赖等） |
| `test:` | 测试相关 |

---

## 进度追踪

> ⚠️ **重要：每完成一个功能，必须同步更新下方进度表。**

### 已完成功能

| # | 功能 | commit | 日期 | 备注 |
|:-:|:-----|:-------|:----|:-----|
| 1 | {{第一个已完成功能}} | `abc1234` | 2026-04-30 | {{备注}} |
| 2 | {{第二个已完成功能}} | | | |

### 未完成功能

| # | 功能 | 优先级 | 状态 | 备注 |
|:-:|:-----|:------|:----|:-----|
| 1 | {{待实现功能}} | 高/中/低 | ⏳ 进行中 / ⏸️ 阻塞 / ⏹️ 待开始 | {{备注}} |
| 2 | {{待实现功能}} | 高 | ⏹️ 待开始 | |

### 状态标记

```
✅ 已完成     ⏳ 进行中     ⏸️ 阻塞     ⏹️ 待开始
```

---

## 项目目录结构

```
{{项目根目录}}/
├── agents.md              # 本文件：AI 规则 + 进度追踪
├── CLAUDE.md              # （可选）Claude Code 读取的同内容文件
├── docs/                  # 设计文档、API 文档
├── src/                   # 源代码
├── tests/                 # 测试
├── requirements.txt       # Python 依赖
├── pyproject.toml         # 项目配置
└── README.md              # 项目说明
```

---

## 编码规范

- Python 使用 `snake_case` 命名
- 函数和类必须写 docstring
- 遵循 PEP 8（可使用 `ruff` 自动检查）
- 类型注解：所有函数参数和返回值必须标注类型
- 数据库操作放在 `repositories/` 层，业务逻辑放在 `services/` 层
- 不要硬编码配置项，使用环境变量或配置文件

---

## 质量要求

- 每个功能必须有对应的测试
- 提交前确保现有测试全部通过
- lint 无报错后方可提交
- 不要删除或修改已有功能，除非明确要求

---

## 常用命令速查

```bash
# 激活环境
source qwen3-tts-venv/bin/activate

# 运行开发服务器
python main.py

# 运行测试
pytest

# 运行 lint
ruff check .

# 格式化代码
ruff format .
```

---

## 参考

- 本文件灵感来源于 Harness Engineering 方法论中的 `agents.md` 概念
- 更多配置说明 → [[AI模型/Agent工具/Claude Code.md]]
