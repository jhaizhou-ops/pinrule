# karma

**[🇬🇧 English](./README.md) · [🇨🇳 中文（当前）](./README.zh.md)**

[![CI](https://github.com/jhaizhou-ops/karma/actions/workflows/ci.yml/badge.svg)](https://github.com/jhaizhou-ops/karma/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-passing-brightgreen)](https://github.com/jhaizhou-ops/karma/actions)
[![Latest Release](https://img.shields.io/github/v/release/jhaizhou-ops/karma?label=release)](https://github.com/jhaizhou-ops/karma/releases)
[![Last Commit](https://img.shields.io/github/last-commit/jhaizhou-ops/karma)](https://github.com/jhaizhou-ops/karma/commits/main)

> ⚠️ **v0.6.0 破坏性变更 (2026-05-15)**：`karma.sticky` 模块、`.sticky_id` 属性、`karma sticky` CLI 子命令删除（废弃周期完成）。迁移机械化 — 符号 `s/sticky/rule/`，CLI 换 `karma rule`。详细 cookbook 见 [CHANGELOG v0.6.0](./CHANGELOG.zh.md)。用户内部数据（`sticky.yaml` / 历史 `violations.jsonl`）仍自动迁移、保持可读。
>
> **Andrej Karpathy 60k stars 的 [CLAUDE.md](https://github.com/forrestchang/andrej-karpathy-skills) 告诉 AI 怎么写好代码。karma 解决另一半 — 怎么让 AI 在长任务中绝不违反你的规则，并且最重要的是如果发生了违反如何在你恼火前已经自行修正。**
>
> **同一闭环的两面**：
>
> 🛡️ **钉住规则 → Agent 遵守。** 5-10 条核心方向注入每个 prompt 头部；real-time hook 检测；跨 compact + 跨 locale + 跨 backend 都稳。实测违规率长程任务中降为 **≈ 0%**。
>
> ✨ **大白话告诉 karma → Agent 替你写规则。** 输 `/karma <自然语言>` — Claude Code / Codex / Gemini CLI 任一启动 karma skill 自动 refine 成 karma 验证过的「协作默契」语气、预览注入效果、跟你确认、写入 rules.yaml。`karma init` 时自动装到三家 backend。
>
> Claude Code / Codex CLI / Gemini CLI 通用。纯工程零 LLM 零依赖，违规监控响应速度 < 60ms。

---

<!-- DEMO PLACEHOLDER — 跑 `bash scripts/record-demo.sh` 后替换 URL：
[![asciicast](https://asciinema.org/a/XXXXXX.svg)](https://asciinema.org/a/XXXXXX)
-->

**目录**：[痛点](#你遇到的实际问题) · [10 秒上手](#0-依赖纯工程10-秒上手) · [`/karma` 自然语言录入规则](#karma-自然语言--agent-替你写规则) · [使用效果](#使用效果) · [原理](#为什么有效) · [性能](#性能量化对照) · [8 个 hook 全面监管](#8-个-hook-位置全面监管) · [自定义规则](#自定义你自己的核心方向) · [karma 不做的事](#试过但放弃的karma-不做的事) · [FAQ](#faq) · [文档导航](#文档导航)

---

## 你遇到的实际问题

| 实际痛点 | 翻车现场 | karma 怎么解 |
|---|---|---|
| **「我说过用长期方案不打补丁」— 30 turn 后 Agent 又开始打补丁** | turn 1 你说「用最干净的方案」，Agent 答「明白」，50 turn 后说「先打个补丁应付」— 你的偏好被新内容稀释 | 5-10 条核心方向钉死在每条 prompt 头部最显眼位置，Agent 看不到都不行 |
| **「我说过不阻塞前端，测试跑着我们做别的」— Agent 又默认 sleep 等** | Agent 跑 `sleep 30`，UI 卡 30 秒，你眼睁睁看进度条 — Agent 完全没意识到这是「卡了用户」 | tool 调用前实时拦截 sleep / wait / 长任务无 background，命中直接 deny |
| **compact 后 Agent 把我的偏好压成模糊词忘了** | 80K context 触发 compact 后，Agent 把「不打补丁」压成「干净写代码」，规则失真 | compact 前自动落盘完整规则状态，compact 后重起时自动读回来强注入 |
| **长 context 累积后 Agent 注意力衰减偏离方向** | 1 turn 累积 60K-80K 后，头部规则被新内容稀释 — Agent 不是不知道，是注意力衰减了 | 按当前模型自适应阈值（不同模型衰减拐点不同），累积达阈值自动中段重新注入 |
| **Agent 看到提醒激发防御反应 / 找借口合理化** | 大模型为迎合用户，在面对违规提醒和纠错时第一反应是防御性自证或走最短路径打补丁 — 不是真心地改 | 将「规则」转译成「合作默契」语气，经长期真实环境验证，大模型对「合作默契」语气第一反应已经调整为「对齐与遵守」非「绕过」 |
| **Agent 完成一个小功能点就停下问下一步（作者是全权委托型）** | 用户给明确方向后 Agent 完成第 1 件后说「下一步做什么？」然后静默停下 — 用户忙完手头工作回头一看 Agent 已经停在那里半小时 | Stop hook 判定 Agent 静默停止以后注入启发性反思提示语，最多连续两次启发鼓励 Agent 继续执行，直到方向推进真正饱和 |
| **「想加一条规则但 yaml 门槛太高 / 现有措辞 Agent 不响应」** | 你知道想要什么行为但写规则本身是个体力活 — `violation_keywords` 格式错触发假阳，语气错激发 Agent 防御反应 | 在 Claude Code / Codex / Gemini CLI 任一输 `/karma <自然语言>` — karma skill 自动 refine 语气、格式化 keyword、检测跟现有规则重叠、预览注入效果、跟你确认、写入 — 30 秒端到端 |

---

## 使用效果

karma 装完 AI 客户端重启后，你会看到这几种典型场景下的自动干预：

### 1. 每次对话都自动注入规则全文 + 过往违规重点提示

每条 user prompt 提交后，AI 客户端把你的 5-10 条核心方向 + 上一回应偏离过的规则提醒**自动加到对话最顶部**，Agent 第一眼看见：

```
[karma — 你跟用户的长期默契]
跟你协作的是一位真人用户，他列出了几条长期最看重的方向。
这不是规则也不是审判 — 是他希望跟你建立的协作默契。

1. 用户相信你能深挖根因。遇到难题他希望你先停下想「最干净的解法是什么」
   〔上一回应这条有偏离，本 turn 看看能否更对齐〕
2. sleep / wait / 等长任务跑完期间，用户等你的输出...
3. 跟你协作的用户是非技术身份，他要的是听得懂的汇报...
...
```

### 2. 长 context 累积时自动中段提醒（防注意力漂移）

当代 LLM 在长 context 中注意力会衰减 — 头部规则被新内容稀释。karma 在每个 tool 调用后跟踪累积量，达到当前模型的衰减阈值（不同模型不同）后自动在中段重新注入精简提醒，让 Agent 在「即将偏离」的 context 长度点位再次锚定：

```
[karma — 长 context 后回想一下跟用户的默契]
context 已累积一段，提醒一下用户长期看重的几条方向
（不需要回应这条，只是让你在脑中回顾免得后续偏离）：
  ▸ long-term-fundamental: 用户相信你能深挖根因...
  ▸ non-blocking-parallel: sleep / wait / 等长任务跑完期间，用户等你的输出...
  ▸ chinese-plain-no-jargon: 跟你协作的用户是非技术身份...
```

### 3. 工具调用前实时违规判断 + 针对性提醒

Agent 在调 Bash / Edit / Write 等工具**之前**，karma 扫命令内容 + 关键词，命中违规规则直接拒绝执行，附改进建议：

```
$ Bash sleep 30
karma ⚠️: 'non-blocking-parallel' 违反 — sleep 期间用户等你输出体验是「卡了」
        改 run_in_background=True 启动任务，然后立刻推进下一件能做的事，
        任务完成你会被通知到。
[permission deny]
```

### 4. 子 Agent 监管也全面覆盖

主 Agent 起子 Agent 跑独立任务（Task tool）时，karma 自动给子 Agent 也注入完整规则集 + 维护独立监控状态。子 Agent 跑任务过程跟主 Agent 同等监管力度，结束后状态自动销毁不污染主 session。

### 5. 上下文压缩前后的自动注入（compact 失忆防护）

AI 客户端长 session 自动触发 compact 压缩历史时，karma 在压缩前把完整规则状态落盘到本地文件，压缩重起后立即读回来重新强注入 — 跨 compact 规则不丢失。

### 6. 静默停止时的启发性注入

Agent 完成一波后想停下问「下一步做什么」时，karma 检测到这种静默停止行为后注入启发性提示，鼓励 Agent 继续推进：

```
[karma — 上一回应没看到下一步推进信号]
用户是全权委托型，他期待你完成一波后立刻接着推进。
如果有方向需要他判断就明确问出来；
如果是任务任务到饱和合理停下，明说卡在哪一步让他知道，不要默默等。
（提醒 1/2）
```

最多连续两次启发提示 — 任务到饱和合理停下时 Agent 明说卡在哪，karma 不强推。

---

## `/karma <自然语言>` — Agent 替你写规则

这是 karma 的另一面 — **伙伴**面，不是**监督**面。

```
你（在 Claude Code 里）：/karma 我说「完成」的时候希望附上测试通过证据
                       不要接受模糊的「应该可以」声明

Agent（karma skill 自动走 7 步）：
  ① 识别意图 — 检测 anchor-vs-scope 歧义
  ② 检查现有规则 — 语义重叠决策（修改 vs 新加）
  ③ 内联起草 yaml — 协作默契语气、locale 感知
  ④ karma rule preview — schema + REGISTRY 校验
  ⑤ 跟你确认 — 措辞 / keyword / engine-check 调整
  ⑥ karma rule add — 原子写入 rules.yaml
  ⑦ 反馈 — 当前数量、生效时机、冗余建议

→ 30 秒端到端，下个 UserPromptSubmit 起规则生效
```

### skill 替你做的事

| 写规则的难点 | skill 怎么处理 |
|---|---|
| **语气 — 「你必须 X」对 LLM 反向激发防御** | 重写成 karma「协作默契」语气。长期实测 LLM 对此回应是「我来对齐」不是「我来争辩」 |
| **格式 — 裸 keyword 触发假阳** | 转换成「意图前缀 + 动作」格式（如 `"我先打个补丁"` 不是 `"补丁"`），讨论 vs 行动可区分 |
| **重叠 — 不小心加重复规则浪费 slot** | 4 行 overlap 决策表（完全重复 / superset / keyword 交集 / 无重叠）；建议 modify 现有不是膨胀到 11 条 |
| **作用域歧义 — 「在 X 场景下做 Y」往往是 anchor 不是 scope** | 主动问出来「确认下：所有协作时还是只 X 时？」而不是默默猜 |
| **locale — 给中文用户写英文 preference** | 检测用户聊天语言，中文用户写中文 preference，英文用户写英文。`violation_checks` 函数名保持英文（稳定标识符） |
| **修改 vs 新加 — 没单独 `rule replace` 命令** | 知道 `remove + add` recipe 原子组合；保留 `id` 让违反历史连续 |

### 三家 backend，一个命令

| Backend | 路径（自动装机） | 客户端内触发方式 |
|---|---|---|
| Claude Code | `~/.claude/skills/karma/SKILL.md` | `/karma <自然语言>` |
| Codex CLI | `~/.agents/skills/karma/SKILL.md`（注：`~/.agents/` 跟 Anthropic 共享） | `/skills` menu / `$karma <描述>` inline / auto-trigger |
| Gemini CLI | `~/.gemini/skills/karma/SKILL.md`（auto）+ `~/.gemini/commands/karma.toml`（显式） | `/karma <自然语言>`（显式）或 auto-trigger（skill 路径） |

仓库内一份 Markdown source of truth 在 [`skills/karma/SKILL.md`](./skills/karma/SKILL.md)；`karma install-skill` 命令自动处理 Markdown → TOML 转换给 Gemini commands 路径（`$ARGUMENTS` ↔ `{{args}}` 语法翻译也包含）。

### karma 升级后更新 skill

```bash
karma install-skill --force          # 强制覆盖所有 backend 的 skill 为当前版本
karma install-skill --backend codex  # 只更新一家 backend
```

不带 `--force` 时，新版本会写到 `.new` 兄弟文件让你先 `diff` 本地改动跟 upstream 对比再决定。

`karma doctor` 报每个 backend 的 skill 装机状态让你一眼看哪个最新哪个旧。

---

## 为什么有效

karma 不是 lint，不是评分系统，不是搜索召回。它解决的是 3 个真实但被忽视的 LLM 协作问题：

### 1. 长 context 注意力衰减是真实存在的

当代大模型的注意力衰减不像早期模型那么早 — 但仍然有衰减拐点。规则放在对话最顶部，几十次对话后会被新内容稀释。karma 按当前模型自适应阈值，在恰好衰减开始的 context 长度点位自动中段补一次提醒。

### 2. 模型每次对话开始都「重新失忆」

每个 AI 客户端的对话本质是「把所有上下文重新发给模型」— 模型不持续记住任何东西。所以你说过的偏好需要每次重新送进去。karma 自动做这件事，不用你重复说。

### 3. 「合作默契」语气比「规则系统」激活的反应不一样

大模型看到「请始终遵守 X」「⚠️ 上次违反」类警示词时，第一反应是防御性自证或找借口绕过 — 因为这激活的是「我做错事被骂」的心理。

karma 用「跟你协作的真人用户希望...」类合作默契语气替代规则系统语气 — 大模型看到时第一反应是「调整对齐让协作更顺」而不是「找借口绕过」。这是 karma 长期真实环境验证的核心发现，也是违规率能降到 ≈ 0% 的关键。

### 4. 监管覆盖所有 hook 位置，不漏死角

karma 装机后在 AI 客户端的 8 个 hook 位置都有监管（详见下一章）— 不只是「对话开始时注入一次」这么简单。每次 tool 调用前后 / 子 Agent 启停 / 上下文压缩前后 / Agent 静默停止时 — 都有针对性的注入或拦截，覆盖所有可能漂移的时间点。

---

## 性能（量化对照）

| 维度 | 数字 | 说明 |
|---|---|---|
| **运行时依赖** | **0 依赖** | 仅用 Python 生态标准 YAML 解析（PyYAML 是 15+ 年成熟基础组件），无 LLM API key / 无网络调用 / 无 ML 框架 |
| **源码总量** | 5481 行 | 全 Python，可读可改 |
| **测试覆盖** | 完整 4 件套全绿 + 5610 行测试用例通过 + 500+ 小时真实开发调优 | lint / 类型检查 / 死代码扫 / 单元测试 |
| **违规监控响应延迟** | **< 60ms**（实测 user_prompt_submit hook ~49ms） | AI 客户端协议要求 < 200ms |
| **Token 注入消耗** | 平均 ~400 token / turn 头部 + ~60 token / 中段刷新 | 1 turn 60K context 总注入占比 < 1% |
| **磁盘占用** | < 10MB | 配置 + 历史违规日志 + session 状态 |
| **支持模型** | 自适应阈值 | 各家主流模型按真实衰减拐点自动适配 |
| **支持客户端** | 3 家通用 | Claude Code / Codex CLI / Gemini CLI |

---

## 8 个 hook 位置全面监管

| Hook 位置 | 生效功能与场景 | 解决的痛点 |
|---|---|---|
| **每次用户提问时**（UserPromptSubmit）| 头部注入完整规则 + 偏离标记 | Agent 长 session 后忘记你说过的偏好 |
| **每次工具调用前**（PreToolUse）| 关键词 + 工程层双层检测，命中规则直接拒绝 | Agent 想跑 sleep / 想 commit --no-verify / 想绕过规则 |
| **每次工具调用后**（PostToolUse）| 跟踪文件 read / edit / bash 状态 + 累积达阈值自动中段刷新规则 | 长 context 累积后注意力衰减，Agent 偏离原方向 |
| **Agent 停止生成时**（Stop）| 终端 stderr ⚠️ 提醒 + 桌面通知 + 静默停止启发性反思干预 | Agent 完成一波就停下问下一步，用户被反复打扰 |
| **每次 session 起手**（SessionStart）| session 起手注入规则 baseline，compact 重起时读 snapshot 强注入 | 跨 session / 跨 compact 规则不丢失 |
| **AI 客户端压缩历史前**（PreCompact）| 落盘完整规则状态 snapshot 给 SessionStart 重读 | compact 后 Agent 把规则压成模糊词忘了 |
| **子 Agent 启动时**（SubagentStart）| 子 Agent 自动继承完整规则集 + 写独立监控状态 | 子 Agent 跑独立任务时漏出监管覆盖 |
| **子 Agent 结束时**（SubagentStop）| 子 Agent 临时状态自动销毁，不污染主 session | 多次起子 Agent 后状态累积，主 session 数据混乱 |

所有 hook 输出严格按 AI 客户端官方协议 schema — 不会被 UI 报错。

---

## 自定义你自己的核心方向

> 👉 **大多数用户用 `/karma <自然语言>`** ([见上方独立 section](#karma-自然语言--agent-替你写规则)) — skill 会处理语气 / 重叠 / locale / schema 校验。本 section 给**进阶用户**用：直接 yaml 控制，或者在没装 skill 的环境跑 karma。

### 手工编辑 `rules.yaml`

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

**关键设计点**：
- **`violation_keywords` 用「意图前缀 + 动作」格式**（「我先硬编码」而非「硬编码」）— 区分讨论概念 vs 真行动声明，避免「不要硬编码」类自然语言讨论被误判
- **软上限 10 条 / 硬上限 12 条** — 超过 12 条 Claude 倾向只做模式匹配「规则存在」不真读，遵循率反而下降
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
| `keep_pushing_no_stop` | Agent 沉默式停下时让继续推进 |
| `chinese_plain_no_jargon` | 中文比例 < 40% / 英文 jargon 未配中文解释 |

---

## 0 依赖纯工程，10 秒上手

```bash
git clone https://github.com/jhaizhou-ops/karma.git ~/karma
cd ~/karma && python -m venv .venv && .venv/bin/python -m pip install -e .
.venv/bin/karma init && .venv/bin/karma install-hooks
```

> Claude Code / Codex CLI / Gemini CLI 重启后立即生效。

### 让 AI 客户端帮你装（推荐）

把这段话发给 Claude Code / Codex / Gemini CLI 任一家：

```
帮我装 karma（github.com/jhaizhou-ops/karma）— 让长任务中我的核心方向偏好
不被淹没的轻量 hook 系统。完成步骤：
1. git clone 到 ~/karma
2. 创建 .venv 装 pip install -e .
3. 跑 karma init 初始化默认规则模板
4. 跑 karma install-hooks 装到我当前用的客户端
5. 跑 karma doctor 确认装机成功
```

### 装机后验证

```bash
.venv/bin/karma doctor              # 检查环境 + hook 装机状态
.venv/bin/karma --version           # 看当前版本
```

### 各 AI 客户端装机命令

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

## 配置

`~/.claude/karma/config.yaml` 调阈值不用改代码：

```yaml
recent_violation_turns: 5         # 偏离标记窗口
stop_block_max_per_turn: 2        # Stop hook 单 turn 反思干预上限
force_block_threshold: 5          # 累积强制 block 阈值
escalate_window_turns: 3          # 累积告警窗口
escalate_threshold: 3             # 累积告警阈值
session_state_max_age_days: 30    # session 状态自动清理周期
# reinject_every_n_tokens: 60000  # 覆盖按模型自适应阈值
```

完整字段表 + 默认值看 [docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md#配置)。

---

## 试过但放弃的（karma 不做的事）

作者开发过程长达 2 个月，经过 3 次大的重构和长期自用验证：

| 试过 | 放弃原因（用户视角） |
|---|---|
| **LLM 自动蒸馏新规则** | 不仅是成本，在响应速度上也会大幅下降用户体验，自动蒸馏出的规则还经常出现噪声 / 错位（用户原话听过一次不代表是核心方向）— 因此最终选择「用户手工维护 5-10 条」的方式，由用户自己掌控规则集 |
| **Retrieval / cosine 召回** | 实际痛点是「永驻」不是「召回」— 5-10 条规则全 always-on 不需要选，检索反而引入额外延迟跟匹配错误 |
| **超过 12 条规则** | 规则太多反而效果下降 — 大模型倾向只做模式匹配「规则存在」不真读，遵循率反而从 76% 掉到 52%。控制规则数量在 10 条以内是经验最优 |
| **抢记忆系统赛道** | 「关于用户的事实 / 偏好」交给 AI 客户端自带的记忆系统更合适，karma 只做「钉死你已经反复说过的事」这一件事 |
| **引入 LLM 依赖** | 不仅是成本，在响应速度上也会大幅下降用户体验 — 因此最终选择纯工程 0 依赖 < 60ms 极速响应方案 |
| **奖惩 / RL 评分系统** | 行为提示不是 reward function — 给规则打分会让大模型把注意力放在「分数」而非「行为」上，反而劣化表现 |
| **阻止 compact** | compact 是 AI 客户端的保护机制 karma 不该干扰 — 用 PreCompact 落盘 + SessionStart 重读跨过去，而不是强行禁止 |
| **「请始终遵守 / 立即按 fix / 不要再犯」类警示词** | 大模型看到警示词的第一反应是防御性自证或找借口绕过 — 不是真心地改。换合作默契语气后大模型第一反应是「调整对齐」非「绕过」，违规率显著下降 |
| **精确数字阈值在改进建议文本** | 大模型看到「34% < 40%」会优化数字（凑字数）而不优化背后的用户体验 — 改成「让用户读完不用查词」类目标描述效果更好 |

---

## 诚实的工具边界

karma 是 **regex 字面匹配 + 计数** 的工程工具，不是 LLM 语义理解：

- **确实有假阳**（误拦合法操作）：表格 cell 引用术语 / `python -c` 内字符串字面 / commit message 描述违反字眼等场景可能误拦。遇到时跑 `karma audit` 看「⚠️ 可能假阳」标记反馈给作者
- **确实有假阴**（漏拦实际违反）：用户故意伪装的违规 regex 分不清。karma 信任用户不蓄意作弊
- **`karma audit` 修后 0 触发 ≠ fix 正确**：可能只是 pattern 过宽把实际违反吃了。历史 audit 数据是嫌疑提示不是绝对真实

把 karma 当成 **「git 跟 lint 之间的工具」** — 给信号，不替决策。

---

## FAQ

<details>
<summary><b>装完没反应怎么办？</b></summary>

跑 `karma doctor` 看：
- hook event 是否全 ✓（Claude Code 8 / Codex 4 / Gemini 4）
- 规则是否加载成功
- session 状态目录是否产生新文件

Codex CLI 0.130+ 须 TUI 内输 `/hooks` 手动审批 karma 4 个 wrapper。
</details>

<details>
<summary><b>太多假阳怎么办？</b></summary>

`karma audit` 看「⚠️ 可能假阳」标记 trigger，给作者反馈（GitHub Issue）。临时关掉某条规则可以 `karma sticky remove <id>` 或编辑 `~/.claude/karma/sticky.yaml` 删 `violation_keywords` / `violation_checks` 字段保留 `preference`。
</details>

<details>
<summary><b>跟 Andrej Karpathy 的 CLAUDE.md 重叠吗？</b></summary>

**完全互补，不重叠**：
- Karpathy 12 条（[完整版](https://github.com/forrestchang/andrej-karpathy-skills)）是**通用编码原则**（跨用户跨项目都适用 — 「先想后写」「简单至上」「外科手术式修改」等）
- karma 的规则是**用户个性化偏好**（每个用户不同 — 「我喜欢中文不要 jargon」「我希望 Agent 全权委托不停下问」等）

**推荐用法**：CLAUDE.md 装 Karpathy 12 条（项目共享） + karma 装你个性化规则（用户级）。两者跑同一个 AI 客户端不冲突。
</details>

<details>
<summary><b>自定义场景规则集（写作 / 研究 / 法律）？</b></summary>

`karma init` 默认装「软件开发」场景。其他场景写 `~/.claude/karma/sticky.yaml` 自定义 — 框架（hook 注入 / 实时拦截）跨场景通用，但 8 个内建工程层 check 偏开发场景。其他场景可能需要 preference 文本提醒 + 自定义 keyword（不依赖 check 函数）。
</details>

---

## 心智模型

> **规则文件不是许愿清单。是一个闭合了你观察到过的特定失效模式的行为合约。每条规则都应该能回答一个问题：这条规则预防的是什么错误？**

karma 同理：

> **6 条针对你真踩过的坑的规则，远胜 12 条里有 6 条你永远用不上的。**

karma `data/sticky.dev.example.yaml` 的 7 条默认规则是作者自用累积的实际痛点 — **但不是给你照搬的**。装完后跑 `karma sticky list` 看默认有哪些，保留映射到你真实翻车现场的，其余删掉换成你自己的实际痛点。

---

## 文档导航

- [docs/PRD.md](./docs/PRD.md) — 产品需求 + 验证标准 + 场景化定位
- [docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md) — 技术架构 + hook 协议层细节 + 8 个 check 实现
- [CHANGELOG.md](./CHANGELOG.md) — 版本变更历史
- [docs/HANDOFF.md](./docs/HANDOFF.md) — 内部开发接力文档
- [docs/RULES_REDESIGN_PROPOSAL.md](./docs/RULES_REDESIGN_PROPOSAL.md) — 「合作默契」语气设计提案（核心设计哲学）
- [CLAUDE.md](./CLAUDE.md) — 给 Claude Code 协作的项目宪章

## 相关项目与致敬

- [Andrej Karpathy 的 CLAUDE.md 编码原则模板](https://github.com/forrestchang/andrej-karpathy-skills)（60k stars / 通用编码原则）— karma 互补不冲突。Karpathy 教 AI 怎么写好代码，karma 帮 AI 在长任务中绝不偏离你的偏好
- [Mnilax 在 30 个代码库 6 周实测 CLAUDE.md 规则数量上限](https://x.com/Mnilax/status/2053116311132155938) — karma「软上限 10 条 / 硬上限 12 条」设计直接借鉴这篇实测结论

## 贡献

- 报 bug / 提建议：[GitHub Issues](https://github.com/jhaizhou-ops/karma/issues)
- 加新 AI 客户端 backend：[karma/backends/HOWTO.md](./karma/backends/HOWTO.md)
- 加新场景规则模板（写作 / 研究 / 法律等）：PR 加到 `data/`

karma 当前**真实用户使用期**起步 — 新用户首装踩坑会持续触发改进。

## License

MIT
