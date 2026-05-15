# karma 产品需求文档

**[🇬🇧 English](./PRD.md) · [🇨🇳 中文（当前）](./PRD.zh.md)**

## 用户痛点（实证）

karma v2 的设计起点是一个**真实长期痛点**，用户原话：

> 我不停强调但是 Agent 一再触犯到的规则就是：Agent 采取的方法总是短视、作弊、逐利和补丁性的，
> 而我一直追求根本、长期、普适和正确的，这需要我不断的重复和强调，但 Agent 仍然在硬编码、
> 作弊、追求短期目标的达成而忘掉长期目标。

> 还有比如我非常坚持不要前端阻塞开发和测试，但是过几个 turn 以后 Agent 就开始不顾后面
> 还有没有任务，全都是默认阻塞前端的无意义等待。

> 还有比如我非常追求效率，一再要求要并发多 Agent 开发和测试，以及不断探求更高效的工作方式，
> 但是 Agent 很快就会遗忘。

> 还有比如我只看中文和非技术背景，但 Agent 压缩后就会开始默认输出英文，并且内容越来越
> 技术化直到我完全看不懂。

## 痛点本质

这些例子有同一个模式：

| 特征 | 描述 |
|---|---|
| 类型 | 是「**长期方向偏好**」不是事实记忆（不是「我家狗叫 X」） |
| 用户行为 | 反复强调过（5+ 次），不是 Agent 没听到 |
| Agent 当下行为 | 听到时配合做对，记住几个 turn |
| Agent 中期行为 | 几个 turn 后注意力漂移，开始违反 |
| 跨 session/compact | 上下文压缩后完全丢失 |

**核心问题**：不是 Agent **不知道**用户偏好，是 **「在长上下文中注意力漂移 + compact 后压缩成模糊词」**。

## 为什么现有方案不够

| 方案 | 不够的地方 |
|---|---|
| **CLAUDE.md** | 写了但被任务细节淹没，Agent 注意力分散；compact 后压成模糊词；项目级不跨项目 |
| **Claude Code auto-memory** | 偏「事实记忆」(我用 Mac / 我喜欢 X)，不专门处理「行为方向偏好」；召回时机不对 |
| **karma v1** | 试图自动蒸馏 + retrieval — 但真实痛点是「永驻」而非「召回」，方向错位 |

## karma v2 设计哲学

### 1. 核心方向「钉死」而不是「检索」

用户的最高优先级方向（10 条上限（接近但不越 14 注意力拐点））**always-on**，每个 user_prompt 前面都注入。

不需要 cosine / scene 选哪条 — 因为这些都是**用户公开声明的最高优先级**，每次都该看到。

### 2. 用户掌控（不自动蒸馏）

karma 不学新规则。用户手工列「核心方向」，karma 只负责让它们 **always 在 Agent 注意力最高的位置**。

这避免了：
- LLM 蒸馏的噪声 / 错位 / 过拟合特定用户
- 「关于用户的事实」跟「Agent 行为偏好」赛道混淆

### 3. 违反检测 → 反馈闭环

retrieve 的局限：把规则放进 context 让 Agent「看一眼」 — 但看见不等于优先级高。

karma 用 **「行为违反检测」** 做反馈：
- Agent 响应后，hook 扫触发词 / 正则 / 简单分类
- 检测到违反 → 通知用户 + 下次注入时该规则**显式标 RECENT_VIOLATION**
- Agent 看到 RECENT_VIOLATION 提示会比纯描述更注意（实证未验证，是核心假设）

### 4. 不抢任何已有赛道

- 事实记忆 / 偏好检索 → Claude Code auto-memory / mem0 等
- 项目级规则 → CLAUDE.md
- 工作流自动化 → Claude Code hooks 直接做

karma 只做**「核心方向永驻 + 违反检测」**这一件事。

## 功能需求（v0 MVP — 已交付）

### F1. 核心方向配置 ✅

