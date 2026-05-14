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
karma stats                              # 每条规则违反次数 + 本 session turn 漂移
karma violations recent                  # 详细看最近 20 条违反
karma violations clear                   # 清全部历史
karma violations clear --sticky <id>     # 选择性清某 sticky 历史
karma violations clear --trigger <text>  # 按触发词 substring 清（fix 后清假阳累积）
karma audit                              # 审计 + 自动改进建议（同触发词占 ≥ 50% 标 ⚠️）
karma reset                              # 清 session-state 漂移实验重启
karma doctor                             # 检查环境 + hook 装机 + 当前生效 config + 活跃 session
karma sticky list                        # 看当前 sticky 配置
karma sticky edit                        # 用 $EDITOR 编辑规则
```

## 设计

karma 做三件事：

1. **核心方向永驻** — 用户手工维护 5-10 条 `sticky.yaml`，每条消息前注入到 Claude 注意力最高位置
2. **实时拦截 (PreToolUse hook)** — Agent 调 tool 前扫违反，关键词层 + 工程层（regex pattern）双层检测，命中 deny
3. **事后扫违反 (Stop hook)** — Agent 回复后扫 transcript，违反写 `~/.claude/karma/violations.jsonl`，下次 user_prompt_submit 标 ⚠️

### 反馈机制（一句话概述）

- **stderr 通知 + 桌面通知**（macOS / Linux / Windows）让违反不被错过
- **按 turn 累积告警**：Agent 注意力漂移按 turn 不按人类时钟（用户离开开会
  30 分钟回来跟连续操作 30 分钟，Agent 状态完全不同）
- **Stop hook 真干预**：Agent 沉默式停下时让继续生成下一步（防死循环 safeguard）
- **累积强制 block**：同规则反复违反 → 要求 fix 真根因或让用户介入；可在
  sticky 配置 `force_block_exempt: true` 关闭（给「应该继续推进」类规则用）
- **元层监管**：Bash 命令含 karma 内部状态字面 + 写操作 → 拦「绕开检测」

实现细节（描述上下文豁免 / shell 引号 + heredoc 剥 / background 证据自动接入 /
跨语言注释扫描 / 8 个工程检测函数实现）详 [ARCHITECTURE.md](./ARCHITECTURE.md)。

### 配置

`~/.claude/karma/config.yaml` 调阈值不用改代码。`karma doctor` 看当前生效值
+ 完整字段表 详 [ARCHITECTURE.md](./ARCHITECTURE.md#配置)。

## 场景化定位

karma = **通用 hook 框架** + **场景规则集**。`karma init` 默认装「软件开发」场景。

**两套开发场景模板按需选**：

| 模板 | 内容 | 适合 |
|---|---|---|
| `data/sticky.dev.example.yaml`（默认 7 条） | 长期方案 / 不阻塞 / 直白中文 / 完成证据 / 不喂测试集 / 不绕开检测 / 先读再写 | 中文用户 / ML 或数据 / 评测场景 |
| `data/sticky.dev.minimal.example.yaml`（5 条精简） | 长期方案 / 不阻塞 / 完成证据 / 不绕开检测 / 先读再写 | 英文母语 / 普通后端 / 前端 / 工具开发 |

精简版砍掉「直白中文」「不喂测试集」两条场景化规则。**装时按系统语言偏好自动选**：

```bash
karma init              # 自动选：中文系统 → 7 条完整；非中文 → 5 条精简
karma init --minimal    # 强制 5 条精简
karma init --no-minimal # 强制 7 条完整
```

跨平台检测（跟 VS Code / Slack 等 app 一样的标准做法）：
- macOS：`defaults read -g AppleLanguages`（系统设置里的真实语言偏好，不是 shell `LANG`）
- Linux：`$LC_ALL` / `$LC_MESSAGES` / `$LANG`（POSIX 优先级）
- Windows：`GetUserDefaultUILanguage` Windows API + `locale.windows_locale` 查表

检测不到（容器 / CI / 异常）fallback 5 条精简（最安全默认）。

其他场景（写作 / 研究 / 产品 / 设计 / 法律等）— 用户可自己写 sticky.yaml,
或社区贡献预设。karma 框架本身（hook 注入 / 实时拦截 / 违反检测）跨场景通用。
工程检测层 `karma/checks/` 偏开发场景（识别 pytest / Edit / Write / Bash）;
其他场景可能需要不同 check 函数。

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

**字段表**：

| 字段 | 必填 | 含义 |
|---|---|---|
| `id` | ✓ | kebab-case slug（如 `long-term-fundamental`），唯一 |
| `preference` | ✓ | 一句或多行的方向描述。注入 Claude 看到的就是这个，写清楚有例外有决策提示 |
| `violation_keywords` | ✗ | 关键词数组。Bash command + Write/Edit 代码注释 + Stop hook 扫 Agent response 命中则记违反 |
| `violation_checks` | ✗ | 工程层 check 函数名数组（见下表），精确 pattern 检测 |
| `force_block_exempt` | ✗ | bool，默认 false。设 true 关闭累积处罚 — 给「应该继续推进 / 不阻塞」类规则用，否则累积「停下太多」触发 force_block 让 Agent 必须停下会语义自我矛盾 |

**8 个内建 `violation_checks`** 名（从 `karma/checks/` 注册表选）：

| 函数名 | 默认装？ | 检测内容 |
|---|---|---|
| `long_term_fundamental` | ✓ | git commit/push --no-verify 等 / 长 hash 黑白名单字面 / 意图注释「我先打个补丁」 |
| `non_blocking_parallel` | ✓ | sleep N / 阻塞 wait / 长任务（docker / cargo / npm install）无 background |
| `chinese_plain_no_jargon` | ✓（仅 dev.example，minimal 砍掉） | 中文占比 < 40% / 英文技术 jargon 列表（剥 code block + inline code） |
| `loud_failure_with_evidence` | ✓ | 完成词「fix 了 / done」+ 代码任务上下文 + session 内无测试通过证据 |
| `no_testset_no_future_leakage` | ✓（仅 dev.example，minimal 砍掉） | gold_cases 反喂 / 跨 split 复制 / 长 hash 字面 |
| `read_before_write` | ✓ | Edit / Write 前未 Read 过该 file_path（路径规范化等价） |
| `bypass_karma_detection` | ✓ | Bash 命令含 karma 内部字面 + 写操作 → 拦绕开检测 |
| `keep_pushing_no_stop` | **可选**（自加 sticky 引用） | response 末尾推进信号 / 问号 / 停顿词 / 默认四路检测。给「全权委托型」用户用 — 想开就在 sticky.yaml 加一条 `id: keep-pushing-no-stop` + `violation_checks: [keep_pushing_no_stop]` + 建议 `force_block_exempt: true` |

软上限 10 条，硬上限 12 条（超过 karma 拒绝加载）。

### 默认 7 条开发场景 sticky + 2 条元层 sticky

`data/sticky.dev.example.yaml` 默认装 7 条：
1. `long-term-fundamental` 用最根本方案不打补丁
2. `non-blocking-parallel` 测试 / 子 Agent 跑时并行推进
3. `chinese-plain-no-jargon` 直白中文不堆 jargon
4. `loud-failure-with-evidence` 完成附测试证据
5. `no-testset-no-future-leakage` 不喂测试集 / mock 反喂主流程
6. `read-before-write` 改代码前先读
7. `deep-fix-not-bypass`（**元层**）karma 拦截时深挖根因，禁止手动改 karma 内部状态绕开

可选个人 sticky（全权委托型用户）：
- `keep-pushing-no-stop`（**元层**）完成一波后立即推下个，不停下等用户决定。Stop hook 配合 `decision=block` 让 Agent 不真停继续生成（safeguard：单 turn 累积 ≥ 3 次后真放停）。

## 状态

- [PRD.md](./PRD.md) — 产品需求 + 验证标准
- [ARCHITECTURE.md](./ARCHITECTURE.md) — 技术架构
- [CHANGELOG.md](./CHANGELOG.md) — 版本变更
- [CLAUDE.md](./CLAUDE.md) — 给 Claude Code 协作的项目宪章
- [karma v1 归档](https://github.com/jhaizhou-ops/karma-v1) — v1 探索过程与反思
- HANDOFF.md — 内部开发接力文档（非最终用户文档）

karma v2 已完成 M0-M4 + 多轮评审 Agent 交叉评审 + 多轮 dogfooding 修真 bug，275 个测试全绿（含 17 条跨平台 locale 检测守护）。验证标准是「开发过程能否减少 Agent 在长任务中的方向漂移」— 而**开发 karma 的过程本身就是它最严酷的自用观察期**。
