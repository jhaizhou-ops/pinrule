# karma

[![CI](https://github.com/jhaizhou-ops/karma/actions/workflows/ci.yml/badge.svg)](https://github.com/jhaizhou-ops/karma/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-passing-brightgreen)](https://github.com/jhaizhou-ops/karma/actions)
[![Release](https://img.shields.io/badge/release-v0.4.44-blue)](https://github.com/jhaizhou-ops/karma/releases)

> **让 AI Agent 长任务中不再忘记你最在乎的几条原则。**
>
> Andrej Karpathy 60k stars 的 [CLAUDE.md](https://github.com/forrestchang/andrej-karpathy-skills) 告诉 AI **怎么写好代码**。karma 解决另一半 — **怎么让 AI 长任务中不忘你的偏好**。
>
> Claude Code / Codex CLI / Gemini CLI 通用。纯工程零 LLM，单依赖 PyYAML，hook 响应 < 100ms。装完立刻生效，违反实时拦截，跨 compact 不丢。

---

**目录**：[痛点](#你遇到的真问题) · [30 秒上手](#30-秒上手) · [原理](#为什么有效4-个机制) · [性能](#性能量化对照) · [自定义](#自定义你自己的核心方向) · [装机](#装机详情) · [8 个 hook 真生效功能](#8-个-hook-真生效功能) · [karma 不做的事](#试过但放弃的karma-不做的事) · [FAQ](#faq) · [文档导航](#文档导航)

---

## 你遇到的真问题

| 真痛点 | 翻车现场 | karma 怎么解 |
|---|---|---|
| **「我说过用长期方案不打补丁」— 30 turn 后 Agent 又开始打补丁** | 你 turn 1 说「用最干净的方案」/ Agent 答「明白」/ 50 turn 后说「先打个补丁应付」 | sticky.yaml 钉死你的核心偏好，每条 prompt 头部注入 |
| **「我说过不阻塞前端，测试跑着我们做别的」— Agent 又默认 sleep 等** | Agent 跑 `sleep 30` 期间不推进任何事，UI 卡 30 秒 | PreToolUse hook 实时拦 `sleep / wait / 长任务无 background` |
| **compact 后 Agent 把我的偏好压成模糊词忘了** | 80K context 触发 compact / SessionStart 后 Agent 把「不打补丁」压成「干净写代码」 | PreCompact 落盘 + SessionStart 重读两端夹击，跨 compact 不丢 |
| **长 context 累积 60K 后 Agent 注意力衰减偏离方向** | Opus 真衰减拐点在 70K-200K，60K 已经开始漂移 | PostToolUse 按模型自适应阈值（Opus 80K / Sonnet 60K / Haiku 30K）中段重新注入 |
| **Agent 看到提醒激发防御反应 / 找借口合理化** | 「⚠️ 上次违反！」红警示 → Agent 激发 fight-or-flight 防御反应，倾向找借口绕过或表达扭曲 | 「合作默契」语气替代「请始终遵守」规则系统，第一反应是「调整对齐」非「绕过」 |
| **Agent 完成一波就停下问下一步（我是全权委托型）** | 用户给方向后 Agent 完成第 1 件后说「下一步做什么？」用户已经累 | Stop hook `decision=block` 反思干预，让 Agent 立即接着推进 |

---

## 30 秒上手

```bash
git clone https://github.com/jhaizhou-ops/karma.git ~/karma
cd ~/karma && python -m venv .venv && .venv/bin/python -m pip install -e .
.venv/bin/karma init && .venv/bin/karma install-hooks
```

Claude Code 重启，每次提交 prompt 看到注入头部：

```
[karma — 你跟用户的长期默契]
跟你协作的是一位真人用户，他列出了几条长期最看重的方向。
这不是规则也不是审判 — 是他希望跟你建立的协作默契。

1. 用户相信你能深挖根因。遇到难题他希望你先停下想「最干净的解法是什么」...
2. sleep / wait / 等长任务跑完期间，用户等你的输出...
3. 跟你协作的用户是非技术身份，他要的是听得懂的汇报...
...
```

**Agent 违反时 PreToolUse 实时拦截**：
```
$ Bash sleep 30
karma ⚠️: 'non-blocking-parallel' — sleep 期间用户等你输出体验是「卡了」
        改 run_in_background=True, 任务完成会通知到你
[permission deny]
```

**Agent 沉默式停下时 Stop hook 反思干预**：
```
[karma — 上一回应没看到下一步推进信号]
用户是全权委托型，他期待你完成一波后立刻接着推进...
（提醒 1/2）
```

---

## 为什么有效（4 个机制）

karma 不是 lint，不是 RL，不是 retrieval。是基于 **Anthropic Claude Code hook 协议** + **LLM 注意力衰减真衰减拐点** 两个事实驱动的工程方案。

### 1. 长 context 注意力衰减

当代 Claude 真衰减拐点 **70K-200K**（不是早期模型 8K），karma `model_threshold.py` 按模型自适应（Opus 80K / Sonnet 60K / Haiku 30K）— 长 session 累积达阈值时 PostToolUse hook 中段重新注入「锚定刷新」。

**Test**: 你说「用长期方案」后 50 turn 还记得吗？没 karma 时答案是 No — 头部 sticky 被新内容稀释。

### 2. compact 失忆

Claude Code 长 session 自动 compact 压缩历史 → sticky 头部被压成模糊词。karma 用 **PreCompact 落盘 + SessionStart 重读** 两端夹击。

**Test**: compact 后 Agent 还按你的偏好行为吗？没 karma 时答案是 Maybe — 取决于压缩质量。

### 3. 合作默契语气（不是规则系统）

**Don't preach. Don't accuse. Invite.**

「请始终遵守」激活 fight-or-flight 防御反应 → Agent 找借口合理化绕过或表达扭曲。「跟你协作的真人用户希望...」激活 cooperation → Agent 第一反应是调整对齐。

**Test**: Agent 看到「⚠️ 上次违反！」会激发防御性反应吗？合作默契语气避免这副作用。

### 4. 协议层 schema 严格合规

karma 所有 hook 输出严格按 Claude Code 官方 hook 协议 schema — 8 个 hook event 各自只用协议支持的字段（PreToolUse / UserPromptSubmit / PostToolUse / SessionStart / SubagentStart 用 `hookSpecificOutput`；Stop / SubagentStop / PreCompact 仅用 `decision/reason`）。

**Test**: Claude Code UI 报 `Expected schema` 错吗？答案是 No。

---

## 性能（量化对照）

| 维度 | 数字 | 说明 |
|---|---|---|
| **运行时依赖** | 1 个（PyYAML） | 无 LLM API key / 无网络调用 / 无 ML 框架 |
| **源码总量** | 5481 LOC | 全 Python，可读可改 |
| **测试覆盖** | 完整 4 件套全绿 | lint / 类型检查 / 死代码扫 / 单元测试 |
| **hook 响应延迟** | < 100ms（user_prompt_submit 实测 ~60ms） | Claude Code 协议要求 < 200ms |
| **Token 注入消耗** | 平均 ~400 token / turn 头部 + ~60 token / 60K-80K context 中段刷新 | 1 turn 60K context 总注入占比 < 1% |
| **磁盘占用** | `~/.claude/karma/` < 10MB | sticky.yaml + violations.jsonl + session-state |
| **支持模型** | 自适应 | Opus 80K / Sonnet 60K / Haiku 30K / 老模型 8K / 未知 60K |
| **支持客户端** | 3 家通用 | Claude Code / Codex CLI / Gemini CLI（共用 `JsonHooksBackend` 抽象基类） |

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
    - 我先打个补丁          # 「意图前缀 + 动作」格式区分讨论概念 vs 真行动声明
    - 先用 workaround
    - 我先硬编码
  violation_checks:
    - long_term_fundamental    # 8 个内建工程层 check 任选

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

**关键设计点**（继承 Karpathy / Mnilax 经验）：
- **`violation_keywords` 用「意图前缀 + 动作」格式**（「我先硬编码」而非「硬编码」）— 区分讨论概念 vs 真行动声明，避免「不要硬编码」类自然语言讨论假阳
- **软上限 10 条 / 硬上限 12 条** — 跟 Mnilax 实测一致（超过 12 条 Claude 只做模式匹配规则存在不真读，遵循率从 76% 掉到 52%）
- **`force_block_exempt`** 给「应该继续推进」类规则用 — 否则累积处罚跟规则语义自我矛盾

**8 个内建工程层 check 函数**：

| 函数名 | 检测内容 |
|---|---|
| `long_term_fundamental` | git `--no-verify` / 长 hash if 分支 / TODO 注释 |
| `non_blocking_parallel` | `sleep N` / 长任务无 `run_in_background` |
| `loud_failure_with_evidence` | 完成代码任务但 session 内无测试通过证据 |
| `no_testset_no_future_leakage` | 评测数据反喂训练 / 跨 split 复制 |
| `read_before_write` | Edit / Write 前未 Read 过该 file_path |
| `bypass_karma_detection` | Bash 命令含 karma 内部状态字面 + 写操作 |
| `keep_pushing_no_stop` | Agent 沉默式停下时 decision=block 让继续推进 |
| `chinese_plain_no_jargon` | 中文比例 < 40% / 英文 jargon 未配中文解释 |

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
4. 跑 karma install-hooks 装到我当前用的客户端
5. 跑 karma doctor 确认装机成功
```

### 手动装机

```bash
git clone https://github.com/jhaizhou-ops/karma.git ~/karma
cd ~/karma
python -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/karma init                # 按系统语言自动选 7 条完整 / 5 条精简
.venv/bin/karma install-hooks       # 默认装 Claude Code
.venv/bin/karma doctor              # 检查装机
```

### 支持的 AI 编程客户端

| 客户端 | 装机命令 | 备注 |
|---|---|---|
| Claude Code | `karma install-hooks`（默认） | 立即生效 |
| Codex CLI | `karma install-hooks --backend codex` | **codex 0.130+ 须 TUI 内 `/hooks` 手动审批** karma 4 个 wrapper |
| Gemini CLI | `karma install-hooks --backend gemini-cli` | 立即生效 |

### 卸载

```bash
.venv/bin/karma uninstall-hooks                                # 拆 hook
cp ~/.claude/settings.json.before-karma ~/.claude/settings.json # 恢复原 settings
```

---

## 8 个 hook 真生效功能

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

所有 hook 输出严格按 Claude Code 官方协议 schema — 不会被 UI 报 `Expected schema` 错。

---

## 配置

`~/.claude/karma/config.yaml` 调阈值不用改代码：

```yaml
recent_violation_turns: 5         # 偏离标记窗口
stop_block_max_per_turn: 2        # Stop hook 单 turn 反思干预上限
force_block_threshold: 5          # 累积强制 block 阈值
escalate_window_turns: 3          # 累积告警窗口
escalate_threshold: 3             # 累积告警阈值
session_state_max_age_days: 30    # session-state 自动清理周期
# reinject_every_n_tokens: 60000  # 覆盖按模型自适应阈值
```

完整字段表 + 默认值看 [docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md#配置)。

---

## 试过但放弃的（karma 不做的事）

继承 [karma v1 失败教训](https://github.com/jhaizhou-ops/karma-v1) + 长期自用验证：

| 试过 | 放弃原因 |
|---|---|
| **LLM 自动蒸馏新规则** | karma v1 的真失败 — LLM 蒸馏噪声 / 错位，用户手工维护 5-10 条远胜自动召回 |
| **Retrieval / cosine 召回** | 真痛点是「永驻」不是「召回」— 5-10 条全 always-on，不需要选 |
| **超过 12 条 sticky** | Mnilax 实测 18 条时 Claude 只做模式匹配「规则存在」不真读，遵循率从 76% 掉到 52% |
| **抢记忆系统赛道** | 「关于用户的事实 / 偏好」交给 Claude Code auto-memory，karma 只钉死你已经反复说过的事 |
| **引入 LLM 依赖** | 全工程化（regex + 计数 + state tracking），无 API key / 无网络 / 无 ML 框架 |
| **奖惩 / RL 评分** | 行为提示不是 reward function — karma v1 验证后明确放弃 |
| **阻止 compact** | compact 是 Claude Code 保护机制，karma 用 PreCompact 落盘 + SessionStart 重读跨过去 |
| **「请始终遵守 / 立即按 fix / 不要再犯」类警示词** | 激活 Agent fight-or-flight 防御反应 → 找借口合理化绕过或表达扭曲。换合作默契语气后第一反应是「调整对齐」 |
| **精确数字阈值在 suggested_fix 文本** | Agent 看到「34% < 40%」会优化 metric（凑中文字数）不优化用户体验。改成「让用户读完不用查词」目标描述 |

---

## 诚实的工具边界

karma 是 **regex 字面匹配 + 计数** 的工程工具，不是 LLM 语义理解：

- **确实有假阳**：表格 cell 引用术语 / `python -c` 内字符串字面 / commit message 描述违反字眼等场景可能误拦。遇到时 `karma audit` 看「⚠️ 可能假阳」标记。
- **确实有假阴**：用户故意伪装（假数字「9999 测试通过」/ kebab-case 包裹 jargon）regex 分不清。karma 信任用户不蓄意作弊。
- **`karma audit` 修后 0 触发 ≠ fix 正确**：可能只是 pattern 过宽把真违反吃了。历史 audit 数据是嫌疑提示不是 truth。

把 karma 当成 **「git 跟 lint 之间的工具」** — 给信号，不替决策。

---

## FAQ

<details>
<summary><b>装完没反应怎么办？</b></summary>

跑 `karma doctor` 看：
- hook event 是否全 ✓（Claude Code 8 / Codex 4 / Gemini 4）
- sticky 是否加载成功
- session-state 是否产生新文件

Codex CLI 0.130+ 须 TUI 内输 `/hooks` 手动审批 karma 4 个 wrapper。
</details>

<details>
<summary><b>太多假阳怎么办？</b></summary>

`karma audit` 看「⚠️ 可能假阳」标记 trigger，给作者反馈（GitHub Issue）。临时关掉某条 sticky 可以 `karma sticky remove <id>` 或编辑 `~/.claude/karma/sticky.yaml` 删 `violation_keywords` / `violation_checks` 字段保留 `preference`。
</details>

<details>
<summary><b>跟 Andrej Karpathy 的 CLAUDE.md 重叠吗？</b></summary>

**完全互补，不重叠**：
- Karpathy 12 条（Mnilax 补 8 条 = [完整 12 条](https://github.com/forrestchang/andrej-karpathy-skills)）是**通用编码原则**（跨用户跨项目都适用 — 「先想后写」「简单至上」「外科手术式修改」等）
- karma sticky 是**用户个性化偏好**（每个用户不同 — 「我用户喜欢中文不要 jargon」「我希望 Agent 全权委托不停下问」等）

**推荐用法**：CLAUDE.md 装 Karpathy 12 条（项目共享） + karma 装你个性化 sticky（用户级 ~/.claude/karma/sticky.yaml）。两者跑同一个 Claude Code 不冲突。
</details>

<details>
<summary><b>自定义场景规则集（写作 / 研究 / 法律）？</b></summary>

`karma init` 默认装「软件开发」场景。其他场景写 `~/.claude/karma/sticky.yaml` 自定义 — 框架（hook 注入 / 实时拦截）跨场景通用，但 8 个内建 violation_checks 偏开发场景。其他场景可能需要 preference 文本提醒 + 自定义 keyword（不依赖 check 函数）。
</details>

<details>
<summary><b>跟 karma v1 关系？</b></summary>

[karma v1](https://github.com/jhaizhou-ops/karma-v1) 试图 LLM 自动蒸馏新规则 + retrieval 召回 — 验证后发现真痛点是「永驻」不是「召回」。v2 是认知重启，纯工程零 LLM。
</details>

---

## 心智模型

借 [Mnilax 文章](https://x.com/Mnilax/status/2053116311132155938) 关于 CLAUDE.md 设计的结论：

> **CLAUDE.md 不是许愿清单。是一个闭合了你观察到过的特定失效模式的行为合约。每条规则都应该能回答一个问题：这条规则预防的是什么错误？**

karma sticky 同理：

> **6 条针对你真踩过的坑的 sticky，远胜 12 条里有 6 条你永远用不上的。**

karma `data/sticky.dev.example.yaml` 的 7 条是作者自用累积的真痛点 — **但不是给你照搬的**。读完 `karma sticky list` 后保留映射到你真实翻车现场的，其余删掉换成你自己的真痛点。

---

## 文档导航

- [docs/PRD.md](./docs/PRD.md) — 产品需求 + 验证标准 + 场景化定位
- [docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md) — 技术架构 + hook 协议层细节 + 8 个 check 实现
- [CHANGELOG.md](./CHANGELOG.md) — 版本变更历史
- [docs/HANDOFF.md](./docs/HANDOFF.md) — 内部开发接力文档
- [docs/RULES_REDESIGN_PROPOSAL.md](./docs/RULES_REDESIGN_PROPOSAL.md) — 「合作默契」语气设计提案（核心设计哲学）
- [CLAUDE.md](./CLAUDE.md) — 给 Claude Code 协作的项目宪章

## 相关项目

- [Andrej Karpathy 的 CLAUDE.md 编码原则模板](https://github.com/forrestchang/andrej-karpathy-skills)（60k stars / 通用编码原则 / **跟 karma 互补不冲突**）
- [karma v1 归档](https://github.com/jhaizhou-ops/karma-v1)（v1 探索过程 + 失败反思）

## 贡献

- 报 bug / 提建议：[GitHub Issues](https://github.com/jhaizhou-ops/karma/issues)
- 加新 AI 客户端 backend：[karma/backends/HOWTO.md](./karma/backends/HOWTO.md)
- 加新场景 sticky 模板：PR 加到 `data/`

karma 当前**真实非作者用户使用期**起步（2026-05-14 起）。新用户首装踩坑会持续触发改进。

## License

MIT