- 用户在 `~/.claude/karma/sticky.yaml` 定义 5-10 条（上限 10，超过 12 拒绝加载）
- 字段：`id` / `preference` / `violation_keywords` / `violation_checks`（工程层 check 函数名列表）
- karma CLI: `karma sticky list / edit / remove`、`karma init`

### F2. user_prompt_submit hook ✅

- 每次 user_prompt_submit，hook 读 sticky.yaml
- 用 `additionalContext` 注入到 Claude 上下文（不修改 user_text 本身）
- 格式：`[karma sticky — 用户最高优先级方向，请始终遵守]` 加 1-10 编号规则
- 24h 内触发过的规则前标 `⚠️ 上次违反！`
- 性能：< 50ms

### F3. 违反检测 / 反馈闭环 ✅

两层检测：
- **关键词层**：扫 Bash command + Write/Edit 注释行 + Stop hook 看 Agent response 含违反字眼
- **工程层（M2+ 加强）**：8 个 violation_check 函数针对每条 sticky 做精确 regex 检测
  - long_term_fundamental：长 hash if 分支 / 黑白名单字面 / TODO 实际注释 / 意图字面注释 / 全大写常量名单
  - non_blocking_parallel：sleep / wait / 长任务无 background / 间接 shell 执行
  - chinese_plain_no_jargon：中文占比 + jargon 检测（剥 code block + inline code）
  - loud_failure_with_evidence：完成词 / weak claim 在代码任务上下文 + 无测试证据
  - no_testset_no_future_leakage：长 hash 字面 / 反喂池子等
  - read_before_write：Edit/Write 未 Read 同文件就拦
  - keep_pushing_no_stop：response 末尾推进信号 / 问号 / 停顿词检测
  - bypass_karma_detection：Bash 命令含 karma 内部敏感字面 + 写操作
  - no_testset_no_future_leakage：gold_cases 反喂 / 跨 split 复制 / 长 hash 在比较或赋值
  - read_before_write：Edit/Write 前未 Read

三个 hook 反馈点：
- **PreToolUse**：Agent 调 tool 前实时拦截（deny + 显示原因）
- **PostToolUse**：跟踪 session 状态（Read/Edit/Write 历史 + Bash PASS/FAIL）
- **Stop**：扫 Agent response 字面违反

### F4. 自用观察工具 ✅

- `karma stats` — 每条规则违反次数 + 最近触发时间
- `karma violations recent [N]` — 最近 N 条违反详情
- `karma doctor` — 检查环境（规则合法 + 全部 hook 装机状态 + skill 装机状态，Claude Code 8 个 event）
- `karma audit` — 每条规则 top 触发词频次 + 跨 locale 稳定分组（v0.5.7+）
- `karma install-hooks / uninstall-hooks` — 自动写/清 settings.json（idempotent + 备份 + 保留他人 hook）
- `karma install-skill [--force]` — 装 / 升级 `karma-rule` Claude Code skill（`karma init` 自动跑过；独立命令给升级用）

### F5. 自然语言规则录入（`/karma` skill）✅（v0.5.16+ — skill 第一次真触发的 release）

**触发方式**：用户在 Claude Code / Codex CLI / Gemini CLI 任一输 `/karma <自然语言>`。skill 走 7 步：识别意图 → 检查现有规则重叠 → 内联起草 yaml → `karma rule preview` schema 校验 → 跟用户确认 → `karma rule add` 写入 → 反馈报告

**skill 替你做的事**：
- 语气优化（协作默契语气 — 大模型对此回应是「我对齐」不是「我争辩」）
- `violation_keywords` 转「意图前缀 + 动作」格式（`"我先打个补丁"` 不是 `"补丁"`）
- 重叠检测（4 形态决策表：完全重复 / superset / keyword 交集 / 无重叠）
- anchor-vs-scope 歧义识别（always-on 注入无 scene routing）
- locale 感知 preference 起草（按用户聊天语言；`violation_checks` 函数名保持英文为稳定标识符）
- modify recipe（`remove + add` 组合 — 不需要单独的 `replace` CLI 命令）

