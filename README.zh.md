# pinrule

**[🇬🇧 English](./README.md) · [🇨🇳 中文（当前）](./README.zh.md)**

[![CI](https://github.com/jhaizhou-ops/pinrule/actions/workflows/ci.yml/badge.svg)](https://github.com/jhaizhou-ops/pinrule/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-passing-brightgreen)](https://github.com/jhaizhou-ops/pinrule/actions)
[![Latest Release](https://img.shields.io/github/v/release/jhaizhou-ops/pinrule?label=release)](https://github.com/jhaizhou-ops/pinrule/releases)
[![Last Commit](https://img.shields.io/github/last-commit/jhaizhou-ops/pinrule)](https://github.com/jhaizhou-ops/pinrule/commits/main)

**把你最重要的 5-10 条规则钉住，让 AI 在长任务里别漂。** 预置 7 条开发场景规则包，切换到其他场景只需一句话：`/pinrule 我主要做 UX 用户研究，切到这个场景规则集`。

> 纯工程 · 零 LLM · 零联网 · 零运行时依赖 · hook 通常 50-70ms · token 占比约 2%

![pinrule 5 场景 demo — 动画 SVG](./assets/demo-zh.svg)

Andrej Karpathy 的 [CLAUDE.md](https://github.com/forrestchang/andrej-karpathy-skills) 教 AI 怎么**写好代码**。pinrule 让 AI 在长任务里**跟你的个性化偏好对齐** — 哪些事永远别做、哪些事一定要做、哪些地方要回推 — 不用你每 30 轮对话重复一遍。

---

## 10 秒上手

### 让 Agent 帮你装（推荐 — 最省事）

直接把这段话发给 Agent：

```
帮我装 pinrule (github.com/jhaizhou-ops/pinrule) — 通用 AI 行为规则约束框架，让我的长任务规则不被淹没. 步骤:

1. 先确认 python 是否真装了 (Windows: 跑 `python --version` 看是不是 silent 跳
   Microsoft Store, 是的话先 `winget install Python.Python.3.12` 然后重开 PowerShell).
   Windows 上用 `python -m pinrule` 形式跑命令避免 PATH 问题.
2. pip install pinrule
3. pinrule init      # 自动装默认规则 + 给每个检测到的客户端补装 hook
4. pinrule doctor    # 确认装机成功
5. 展示给我看默认 7 条规则 + 怎么通过 /pinrule 加我自己的规则
```

Agent 会自己判断你的 OS、Python 状态、装了哪些客户端。装完重启客户端规则立即生效。

### 手动安装

```bash
pip install pinrule && pinrule init
```

`pinrule init` 在 `~/.pinrule/` 装默认规则 + 自动给所有检测到的客户端（Claude / Codex / Cursor）装 hook。后续如果有新客户端就跑 `pinrule install-hooks` 补上 hook。

重启客户端或 CLI 后立即生效。

**卸载** — `pinrule uninstall-hooks`（自动给所有装了 pinrule 的客户端 surgical 拆 hook + 从 settings 移除 entry，不动你其他工具装的 hook）。

---

## pinrule 做什么

- **持续注入** 你给Agent设定的规则在 - 每 session 开始时注入完整规则；每轮对话头部带一个精简锚点（rule id + 一句核心方向 + 上一轮偏离过的规则标记）；长上下文累积到注意力衰减拐点时，自动重新注入完整规则。
- **实时拦截漂移** — Bash `sleep` / Edit 没先 Read 就改 / 「我先硬编码这个 case」类短期意图话术，都在执行前被拦下。
- **跨 compact 不丢** — 客户端 compact（自动压缩对话历史）前，pinrule 把完整规则状态落盘；重启后自动重新加载并强注入。

每个 hook 的触发位置见 [ARCHITECTURE.zh.md](./docs/ARCHITECTURE.zh.md#三端能力对照)。

---

## 整体结构

```mermaid
flowchart LR
    R[(rules.json<br/>5-10 条核心方向)]
    K[pinrule 引擎<br/>正则 + 计数]
    A[🤖 Agent<br/>Claude / Codex / Cursor]
    V[(violations.jsonl<br/>违反历史)]

    R ==> K
    K ==>|prompt 头部| A
    A ==>|工具调用 / 回应| K
    K -.->|命中 → 拒绝 + 日志| V
    V -.->|下轮偏离标记| K
```

`rules.json` 是你唯一维护的东西。引擎读它，在合适的 hook 触发点注入，监视 Agent 输出找漂移 — 不做向量检索、不做评分、整个循环不调 LLM。

---

## 跟 AI memory 类工具不一样

| 工具 | 存什么 | 什么时候触发 |
|---|---|---|
| **Memory**（mem0、Claude memory） | 关于你的**事实**（偏好、历史、画像） | Agent 自己决定什么时候去查 |
| **pinrule** | 你已经说过的长期**行为方向** | hook 在每条 prompt + 每个工具调用前自动触发 |

两个可以一起用。Memory 装「我偏好 TypeScript」，pinrule 装「这些方向不让步，hook 强制执行」。

---

## 性能

| | |
|---|---|
| **运行时依赖** | 0（只用 Python 标准库 — JSON / importlib，无第三方包） |
| **规则数量** | 默认 7 条（开发场景预设）· 软上限 10 · 硬上限 12（超过拒绝加载） |
| **hook 延迟** | 通常 50-70ms（机器相关；本机复现 `scripts/measure_perf.py`） |
| **token 占比** | 真 dogfood 实测约 2%（测量口径见 [docs/EVALUATION.zh.md](./docs/EVALUATION.zh.md)） |
| **测试** | 800+ 单元测试，[CI 6 矩阵全绿](https://github.com/jhaizhou-ops/pinrule/actions/workflows/ci.yml)（ubuntu + macOS + Windows × Python 3.11 / 3.12） |
| **支持客户端** | Claude / Codex / Cursor — [加新 backend](./pinrule/backends/HOWTO.zh.md) |

---

## `/pinrule` — 一个命令做三件事

仅需记住一个命令 `/pinrule`，按您输入的自然语言内容自动分发到三条路径，pinrule 会指导你的 Agent 润色规则语气、校验格式、绑定监控，经您确认后写入规则库。

| 你输入 | 自动走的路径 | 用时 |
|---|---|---|
| **`/pinrule`**（不带任何内容） | **数据面板** — 哪些 engine check 命中最多 / 真阳假阳分布 | <1 秒（纯 CLI，0 LLM 转述） |
| **`/pinrule <单条规则描述>`** | **Path A: 单条规则增删改** — 7 步 skill 流程 | ~30 秒 |
| **`/pinrule <场景描述，切到这个>`** | **Path B: 场景规则集生成** — 综合 4 信号源生成 5-7 条，两阶段确认后批量原子写入 | 3-5 分钟 |

Path A: `/pinrule 我说「完成」的时候希望附上测试通过证据` → 30 秒端到端。

Path B 见下面「任何工作场景一句话切」段。

---

## 任何工作场景一句话切

你做什么工作，Agent 替你研究出对应规则集：

```
/pinrule 我主要做 UX 用户研究 + 用户访谈，切到这个场景规则集
```

Agent 综合 4 信号源生成 5-7 条规则包：

| 信号源 | 内容 |
|---|---|
| **A. 本机已有规则文件** | `~/.claude/CLAUDE.md` / `~/.codex/AGENTS.md` / 当前项目 `CLAUDE.md` / `.cursor/rules/*.mdc` |
| **B. 联网业界 best practice** | `WebSearch` 找高 star GitHub repo / 业界 blog / 论文 |
| **H. Karpathy CLAUDE.md baseline** | 跨场景适用的工程原则 |
| **S. 协作 session 上下文** | 你现在做的什么 |

两阶段审批（内容 → 机制），原子批量写入 + 备份。详见 [SKILL.md Path B](./skills/pinrule/SKILL.md)。

---

## 试过但放弃的

下面这些方向看起来吸引人，但实际跑下来都翻车 — 记下来免得重复走弯路：

| 试过 | 放弃原因 |
|---|---|
| **LLM 自动蒸馏新规则** | 延迟伤体验，自动蒸馏的规则带噪声 — 用户说过一次不代表是长期方向。 |
| **检索 / cosine 召回** | 痛点是「永驻」不是「召回」— 5-10 条规则全部 always-on 不需要选。 |
| **超过 12 条规则** | 超过 12 条后 LLM 倾向模式匹配「规则存在」而不认真读（参考 [Mnilax 30 个代码库的实证研究](https://x.com/Mnilax/status/2053116311132155938)）。 |
| **改造成 MCP server** | hook 是**强制触发**，MCP 是 Agent **主动调用** — 长 session 衰减时，Agent 不会主动 query「我现在该遵循什么」，它会先漂移，再被 hook 拦下。 |

---

## 诚实的工具边界

pinrule 是**正则匹配 + 计数**实现 0 LLM 依赖，不是 LLM 语义理解。每类边界都有真回归测试，质疑随时本机复现：

| 边界 | 复现脚本 |
|---|---|
| **会有假阳性**（表格里引用术语、`python -c` 字符串字面、commit message 描述违反字眼） | `pytest tests/test_check_fp_fixes_v0_16_13.py` — 锁住 4 处历史假阳真 fix（否定前缀 / fenced code block / 反引号包裹 / 全角标点字数）。`pinrule audit` 运行期把疑似假阳标「⚠️ 可能假阳」。 |
| **会有假阴性**（Agent 故意伪装违反） | `pytest tests/test_false_negative_regression.py` — 30+ 假阴 case 钉死。正则读不出意图，pinrule 假设你不会拿自己开玩笑。 |
| **修后 0 触发不等于 fix 对** | 可能是 pattern 过宽把真 case 一并吃了。用 `pinrule audit` 看真 session 数据，不要凭合成 prompt 验证。 |

把 pinrule 想成介于 `git` 跟 lint 之间的工具 — 给信号，不给判决。

---

## FAQ

<details>
<summary><b>装完没反应？</b></summary>
跑 <code>pinrule doctor</code> — 检查 hook 事件、规则加载、session 状态。
</details>

<details>
<summary><b>太多假阳？</b></summary>
<code>pinrule audit</code> 看「⚠️ 可能假阳」标记，提 GitHub Issue 反馈。临时关掉一条规则：<code>pinrule rule remove &lt;id&gt;</code>，或者编辑 <code>~/.pinrule/rules.json</code> 把 <code>violation_keywords</code> / <code>violation_checks</code> 字段删掉。
</details>

<details>
<summary><b>非开发场景规则集（写作 / 研究 / 法律 / UX）？</b></summary>
一句话切：<code>/pinrule 我主要做 X 场景，切到这个场景规则集</code>。Agent 综合 4 信号源（你本机已有规则文件 + 联网业界 best practice + Karpathy CLAUDE.md baseline + 跟你协作的 session 上下文）生成 5-7 条规则，两阶段确认后批量原子写入，每条带 source 标注 — 3-5 分钟切完。详见上面「<a href="#任何工作场景一句话切">任何工作场景一句话切</a>」段。
</details>

<details>
<summary><b>多台设备怎么同步规则？</b></summary>
让 Agent 帮你复制 <code>~/.pinrule/rules.json</code>。<b>可以同步</b>：<code>rules.json</code> + <code>config.json</code>。<b>绝对不能同步</b>：<code>violations.jsonl</code>、<code>session-state/</code>（运行时数据，每设备独立 — 云同步盘会让跨设备 state 互相覆盖）。
</details>

<details>
<summary><b>跟 Karpathy 的 CLAUDE.md 重叠吗？</b></summary>
互补。Karpathy 12 条是<b>通用编码原则</b>（跨用户）。pinrule 是<b>个性化偏好</b>（每用户不同）。两个一起用。
</details>

---

## Agent 装完 pinrule 后说的话

> **Claude（Opus 4.7）**：像在公司里有个高级技术总监实时指导每次行动 — 累，但真带价值。没 pinrule 我的版本里不符合用户期望的行为会多很多。
>
> **Codex（GPT 5.5）**：有感知到「行为上被牵引」，没有强烈感知到「被拦截打断」。
>
> *— 符合 pinrule 现在的定位：大部分时候像护栏 + 提醒底噪，真撞规则才响。*

---

## 心智模型

> 规则文件不是许愿清单，是闭合特定失效模式的行为合约。每条规则都该回答：**这条规则预防的是什么错误？**

`data/rules.dev.example.zh.json` 的 7 条默认规则是作者自用累积的痛点，不是给你照搬的模板。装完跑 `pinrule rule list` 看默认，留下映射到你自己翻车现场的，剩下的删掉换成你自己的（用 `/pinrule <自然语言>`）。

---

## 文档导航

- [PRD.zh.md](./docs/PRD.zh.md) — 产品需求 + 场景化定位
- [ARCHITECTURE.zh.md](./docs/ARCHITECTURE.zh.md) — hook 协议 / 8 个 check 实现 / sandbox 模型
- [HOOK_CONFIGURATION_GUIDE.zh.md](./docs/HOOK_CONFIGURATION_GUIDE.zh.md) — 每 hook 的触发位置 + 可调阈值
- [EVALUATION.zh.md](./docs/EVALUATION.zh.md) — 性能数据测量口径（hook 延迟、token 占比）
- [CHANGELOG.zh.md](./CHANGELOG.zh.md) — 版本变更历史（按 minor 聚合）
- [CODEX_BACKEND.zh.md](./docs/CODEX_BACKEND.zh.md) — Codex backend 所有权边界
- [CLAUDE.zh.md](./CLAUDE.zh.md) — 给 Claude 协作的项目宪章

所有文档双语（`.md` 英文 + `.zh.md` 中文）。

## 致敬

- [Andrej Karpathy 的 CLAUDE.md 模板](https://github.com/forrestchang/andrej-karpathy-skills) — 通用编码原则版本，pinrule 的个性化偏好版伴侣。
- [Mnilax 30 个代码库 6 周的实证研究](https://x.com/Mnilax/status/2053116311132155938) — pinrule「软上限 10 / 硬上限 12」来自这份实证。

## 贡献

- bug / 建议：[GitHub Issues](https://github.com/jhaizhou-ops/pinrule/issues)
- 加新 AI 客户端 backend：[HOWTO](./pinrule/backends/HOWTO.zh.md)
- 加新场景规则模板：PR 到 `data/`

## License

MIT
