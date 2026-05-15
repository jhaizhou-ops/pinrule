# karma

[![CI](https://github.com/jhaizhou-ops/karma/actions/workflows/ci.yml/badge.svg)](https://github.com/jhaizhou-ops/karma/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-392%20passed-brightgreen)](https://github.com/jhaizhou-ops/karma/actions)
[![Release](https://img.shields.io/badge/release-v0.4.44-blue)](https://github.com/jhaizhou-ops/karma/releases)

> **让 AI Agent 在长任务中不再忘记你最在乎的那几条原则。**
>
> Claude Code / Codex CLI / Gemini CLI 通用。纯工程零 LLM，单依赖 PyYAML，hook 响应 < 100ms。

---

## 你是不是也遇到过 ↓

```
你（turn 1）：用最干净最长期的方案做，不要打补丁。
Agent：明白！设计干净的方案 X...

（30 分钟、50 turn、context 累积到 80K 之后...）

你（turn 50）：这块出了 bug，看看怎么修
Agent：先打个补丁应付一下，回头再深挖 ← 你之前的偏好已经被淹没
```

**你的高优先级偏好被长 context 淡化** — 不是 Agent 不知道，是 Agent 注意力衰减了。

karma 把你**手工写的 5-10 条核心方向**钉死在每条消息最显眼的位置，长 context 衰减时按模型自适应阈值（Opus 80K / Sonnet 60K / Haiku 30K）中段重新注入，违反时实时拦截 + 反思干预 — Agent 想偏离都难。

---

## 30 秒看效果

**安装一行命令**：

```bash
git clone https://github.com/jhaizhou-ops/karma.git ~/karma
cd ~/karma && python -m venv .venv && .venv/bin/python -m pip install -e . && .venv/bin/karma init && .venv/bin/karma install-hooks
```

**Claude Code 重启后，每次提交 prompt 都会看到注入头部**（合作默契语气，不是冷冰冰的规则）：

```
[karma — 你跟用户的长期默契]
跟你协作的是一位真人用户，他列出了几条长期最看重的方向。
这不是规则也不是审判 — 是他希望跟你建立的协作默契。

1. 用户相信你能深挖根因。遇到难题他希望你先停下想「最干净的解法是什么」...
2. sleep / wait / 等长任务跑完期间，用户等你的输出...
3. 跟你协作的用户是非技术身份，他要的是听得懂的汇报...
...
```

**Agent 想违反时实时拦截**（PreToolUse hook）：

```
$ Bash sleep 30
karma ⚠️: 'non-blocking-parallel' — sleep 期间用户等你输出体验是「卡了」
        改 run_in_background=True, 任务完成会通知到你
[permission deny]
```

**Agent 沉默式停下时反思干预**（Stop hook）：

```
[karma — 上一回应没看到下一步推进信号]
用户是全权委托型，他期待你完成一波后立刻接着推进...
（提醒 1/2）
```

---

## 为什么有效（原理）

karma 解决三个真实的 LLM 行为问题：

### 1. 长 context 注意力衰减（attention dilution）

当代 Claude 真衰减拐点在 70K-200K（不是早期模型的 8K），但**长 session 头部的 sticky 仍然会被新内容稀释**。karma 在每个 PostToolUse 累积 token 达阈值后注入「锚定刷新」— 提醒频率按模型自动适应（Opus 80K / Sonnet 60K / Haiku 30K），不按时钟也不按 turn。

### 2. compact 失忆

Claude Code 长 session 会自动 compact 压缩历史 → sticky 头部被压成模糊词。karma 用 **PreCompact 落盘 + SessionStart(compact) 重读** 两端夹击 — compact 触发前把 sticky 完整状态落盘到 `pre_compact_snapshot.md`，重起时 SessionStart hook 读盘重新强注入。

### 3. 合作默契语气（不是规则系统）

v0.4.42 起 karma 规则文本从「请始终遵守」改成「跟你协作的真人用户希望...」— Agent 看到提醒第一反应是「调整对齐」而非「防御 / 绕过」。心理学根据：威胁式语气激活 fight-or-flight，反思式语气激活 cooperation。

实测 in-context mimicry 副作用（如「真字狂魔」防御性堆叠前缀）从 30+ 次/response 降到 0。

---

## 性能 / 资源消耗

karma 设计原则：**纯工程零 LLM，性能可观察**。

| 指标 | 数据 | 说明 |
|---|---|---|
| **运行时依赖** | 1 个（PyYAML） | 无 LLM API key / 无网络调用 / 无 ML 框架 |
| **源码总量** | 5481 LOC | 全 Python，可读可改 |
| **测试覆盖** | 392 个测试全绿 | ruff + mypy + vulture + pytest 4 件套 |
| **hook 响应延迟** | 实测 60ms（user_prompt_submit） | Claude Code 协议要求 < 200ms |
| **Token 注入消耗** | 平均 ~400 token / turn 头部 + ~60 token / 60K-80K context 中段刷新 | 8 条 sticky 平均每条 ~50 token，1 turn 60K context 总注入占比 < 1% |
| **磁盘占用** | `~/.claude/karma/` 通常 < 10MB | sticky.yaml + violations.jsonl + session-state JSON |
| **支持模型** | 自适应（Opus / Sonnet / Haiku / 未知 fallback） | `model_threshold.py` 表驱动 |
| **支持客户端** | Claude Code ✓ / Codex CLI ✓ / Gemini CLI ✓ | 共用 `JsonHooksBackend` 抽象基类 |

---

## 24h dogfooding 实测干预效果

作者本机连续一年 dogfooding 跑 karma 自身开发。**v0.4.39 模型自适应阈值架构落地后**：

| 场景 | v0.4.32（8K 阈值） | v0.4.39（Opus 80K 阈值） | 改善 |
|---|---|---|---|
| 1 turn 累积 ~60K context | 中段提醒触发 7+ 次 | 触发 0 次 | **7x+ 频率下降** |
| Agent 防御性「真字狂魔」副作用 | 单 response 出现 30+ 次「真X」前缀 | 0 次 | 根因消除 |
| sticky 跨 compact 是否还记得 | compact 后 sticky 被压成模糊词 | PreCompact + SessionStart 两端夹击，跨 compact 完整保留 | 100% |
| 装机生效频率 | Claude Code ✓ / Codex CLI（v0.130 approval gate 须 `/hooks` 审批）✓ / Gemini CLI ✓ |

---

## 强大在哪

### ▸ 完全用户掌控

没有 LLM 蒸馏，没有「关于你的事实」推断 — **5-10 条 sticky 全是你自己写的**。karma 不抢记忆系统赛道，只把你已经反复说过的事「钉死」。

### ▸ 实时双层拦截

- **PreToolUse**（事前）：Agent 调 tool 前扫违反，关键词层 + 工程层 regex 检测，命中 deny
- **Stop**（事后）：扫 Agent response，违反写 `violations.jsonl`，下次 user prompt 头部加偏离标记
- **PostToolUse**（中段）：长 context 累积时自动「锚定刷新」

### ▸ 8 个内建工程层 check 函数

不是关键词匹配 — 是 AST / regex / state tracking 工程层检测：

| 检测项 | 含义 |
|---|---|
| `long_term_fundamental` | 拦 `git commit --no-verify` / `先打个补丁` 注释 / 长 hash if 分支硬编码 |
| `non_blocking_parallel` | 拦 `sleep N` / 长任务无 `run_in_background` |
| `loud_failure_with_evidence` | 完成代码任务但 session 内无测试通过证据 → 拦 |
| `no_testset_no_future_leakage` | 拦评测数据反喂训练 / 跨 split 复制 |
| `read_before_write` | Edit / Write 前未 Read 过该 file_path → 拦（路径规范化等价识别） |
| `bypass_karma_detection` | Bash 命令含 karma 内部状态字面 + 写操作 → 拦绕开检测 |
| `keep_pushing_no_stop` | Agent 沉默式停下时 Stop hook decision=block 让继续推进 |
| `chinese_plain_no_jargon` | 中文比例 < 40% / 英文 jargon 未配中文解释（默认装但工程层可单独撤） |

### ▸ 跨 session 数据分析工具

```bash
karma stats     # 每条 sticky 累积违反 + 本 session vs 历史对照
karma audit     # 按 sticky_id 聚合 trigger 词频 + 字面多样性 + 假阳嫌疑标记
karma doctor    # 检查环境 + hook 装机状态 + 当前生效 config
```

`karma stats` 输出示例：

```
sticky_id                             本 ses     历史     7d      最近 5 turn
keep-pushing-no-stop                      1     53     54              1
chinese-plain-no-jargon                   4     25     29              4
non-blocking-parallel                     1     11     12              1
long-term-fundamental                     1      8      9              1
```

---

## 自定义你自己的核心方向

### sticky.yaml 写法

`~/.claude/karma/sticky.yaml`（`karma init` 会复制默认模板）：

```yaml
- id: long-term-fundamental
  preference: |
    用户相信你能深挖根因。遇到难题他希望你先停下想「最干净的解法是什么」
    而不是「最快糊过去」。短期补丁 / 硬编码 / 跳验证 flag 都是「以后会还的债」—
    他愿意为长期质量等你多想几分钟。
  violation_keywords:
    - 我先打个补丁
    - 先用 workaround
    - 我先硬编码
  violation_checks:
    - long_term_fundamental    # 调用工程层 regex pattern 集
  # force_block_exempt: true   # 可选 — 关闭累积处罚

- id: non-blocking-parallel
  preference: |
    sleep / wait / 等长任务跑完期间，用户等你的输出。盯着进度条不是协作 — 是「卡了」。
    起完 background 任务立刻推进下一件能做的事 — 任务完成你会被通知到。
  violation_keywords:
    - 我先等测试
    - 我先等子 Agent
  violation_checks:
    - non_blocking_parallel
  force_block_exempt: true     # 「不阻塞」规则跟累积处罚语义冲突，豁免
```

**字段表**：

| 字段 | 必填 | 含义 |
|---|---|---|
| `id` | ✓ | kebab-case slug，唯一 |
| `preference` | ✓ | 一句或多行的方向描述。Claude 看到的就是这个 |
| `violation_keywords` | ✗ | 关键词数组（用「意图前缀 + 动作」格式区分讨论概念 vs 真行动声明，如「我先硬编码」而非「硬编码」） |
| `violation_checks` | ✗ | 工程层 check 函数名数组（8 个内建可选） |
| `force_block_exempt` | ✗ | bool。设 true 关闭累积处罚 — 给「应该继续推进」类规则用 |

**软上限 10 条，硬上限 12 条**（超过 karma 拒绝加载，防注意力被稀释）。

---

## 装机详情

### 推荐：让 AI 客户端帮你装

把这段话发给 Claude Code / Codex / Gemini CLI 任一家：

```
帮我装 karma（github.com/jhaizhou-ops/karma）— 让长任务中我的核心方向偏好
不被淹没的轻量 hook 系统。完成步骤：
1. git clone 到 ~/karma
2. 创建 .venv 装 pip install -e .
3. 跑 karma init 初始化默认 sticky.yaml
4. 跑 karma install-hooks 装到我当前用的客户端（Claude Code / Codex / Gemini CLI）
5. 跑 karma doctor 确认装机成功
```

### 手动装机

```bash
# 1. clone + 装 Python 包
git clone https://github.com/jhaizhou-ops/karma.git ~/karma
cd ~/karma
python -m venv .venv
.venv/bin/python -m pip install -e .

# 2. 初始化默认 sticky.yaml（按系统语言自动选 7 条完整 / 5 条精简）
.venv/bin/karma init

# 3. 装 hook 到 Claude Code（默认）
.venv/bin/karma install-hooks

# 4. 检查装机
.venv/bin/karma doctor
```

### 支持的 AI 编程客户端

| 客户端 | 装机命令 | 备注 |
|---|---|---|
| Claude Code | `karma install-hooks`（默认） | 立即生效 |
| Codex CLI | `karma install-hooks --backend codex` | **codex 0.130+ 须 TUI 内 `/hooks` 手动审批** karma 4 个 wrapper |
| Gemini CLI | `karma install-hooks --backend gemini-cli` | 立即生效 |

加新 backend 看 [karma/backends/HOWTO.md](./karma/backends/HOWTO.md) — 继承 `JsonHooksBackend` 基类只需填 6 个类属性 + 4 个 event 映射。

### 卸载

```bash
.venv/bin/karma uninstall-hooks   # 删 wrapper + 清 settings.json 里 karma entry
# 或恢复完整原 settings
cp ~/.claude/settings.json.before-karma ~/.claude/settings.json
```

---

## 8 个 hook 真生效功能

karma 装机后 Claude Code 跑这 8 个 hook：

| Hook | 真生效功能 |
|---|---|
| **UserPromptSubmit** | 头部注入 sticky baseline + 偏离标记，turn_count + 1，session-state 30 天自动清理 |
| **PreToolUse** | 关键词层 + 工程层 violation 检测，命中 deny |
| **PostToolUse** | session_state 跟踪（read / edit / bash），按 token 阈值自适应注入「锚定刷新」 |
| **Stop** | stderr ⚠️ + violations.jsonl 落盘 + 桌面通知 + keep-pushing 反思干预 |
| **SessionStart** | session 起手 sticky baseline 注入，compact 重起时读 snapshot 重新强注入 |
| **PreCompact** | 落盘 sticky snapshot 给 SessionStart(compact) 重读 |
| **SubagentStart** | 子 Agent 启动时注入 sticky baseline + 写子 Agent state.model |
| **SubagentStop** | 子 Agent 临时 state 自动销毁（不污染主 session） |

所有 hook 输出都协议层 schema 合规（v0.4.43 / v0.4.44 系统性根治早期 schema bug）。

---

## 配置

`~/.claude/karma/config.yaml` 调阈值不用改代码：

```yaml
recent_violation_turns: 5         # 偏离标记窗口（最近 N turn 内违反过标记）
stop_block_max_per_turn: 2        # Stop hook 单 turn 反思干预上限
force_block_threshold: 5          # 累积强制 block 阈值
escalate_window_turns: 3          # 累积告警窗口
escalate_threshold: 3             # 累积告警阈值（升级桌面通知严重度）
session_state_max_age_days: 30    # session-state 自动清理周期
# reinject_every_n_tokens: 60000  # 覆盖按模型自适应阈值
```

完整字段表 + 默认值看 [docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md#配置)。

---

## 诚实的工具边界

karma 是 **regex 字面匹配 + 计数** 的工程工具，不是 LLM 语义理解：

- **确实有假阳**：表格 cell 引用术语 / `python -c` 内字符串字面 / commit message 描述违反字眼等场景可能误拦。遇到时 `karma audit` 看「⚠️ 可能假阳」标记。
- **确实有假阴**：用户故意伪装（假数字「9999 测试通过」/ kebab-case 包裹 jargon）regex 分不清。karma 信任用户不蓄意作弊。
- **`karma audit` 修后 0 触发 ≠ fix 正确**：可能只是 pattern 过宽把真违反吃了。dogfooding 数据是嫌疑提示不是 truth。

把 karma 当成 **「git 跟 lint 之间的工具」** — 给信号，不替决策。

---

## karma 不做的事

为避免 [karma v1](https://github.com/jhaizhou-ops/karma-v1) 覆辙，karma 明确**不做**这些：

- ❌ **不自动蒸馏新规则** — 用户自己维护 5-10 条
- ❌ **不做 retrieval / cosine 召回** — 全 always-on，注意力优先级靠手工排序
- ❌ **不抢记忆系统赛道** — 「关于用户的事实」交给 Claude Code auto-memory
- ❌ **不引入 LLM** — 全工程化（regex + 计数 + state tracking）
- ❌ **不做奖惩 / RL 评分** — 行为提示不是 reward function
- ❌ **不阻止 compact** — compact 是 Claude Code 保护机制，karma 用 PreCompact 落盘 + SessionStart 重读跨过去

---

## FAQ

<details>
<summary><b>装完没反应怎么办？</b></summary>

跑 `karma doctor` 看：
- hook event 是否全 ✓（Claude Code 8 个 / Codex 4 个 / Gemini 4 个）
- sticky 是否加载成功
- session-state 是否产生新文件（提交 1 个 prompt 后看 `~/.claude/karma/session-state/`）

Codex CLI 0.130+ 须 TUI 内输 `/hooks` 手动审批 karma 4 个 wrapper。
</details>

<details>
<summary><b>太多假阳怎么办？</b></summary>

`karma audit` 看「⚠️ 可能假阳」标记的 trigger，给作者反馈（GitHub Issue）。临时关掉某条 sticky 可以 `karma sticky remove <id>` 或直接编辑 `~/.claude/karma/sticky.yaml` 删掉 `violation_keywords` / `violation_checks` 两字段保留 `preference`（preference 仍头部注入但不触发实时拦截）。
</details>

<details>
<summary><b>自定义场景规则集（写作 / 研究 / 产品 / 法律）？</b></summary>

`karma init` 默认装「软件开发」场景。其他场景写 `~/.claude/karma/sticky.yaml` 自定义 — 框架（hook 注入 / 实时拦截 / 违反检测）跨场景通用，但 8 个内建 violation_checks 偏开发场景。其他场景可能需要 preference 文本提醒 + 自定义 keyword（不依赖 check 函数）。
</details>

<details>
<summary><b>关 karma 紧急方案？</b></summary>

```bash
karma uninstall-hooks                                    # 拆 hook
cp ~/.claude/settings.json.before-karma ~/.claude/settings.json   # 恢复原 settings
```
</details>

<details>
<summary><b>跟 karma v1 关系？</b></summary>

[karma v1](https://github.com/jhaizhou-ops/karma-v1) 试图 LLM 自动蒸馏新规则 + retrieval 召回 — 验证后发现真痛点是「永驻」不是「召回」。v2 是认知重启，纯工程零 LLM。
</details>

---

## 文档导航

- [docs/PRD.md](./docs/PRD.md) — 产品需求 + 验证标准 + 场景化定位
- [docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md) — 技术架构 + hook 协议层细节 + 8 个 check 实现
- [CHANGELOG.md](./CHANGELOG.md) — 版本变更（v0.4.44 是当前最新）
- [docs/HANDOFF.md](./docs/HANDOFF.md) — 内部开发接力文档（每个 milestone + 已知 bug 清单）
- [docs/RULES_REDESIGN_PROPOSAL.md](./docs/RULES_REDESIGN_PROPOSAL.md) — v0.4.42 「合作默契」语气设计提案（已实施）
- [CLAUDE.md](./CLAUDE.md) — 给 Claude Code 协作的项目宪章

---

## 贡献

- 报 bug / 提建议：[GitHub Issues](https://github.com/jhaizhou-ops/karma/issues)
- 加新 AI 客户端 backend：[karma/backends/HOWTO.md](./karma/backends/HOWTO.md)
- 加新场景 sticky 模板（写作 / 研究 / 法律等）：PR 加到 `data/`

karma 当前**真实非作者用户使用期**起步（2026-05-14 起）。之前一年是作者自用 dogfooding，新用户首装踩坑会持续触发改进。验证标准是「Agent 在长任务中是否真减少方向漂移」。

---

## License

MIT