**底层 CLI**（可独立从 skill 或脚本调用）：
- `karma rule add --from-yaml <file>` / `karma rule add --from-stdin` — 程序化写规则，含 schema + id 唯一性 + REGISTRY 校验
- `karma rule preview --from-yaml/--from-stdin` — dry-run 校验 + 头部注入预览

**多 backend 装机**（v0.5.16+）：
- Claude Code: `~/.claude/skills/karma/SKILL.md`（Markdown + YAML frontmatter）
- Codex CLI: `~/.agents/skills/karma/SKILL.md`（注：`~/.agents/` 不是 `~/.codex/` — 按 OpenAI 设计跟 Anthropic 共享命名空间）
- Gemini CLI: `~/.gemini/skills/karma/SKILL.md`（auto-trigger）**加** `~/.gemini/commands/karma.toml`（显式 `/karma` slash，通过 `karma/skill_packaging.py` Markdown → TOML 转换生成，含 `$ARGUMENTS` ↔ `{{args}}` 语法翻译）
- `karma init` 自动装到所有三家；`karma install-skill [--force] [--backend <name>]` 给升级用；`karma doctor` 报每个 backend skill 状态

**诚实历史**：v0.5.1 ship 了 skill 模板但路径错（`<name>.md` 裸文件而不是 Claude Code 协议要求的 `<name>/SKILL.md` 目录结构）。v0.5.1 ~ v0.5.15 skill 从未真触发 — 手工 CLI 测试能用，但自然语言 → 自动 refine 路径是空气。v0.5.16 按 Claude Code 协议重建装机；ship v0.5.16 那个 session 的 SessionStart hook 是 karma skill 第一次出现在 available skills 列表里。完整披露见 [CHANGELOG.md v0.5.16](../CHANGELOG.md)。

### F6. 国际化（v0.5.2+）✅

- `karma/i18n.py` 含 `tr(key, **fmt)` lookup，`{placeholder}` 插值，缺 key fail-open
- locale 解析链：`KARMA_LOCALE` env > `config.yaml` `locale` 字段 > `karma.locale_detect.is_chinese_user()` 自动检测 > `en` fallback
- 所有 hook 注入文本（头部 / 偏离标记 / 中段注入 / 强提醒 / Stop reason / SessionStart 变体 / SubagentStart）+ 28 处 check `suggested_fix` + 28 处 `CheckHit.trigger` audit 标签全部走 `data/locales/{en,zh}.yaml` 双语切换
- `Violation.trigger_key` + `CheckHit.trigger_key`（v0.5.7+）— locale-agnostic 稳定标识符让 `karma audit` 跨 locale 分组（用户中途切语言仍能正确聚合）
- `karma init` 按 detected locale 选规则模板（中文用户装 `rules.dev.example.zh.yaml`，其他用英文 default）

### M3 完整化补充（v0 MVP 之上的工程精细化）

- **描述上下文统一豁免**（`karma/checks/description_context.py`）— `.md` / `.yaml` / `.json` / tests/ / `/tmp/` / probe-sample 命名文件下「描述触发模式」不算执行意图
- **shell 引号字面 + heredoc 智能剥** — `git commit -m "..."` 引号字面是描述；`bash <<EOF` heredoc 内是 shell 命令保留扫；`python <<EOF` heredoc 内是数据剥
- **background 任务证据自动接入** — `pytest > log.txt &` 后下次 hook 触发 catchup_pending_bg 读 log 接进 last_test_pass_ts
- **`has_recent_test_pass` 新语义** — 「自最近一次代码改动以来跑过测试且通过」
- **post_tool_use 跳过失败 tool** — Read 失败不 record_read 防 read_first 被绕过
- **跨语言注释 + docstring 扫描** — `# / // / -- / """ / ''' / /* */` 都被关键词层 Write/Edit 扫覆盖

### 反馈机制 + 配置系统

