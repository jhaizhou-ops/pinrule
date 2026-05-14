# karma

> **让 Agent 不在长任务中遗忘你最重视的几条原则。**

karma 是 Claude Code 的一个轻量插件，把你**反复强调过但 Agent 总忘**的几条核心方向偏好「钉」在每次对话最显眼的位置，并在 Agent 违反时实时拦截 / 事后提醒。

## 这是什么

你跟 Claude 长会话推进任务时，是不是经常遇到：
- 你**反复强调过**「用普适长期方案不要打补丁」，但 Agent 几个 turn 后又开始打补丁
- 你说过「不要前端阻塞 — 测试跑着我们继续别的事」，但 Agent 又默认 sleep 等
- 你要求「多 Agent 并发」，但 Agent 用了一会儿又串行了
- 你强调「用中文不要技术黑话」，但 compact 后又开始 English + 缩写

这些不是 Agent **不知道**你的偏好（你说过），是 **「在长上下文中漂移 + compact 后压缩成模糊词」**。

karma 解决的就是这个 — 不让你的最高优先级方向被淹没。

## 安装

3 步上手（< 5 分钟）：

```bash
# 1. 拉代码 + 装依赖
git clone https://github.com/jhaizhou-ops/karma.git
cd karma
python -m venv .venv && source .venv/bin/activate
pip install -e .

# 2. 初始化（创建 ~/.claude/karma/ + 复制 sticky 模板）
karma init

# 3. 装 Claude Code hooks（自动写 settings.json，保留你已有的其他 hook）
karma install-hooks

# 验证
karma doctor    # 应看到 4 个 hook event 全 ✓
```

接下来正常用 Claude Code，karma 自动工作。

## 你会看到什么

### 1. 每条消息开头注入「最高优先级方向」

Claude 看到你消息前会先看到你的 sticky.yaml 6-10 条核心方向：

```
[karma sticky — 用户最高优先级方向，请始终遵守]
1. 用最根本、最长期、最普适、最优雅的方案。 ⚠️ 上次违反！
   不打补丁、不硬编码、不为追短期 KPI 牺牲长期质量。
2. 不阻塞前端 — 测试 / 子 Agent / 长任务跑步时，立刻并行推进其他能做的事。
3. 用直白中文。不用英文技术术语...
...

[你的消息]
开始下一步吧
```

24 小时内被触发过的规则会带 `⚠️ 上次违反！` 加强提醒。

### 2. Agent 想违反时实时拦截

```bash
# Agent 想跑 sleep —— PreToolUse hook 拦下
🛑 karma 拦截：违反 'non-blocking-parallel'
检测到：Bash sleep 命令: 'sleep 30'
建议：用 run_in_background=True 启动任务，并行做其他事

# Agent 想 commit 但没跑过测试 —— 拦下
🛑 karma 拦截：违反 'loud-failure-with-evidence'
检测到：git commit 前最近 session 内无测试通过证据
建议：commit 前跑测试（pytest / npm test 等）确认通过，再 commit
```

### 3. 累积观察

```bash
karma stats              # 每条规则违反次数 + 最近触发时间
karma violations recent  # 详细看最近 20 条违反
karma audit              # 审计 violations 历史 — 自动标可疑假阳（同触发词占 ≥ 50%）
karma doctor             # 检查环境 + hook 装机状态 + 当前生效 config
karma sticky list        # 看当前 sticky 配置
karma sticky edit        # 用 $EDITOR 编辑规则
```

## 设计

karma 做三件事：

1. **核心方向永驻** — 用户手工维护 5-10 条 `sticky.yaml`，每条消息前注入到 Claude 注意力最高位置
2. **实时拦截 (PreToolUse hook)** — Agent 调 tool 前扫违反，关键词层 + 工程层（regex pattern）双层检测，命中 deny
3. **事后扫违反 (Stop hook)** — Agent 回复后扫 transcript，违反写 `~/.claude/karma/violations.jsonl`，下次 user_prompt_submit 标 ⚠️

### 工程精细化（M3 完整版）

- **描述上下文统一豁免** — `.md` 文档 / `.yaml/.json/.toml` 数据 / `tests/` 目录 / `/tmp/` 探针 / 文件名含 probe/sample 等都豁免，避免「描述触发模式」被误判
- **shell 引号字面 + heredoc 智能剥** — `git commit -m "..."` 引号内是描述不是执行；`bash <<EOF` heredoc 内是真 shell 命令；`python <<EOF` heredoc 内是数据
- **background 任务证据自动接入** — `pytest > log.txt &` 跑通后下次 hook 自动读 log 接入「最近测试通过」证据，解决长任务 evidence check 死结
- **跨语言注释扫描** — Write/Edit 代码注释行 + docstring 扫意图字面（`# 先打个补丁`），代码主体（字符串数据）不扫

### 反馈机制

