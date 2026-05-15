# karma

[![CI](https://github.com/jhaizhou-ops/karma/actions/workflows/ci.yml/badge.svg)](https://github.com/jhaizhou-ops/karma/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-275%20passed-brightgreen)](https://github.com/jhaizhou-ops/karma/actions)

> **让 Agent 不在长任务中遗忘你最重视的几条原则。**

karma 是 **Claude Code / Codex CLI / Gemini CLI 通用**的轻量插件，把你**反复强调过但 Agent 总忘**的几条核心方向偏好「钉」在每次对话最显眼的位置，并在 Agent 违反时实时拦截 / 事后提醒。

## 这是什么

你跟 Claude 长会话推进任务时，是不是经常遇到：
- 你**反复强调过**「用普适长期方案不要打补丁」，但 Agent 几个 turn 后又开始打补丁
- 你说过「不要前端阻塞 — 测试跑着我们继续别的事」，但 Agent 又默认 sleep 等
- 你要求「多 Agent 并发」，但 Agent 用了一会儿又串行了
- 你强调「用中文不要技术黑话」，但 compact 后又开始 English + 缩写

这些不是 Agent **不知道**你的偏好（你说过），是 **「在长上下文中漂移 + compact 后压缩成模糊词」**。

karma 解决的就是这个 — 不让你的最高优先级方向被淹没。

## 安装

**前置要求**：
- Python ≥ 3.11
- 已装 Claude Code / Codex CLI / Gemini CLI **至少一家**（不装 karma 装上也没用）
- 操作系统：**macOS / Linux**（Windows 兼容未真测，wrapper 用 Unix shebang，
  Windows 用户建议先 WSL 跑）
- 仓库**私有**期间：访问需 GitHub collaborator 权限 + 配好 git auth
  （SSH key 或 HTTPS token）。看 `gh auth status` 确认登入，或试
  `git clone https://github.com/jhaizhou-ops/karma.git` 看是否提示输入密码 /
  token。clone 失败先解决 auth。

### 推荐：让 AI 客户端帮你装

如果你已经在用 Claude Code / Codex / Gemini CLI 任意一家，最简单的装机方式是
**把下面这段话发给它，让它帮你跑装机命令**：

````
帮我装 karma（github.com/jhaizhou-ops/karma） — Claude Code / Codex / Gemini CLI
通用偏好提醒系统。

前置检查：
- Python ≥ 3.11: `python3 --version`
- git: `command -v git`
- **GitHub auth**: `gh auth status`（私有仓库期间必需；如果命令报 `gh:
  command not found` 试 `git ls-remote https://github.com/jhaizhou-ops/karma.git`
  — 列出分支就 OK，401/Permission denied 先配 SSH key 或 GitHub token）
- 可选 uv: `command -v uv`

步骤：
1. `mkdir -p ~/code && cd ~/code && git clone https://github.com/jhaizhou-ops/karma.git
   && cd karma`
2. 建 venv + 装：方式 A `python3 -m venv .venv && source .venv/bin/activate &&
   pip install -e .`，或方式 B（Python <3.11 但有 uv）`uv venv --python 3.11 .venv
   && uv pip install -e .`
3. `karma init` 初始化 ~/.claude/karma/
4. `karma install-hooks --backend all` 装 hook 到所有检测到的 AI 客户端
5. 验证：跑 `karma --version` `karma doctor` `karma sticky list` 把输出贴给我

完成后告诉我：⚠️ 必须重启 AI 客户端 karma 才生效。fish shell 用户第 2 步
用 activate.fish。想隔离试用：装前 `export KARMA_HOME=~/karma-test`。

⚠️ **codex 0.130 hook approval gate（最关键一步！）**：codex 0.130 起所有新
装的 hook 默认在「待审批」状态不执行。装完 karma 后**必须**：

```bash
codex                  # 起终端 TUI（不是 Desktop App，Desktop App 还有 regression）
                       # 会看到 ⚠ N hooks need review 横幅
> /hooks               # 在 TUI 输入这条命令
                       # 逐条 approve karma 4 个 wrapper（user_prompt_submit /
                       # pre_tool_use / post_tool_use / stop）
> /quit
```

审批后 karma 在 codex CLI 才真触发。Claude Code 这条线没 approval gate
任何用法都真生效。
````

AI 会逐步检查环境、克隆代码、装依赖、装 hook、验证、提醒你重启客户端。

### 手动装机（< 5 分钟）：

```bash
# 1. 拉代码 + 装依赖（Python ≥ 3.11）
git clone https://github.com/jhaizhou-ops/karma.git
cd karma

# 建 venv 用以下任一方式（看你机器装 Python 的方法）：
python3 -m venv .venv                              # 系统 python3 是 3.11+
# 或者 python3.11 -m venv .venv                    # 装了 python3.11 命令
# 或者 uv venv --python 3.11 .venv                 # 用 uv 按需下载 Python 3.11
source .venv/bin/activate
pip install -e .                                    # 没 pip 用 `uv pip install -e .`

# 2. 初始化（创建 ~/.claude/karma/ + 复制 sticky 模板）
#    默认按系统语言偏好自动选 7 条完整（中文）或 5 条精简（其他）。
karma init

# 3. 装 hooks（默认 Claude Code 向后兼容；codex / gemini-cli / all 显式选）
karma install-hooks                    # Claude Code（默认）
karma install-hooks --backend codex    # Codex CLI（自动启用 features.hooks）
karma install-hooks --backend gemini-cli  # Gemini CLI
karma install-hooks --backend all      # 本机检测到的所有客户端一次装

# 4. 验证
karma doctor    # 应看到对应 backend 的 hook event 全 ✓（Claude Code 8 个）
```

**期望输出片段**（`--backend all` 装齐三家）：

```
→ Claude Code（claude-code）
  生成: ~/.claude/hooks/karma_user_prompt_submit.py
  生成: ~/.claude/hooks/karma_pre_tool_use.py
  生成: ~/.claude/hooks/karma_post_tool_use.py
  生成: ~/.claude/hooks/karma_stop.py
  生成: ~/.claude/hooks/karma_session_start.py    # v0.4.28 v3 第四步
  生成: ~/.claude/hooks/karma_pre_compact.py      # v0.4.29 v3 第五步
  生成: ~/.claude/hooks/karma_subagent_start.py   # v0.4.30 v3 第六步
  生成: ~/.claude/hooks/karma_subagent_stop.py    # v0.4.30 v3 第六步
  已配置 ~/.claude/settings.json（8 个 hook event）

→ Codex CLI（codex）
  Codex features.hooks 已启用 ✓
  生成: ~/.codex/hooks/karma_user_prompt_submit.py
  ... (同上)

→ Gemini CLI（gemini-cli）
  ... (同上)
```

`karma doctor` 应该每个 backend 的 4 个 event 都 `✓`。如果有 `✗` 重跑
`karma install-hooks --backend <对应名>`。

**⚠️ 装完必读 2 条**：

1. **必须重启 AI 客户端 karma 才生效** — Claude Code / Codex / Gemini CLI 都是
   session 启动时**一次性**读 hook 配置不热重载。当前正在跑的 session karma
   不会触发，重启新 session 即可。

2. **删 / 移动 `.venv` 前必须先 `karma uninstall`** — karma hook wrapper 用
   `#!/path/to/.venv/bin/python` 硬写 venv 路径，删了 .venv 后 hook 会指向
   不存在的 python 让 AI 客户端启动报错。要重建 venv：先 `karma uninstall`,
   再删 .venv 重建 + `pip install -e . && karma install-hooks --backend all`。

接下来用 Claude Code / Codex / Gemini CLI 哪家，karma 自动工作。保留你已装
的其他 hook 插件（vibe-island / rtk / 等），共存不冲突。

### 维护跟卸载

```bash
# 重装 hooks（修改 sticky.yaml 后不需要重装；只在删了 .venv / 换路径时重装）
karma install-hooks --backend all

# 卸载（按 backend 单独卸 / all 一次卸 / 一键 uninstall alias）
karma uninstall-hooks --backend codex
karma uninstall-hooks --backend all
karma uninstall                            # 等同 --backend all 一键卸所有
```

**⚠️ 重要**：详情见前面「装完必读 2 条」第 2 条 — venv 重建前必须先
`karma uninstall`。

## 装完立即做：自定义 sticky 偏好

karma 默认装的 5/7 条 sticky 是「跨用户合理」的中性版本，**不一定是你的真偏好**。
装完立即跑 `karma sticky list` 看默认，然后 `karma sticky edit` 改成你自己的。

特别注意 **karma 默认是「逐步确认型」** — Agent 完成一波后会停下问你下一步。如果
你是「全权委托型」（希望 Agent 自主推进不等你确认），手动在 `sticky.yaml` 加：

```yaml
- id: keep-pushing-no-stop
  preference: |
    完成一波后不要停下汇报完等用户反馈 — 立刻选下一个推进点继续做。
    我是全权委托型用户，期待自主推进；汇报跟推进可以同步进行不互斥。
    例外：用户明确叫停（「停 / 不用了 / 明天再说 / 先到这」等）→ 才停。
  violation_keywords:
    - 等你叫停
    - 等你决定
    - 要不要继续
  violation_checks:
    - keep_pushing_no_stop
  force_block_exempt: true   # 避免累积处罚自身矛盾
```

注：keep-pushing 是「让 Agent 不停」的强干预规则，作者本机一天累积 14 次触发
表示生效，但对「逐步确认型」用户是 noise。**按你真偏好选**。

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

## 支持的 AI 编程客户端

karma v0.4+ 支持 **3 家 AI 编程客户端 hook 协议**（基类抽象，加新家是「填表」）：

| 客户端 | 配置文件 | 启用方式 | 实测状态 |
|---|---|---|---|
| Claude Code | `~/.claude/settings.json` | 默认启用 | ✓ v0.1.0 起 |
| Codex CLI | `~/.codex/hooks.json` | `karma install-hooks --backend codex`<br/>自动启用 `[features] hooks = true` | ✓ v0.3.0 装机层<br/>⚠️ **codex 0.130 新加 hook approval gate** — 装完 karma 4 个 hook 默认在「待审批」状态不执行。**必须**第一次跑 `codex` TUI 输入 `/hooks` 手动审批 4 个 karma wrapper 才真触发。codex 启动会显示 `⚠ N hooks need review before they can run`。<br/>另：codex Desktop App 0.129+ 还有 [regression issue #21639](https://github.com/openai/codex/issues/21639)。 |
| Gemini CLI | `~/.gemini/settings.json` | `karma install-hooks --backend gemini-cli` | ✓ v0.4.0 起 |

加新客户端 backend 看 [karma/backends/HOWTO.md](./karma/backends/HOWTO.md) —
继承 `JsonHooksBackend` 基类只需填 6 个类属性 + 4 个 event 映射。

vibe-island 等其他通用桥实证支持的客户端清单：cursor / factory / qoder /
copilot / codebuddy / kimi — 这些都能填表加进 karma backend。

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

## 诚实的工具边界

karma 是 **regex 字面匹配 + 计数**的工程工具，不是大模型语义理解。这意味着：

- **真有假阳**（误拦你的合法操作） — 表格 cell 引用术语 / `python -c` 内字符串字面 / commit message 描述违反字眼等场景都可能误拦。遇到时按 `karma audit` 看 `⚠️ 可能假阳` 标记，给作者反馈
- **真有假阴**（漏拦真违反） — 用户故意伪装（假数字「9999 测试通过」/ kebab-case 包裹 ML 真 jargon 等）regex 分不清。karma 信任用户不蓄意作弊
- **`karma audit` 修后 0 触发 ≠ 真根因 fix 正确** — 可能只是 fix 过宽把真阳吃了。dogfooding 数据是嫌疑提示不是 truth

karma 是**让你注意自己偏好被 Agent 偏离时收到提示**，不是「绝对正确的行为审计」。把它当成 git 跟 lint 之间的工具用 — 给信号，不替决策。

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

### v3 演化中（2026-05-14 起）

karma v2 「事后审计」架构有天花板 — Agent 容易学到「怎么不被 hook 拦」而不是「真按 sticky 行为」。v3 往「proactive 教练」方向演化，已落地 5 步：

- **v0.4.24 中段注入 anchor** — PostToolUse hook 在每次 tool call 后注入最近触发过的 sticky 简化提醒。Claude Code 协议层验证 `additionalContext` 真接受 — sticky 不再只在 user prompt 头部一次注入
- **v0.4.25 字面多样性元行为监测** — `karma audit --with-fix-timeline` 加 🎭 字面试探标记。Agent 用多种 snippet 字面变体触发同一 sticky 时（如 keep-pushing 91% 多样性）标出来，让用户看到 Agent 在反向工程绕 check 还是真改行为
- **v0.4.26→v0.4.27 反思式语气改造** — keep-pushing / chinese-plain 两条表达风格类规则的 suggested_fix 改反思式（自检你是不是真合理停下 / 真技术专名必须保留）。`long-term` 补丁 + `non-blocking` sleep 等工程行为类规则保持命令式（防 Agent 自我合理化）
- **v0.4.28 SessionStart sticky baseline** — Claude Code SessionStart hook 在 session 起手注入 sticky baseline。`source` 字段区分 startup / resume / clear / compact，compact 场景额外加强警示
- **v0.4.29 PreCompact 落盘 + 两端夹击 compact 失忆** — compact 触发前 PreCompact hook 落盘完整 sticky 状态到 `~/.claude/karma/pre_compact_snapshot.md`（含 sticky 内容 + 最近 5 turn 违反清单 + 时间戳），SessionStart(source=compact) 重起时读盘加强提醒。两端夹击让 sticky 跨 compact 不丢。**不阻止 compact** — compact 是 Claude Code 保护机制 karma 不该干扰
- **v0.4.30 SubagentStart/Stop + 删 PostCompact 幽灵代码** — SubagentStart 注入 sticky baseline，SubagentStop 给主 Agent 透明度提醒。确认 PostCompact 协议层不支持 additionalContext → 删 v0.4.29 残留 post_compact.py 幽灵代码。install-hooks 现装 8 hook event
- **v0.4.31~33 真根因 fix** — subagent_start.py ensure_ascii 子 Agent 收乱码 / bypass_karma `json.dump\b` regex 缺 word boundary 假阳 / strip_shell_quoted_literals 复合 shell 嵌套（heredoc + indirect Step 顺序错导致 release notes markdown 反引号路径漏剥）
- **v0.4.34~39 真闭环架构 — 按当前模型自动适应阈值** — 用户洞察连击驱动：
  - **v0.4.34 子 Agent 独立 state 架构** — 用户「彼此互不干扰 + 临时独立 + 自动销毁」原则。session_state 加 agent_id 路由（`<session_id>__<agent_id>.json`），SubagentStop 自动销毁子 Agent 临时 state
  - **v0.4.35 model_threshold 表** — 用户「真衰减拐点 70K-200K 不是 8K，差 10x，建议至少 60K + 自动适应不用手动调」。Opus 80K / Sonnet 60K / Haiku 30K / 老模型 8K 向后兼容 / 未知 fallback 60K
  - **v0.4.36~38 hook payload 路径尝试** — SessionStart payload 真有 model（v0.4.36），但 user_prompt_submit / PreToolUse / PostToolUse / Subagent* 都没（v0.4.38 dogfooding 验证 7 turn state.model 仍 None 证明）
  - **v0.4.37 子 Agent model 真捕获** — 用户「自己试一下就知道答案」。manual run 实验真发现：tool_name 真是 "Agent" 不是 "Task"，tool_input 真含 model 字段。主 PreToolUse(Agent) 入队 pending → SubagentStart pop 写子 Agent state.model
  - **v0.4.39 真根本路径 — transcript_path** — 用户「怎么查 model 你不是就能查么」+「我随时 /status 都能看到当前 model」。深挖发现所有 hook payload 真有 transcript_path → reverse scan jsonl 找最后非合成 model 字面 → karma 真权威路径，不依赖 payload 含 model 字段。dogfooding 真生效证据：state.model='claude-opus-4-7' 真写入
- **v0.4.40 反思阈值 + chinese-plain 分母精化 + 真字狂魔治理** — 用户 3 条精确反馈驱动：① `stop_block_max_per_turn` 默认 3 → 2，减弱自证清白压力但不放松规则。② chinese_plain 分母精化（不改 40% 阈值，改算法）：剥含点号工程标识符 / 路径字面 / commit message 引号块，工具调用纯英文不再被错算成中文比例分母。③ 加 Check 3 同前缀字重复检测（同前缀 ≥ 5 次/response 触发自审），reactive 治理 HANDOFF 第 7 类矛盾「真字癫狂」副作用。白名单豁免高频合理前缀（一/不/是/有/没/我/你/他/这/那/在）
- **v0.4.41 keep_pushing 加 user_prompt 上下文叫停检测** — dogfooding 真触发：用户「不用啦感谢，休息吧」明确叫停但反思 hook 反复触发。真根因：keep_pushing.check 只看 Agent response 末尾，看不到 user prompt 上文。sticky #8 例外清单字面（停 / 不用了 / 明天再说 / 先到这 / 算了 / 晚安 / 够了等）从文本声明变工程层 enforced：stop.py 加 `_read_last_user_prompt` + checks `run_checks` 加 user_prompt 入参透传 + keep_pushing `_USER_STOP_HINT_RE` 整 turn 豁免

**真效果对比**（本机 dogfooding 真测）：1 turn 累积 ~60K token 场景下，v0.4.32 (8K 阈值) 触发 7+ 次中段提醒，v0.4.39 (opus 80K 真阈值) 触发 0 次 — **7x+ 频率真降，「Agent 防御性写作扭曲」副作用真根因消除**。

后续观察方向：跨场景真用户使用 + 真验证 transcript_path 真路径在长 session（jsonl 几 MB 级别）真性能 + 真用户跨模型场景。
- [CLAUDE.md](./CLAUDE.md) — 给 Claude Code 协作的项目宪章
- [karma v1 归档](https://github.com/jhaizhou-ops/karma-v1) — v1 探索过程与反思
- HANDOFF.md — 内部开发接力文档（非最终用户文档）

karma v2 已完成 M0-M5（多 backend 横向扩展）+ v3 演化（中段注入 / 字面多样性监测 / 反思式语气 / SessionStart baseline / PreCompact 落盘 / SubagentStart 装机 / 子 Agent 独立 state + 按当前模型自动适应阈值）+ 多轮评审 Agent 交叉评审 + 多轮 dogfooding 修真 bug，**389 个测试全绿**。三家 AI 客户端（Claude Code / Codex CLI / Gemini CLI）实测装机 / 卸装 / hook 触发全跑通。

**用户状态**：2026-05-14 起进入「真实非作者用户使用期」— 之前一年是作者 dogfooding 自用观察，现在开始有同事/朋友首次接触 karma。这是 dogfooding 转 real-user 的关键时刻，新用户首装踩坑会持续触发新一波改进。验证标准是「开发过程能否减少 Agent 在长任务中的方向漂移」— 而**开发 karma 的过程本身就是它最严酷的自用观察期**。