- **桌面通知**（`karma/notify.py`）— 跨平台（macOS osascript / Linux notify-send / Windows msg），stop hook 检测违反时补充 stderr 视野外提示
- **累积告警按 turn 维度** — 最近 N turn 内同 sticky 违反 ≥ M 次 → 🚨 严重通知（窗口 / 阈值可配）。按 turn 而非人类时钟 — Agent 注意力漂移按 turn 累积，用户离开开会跟连续操作 Agent 状态完全不同
- **配置系统**（`karma/config.py` + `~/.claude/karma/config.yaml`）— 所有阈值集中可调（notify 开关 / rotation / purge / escalate）；fail open（文件缺失 / 字段为 null 用 DEFAULTS）
- **`karma doctor` 显示当前生效配置** — 让用户看清现在所有阈值

## 验证标准（v0）

karma v0 不追求精度数字 — 追求 **作者自用是否确实感觉到「Agent 在长任务中少犯方向错」**。

观察指标：
1. **长任务中违反触发频次** — 装 karma 前 vs 后对比
2. **用户重复强调同一规则次数** — 减少
3. **compact 后 Agent 是否还记得核心方向** — 通过几次 long-session 测试

如果一周自用没明显改善 → karma 假设错了，需要重新设计。

### 验证标准的工作框架（M3 后更新）

用户原话「咱们继续推就是观察期啊」— **「开发」和「自用观察」不是二元选择**。

karma 的开发过程本身就是它最严酷的自用观察期：每次推进开发 Claude 都装着 karma 跑，每个 commit 都经历 hook 拦截。M3 六波累积了 30+ 条真实违反数据，6 个 sticky 全部触发过，假阳 / 假阴边界在 dogfooding 中持续暴露 + 修复。

这比「装好等一周观察」更密集 / 真实 / 反馈快。

## 场景化定位（M3 之后明确）

karma = **通用 hook 框架** + **场景规则集**。

当前 `data/sticky.dev.example.yaml` 是「**软件开发场景**」预设 — 7 条规则全部针对写代码时的注意力漂移（长期方案 / 不阻塞 / 直白中文 / 完成证据 / 不喂测试集 / 不绕开检测 / 先读再写）。工程层 8 个 violation_check 函数（pytest / Edit / Write / Bash / bypass_karma / keep_pushing 等）也偏开发场景。

其他场景（写作 / 研究 / 产品 / 设计 / 法律等）需要不同的规则集 — 用户可自定义 sticky.yaml，或社区贡献预设。karma 框架层跨场景通用。

这个定位是 M3 dogfooding 中浮现的洞察 — 之前以为「跨用户通用」，实际是「跨用户但同场景通用」。

## 非功能性要求

- **不能用 sonnet** — 严格继承 v1 LLM 授权规则
- **本地 ≤4 并发的小型任务可用 mlx Qwen3.6** — 但 karma v0 设计上不需要 LLM
- **Hook 性能** — user_prompt_submit hook 必须 < 50ms（不能拖 Agent 响应）

## v0 范围明确说不做

- ❌ 自动蒸馏新 sticky 规则
- ❌ retrieval / cosine / scene 路由
- ❌ 多用户协作 / 同步
- ❌ Web UI / 图形配置（CLI 编辑 yaml 够了）
- ~~❌ 跨 IDE / 跨 AI 平台支持（先 Claude Code only）~~ — **v0.4+ 已支持**：
  Claude Code / Codex CLI / Gemini CLI 三家通用，基类抽象未来加 Cursor /
  Factory / Qoder / Copilot / CodeBuddy / Kimi 等成「填表」工作。详
  [`karma/backends/HOWTO.md`](./karma/backends/HOWTO.md)。
- ❌ 评测体系 / accuracy 指标（自用观察够了）

## 后续可能（v1+）

如果 v0 验证 karma 确实有用：

- **跨 IDE/平台**：Cursor / Windsurf / Codex 支持
- **团队级 sticky**：团队共享一份核心方向（如 SWE 团队的代码风格）
- **行为违反检测增强**：从「关键词」升级到「LLM-judged」（但本地小模型，零外发）
- **核心方向模板市场**：跨用户分享好用的 sticky 集（不强制 karma 自动用，仅参考）

但**v0 不做这些**。先验证最小假设。