- **stderr 通知** — pre_tool_use 拦截时显示 deny reason；stop hook 列违反
- **桌面通知（macOS / Linux / Windows）** — stop hook 检测违反时弹系统通知（用户离开 stderr 视野时的补充）。`KARMA_NO_NOTIFY=1` 或 `notify_enabled: false` 关
- **累积告警按 turn 维度** — 最近 N turn 内同 sticky 违反 ≥ M 次 → 升级 🚨 严重通知
- **⚠️ 标记按 turn 维度** — 最近 N turn 内违反过的 sticky 下次 user_prompt_submit 注入时标红

**为啥按 turn 不按时间**：Agent 注意力漂移按 turn 累积。用户离开开会 30 分钟回来跟连续操作 30 分钟，Agent 状态完全不同 — 按人类时钟错维度。

### 配置（`~/.claude/karma/config.yaml`）

调阈值不用改代码。`karma doctor` 看当前生效值：

```yaml
notify_enabled: true                # 桌面通知开关
recent_violation_turns: 5           # ⚠️ 标记窗口（最近 N turn 内违反过的标）
escalate_window_turns: 3            # 累积告警窗口
escalate_threshold: 3               # 累积告警次数阈值
violations_max_lines: 5000          # rotation 触发行数
violations_keep_history: 3          # 保留几个历史
session_state_max_age_days: 30      # session-state 清理周期
max_recent_bash: 15
```

字段缺失用代码默认值（fail open）。`karma init` 复制模板。

## 场景化定位

karma = **通用 hook 框架** + **场景规则集**。

当前默认装的是「**软件开发场景**」预设（`data/sticky.dev.example.yaml`） — 6 条核心方向针对写代码时的注意力漂移：长期方案 / 不阻塞 / 完成证据 / 不喂测试集 / 先读再写 / 直白中文。

其他场景（写作 / 研究 / 产品 / 设计 / 法律等）需要不同的规则集 — 用户可以自己写 sticky.yaml，或社区贡献更多场景预设。karma 框架本身（hook 注入 / 实时拦截 / 违反检测 / 自动 catchup）跨场景通用。

工程检测层（`karma/checks/`）也偏开发场景（识别 pytest / Edit / Write / Bash 等开发工具）；其他场景可能需要不同 check 函数集。

## karma 不做的事

为避免重蹈 [karma v1](https://github.com/jhaizhou-ops/karma-v1) 覆辙，karma 明确**不做**这些：

- ❌ **不自动蒸馏新规则** — 用户自己维护核心方向 (5-10 条上限)
- ❌ **不做 retrieval / cosine 召回** — 5-10 条全 always-on，不需要选
- ❌ **不抢记忆系统赛道** — 「关于用户的事实/偏好」交给 Claude Code auto-memory
- ❌ **不引入 LLM** — 全工程化（regex / 计数 / 上下文判定）
- ❌ **不做奖惩 / 评分** — karma 是行为提示不是 RL

## sticky.yaml 写法

`~/.claude/karma/sticky.yaml`（`karma init` 会复制默认模板）:

```yaml
- id: long-term-fundamental
  preference: |
    用最根本、最长期、最普适、最优雅的方案。
    不打补丁、不硬编码、不为追短期 KPI 牺牲长期质量。
  violation_keywords:
    - 先打个补丁
    - 快速绕过
    - 硬编码
    - 临时方案
  violation_checks:
    - long_term_fundamental    # 工程层 regex pattern 集

- id: non-blocking-parallel
  preference: 不阻塞前端 — 测试 / 子 Agent / 长任务跑时，立刻并行推进
  violation_keywords:
    - 等测试完
    - 串行执行
  violation_checks:
    - non_blocking_parallel
```

字段：
- `id` — kebab-case slug，唯一
- `preference` — 一句或多行的方向描述（注入 Claude 看到的就是这个）
- `violation_keywords` — 关键词数组（Bash command + Write/Edit 注释扫）
- `violation_checks` — 工程层 check 函数名（可选，精确 pattern 检测）

软上限 10 条，硬上限 12 条（超过 karma 拒绝加载）。

## 状态

- [PRD.md](./PRD.md) — 产品需求 + 验证标准
- [ARCHITECTURE.md](./ARCHITECTURE.md) — 技术架构
- [HANDOFF.md](./HANDOFF.md) — 当前里程碑 + 接力棒
- [CLAUDE.md](./CLAUDE.md) — 给 Claude Code 协作的项目宪章
- [karma v1 归档](https://github.com/jhaizhou-ops/karma-v1) — v1 探索过程与反思

karma v2 已完成 M0-M3（六波 commit），158 个测试全绿，作者在 dogfooding 中。验证标准是「开发过程能否减少 Agent 在长任务中的方向漂移」— 而**开发 karma 的过程本身就是它最严酷的自用观察期**。
