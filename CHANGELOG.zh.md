# Changelog

**[🇬🇧 English](./CHANGELOG.md) · [🇨🇳 中文（当前）](./CHANGELOG.zh.md)**

记录 karma 每个版本的重要变化。版本号遵循 [SemVer](https://semver.org/lang/zh-CN/)。

## [Unreleased]

## [0.6.1] — 2026-05-15（fix — `record_edit` 豁免非代码路径；issue #1 真用户 bug 真根因 fix）

### 真用户 bug — docker pytest + 改 README + git commit 不再被误拦

**Bug**（issue #1，真用户 `@fyn1320068837-source`）：`docker exec <container> python -m pytest tests/` 通过（如 1190 passed）→ 用户改任何文件（甚至 README.md / .gitignore / IDE auto-save）→ `git commit` 被 `loud-failure-with-evidence` 拦截，trigger 是「最近 session 内无测试通过证据」。

**真根因**（真测复现）：`has_recent_test_pass()` 返 `last_test_pass_ts >= last_edit_ts`。任何 `record_edit()` 调用把 `last_edit_ts` 推到「现在」，立即让 `has_recent_test_pass` 翻 False — 包括对文档 / `.gitignore` / `LICENSE` 等**改了不影响 pytest 是否需要重跑**的文件的编辑。by-intent 设计（「代码改了没重测就该拦 commit」）被无差别应用到非代码 edit。

reporter 提议的 fix（`_TEST_CMD_RE` 加 docker 可选前缀）修错层 — regex 已正确匹配 `docker exec ... pytest`（4 层端到端真测确认）。真根因需要在 `record_edit` 时间跟踪层 fix。

### Fix

`karma/session_state.py` 加 `_NON_CODE_EDIT_RE` 豁免清单 — `record_edit()` 在 file 是文档 / 元数据 / 顶级仓库文本时不推 `last_edit_ts`：

- 文档后缀：`.md` / `.rst` / `.txt` / `.markdown` / `.adoc`
- 元数据文件：`.gitignore` / `.gitattributes` / `.editorconfig`
- 顶级路径模式：`docs/` / `.github/` 目录；仓库根的 `CHANGELOG` / `README` / `LICENSE` / `CONTRIBUTING` / `CODE_OF_CONDUCT` / `SECURITY` / `HANDOFF`（任意扩展名）

**仍触发**（by-intent 保留）：
- `src/**/*.py` / 业务代码 → commit 前必须重跑 pytest
- `tests/**/*.py` / 测试文件本身 → 测试改了表示之前的测试在新版没跑过
- `*.yaml` / `*.toml` / 生产配置 / 构建文件 → commit 前重测

### 验证

- `tests/test_session_state.py` 新增 6 个回归测试（`test_v061_*`）：
  - 4 个豁免 case：README.md / CHANGELOG.md / docs/*.md / .gitignore edit 后 `has_recent_test_pass` 仍 True
  - 2 个对偶 case：src/*.py 和 tests/*.py edit 后仍翻 False（保留 by-intent 设计）
- `pytest`：429/429 通过（之前 423 + 新 6）
- `ruff`：0 issues

### 真用户协作价值

karma 第一个外部贡献者 `@fyn1320068837-source` 报了他在 `henghai-backend` 工作流真踩的 bug — `docker exec container python -m pytest` + edit + commit。他最初的根因诊断（「regex 不 match docker 前缀」）是错的，但 **bug 本身是真的**。maintainer 本机端到端 docker pytest 实测在候选 A 场景（`last_edit_ts > last_test_pass_ts` 在非代码 edit 后）真复现。v0.6.1 在正确层修真根因。

Issue #1 由本 release 关闭 — 完整 thread 记录真用户协作 → 真测 → 真根因弧线。

## [0.6.0] — 2026-05-15 ⚠️ BREAKING — 删 `sticky` → `rule` 改名留的 backward-compat 脚手架

### 删了啥（破坏性）

- **`karma.sticky` 模块** — `from karma.sticky import ...` 现在抛 `ModuleNotFoundError`。迁移：`from karma.rule import ...`（exports 完全一致）。
- **`Violation.sticky_id` @property** — `violation.sticky_id` 抛 `AttributeError`。迁移：用 `.rule_id`。
- **`CheckHit.sticky_id` @property** — `hit.sticky_id` 抛 `AttributeError`。迁移：用 `.rule_id`。
- **`karma sticky <subcommand>` CLI** — 退 1 带提示 `💡 你是不是想用 karma rule？`。迁移：用 `karma rule list / edit / remove / add / preview`。
- **`karma.rule` aliases** — `Sticky` / `MAX_STICKY` / `StickyConfigError` 删了。迁移：`Rule` / `MAX_RULES` / `RuleConfigError`。
- **`karma.cli` aliases** — `EXAMPLE_STICKY` / `EXAMPLE_STICKY_MINIMAL` 删了（内部符号，对用户基本无影响）。

### 保留（盘上数据兼容永久保留）

这些不是废弃 alias，是处理真实用户盘上数据的兼容补丁，karma 永远保留：

- **`sticky.yaml` → `rules.yaml` 自动迁移** 在 `karma init` — 从 v0.4.x 升级的用户盘上仍有 `sticky.yaml`；karma 静默移到 `rules.yaml` 并备份 `.bak`
- **`violations.jsonl` `sticky_id` 字段兜底** — v0.4.x 历史 jsonl 行用 `sticky_id` 不是 `rule_id`；`karma audit` / `stats` 通过 `_extract_rule_id` 仍能正确读
- **`STICKY_PATH` 内部常量** in `karma.cli` — 向后兼容路径 alias 指向 `rule.DEFAULT_PATH`。测试在用；无需迁移

### 这版动机

v0.5.0（今天稍早）改 `sticky` → `rule` 全代码库 + ship backward-compat alias 让用户脚本不立即破。废弃 warning 跑了一个完整 release 周期（v0.5.x 共 18 个 release）。v0.6.0 悬崖按 [`docs/V0_6_0_PLAN.md`](./docs/V0_6_0_PLAN.md) 计划兑现。

karma 自己代码 v0.5.13 起停用 `.sticky_id` 属性访问，v0.5.15 起停用 `from karma.sticky` import。v0.6.0 是**纯删除 commit** — 无 refactor 逻辑，只是删除。

### 用户脚本迁移指南

绝大部分用 karma 的用户脚本是 1 行机械替换：

```python
# 之前 (任何 v0.5.x — 带 warning)
from karma.sticky import Sticky, MAX_STICKY, StickyConfigError
violation.sticky_id  # 工作但 warning

# v0.6.0 之后
from karma.rule import Rule, MAX_RULES, RuleConfigError
violation.rule_id  # 必须改
```

```bash
# 之前
karma sticky list

# 现在
karma rule list
```

### 验证

- `tests/test_sticky.py` 新增 5 个 deletion-lock 测试（`test_v0600_*`）：
  - `import karma.sticky` 抛 `ModuleNotFoundError` ✓
  - `Violation.sticky_id` 抛 `AttributeError` ✓
  - `CheckHit.sticky_id` 抛 `AttributeError` ✓
  - `karma.rule.Sticky` / `MAX_STICKY` / `StickyConfigError` `hasattr() == False` ✓
  - `karma sticky list` subprocess 退 1 + stderr 含 `"karma rule"` ✓
- `pytest`：423/423 通过（之前 418 + 新 5）
- `ruff`：0 issues
- 累积：今早 v0.5.0 改名到今晚 v0.6.0 悬崖，**一天 ship 20 个 release** — 完整 sticky → rule 改名 + 1 周期废弃 + 悬崖弧线在 `git log v0.5.0..v0.6.0` 里

## [0.5.20] — 2026-05-15（docs — rule 10 自审 follow-up: 补 v0.5.19 漏的 ARCHITECTURE + HANDOFF 同步）

### 这版动机

用户让我自审过去 4 个 release 是不是真做到 rule 10「commit 后同步所有受影响 doc」。审计发现一个真漏：**v0.5.19 commit 时没更新 `docs/ARCHITECTURE.md` milestone 表也没更 `docs/HANDOFF.md` current status**。CHANGELOG 有条目，但技术档案 doc 没有。rule 10 例外条款「内部 refactor → 只更 CHANGELOG + HANDOFF」我之前理解成「只更 CHANGELOG」漏了 HANDOFF。

### 改了啥

- `docs/ARCHITECTURE.md` + `.zh.md` — milestone 表加 v0.5.19 行（饱和豁免根因 + 跟 v0.4.41 对偶 note）
- `docs/HANDOFF.md` — current status section 加 v0.5.19 条目（dogfood 触发 context: 被它要 fix 的同一个 Stop hook 拦到）

### 完整审计结果

| Rule-10 要求 | v0.5.16–19 结果 |
|---|---|
| ① commit 后立刻 audit doc | ✅ v0.5.16/17/18；❌ v0.5.19（本版 fix） |
| ② 功能放主语 version 放从句 | ✅ README hero / `/karma` section / PRD F5 都做到；ARCHITECTURE milestone 表是 patch 体（按格式可接受 — milestone 表本质就是时间线） |
| ③ 重要亮点进 README 顶部 | ✅ v0.5.16 skill 进 hero + Real-problems 行 + 新顶级 section |
| ④ 双语 `.md` + `.zh.md` 同步 | ✅ v0.5.16-18 的 README/PRD/ARCH/HANDOFF 同步；❌ v0.5.19（本版 fix） |
| ⑤ 内部 refactor 例外 | ✅ v0.5.18/19 正确没动 README/PRD（无 user-visible CLI 变化），但 HANDOFF 仍需要 v0.5.19 漏了 |

净结: 5 条做到 4 条. miss 由 rule 10 显式自审触发, 几分钟内 fix — 正是 rule 10 写来 enable 的 dogfood 驱动纠正闭环.

### 验证

- `pytest`：418/418 通过（纯文档无代码改）
- `ruff`：0 issues

## [0.5.18] — 2026-05-15（fix — `bypass_karma` 区分「读 karma 写别处」vs「写到 karma 路径」）

### dogfooding 真假阳触发的根因 fix

正在看 `karma audit` 今天累积的违反数据时，跑 `grep deep-fix ~/.claude/karma/violations.jsonl > /tmp/df_audit.jsonl` 想提取几行分析 — 被 bypass_karma 拦「绕开检测 — 手动写 karma 内部状态」。按规则 7 没绕，深挖根因。

**之前的问题**：`bypass_karma` 老判定是 `(has_internal OR has_state_path) AND has_write` — 命令含 karma 路径 + 任何 redirect/write op 就拦，不管 redirect target 是不是 `/tmp/`。读 karma 状态到 tmp 分析是合法 audit 用途，但 rule 把「karma 路径出现在命令里」跟「写到 karma 路径」混为一谈。

**修法**：通过 `_BASH_REDIR_TARGET_RE`（v0.5.9 起放在 `description_context.py` 共享）提取 redirect target，看任一 target 是否匹配 `_KARMA_STATE_PATH_RE`。新规则: `(has_internal OR has_state_path) AND write_to_karma_state`，其中 `write_to_karma_state = has_python_write OR (任一 redirect target 真是 karma 路径)`。

**行为对比**（4 个新回归测试验证）：

| 命令 | v0.5.17 | v0.5.18 |
|---|---|---|
| `grep ~/.claude/karma/violations.jsonl > /tmp/x` | ❌ 拦 (假阳) | ✓ 豁免 |
| `cat ~/.claude/karma/violations.jsonl \| python3 -m json.tool > /tmp/pretty.json` | ❌ 拦 | ✓ 豁免 |
| `echo '{}' >> ~/.claude/karma/violations.jsonl` | ✓ 拦 | ✓ 拦（真写 karma）|
| `python -c "open('.claude/karma/x', 'w').write(...)"` | ✓ 拦 | ✓ 拦（python 写接口）|
| `echo 'last_test_pass_ts=999' > /tmp/inject.txt` | ✓ 拦 | ✓ 豁免（target 是 /tmp 不是 karma 路径 — 跟 state_path 维度对称）|

`has_internal`（字段名引用）维度也对称收紧：写 `last_test_pass_ts=...` 到 `/tmp/` 不影响 karma 状态，现在豁免。同样字符串写到 `~/.claude/karma/...` 仍拦因为 redirect target 是 karma 路径。

### 为啥这事重要

这是 karma 自己 false-positive 拦真合法的 audit 工作 — 正是规则 7 写来防的「karma 过度纠正 → 用户被迫绕」失败模式。Catch trigger 没绕，深挖 regex，修判定器。两个新 case lock 住新豁免和保留拦截（`test_v0518_read_karma_state_write_tmp_exempted` + `test_v0518_redirect_target_is_karma_path_still_blocked`）。

### 验证

- `tests/test_bypass_karma.py` 加 5 个回归测试覆盖: read-karma-写-tmp 豁免、pipe-to-python 豁免、write-to-karma 仍拦、internal-field-name + write-tmp 豁免（跟 state_path fix 对称）、internal-field-name + write-karma 仍拦
- `pytest`：416/416 通过（411 + 新 5）
- `ruff`：0 issues
- 4 个之前 `test_*_real_bypass_*` 仍绿 — fix 没松开真写检测

## [0.5.17] — 2026-05-15（docs — README narrative 重写：`/karma <NL>` skill 提升为顶级 section，不再是 patch 式提及）

### 这版动机

v0.5.16 ship 了真工作的 skill 但 README 仍然把它当成「Customize 章节内的 patch 式提及」— 「Agent 替你写规则」能力是一行 aside，「Agent 守规则」能力独占整个 hero。本版按用户原则重写 README narrative 让 karma 两面闭环在 landing page 上平起平坐：

> 「对外说明文档一定不要只是打补丁，要很「爆款」的融入整体说明，重要亮点和功能说明展示好。」

### 改了啥（README + README.zh.md 对称）

**1. Hero opening 重写** — 之前是单段「监督 Agent」+ 违规率数字。现在明确把 karma framing 为「同一闭环的两面」：🛡️ 钉规则 / Agent 守 + ✨ 大白话告诉 karma / Agent 替你写。两面各配具体一行。

**2. 目录** — 加 `/karma 自然语言录入规则` 作为顶级 entry，跟 install / 原理 / 自定义并列。

**3. 真痛点表格** — 加第 7 行 v0.5.16 真解决的痛点（「想加规则但 yaml 太重 / 措辞 Agent 不响应」），让 value-prop 用跟其他 6 个痛点同样的对照表格出现。

**4. Quick install 段** — 加一行 callout 说 `karma init` 自动装 skill 到三家 backend，让用户从 install 起就知道开箱即用不需要额外步骤。

**5. 新顶级 section `/karma <自然语言>` — Agent 替你写规则** — 替换 v0.5.15 在 Customize 内 patch 的 20 行「推荐路径」子段。新 section 55+ 行：7 步流程可视化、「skill 替你做的事」6 行表（语气 / 格式 / 重叠 / scope / locale / modify）、「三家 backend 一个命令」装机表、升级流程（`karma install-skill --force` / `--backend`）。

**6. 「自定义你自己的核心方向」缩成 1 行 pointer** — 指向新顶级 skill section，注明手工 yaml fallback 是给进阶用户 / 无 skill 环境。yaml 示例块保留作 fallback 参考；v0.5.15 patch 的重复「推荐：」内容删除（不再冗余）。

### 其他 doc 同步

- **`docs/PRD.md` + `.zh.md` F5** — 用 v0.5.16 多 backend 现实重写。老版本仍说「v0.5.1+」可用；新版本明确「v0.5.16+ — skill 第一次真触发」含诚实历史披露
- **`docs/ARCHITECTURE.md` + `.zh.md`** — milestone 表加 v0.5.15 / v0.5.16 / v0.5.17 行
- **`docs/HANDOFF.md`** — Current status 更新到 v0.5.17

### 验证

- `pytest`：411/411 通过（纯文档无代码改）
- `ruff`：0 issues
- 手工 sanity：TOC anchor `#karma-自然语言--agent-替你写规则` resolve；首次读者落到 README 的章节切分合理

### 触发

本 release 由用户输 `/karma 每次commit以后必须更新所有 github 文档至最新版本...要很「爆款」的融入整体说明` 触发 — karma skill 第一次现场端到端使用加了 rule 10（`docs-sync-after-commit`），本 commit 是新加规则的第一次立即应用。

## [0.5.16] — 2026-05-15（feat — `/karma <自然语言>` skill 真工作，多 backend 装机）

### 这版为啥重要

session 内深度 audit（用户问「`/karma rule X` 能不能简化成 `/karma X`」触发）发现 **v0.5.1 起 karma skill 从未真正触发过**。根因：Claude Code skill 机制要求 `<name>/SKILL.md` 目录形式（不是裸 `<name>.md`）+ `name:` frontmatter 字段 + 单 token 命令（不是 `/karma rule` 多词）。v0.5.1 ~ v0.5.15 全部按错的假设 ship — 手工 CLI 测试能工作，但 skill 自动触发从来没工作。

本版按正确机制重建 **3 个 backend** 的 skill 装机：

| Backend | 路径 | 格式 | 触发方式 |
|---|---|---|---|
| Claude Code | `~/.claude/skills/karma/SKILL.md` | Markdown + YAML frontmatter | `/karma <args>` |
| Codex CLI | `~/.agents/skills/karma/SKILL.md`（注意 `~/.agents/` 不是 `~/.codex/`）| Markdown | `/skills` menu / `$karma <args>` inline / auto |
| Gemini CLI | `~/.gemini/skills/karma/SKILL.md` + `~/.gemini/commands/karma.toml`（双轨）| Markdown（skill）+ TOML（commands）| skill 路径 auto-trigger + commands 路径显式 `/karma <args>` |

### 改了啥

**1. 仓库 skill source 重组** — `skills/karma-rule.md`（裸文件，错）→ `skills/karma/SKILL.md`（正确目录形式）。加 `name: karma` + `description: ...` frontmatter。skill body 内所有 `/karma rule X` 引用改 `/karma X` 跟简化触发命令对齐。

**2. 新模块 `karma/skill_packaging.py`** — 格式转换处理：
- `parse_frontmatter(md_text)` — 提取 YAML frontmatter 不引入 PyYAML 依赖
- `markdown_to_toml(md_text)` — Markdown skill 转 Gemini CLI `commands/*.toml`（`description = "..."` + `prompt = """..."""`）。自动翻译 `$ARGUMENTS`（Claude/Codex）↔ `{{args}}`（Gemini），同一份 source 跨三家。

**3. `Backend` Protocol 扩展** 加 `skill_install_targets(skill_name="karma") -> list[tuple[Path, str]]`。每个 backend 声明自己装路径 + 内容格式。3 个 backend 实现：
- `ClaudeCodeBackend` → 1 个目标（Markdown）
- `CodexBackend` → 1 个目标（Markdown，`~/.agents/` 路径）
- `GeminiCLIBackend` → 2 个目标（Markdown skill + TOML commands）

**4. CLI 多 backend 支持**：
- `_install_karma_skill_multi_backend(force, backend_filter)` — 中央装机函数，遍历所有 detected backend，按格式写每个目标
- `cmd_install_skill(force, backend)` — `karma install-skill` 默认装到所有；`--backend claude-code|codex|gemini-cli` 指定单家
- `cmd_init` — 自动装到所有 backend，每个目标打印 `创建 [<backend>] karma skill: <path>`
- `cmd_doctor` — 报多 backend skill 状态（✓ 最新 / ⚠ 跟当前版本不一致 / 未装），每个 (backend, path) 一行

**5. `pyproject.toml`** — `force-include` 改 `skills/karma/SKILL.md`，`pip install karma` 装对文件。

### 现场验证（本 session）

装完 v0.5.16 在作者本机后，跑这版 release 的同一个 Claude Code session 在 `SessionStart` hook context 里出现：

> The following skills are available for use with the Skill tool:
> - **karma**: Natural-language karma rule input — refine user's plain description into karma's validated rule structure, preview, confirm, and add to rules.yaml. Use when the user types `/karma <natural language describing a rule preference>`.

**这是 karma skill 第一次真被 Claude Code 看到。** v0.5.1 ~ v0.5.15 它一直默默躺在错的路径上。

### 验证

- `tests/test_cli.py` 新增 7 个回归测试（`test_v0516_*`）：
  - 4 backend init 流程 / 第二次跑 idempotent / 用户改动保留 / `--force` 覆盖 / `--backend` filter / source 缺失 / doctor 多 backend 报告
- `pytest`：411/411 通过（404 + 新 7）
- `ruff`：0 issues
- 作者本机现场装机：4 个路径全验证（Claude/Codex/Gemini-skill/Gemini-toml 都在，大小 16944/16944/16944/16941 字节 — toml 小一点因为 frontmatter 被吸进 description 字段）

### v0.5.15 → v0.5.16 用户迁移说明

- 老的 `~/.claude/skills/karma-rule.md`（v0.5.12-15 装的裸文件）是死重，可以 `rm`
- 新 skill 下次 `karma init` 或 `karma install-skill` 自动装
- `/karma rule X` 命令从来没工作过（虽然 doc 说能），新的 `/karma X` 在 Claude Code 里能（其他家尽力）
- Codex / Gemini 支持是 best-effort — Codex 用 `/skills` menu 或 `$karma` inline；Gemini 显式 `/karma` 走 TOML commands 路径

### v0.5.1 到 v0.5.15 文档说的 vs 现实（sticky #4 诚实披露）

v0.5.1 release notes 说「Claude Code skill template at `skills/karma-rule.md` for natural-language rule input」并描述 `/karma rule <NL>` 触发。**端到端从来没工作过** 直到本版。skill 流程只在用户手工调底层 `karma rule add --from-yaml` CLI 时工作 — 自然语言 → skill 自动 refine 那条路径是空气。对前面误导的 doc 道歉。

## [0.5.15] — 2026-05-15（chore — v0.6.0 准备：起草计划稿 + 内部 `karma.sticky` → `karma.rule` import 迁移）

### 这版动机

v0.5.13 audit 号称「清完所有 `.sticky_id` callsite」但只清了属性级。起草 v0.6.0 计划时 follow-up audit 发现更深一层 miss：karma 自己源码里**还有 11 处 `from karma.sticky import ...`**（cli.py 4 处 + hooks/*.py 6 处 + 自指）— 加上 4 个测试文件里的平行 import。v0.6.0 删 `karma/sticky.py` 前，karma 自己得先不 import 它。本版修这个。

### 本版两件事

**1. v0.6.0 计划稿草稿**（[`docs/V0_6_0_PLAN.md`](./docs/V0_6_0_PLAN.md) + [`.zh.md`](./docs/V0_6_0_PLAN.zh.md)）

把废弃契约说在悬崖之前。三类：

- **Group A** — 内部脚手架（只 karma 自己引用的 alias）。零外部影响。
- **Group B** — public API 破坏性改动（`karma.sticky` 模块 / `.sticky_id` @property / `karma sticky` CLI alias）。v0.5.0 起一直 deprecated；v0.6.0 是悬崖。
- **Group C** — 盘上数据 migration（`sticky.yaml` → `rules.yaml`、老 `violations.jsonl` 的 `sticky_id` 字段兜底）。**永远保留** — 这些处理真实用户数据不是 API 表面。

含执行顺序、测试覆盖期待、风险评估、2 个开放问题（`karma sticky` CLI alias 要不要多活一个 release 周期；非中文用户的 `chinese_plain_no_jargon` 默认行为是否在 v0.6.0 范围 — 都暂定「不」延后再定）。

**2. v0.6.0 前置 import 迁移**（本版执行）

把 `from karma.sticky import X` → `from karma.rule import X`，覆盖：

- `karma/cli.py`（4 处）
- `karma/hooks/post_tool_use.py`、`hooks/stop.py`、`hooks/pre_tool_use.py`、`hooks/subagent_start.py`、`hooks/user_prompt_submit.py`、`hooks/pre_compact.py`、`hooks/session_start.py`（7 个 hook 文件共 7 处）
- `tests/test_violations.py`、`test_sticky.py`、`test_paths.py`、`test_cli.py`、`test_post_tool_use_reinject.py`（5 个测试文件）
- `test_post_tool_use_reinject.py` 里 `mock.patch("karma.sticky.load", ...)` → `mock.patch("karma.rule.load", ...)`（4 处 patch）— Python module aliasing 意味着 patch alias namespace 不会传递到真实 module，如果消费者直接 import 真实 module 的话

### 验证

- `pytest`：410/410 通过
- `pytest -W error::DeprecationWarning`：410/410 通过 — **karma 自己代码和测试里 0 处 `karma.sticky` deprecation warning** 触发
- `ruff`：0 issues
- `grep -rn "from karma.sticky" karma/ tests/` 只剩 `karma/sticky.py` shim 自己 docstring 里写的（shim 存在目的就是被 import，本身不 import 自己）

### v0.6.0 就绪状态

本版后，v0.6.0 删 `karma/sticky.py` 不会破任何内部 callsite。4 个 class/property alias（`MAX_STICKY` / `Sticky` / `StickyConfigError` / `EXAMPLE_STICKY*`）也是 — 0 内部使用者。`CheckHit` + `Violation` 上 `.sticky_id` @property 自 v0.5.13 起就 0 内部使用者。`karma sticky <subcommand>` CLI alias 在 `cli.py:1183` 是个 entry-point 分支，0 内部使用者。

简单说：v0.6.0 可以是纯删除 commit，不需要 refactor。

## [0.5.14] — 2026-05-15（docs — `karma-rule` skill 教会 Agent 用现有命令组合做 modify，不加新 CLI）

### 这版动机

dogfooding 真发现 gap：Agent 走完 skill Step 2 决策表说「modify 现有规则」，但 skill 在这里断了 — 提到 `karma rule edit` 但那命令是启动 `$EDITOR` 给用户手编（Agent 无法自动化）。Agent 没有清晰路径用现有 CLI 完成「modify」，导致我（正在 dogfooding 的 Agent）提议加新命令 `karma rule replace`。用户立刻 pushback：不要扩大 CLI 表面，把现有命令教清楚。

### 改了啥

纯 skill 文档改 — **0 个新 CLI 命令，0 行新代码**。靠把指引说清楚关掉 modify gap。

- **Step 2 下新加 "How to modify an existing rule (replace / merge / extend scope)" section**：
  - 3 步 recipe（起草 yaml → preview → `remove && add` 替换）
  - 4 行「常见 modify shape」表（Replace / Extend scope / Merge / Genuine purpose change），说明什么时候保留 `id`（几乎全保留，让 violation 历史连续）vs 什么时候用新 id
  - 明确说「为啥不用 `karma rule edit`」— 那是用户逃生口不是 Agent 路径
- **Step 6 拆两分支** — 新规则用 add，修改用 `remove && add` 链
- **原子性诚实 caveat** — 明说 `remove && add` 不是真事务（如果 `add` 在 `remove` 成功后失败，规则就丢了）；preview-first 降低风险但不消除；`cp rules.yaml rules.yaml.bak` 是便宜保险. 初稿错说 `&&` 「确保」原子性 — 同一 commit 内 catch + 修正（sticky #4：caveats 要诚实）

### 为啥不加新 CLI

用户本 session 立场原话：「不希望给用户增加一堆不常用的 skill」。Modify = remove + add，现有命令组合够用。加 `karma rule replace` 就是表面 bloat 无真能力增量 — Agent 缺的只是 recipe 写在 skill 里.

### 验证

- skill：269 → 302 行（+33），7 个 `### Step N` 标题完整，10 处 "modify" / "remove + add" / "How to modify" 引用
- `pytest`：410/410 通过（纯文档不变）
- `ruff`：0 issues

### 顺手的 user-data 改动（不在本 commit 内）

用户的 `~/.claude/karma/sticky.yaml` 里 `lighthearted-vibe` 规则被改写：作用域从「加 karma 规则对话时」扩到「整体说话方式」，对偶半句从 mild「该严肃就严肃」升级为「具体问题分析要认真深刻」。这次改写是 dogfooding 真触发，暴露了本版修的 skill gap.

## [0.5.13] — 2026-05-15（refactor — audit 驱动的 dedup：共享 `is_python_c_command` + sticky_id alias 清理 + doctor skill check）

### 本版还的债

今晚收尾代码审计发现 3 个真债。v0.5.13 一波结清。

### F1 — `_LANG_C_HEAD_RE` 在 3 个 check 文件复制粘贴

`testset.py` / `bypass_karma.py` / `non_blocking.py` 各自独立定义同款 regex `r"\b(?:python\d?|node|ruby|perl)\s+-[ce]\b"`。v0.5.9 把平行的 `_BASH_REDIR_TARGET_RE` 提到 `description_context.py` 但漏了这个。

**修复**：在 `karma/checks/common.py` 加 `is_python_c_command(cmd: str) -> bool` helper（这里是对位 home — 跟 `_SHELL_INTERPRETER_RE` / `_HEREDOC_RE` 等其他 Bash 解析工具放一起）。3 个 check 全 import + 调用 `is_python_c_command(cmd_raw)` 代替本地 pattern。

### F2 — `karma doctor` 没报 skill 装机状态

v0.5.12 加了 `karma install-skill`，但 `cmd_doctor` 只报 hook 装机不报 skill。新装用户跑 `karma doctor` 看不到 `/karma rule <NL>` 流程是否真接通。

**修复**：`cmd_doctor` 现在报 `karma-rule skill` 三态：
- "存在 ✓ 最新" — 装好且跟仓库 source 一致
- "存在 ⚠ 跟当前 karma 版本不一致" — 装着但过时（建议 `karma install-skill` 升级）
- "未装" — 没装（建议 `karma install-skill`）

### F3 — 34 处 `.sticky_id` 调用会在 v0.6.0 break

v0.5.0 宣布「sticky → rule 全代码库改名」但实际 34 处 `.sticky_id` 属性访问留存：`cli.py` (13) / hooks (`pre_tool_use.py`/`stop.py`/`user_prompt_submit.py`: 19) / 测试 (6)。靠 `Violation` 和 `CheckHit` 上的 `@property def sticky_id: return self.rule_id` 兜底默默工作。v0.6.0 移除 alias 时（dataclass comment 已注明）这些 callsite 会在远离测试表面的生产路径硬失败。

**修复**：5 个内部文件批量 `s/\b(\w+)\.sticky_id\b/$1.rule_id/g`。`@property` alias 保留在 `violations.py` 和 `_types.py` 让外部用户老代码到 v0.6.0 前仍工作。纯改名，无行为改动。

### 验证

- `tests/test_cli.py` 新加 1 个回归测试 `test_v0513_doctor_reports_skill_status` — 覆盖 3 种 doctor-skill 状态
- 3 个 fix 跟现有测试共存：409 → 410（F2 加了一个）
- `pytest`：410/410 通过
- `ruff`：0 issues

### 审计 verified 通过的维度

- 今晚 diff 里 0 处 TODO/FIXME/HACK 残留（sticky #1 长期方案守住了）
- 0 处弱声明 "应该可以" / "大概率" 在 `evidence.py` 检测 pattern 之外
- 5 个 Bash-aware check 都用统一 `tool_name == "Bash"` 守卫
- v0.5.9 refactor 清理干净（没残留 `_bash_writes_to_description_context` 或 `_DESC_CTX_PATH_RE`）

## [0.5.12] — 2026-05-15（feat — `karma init` 自动装 `karma-rule` skill + 新加 `karma install-skill` 命令）

### feat — `/karma rule <NL>` 流程对新用户开箱即用

v0.5.11 audit 发现的 gap：`skills/karma-rule.md` 在仓库里但没自动装到 `~/.claude/skills/karma-rule.md`，第一次用 karma 的用户在 Claude Code 里输 `/karma rule add a new rule about X` 触发不到 — skill 得手工 copy。本版补齐。

### 改动

- **`karma init` 末尾自动装 skill** 到 `~/.claude/skills/karma-rule.md`。首次跑打印「创建 karma-rule skill: <path>」+ `/karma rule <NL>` 用法提示。
- **新加 `karma install-skill [--force]` 子命令** 给 v0.5.12 之前装过 karma 的用户（或想升级 skill 比如 v0.5.11 clarity audit 之后）。不带 `--force` 时冲突非破坏 — 用户改过本地 skill → 新版写到 `karma-rule.md.new` 提示用户对比/合并。`--force` 强制覆盖。
- **`pyproject.toml` `force-include`** 把 `skills/karma-rule.md` 打进 wheel 让 `pip install karma` 也能用。
- **`karma --help`** 列出新的 `install-skill` 子命令带简短用法。

### 冲突处理（sticky #1：不默默覆盖用户改动）

- 文件不存在 → 装，返回 `(True, "installed")`
- 文件存在 + 内容一致 → skip，返回 `(False, "up-to-date")`
- 文件存在 + 内容不同 + `force=False` → 写 `.md.new` 兄弟文件，返回 `(False, "exists-diff")`
- 文件存在 + 内容不同 + `force=True` → 覆盖，返回 `(True, "force-overwritten")`
- Source missing（shipped wheel 理论不可能，dev install edge case 可能）→ 返回 `(False, "source-missing")`，`cmd_install_skill` 退 1，`cmd_init` 警告但不阻塞

### 验证

- `tests/test_cli.py` 新增 5 个回归测试：
  - `test_v0512_init_auto_installs_karma_rule_skill` — 首次跑装好 ✓
  - `test_v0512_init_second_run_skill_up_to_date` — 第二次跑 idempotent ✓
  - `test_v0512_init_skill_user_modified_writes_new_file` — 用户改动保留，写 `.md.new` ✓
  - `test_v0512_install_skill_force_overwrites` — `--force` 覆盖 ✓
  - `test_v0512_install_skill_handles_missing_source` — source 缺失 graceful `exit 1` ✓
- `pytest`：409/409 通过（之前 404 + 新 5）
- `ruff`：0 issues

## [0.5.11] — 2026-05-15（docs — `skills/karma-rule.md` 清晰度 audit，补 5 个 gap）

### docs — `/karma rule` skill template 5 个清晰度 gap 修复

Dogfooding 驱动的 audit。真用自然语言录入流程跑了一遍 `/karma rule` 之后，发现 5 个陌生 Agent 容易默默猜错的地方：

1. **Step 1 漏 anchor-vs-scope 歧义识别** — 用户原话「在 X 场景下要 Y」通常意思是「X 是引发例子」而不是「Y 只在 X 时生效」，但 karma v2 是 always-on 注入（无 scene routing）。skill 现在要求 Agent 直接把这个歧义明说出来对齐而不是默默猜作用域。还加了「one-off vs long-term」识别清单（`"for this PR" → one-off` / `"I always want" → long-term`），让「这事到底该不该入 karma」的判断有具体抓手。

2. **Step 2 overlap 判断无标准** — skill 之前只说「check existing rules」但没说怎么算 overlap（id 匹配？语义相似？keyword 交集？）。补了 4 行决策表覆盖 4 种 overlap 情况各自的处理动作（修改现有 / 两选项询问 / 提及 keyword 交集 / 直接新加）。

3. **Step 3 → Step 5 缺用户内联草稿审阅** — 原流程是「起草 → 写 tmp 文件 → preview → 用户看到成品 yaml」。用户想动文案要 Agent 重起一遍。skill 现在要求 Step 3 在写盘前先 inline 给用户看草稿，明说「现在说要不要动」。

4. **缺 locale-aware tone 指引** — v0.5.2 i18n 之后 karma 双 locale，但 skill 全英文示例。加了明确规则「用户跟你说哪种语言就用哪种写 preference；violation_checks 函数名保持英文不变」。中文 locale Agent 被指向 `data/rules.dev.example.zh.yaml` 作为参考模式。

5. **Step 7「啥时候生效」埋在底部** — 原 skill 在末尾独立 `## Restart Claude Code after karma rule add` section，容易漏。把「下个 UserPromptSubmit 起注入」notice 搬进 Step 7 内联第 4 条，同时把「建议删改」步骤改具体（直接点名冗余的具体规则对，不要泛泛「review for duplicates」）。删了底部独立 section。

底部 `## Common mistakes to avoid` 列表加 3 条对应 gap 1 / 4 / 3 的反例，让快速扫一眼也能 catch 高影响失败模式。

### 发现但 v0.5.11 没修

audit 顺手发现 `skills/karma-rule.md` **没被 `karma init` 自动装到** `~/.claude/skills/karma-rule.md` — 用户得手工 copy。意思是当前 `/karma rule <NL>` 流程只有手工装 skill 的用户能用。本 release 是纯文档版不在 scope，但值得 v0.5.12 加个 `karma install-skill` 或扩 `karma init`。

### 验证

- skill 结构完整：7 个 `### Step N` 标题在位（原 7 → 现 7）
- 长度：225 → 269 行（净 +44，是具体指引不是水分）
- 无代码改动 — `pytest 404/404`、`ruff 0` 不变

## [0.5.10] — 2026-05-15（docs — `karma --help` 补 `rule add` / `rule preview` 子命令列表）

### docs — `karma --help` 之前藏着 `karma rule add` / `karma rule preview`

用户授权的 dogfooding 测试（第一次端到端跑 v0.5.1 `karma rule` 流程）发现 `karma --help` 仍然只列 `karma sticky list/edit/remove` — v0.5.1 加的 `rule add` / `rule preview` / `rule list/edit/remove` 子命令已经完整实装且 dispatch 正常，但顶层 help 看不到。第一次用 karma 的用户输 `karma --help` 完全不知道 `karma rule add` 存在。

本版修 `karma/cli.py` 顶部 docstring：
- 列全 4 个 `rule` 子命令（`list` / `edit` / `remove` / `add` / `preview`）及其 flags (`--from-yaml <file>` / `--from-stdin`)
- 标注 `karma sticky` 为 v0.6.0 移除的 deprecated alias
- 末尾加 Claude Code `/karma rule <自然语言>` skill 工作流指引

实装从 v0.5.1 起一直工作；本版是纯文档修复。

### 端到端验证 (16 个 test case)

- `karma rule preview --from-stdin` 合法 yaml → schema check + 注入预览渲染 ✓
- `karma rule preview` 错误路径 (缺 id / yaml 文件不存在) → `exit 1` 带 `❌` 信息 ✓
- `karma rule add --from-stdin` 合法 yaml → schema 校验 + id 唯一性 + 上限 + REGISTRY 检查 + 写入 + 反馈 ✓
- `karma rule add --from-yaml <file>` 合法 yaml → 同流程 ✓
- `karma rule add` 重复 id → `exit 1` ✓
- `karma rule add` 未知 `violation_checks` 函数 → `exit 1` 带可用函数清单 ✓
- `karma rule add` schema 错 (缺 preference) → `exit 1` ✓
- `karma rule add` 无效 yaml → `exit 1` ✓
- `karma rule add` 无 flag → `exit 1` 带 usage + `/karma rule` skill 提示 ✓
- `karma rule` 无子命令 → `exit 1` 带子命令列表 ✓
- `karma rule foobar` 未知子命令 → `exit 1` ✓
- `karma rule list` 新加规则可见 ✓
- `karma rule remove <id>` 真删 ✓
- `karma rule remove <id>` 然后 `karma rule add` 同 id → 成功 ✓
- `rules.yaml` 真持久化 (grep 验证 5-minimal + 2 add = 7 条 ✓)

外加 `pytest` 404/404 + `ruff` 0 issues。

## [0.5.9] — 2026-05-15（refactor — Bash heredoc 豁免提到 `description_context.py`，所有 Bash-aware check 共享）

### refactor — `is_description_context(tool_name="Bash")` 落地

v0.5.8 承诺的事情，v0.5.9 兑现：testset.py 的 Bash heredoc 目标路径豁免提到 description_context.py，所有调 `is_description_context()` 的 Bash-aware check (`long_term` / `testset` 等) 自动受益。

- `description_context.py` 新加 `_classify_path(file_path) -> (bool, str)` helper（从原 Write/Edit 分支提取）
- `is_description_context()` 加 `tool_name == "Bash"` 特殊处理 — 扫命令找 `>` / `>>` redirect 目标，每个目标过 `_classify_path`；任一目标是描述上下文 → 整调用豁免
- `testset.py` v0.5.8 局部 helper 删除，行为由共享逻辑保留
- `long_term.py` 自动受益 — 例如 `echo "TODO: x" >> docs/CHANGELOG.md` 现在会豁免（之前会被错算 `TODO` marker）

### 验证

- `pytest`：404/404 通过（v0.5.8 测试仍全绿 — 同测试 case，现走共享 helper）
- `ruff`：0 issues

## [0.5.8] — 2026-05-15（fix — testset check 豁免 Bash heredoc 写到描述上下文路径）

### fix — `cat >> tests/test_x.py <<EOF ... case_id="..." ... EOF` false-positive

v0.5.7 dogfooding session 真触发：往 `tests/test_checks.py` append v0.5.7 回归测试时，heredoc body 内含 `case_id = "a1b2c3d4..."`（测试 fixture 字面），被错算「测试集 case ID 写死」拦截。根因：v0.5.5 只加了 `python -c` 豁免；姊妹场景 Bash redirect/heredoc 写到 description-context 路径 (tests/ / .md / .yaml) 漏覆盖。

跟 v0.5.5 同根因家族：当**写目标**是描述上下文路径，**写内容**是描述性的不是可执行的。今日豁免对等覆盖：

- `python -c "..."` 内容（v0.5.5）
- Bash heredoc / redirect `>` `>>` 目标路径匹配 tests/test/__tests__/spec 目录段，或 `.md/.rst/.txt/.yaml/.yml/.json/.toml/.ini/.csv/.tsv` 后缀，或 `test_*.py` / `*_test.py` 文件名（v0.5.8）

`src/runner.py` 等生产代码路径即使通过 heredoc 写仍被拦。

后续 refactor（预计 v0.5.9）会把这逻辑提到 `description_context.py`，让所有 Bash-aware check 共享豁免界面。v0.5.8 helper 暂只在 `testset.py`。

### 验证

- `tests/test_checks.py` 加 3 个回归测试：
  - `test_testset_v058_heredoc_to_tests_path_exempted` — heredoc 写 `tests/` 豁免
  - `test_testset_v058_heredoc_to_md_doc_exempted` — heredoc 写 `.md` 豁免
  - `test_testset_v058_heredoc_to_src_still_blocked` — heredoc 写 `src/` 仍拦
- `pytest`：404/404 通过（之前 401 + 新 3）
- `ruff`：0 issues

## [0.5.7] — 2026-05-15（feat — `CheckHit` + `Violation` 加 locale-agnostic `trigger_key` 字段，audit 跨 locale 分组合并）

### feat — audit 按 `trigger_key` 而非 `trigger` 字面分组

v0.5.4 i18n 后副作用：`karma audit` 按 `trigger` 字面分组，用户 zh locale 跑一周切到 en locale 后会看到「同行为分两组 counter 计数」。audit「top trigger」分析失真。

v0.5.7 加 locale-agnostic `trigger_key`（i18n key 本身，如 `"check.evidence.commit.trigger"`）作为跨 locale 稳定标识：

- **`CheckHit.trigger_key: str = ""`** — 每个 check 函数现在双传 `trigger=tr(key)`（显示用）+ `trigger_key=key`（分组用）
- **`Violation.trigger_key: str = ""`** — 写入 violations.jsonl 跟 locale-specific `trigger` 字面并存
- **`cli.py cmd_audit`** — 按 `trigger_key or trigger` 分组（缺 key 的老行 fallback 字面）
- **显示** — 仍用 locale 翻译过的 `trigger` 字面（取最早捕获的）让用户能看懂；只是计数合并

### 向后兼容

- 老 `violations.jsonl` 行无 `trigger_key` 字段读入时默认 `""`，按 `trigger` 字面分组 — 数据无损
- `to_json()` 字段空时不写入，老格式 jsonl 体积一致

### 验证

- `tests/test_checks.py` 新增 5 个回归测试：
  - `test_v057_check_hits_carry_trigger_key` — 每个 check 函数返回非空 `trigger_key`，前缀 `"check."`
  - `test_v057_violation_roundtrip_trigger_key` — 写读 jsonl 保留 `trigger_key`
  - `test_v057_violation_backward_compat_no_trigger_key` — 老行 `trigger_key=""` 不崩
  - `test_v057_audit_groups_by_trigger_key_across_locales` — 5 zh + 5 en 同 key → 一组 counter 计 10
  - `test_v057_audit_legacy_no_key_fallback_to_trigger` — 老行 fallback 按字面分组
- `pytest`：401/401 通过
- `ruff`：0 issues

## [0.5.6] — 2026-05-15（fix — keep_pushing `_PUSH_SIGNAL_RE` 补「下一推进点 / 下一步是」类未来规划短语豁免）

### fix — keep_pushing 错拦「下一推进点 / 下一步是 / 接下来打算」类合法收尾

v0.5.4 dogfooding session 真触发 7 次：每个 response 都用「下一推进点：X」/「下一步：Y」明确规划语收尾，但 `keep_pushing.check()` 仍命中默认「纯陈述完结无下一步」trigger。根因：`_PUSH_SIGNAL_RE`（v0.4.19 加的「未来推进规划」分支）漏了最常见形式 — `下一(推进点 / 步 / 个 / 波 / milestone)` + 动词。

跟 v0.4.19 同根因（`_PUSH_SIGNAL_RE` 漏未来规划表达），不同短语族。本版扩 4 个分支：

- `下一(?:推进点|步|个|个推进点|波|个 milestone|个里程碑)` — 「下一推进点 / 下一步」纯前缀
- `下一步\s*(?:是|做|打算|准备|考虑|推进|继续|去|要|想|可以|应该)` — 「下一步是/打算」+ 意图
- `接下来\s*(?:打算|准备|计划|考虑|可以|可选|的方向|的推进点)` — 「接下来打算/方向」类
- `后续\s*(?:推进|步骤|计划|打算|准备|是)` — 「后续推进/步骤」类

假亲戚「下一次再说吧」（推卸不是规划）正确不被覆盖 — 新 pattern 要求 `下一` + 规划名词，不匹配 `下一次` + 填充词。

### 验证

- `tests/test_keep_pushing.py` 加 2 个回归测试：
  - `test_v056_next_push_point_phrasing_exempted` — 6 种推进短语全豁免
  - `test_v056_partial_stop_still_blocked` — `"下一次再说吧"` 推卸语仍拦
- `pytest`：396/396 通过（之前 394 + 新 2）
- `ruff`：0 issues

## [0.5.5] — 2026-05-15（fix — testset check 补 python -c 豁免，跟 non_blocking / bypass_karma 对齐）

### fix — testset.py 漏 python -c 字符串字面豁免（dogfooding 真触发）

v0.5.3 自测时真触发：probe 脚本 `python -c "r = check(content='gold_cases.append(x)')"` 被 testset check 错拦 — 把引号内的 `gold_cases.append(x)` 字面当成真反喂调用。根因：受 `python -c` 影响的 3 个 check 里，只有 `testset.py` 漏了 `_LANG_C_HEAD_RE` 豁免（`non_blocking.py` 在 v0.4.18 加了、`bypass_karma.py` 在 v0.4.13 加了）。

本版给 `testset.py` `check()` 加同款豁免：`tool_name == "Bash"` 且命令头匹配 `\b(?:python\d?|node|ruby|perl)\s+-[ce]\b` 时直接 return None。真 bash 反喂命令（`cp eval/* train/`、`cat detail.json >> pool.jsonl`）不带 `-c` 包装仍正常拦。

### 验证

- `tests/test_checks.py` 新增 2 个回归测试：
  - `test_testset_python_c_string_literal_exempted` — 确认豁免生效
  - `test_testset_real_bash_reverse_feed_still_blocked` — 确认直接 `cp eval/* train/` 仍拦
- `pytest`：394/394 通过（之前 392 + 新 2）
- `ruff`：0 issues

## [0.5.4] — 2026-05-15（feat — Phase D 第三波：28 处 CheckHit.trigger 双语切换）

### feat — 所有 CheckHit.trigger audit 标签 i18n 化

`trigger` 字段写入 `~/.claude/karma/violations.jsonl` 用作 audit log 分类标签，是 v0.5.3 留下的最后一个双语缺口。v0.5.4 收尾：8 个 check 模块 28 处 trigger 全部走 `tr()`，跟 fix namespace 平行。

- 14 处 trigger 直接调用 — `chinese_plain` / `non_blocking` / `evidence` / `keep_pushing` / `read_first` / `bypass_karma`（含 `{term}` / `{cmd}` / `{word}` / `{tool}` / `{file_path}` / `{target}` 插值）
- 14 处 pattern 表 — `long_term` / `testset` tuple 结构改为 `(regex, trigger_key, fix_key)`，命中时双 tr() 同步翻译

### feat — `data/locales/en.yaml` + `zh.yaml` 新增 28 个 `check.*.trigger` key

原 `f"..."` 里的 `!r` 格式说明符保留，让 `'value'` 引号包裹行为不变。

### 验证

- `pytest`：392/392 通过
- `ruff`：0 issues
- 手工 probe：28 key 在 EN/ZH 双 locale 下 lookup 正确 + 插值符合预期（`time.sleep(5)`、`'真' 重复 7 次` 等）

### 本版保留中文的部分（刻意）

`data/rules.dev.example.zh.yaml` 内规则正文内容 — 这是**用户偏好**本身（中文用户装中文模板、英文用户装英文模板，靠 `_select_rule_template()` 路由），所以 per-locale 模板才是正解，不该 runtime 翻译。

## [0.5.3] — 2026-05-15（feat — Phase D 完成：8 个 check 28 处 suggested_fix 双语切换）

### feat — 8 个 check 函数 suggested_fix 全部 i18n 化

所有 `CheckHit.suggested_fix` 字段（直接进 Agent 下一 turn 上下文的关键部分）从写死中文切到 `tr()` lookup，8 个 check 模块全覆盖：

- **`karma/checks/chinese_plain.py`**（3 处）— `ratio` / `jargon` / `repeated_prefix`。注意：chinese_plain check 本身是中文用户专属，英文 default 装机时通过规则模板选择移除
- **`karma/checks/non_blocking.py`**（4 处）— `python_block` / `sleep` / `wait` / `long_task`（含 `{cmd}` 插值）
- **`karma/checks/evidence.py`**（3 处）— `commit` / `completion` / `weak_claim`
- **`karma/checks/keep_pushing.py`**（2 处）— `stop_hint` / `default`
- **`karma/checks/read_first.py`**（1 处，含 `{file_path}` 插值）
- **`karma/checks/bypass_karma.py`**（1 处）
- **`karma/checks/long_term.py`**（pattern 表内 7 处）— `long_id_branch` / `blacklist_literal` / `uppercase_const_list` / `commit_hack` / `git_skip_verify` / `todo_marker` / `patch_intent`
- **`karma/checks/testset.py`**（pattern 表内 7 处）— `reverse_feed` / `detail_writeback` / `cross_split_copy` / `detail_append` / `split_hardcode` / `hash_branch` / `case_list_hash`

`long_term` 和 `testset` 的 `_PATTERNS` tuple 结构保留，第 3 元素从字面 fix 文本改成 `fix_key`（i18n key 字符串），`check()` 函数命中时 `tr(fix_key)` lookup。pattern 表保持紧凑，翻译人员只改 `data/locales/*.yaml` 不动 Python。

### feat — `data/locales/en.yaml` + `data/locales/zh.yaml` 新增 28 个 key

`check.*.fix` namespace 覆盖所有 suggested_fix。占位符（`{term}` / `{prefix}` / `{file_path}` / `{cmd}`）runtime 走 `str.format()` 插值。

### 验证

- `pytest`：392/392 通过（v0.5.2 后无变化，新 key 是追加式）
- `ruff`：0 issues
- 手工 EN/ZH 切换实测确认 14 个新 key 在双 locale 下 lookup 正确

### 本版保留中文的部分（v0.5.3 阶段刻意保留）

- `CheckHit.trigger` 字段 — 内部 audit log 分类标签，写入 `~/.claude/karma/violations.jsonl`。不在 Agent 注入路径上，优先级低，后续小版本配合 trigger-key namespace 设计一并迁移

## [0.5.0] — 2026-05-15（**major breaking change** — sticky → rule 全代码库改名）

> **用户原话**：「将整个 karma 所有代码和文件的 sticky 字样改成 rule」+
> 「直接做成 `/karma rule XXX` 的命令」+「希望支持其他主要语言」

阶段 A 完成：sticky → rule 改名 + 向后兼容 migration。阶段 B / C / D
（自然语言录入 + i18n）在后续 release。

### 改动总览

- **核心类**：`class Sticky` → `class Rule`，`StickyConfigError` → `RuleConfigError`，`MAX_STICKY` → `MAX_RULES`（全部保留 alias 兼容到 v0.6.0）
- **模块**：`karma/sticky.py` → `karma/rule.py`（git mv 保留 history），老 `karma/sticky.py` 改成 compat shim 含 DeprecationWarning
- **字段**：`Violation.sticky_id` → `Violation.rule_id`（property `sticky_id` alias 保留），`CheckHit.sticky_id` → `CheckHit.rule_id`
- **CLI**：`karma sticky list/edit/remove` → `karma rule list/edit/remove`，老 `karma sticky` 作为 deprecated alias
- **配置文件**：`~/.claude/karma/sticky.yaml` → `~/.claude/karma/rules.yaml`，老用户跑 `karma init` 自动迁移 + backup 为 `sticky.yaml.bak`
- **data 模板**：`data/sticky.dev.example.yaml` → `data/rules.dev.example.yaml`（minimal 同），pyproject.toml force-include 路径同步

### 向后兼容（v0.5.x 保留，v0.6.0 移除）

老用户无缝升级 — 所有老 API / 老 import / 老配置都仍工作：

- `from karma.sticky import Sticky / StickyConfigError / MAX_STICKY` 仍工作（DeprecationWarning 提示迁移）
- `karma sticky list` 仍跑（同样输出 + DeprecationWarning）
- `~/.claude/karma/sticky.yaml` 仍可读（karma.rule.DEFAULT_PATH fallback 找到）
- `violations.jsonl` 老 `sticky_id` 字段读取兼容（写入新行用 `rule_id`）

### docs

- **README v5 用户驱动深度优化**（2026-05-15 仓库公开后第二轮，作者亲自给 12 个具体调整方向）— 真实用户视角落地：
  - 开篇引言改「实测违规率长程任务中降为 ≈ 0%」+「纯工程零 LLM 零依赖，违规监控响应速度 < 60ms」
  - 6 个翻车现场表格全部重写更痛点清晰（如「Agent 完成一波停下」改「用户回头一看 Agent 已经停在那里半小时」具体场景）
  - 新增「使用效果」章节列 6 类典型场景（每次对话注入 / 中段提醒 / 实时违规判断 / 子 Agent 监管 / compact 防护 / 静默停止反思）
  - 「为什么有效」去技术术语（fight-or-flight / cooperation）改用户视角描述
  - 性能表 PyYAML 当 0 依赖（Python 生态标准）+ 加「5610 行测试用例 + 500+ 小时真实开发调优」
  - 「自定义规则」加 ⚡ 下阶段重点预告（计划做可视化规则录入 + 实时预览 + 一键回归测试）
  - 装机详情合并进「0 依赖纯工程，10 秒上手」章节
  - 「8 个 hook 位置全面监管」标题 + 每条 hook 补一个解决的痛点场景
  - 「试过但放弃的」9 行原因全用用户视角改写（如 LLM 依赖原因改成「响应速度大幅下降用户体验」）
  - 删全文 karma v1 引用（FAQ + 相关项目），用户不需要知道还有 v1
  - 「相关项目」→「相关项目与致敬」+ 加 Mnilax X 文章致敬
- **README v4 重写**（2026-05-15 仓库公开后第一轮宣传点优化）— 整合两个爆款参考的 7 大表达要素：
  - 首屏量化数字 hook（学 Mnilax「错误率 41% → 3%」首屏冲击）
  - 借 Karpathy 60k stars CLAUDE.md 互补关系建立技术权威背书
  - 真痛点 + 翻车现场对照表（学 [andrej-karpathy-skills](https://github.com/forrestchang/andrej-karpathy-skills)「Problems → Solutions」表格视觉冲击）
  - 命令式 + 反问风格（每原理段加「Test: ...?」反问）
  - 「试过但放弃的」段 9 行表格透明披露 anti-pattern
  - 心智模型收尾（借 Mnilax「不是许愿清单是行为合约」改写）
  - FAQ 加「跟 Karpathy CLAUDE.md 重叠吗」明确互补关系
- 顺手 polish：GitHub repo description / 10 个 topics / issue + PR templates / CODE_OF_CONDUCT 简短中文版 / docs/ 归类详细文档 / README TOC 跳转

## [0.4.44] — 2026-05-15（fix — SubagentStop + PreCompact schema 真合规，跟 v0.4.43 Stop fix 同思路）

### 触发

v0.4.43 fix 了 Stop hook schema 违反后，起子 Agent 调研 Claude Code 官方文档
确认所有非主流 hook 的输出 schema：

| Hook | hookSpecificOutput.additionalContext 支持 |
|---|---|
| PreToolUse / UserPromptSubmit / PostToolUse / PostToolBatch | ✅ 支持（主流 4 个） |
| SessionStart | ✅ 支持（karma 用法合规） |
| SubagentStart | ✅ 支持（v0.4.30 实证子 Agent 真收到） |
| **Stop** | ❌ **不支持**（v0.4.43 已 fix） |
| **SubagentStop** | ❌ **不支持**（本版本 fix） |
| **PreCompact** | ❌ **不支持**（本版本 fix） |

### Fix 1 — SubagentStop schema 合规

`karma/hooks/subagent_stop.py` v0.4.30 起的 `hookSpecificOutput.additionalContext`
输出一直被 Claude Code 静默拒绝 — 主 Agent 根本没看到「子 Agent X 已结束」
透明度提醒。删 hookSpecificOutput 输出 → `{}` passthrough。

子 Agent state 销毁 side effect（v0.4.34 设计核心）保留。「子 Agent 结束」
事件 Claude Code UI 自身会显示，karma 不需要重复 echo。

顺手清死代码（sticky_list 加载不再用 → 删 `from karma.sticky import load`）。

### Fix 2 — PreCompact schema 合规

`karma/hooks/pre_compact.py` 同 SubagentStop 思路 — v0.4.29 起输出
`hookSpecificOutput.additionalContext` 一直被 Claude Code 静默拒绝。

snapshot 落盘 side effect 保留（SessionStart(source=compact) 重起时读 snapshot
重新注入 sticky baseline — 这才是真起作用的路径）。删 hookSpecificOutput 输出
→ `{}` passthrough。

### 测试

`tests/test_compact_hooks.py::test_pre_compact_hook_auto_allows` docstring
更新跟代码对齐（描述 snapshot 落盘 + SessionStart 重读路径，不再说
「输出 hookSpecificOutput」）。原断言用 `if "hookSpecificOutput" in output`
守卫 — 删 hookSpecificOutput 后测试仍过。

测试 392/392 + 4 件套全过 ✓。

### 教训

v0.4.x 早期阶段所有「stop 类」hook（Stop / SubagentStop / PreCompact）都被
错用了 hookSpecificOutput.additionalContext — 这是 v0.4.x 早期对协议理解不
完整的系统性错误。Claude Code 静默拒绝（不阻塞 hook 执行只 log 错），让
karma 长期以为 hook 真生效但 Agent 没看到。

子 Agent 调研真根因（不仅 Stop，三个 stop 类都同 bug）— 不要被一个 fix
满足，深挖系统性问题。

## [0.4.43] — 2026-05-15（fix — Stop hook schema 违反 + 注入文本「合作默契」语气收尾 + sticky keyword 假阳治理）

### 触发

用户报真 bug：Stop hook 输出 `{"hookSpecificOutput": {"hookEventName": "Stop",
"additionalContext": "..."}}` 被 Claude Code 报「Expected schema」错误日志 —
Stop hook 协议**不支持 hookSpecificOutput**（仅 PreToolUse / UserPromptSubmit /
PostToolUse / PostToolBatch 支持）。早期 v0.4.x 设计错误，长期被 Claude Code
静默拒绝。

### Fix 1 — Stop hook 协议层 schema 真合规

`karma/hooks/stop.py:295-301` 删幽灵代码（`hookSpecificOutput` 输出）。
违反摘要已通过 stderr ⚠️ 通知 + violations.jsonl 落盘 + 桌面通知 + 下次
UserPromptSubmit sticky 注入的偏离标记 — 不需要 Stop hook 再 echo 一遍。
无干预原因 → `print(json.dumps({}))` passthrough。

### Fix 2 — Stop hook reason 文本同步「合作默契」语气

v0.4.42 task 2 batch 1 改了 3 处包装文本但漏了 `stop.py decision=block` 的
`reason` 字段 — 仍是 v0.4.41 老版本「karma stop hook 反思提醒 ... 请自检 ...」
指控式 + 双重否定句式。改成合作回顾语气：

```
[karma — 上一回应没看到下一步推进信号]
用户是全权委托型，他期待你完成一波后立刻接着推进。
如果有方向需要他判断就明确问出来；
如果是任务真饱和合理停下，明说卡在哪一步让他知道，不要默默等。
（提醒 N/M）
```

### Fix 3 — SessionStart / SubagentStart / SubagentStop 注入文本同步语气

3 个 hook 注入文本残留旧语气：
- session_start.py：「baseline 重新加载 / 必须留在记忆里 / 别在 compact 后又犯」→
  「回想一下跟用户的默契 / session 接力 / 重起时多留意」
- subagent_start.py：「继承父 session 的核心方向」→「你是父 session 派来的子
  Agent, 继承用户的几条长期默契」
- subagent_stop.py：「sticky 仍生效」→「跟用户的默契仍生效」
- 每条 sticky 前缀 `-` → `▸` 跟 user_prompt_submit + post_tool_use 一致

### Fix 4 — sticky #1 + #2 violation_keywords 假阳收紧

本 session dogfooding 真触发：
- sticky #2「等子 Agent」keyword 在「等子 Agent 完成回报后我 review」描述
  任务依赖关系场景假阳。改「我先 X / 现在 X」一人称行动声明字面。
- sticky #1「硬编码 / 临时方案 / 短期目标」名词在「不要硬编码」「这是临时
  方案」类讨论假阳。改「意图前缀 + 动作」格式（如「我先硬编码 / 先用临时方案」）。

工程层 check（Bash sleep/wait 检测 / TODO/HACK 注释检测）不变，keyword 层
更精化双保险。

### 验证

- 测试 392/392 ✓（一处 test_stop_hook_respects_block_max assertion 更新为
  接受 `{}` passthrough 输出）
- ruff ✓ / mypy karma+tests ✓ / vulture 0 死代码
- `karma --version` = v0.4.43 ✓
- manual run Stop hook：干净 `{"decision": "block", "reason": "..."}` schema
  合规输出，干预原因外 passthrough `{}`，不再被 Claude Code 报「Expected schema」

### 后续

karma stop hook 早期所有 hookSpecificOutput 设计（v0.4.x 早期阶段）都已检查 —
SubagentStart / SubagentStop / UserPromptSubmit / PostToolUse 用法都协议合规
（这 4 个 hook 真支持 additionalContext）。

## [0.4.42] — 2026-05-15（feat — 用户 task 1/2/3/4 元层 4 任务一波落地）

### 触发

接力 session 用户元层 3 问触发深度反思 + 4 任务授权：
1. 「真字狂魔」副作用根因分析 — Agent 在 in-context mimicry 上下文「真X」前缀堆叠
2. 「想不出深度推进点」就宣告饱和 — sticky 当免战金牌而非行为指导
3. 「跨 session 数据混淆」audit/stats/doctor 显示上 session 数据当当前 session

### Task 1 — 源头文档「真X」前缀防御性堆叠清理

清理后总量 615 → ~140（降幅 77%）。各文件分布：
- HANDOFF.md: 192 → 52（子 Agent 协助清，独立 worktree 跑）
- CHANGELOG.md: 376 → 70（子 Agent 协助清）
- README.md: 29 → 10（手工清）
- ARCHITECTURE.md: 10 → 2（手工清）
- PRD.md: 7 → 4（手工清）
- CLAUDE.md: 1 → 1（语义对偶保留）

保留语义对偶（真违反/真阳/真用户/真信号/真字狂魔/真实X 等标准汉语 +
统计学术语 + 项目内梗）。

### Task 2 — 规则文本「合作默契」语气重写（三批次）

**批次 1 — 3 处包装文本**：
- `karma/sticky.py:format_for_injection` 头部「请始终遵守」→「合作默契」+
  加「这不是规则也不是审判」破除监督感；违反标记 ⚠️ → 〔上一回应这条
  有偏离，本 turn 看看能否更对齐〕合作回顾标记
- `karma/hooks/user_prompt_submit.py` 强提醒段「命中检测」→「上一回应
  没对齐默契」+ 收尾「立即按 fix 不要再犯」→「不需要为这条特意补偿过度」
- `karma/hooks/post_tool_use.py` 锚定刷新「sticky 易稀释」技术词 →
  「回想一下默契」+ 加「不需要回应这条」减 Agent 防御性自证

**批次 2 — sticky.yaml 8 条 + dev.example.yaml 7 条 preference 重写**：
起手「用户是真人 / 跟你协作的用户」共情切入 + 解释 why（短期成本 vs 长期信任）
+ 例外通道锚定具体场景 + 沟通通道（「方案分歧大就提出来跟他对齐」）。

**批次 3 — 8 个 check 共 14 处 suggested_fix 重写**：
- chinese_plain 3 / non_blocking 4 / evidence 3 / keep_pushing 2 /
  long_term 7 / testset 7 / read_first 1 / bypass_karma 1
- metric 改「用户阅读体验」/ 加用户视角痛点 + 具体替代行为模板 +
  长期信任视角

### Task 3 — chinese-plain-no-jargon 工程监督层临时撤掉

用户授权：容易执行 + 犯错代价小，靠 user_prompt_submit 头部注入提醒频率够用，
工程层每 turn 触发干扰更大。

- `~/.claude/karma/sticky.yaml` + `data/sticky.dev.example.yaml` 移除
  violation_keywords + violation_checks（保留 preference 文本提醒）
- `karma/checks/chinese_plain.py` + REGISTRY 注册保留供恢复
- `tests/test_sticky.py` 加 soft_only 例外不强制 chinese-plain 有 check

### Task 4 — stats / audit / doctor 跨 session 数据分开

权威 source：`karma/session_state.py:get_current_session_id()` 按 mtime
选主 Agent session-state 文件，比 `violations[-1].session_id` 推更权威 —
当前 session 可能完全没产生违反但仍是当前活跃。

- `karma/cli.py:cmd_stats` 加「本 ses」列对照「历史」列
- `karma/cli.py:cmd_audit` 显示当前 session id 前 8 字（如 `c6d3eb4a...`）
- `karma/cli.py:cmd_doctor` 用 `get_current_session_id()` fallback
- 3 个守护测试（空目录 / 多文件 mtime / 排除子 Agent state）

### 附带

- `pyproject.toml` 加 `[tool.mypy] ignore_missing_imports = true`（本机 / CI
  配置统一，去掉 CI workflow 重复 CLI flag）
- `tests/test_post_tool_use_reinject.py` 修 2 个 list → tuple type error

### 验证

测试 389 → 392（task 4 加 3 个 get_current_session_id 测试）。
4 件套全过：ruff ✓ / mypy karma+tests ✓ / vulture 0 死代码 / pytest 392 ✓。

### 后续观察方向

- Agent 防御反应 / 「真字狂魔」副作用 / 「合理化漏掉」等问题是否减弱
- chinese-plain 工程层撤后头部提醒频率是否够用 / 是否需要恢复工程层
- audit / stats 跨 session 对照在 dogfooding 调试时是否真好用
- 不满意可分批回滚（task 1/2/3/4 独立 commit）

## [0.4.41] — 2026-05-15（fix — keep_pushing 加 user_prompt 上下文叫停检测）

### 触发

今晚多次 dogfooding：用户明确叫停（「不用啦感谢，休息吧」）但反思 hook 反复触发即使 sticky #8 例外清单字面命中。HANDOFF v3 第三步候选段早记这是 keep_pushing.check 盲区，今晚被 dogfooding 触发到忍无可忍。

### 根因

keep_pushing.check 当前签名 `check(*, response: str = "", **_)` — 只看 Agent response 末尾，**完全看不到 user prompt 上文**。sticky #8 例外条件「用户明确叫停（停 / 不用了 / 明天再说 / 先到这等）→ 才停」字面**清单存在但 check 没去读 user 上文匹配** → 用户「不用啦」明确命中清单字面但 check 不知道仍触发反思 hook。

### Fix

按 sticky #1 长期最优雅完整修根因：

- `karma/hooks/stop.py` 加 `_read_last_user_prompt(transcript_path)` 镜像 `_read_last_assistant_response`，抽公共 `_read_last_message_text(path, msg_type)` 函数复用 reverse scan jsonl 路径
- `karma/checks/__init__.py` `run_checks` 加 `user_prompt` 入参透传给 check 函数
- `karma/checks/keep_pushing.py` `check()` 加 `user_prompt: str = ""` 入参 + 新 `_USER_STOP_HINT_RE` 匹配 sticky #8 例外字面（不用啦 / 不用了 / 休息吧 / 明天再说 / 先到这 / 算了 / 停一下 / 停下 / 别推了 / 别继续 / 不再推 / 够了 / 到此为止 / 收尾吧 / 睡吧 / 晚安 / 好了好了 / 走火入魔 等）
- 用户上 turn 命中任何字面 → 整 turn 豁免 keep-pushing 反思（**最高优先级豁免，早于其他豁免**）

### 验证

加 2 守护测试：
- `test_v0441_user_stop_hint_exempts_keep_pushing` — 7 个叫停字眼豁免（不用啦 / 好了好了 / 明天再说 / 先到这 / 算了 / 晚安 / 够了）
- `test_v0441_user_normal_prompt_no_exempt` — 对偶：正常 prompt（继续推 / 还能优化什么 / 看看 audit）不该过宽豁免，反思 hook 仍触发

测试 387 → **389 全过** + ruff 干净。

### 意义

karma 自身设计完整闭环 — sticky #8 例外条件文本里写的「用户明确叫停」字面清单**在工程层 enforced**，不是文本声明而已。今晚多次 dogfooding 触发暴露这盲区，v0.4.41 让 sticky #8 例外清单从「文本声明」变「工程层豁免」。

## [0.4.40] — 2026-05-15（fix — 反思阈值降 + chinese-plain 分母精化 + 「真字狂魔」reactive 治理）

### 触发

用户 3 条精确反馈：

1. 「反思 hook 咱们调整成最多两次触发吧」
2. 「中文比例这个设置可能不太合理，我估计应该要在工程层对于代码注释 / commit message 时的文本内容降低阈值甚至豁免，以及不统计工具调用时候的纯英文字符」
3. 「叠加效应你看要不要优化一下来减弱自证清白的压力（**减弱自证清白而不是放松这两条规则的要求**）」

### Fix

**1. 反思阈值 3 → 2**：
- `karma/config.py` `stop_block_max_per_turn` 默认 3 → 2
- `karma/hooks/stop.py` 两处 fallback 默认 3 → 2
- 用户 sticky.yaml 仍可 override

**2. chinese-plain 分母精化（不放松 40% 阈值）**：

**用户原话「不放松规则要求」严格执行** — 不改 `_MIN_CHINESE_RATIO=0.40` 阈值，改的是「分母怎么算」让 ratio 反映 Agent **自然语言**的中英比，不被工程文本污染。新加 3 个剥：

- `_DOTTED_IDENT_RE` 剥含点号工程标识符（`pre_tool_use.py` / `state.model` / `karma.hooks.session_start` / `extract_model_from_transcript()`）
- `_PATH_LITERAL_RE` 剥路径字面（`/path/to/file` / `~/.claude/karma/...`）
- `_COMMIT_MSG_RE` 剥 commit message 引号块（`git commit -m "feat(...)..."` / `gh release create --notes "..."` 内英文）

**3. 「真字狂魔」reactive 治理（治症状不治根因）**：

加 chinese_plain Check 3 「同前缀字重复 ≥ 5 次/response」检测。LLM 防御性堆「真X」前缀（如「根因 / 生效 / 完成」）触发自审提醒「证据 = 数据 / 测试通过 / 截图，不是『真X』前缀」。

白名单豁免高频合理前缀字（一/不/是/有/没/我/你/他/这/那/在）— 不算防御性堆叠。

**真 dogfooding 第一时刻就抓住测试 fixture 自己**：旧 `test_chinese_plain_markdown_emphasis_not_counted` fixture 含 5 次「真」前缀堆叠，v0.4.40 跑测试时 Check 3 第一时刻命中真违反 — 改 fixture 不堆「真」字保留原测试意图。

### 验证

加 4 条 v0.4.40 守护测试：
- `test_v0440_dotted_identifier_not_counted` — 含 5 个点号标识符不拉低中文比
- `test_v0440_path_literal_not_counted` — 路径字面不算英文
- `test_v0440_repeated_prefix_check_catches_zhen_zi_kuangmo` — 5+ 次「真X」前缀触发
- `test_v0440_repeated_common_word_not_triggered` — 高频汉字「我/不/在」等白名单豁免

测试 383 → **387 全过** + ruff 干净。

### 教训

按 sticky #1 长期最优雅 — 用户精准区分「分母算法」vs「阈值要求」是深刻：阈值是用户最高优先级方向不能改，但**算什么算自然语言**是工程实施可以精化的。这才是「不放松规则」+「根因 fix」同时满足的路径。

「真字狂魔」reactive 治理坦诚是治症状不治根因（根因是 LLM 文案训练习惯），但能减弱视觉别扭程度让 Agent 自审主动减弱前缀堆叠习惯。

## [0.4.39] — 2026-05-15（feat — model 从 transcript_path 根本路径，覆盖所有 hook）

### 触发

用户精准纠正连击：

1. 「协议数据等用户下次输入才能确认（这次是我 fake payload）。这是啥意思？怎么查 model 你不是就能查么？」— 我懒的借口
2. 「如果你查不到说明命令用的不对，claude 设计很完善的，肯定有地方能查」— 有路径深挖
3. 「我随时 /status 命令都能看到当前 model 名称，你怎么可能找不到」— 给路径方向

按 sticky #6 深挖找路径。

### 协议层 limitation 清单（dogfooding 验证）

| Hook event | payload 有 model？ |
|---|---|
| SessionStart | ✅ 有（manual run 复现脚本证明）|
| user_prompt_submit | ❌ 没（本 session 7 turn 实测数据证明 state.model 仍 None）|
| PreToolUse | ❌ 没 |
| PostToolUse | ❌ 没 |
| SubagentStart | ❌ 没（但有 agent_id + agent_type）|
| SubagentStop | ❌ 没 |

意味 v0.4.36 SessionStart payload.model 装机晚于 session 起手就拿不到，v0.4.38 user_prompt_submit 永走 fallback。

### 根本路径

所有 hook payload 有 `transcript_path` 字段 — Claude Code 把对话历史完整存 jsonl，每条 assistant message 含 model 字段（dogfooding 发现：本机当前 transcript 含 663 次 model 字面，3 个实际值 `claude-opus-4-7` / `sonnet` / `<synthetic>`）。

karma 路径：reverse scan transcript jsonl 找最后一条非合成 model 字面。

### 实施

- `karma/model_threshold.py` 加 `extract_model_from_transcript(transcript_path)` 函数 — regex 扫 raw 内容比逐行 json.parse 快 10x，reverse 取最后一个非 `<synthetic>` 实际值
- `karma/hooks/post_tool_use.py` + `karma/hooks/user_prompt_submit.py` 改用 transcript_path 路径替代之前 payload.get("model")（v0.4.36 / v0.4.38 实施）
- `karma/hooks/session_start.py` 保留 payload.model 直接拿（向后兼容）

### 验证

- 本机 dogfooding 实测复现：`extract_model_from_transcript("/Users/jhz/.claude/projects/.../<sid>.jsonl")` → 返回 `claude-opus-4-7` → `threshold_for_model` 返回 80000 ✓
- 测试 383 全过 + ruff 干净

### 依赖（深挖路径已尽 — 等子 Agent 协议查实）

depper 调研 `/status` 命令信息源中 — 可能 Claude Code 进程内 IPC 状态（不在文件系统）。当前 transcript jsonl 是**hook 视角已知最权威路径**。如果调研发现更直接路径（如 sessions/<pid>.json 含 model）会发 v0.4.40 升级。

### 已检查路径（按 sticky #4 老实清单）

- ✅ `~/.claude/settings.json` model 字段：是 user 配置的 default 不是 runtime
- ✅ `~/.claude/sessions/<pid>.json`：含 sessionId / pid / version / status 但**没 model** ✗
- ✅ `~/.claude/session-env/<session_id>/`：空
- ✅ `~/.claude/cache / debug`：没 runtime model
- ✅ `~/.claude/projects/.../<session_id>.jsonl`（transcript）：✅ **含每条 message model 字段**
- ⏸️ `/status` 命令信息源：可能进程内 IPC（hook 视角难拿），等调研

### 闭环架构升级

v0.4.34 子 Agent 独立 state + v0.4.35 model_threshold 表 + **v0.4.39 transcript_path 根本路径** = 完整按当前模型实时自动适应阈值架构（替代 v0.4.36 / v0.4.38 协议层假设错的 payload.model 直接拿 — 那俩协议层走不通，但容错设计救场没爆炸）。

## [0.4.38] — 2026-05-15（feat — user_prompt_submit 每 turn 跟踪主 model 跨 turn 切换）

### 触发

用户洞察：「主 Agent 的 LLM 也有可能是其他的，有没有可能每一 turn 启动的时候也判断下？来决定这一 turn 的中段触发频率？」

v0.4.36 把主 Agent model 拿取放在 SessionStart hook（session 起手一次）— 但用户中途 `/model opus` 切换主模型后：

- SessionStart 早过 → state.model 永远是起手值
- 中段注入仍按旧 model 阈值 → 错配

### 路径

`user_prompt_submit` hook 每 turn 都触发（已用于 turn_count += 1 + tool_byte_seq 归零等）— 加几行从 payload 读 model 写 state.model 几乎零成本。

```python
payload_model = payload.get("model")
if payload_model:
    state.model = payload_model
```

容错设计跟 v0.4.36 SessionStart 同 — 协议层有 model 字段就用，没就保留之前值（fallback 到 SessionStart 那次写入或 DEFAULT 60K）。

### 覆盖场景

| Agent / 场景 | model 来源 |
|---|---|
| 主 Agent session 起手 | SessionStart payload.model （v0.4.36）|
| 主 Agent 中途 /model 切换 | **user_prompt_submit payload.model 每 turn 跟踪**（v0.4.38）|
| 子 Agent (主指定 model) | 主 PreToolUse Agent tool_input.model（v0.4.37）|
| 子 Agent (主没指定 model) | 拿不到 → DEFAULT 60K fallback |

### 验证

- 加 1 守护测试覆盖 user_prompt_submit 写 model 路径（连续 2 turn 不同 model 切换不抛异常 + 容错正确）
- 测试 382 → **383 全过** + ruff 干净
- 协议层是否带 model 字段：当前 manual run 实验未确认（容错设计不依赖 — 有就用没保留之前），dogfooding 持续观察

### 闭环升级

v0.4.34（子 Agent 独立 state）+ v0.4.35（model_threshold 表）+ v0.4.36（SessionStart 主 model）+ v0.4.37（子 Agent model 捕获）+ v0.4.38（user_prompt_submit 每 turn 跟踪主 model）= **完整按当前模型实时自动适应阈值架构**，覆盖：
- session 起手主 model
- 中途 /model 切换主 model
- 主 Agent 派子 Agent 时指定子 model
- 子 Agent 跑长任务时按子 model 阈值

## [0.4.37] — 2026-05-15（feat — 子 Agent model 捕获从主 Agent Task tool input）

### 触发

用户精准纠正：「你刚才问的这俩问题都是不需要我回答的，你自己试一下就知道答案了...」

按 sticky #4 老实做实验拿实测数据：临时给 PreToolUse hook 加 debug dump 所有 payload → 派 sonnet 子 Agent → 看真 tool_name + tool_input。

### 发现（manual run 实验数据）

```
PreToolUse 真 payload (派 sonnet 子 Agent 时):
  tool_name: "Agent"  ← 实际名是 "Agent" 不是 "Task"
  tool_input keys: ["description", "prompt", "subagent_type", "model"]
  tool_input.model: "sonnet"  ← 捕获子 Agent 模型!
  agent_id: None (主 Agent 视角)
```

意味 v0.4.36 没修的子 Agent 模型盲区**有路径解决** — 不是 SubagentStart payload（确实没 model），而是主 Agent **PreToolUse(tool_name="Agent")** 触发时 tool_input 含 model 字段。

### 实施

完整流程：

```
主 Agent 跑 Agent tool (model=sonnet) 派子 Agent
  ↓
主 PreToolUse(Agent, model=sonnet) → karma 入队 main_state.pending_subagent_models
  ↓
SubagentStart(agent_id=uuid) → karma pop 队首 → 写子 Agent state.model = "sonnet"
  ↓
子 Agent 内 PostToolUse → 用子 state.model → threshold_for_model("sonnet") = 60K
  ↓
SubagentStop → purge_subagent_state（v0.4.34 已实施）
```

代码改动：

- `karma/session_state.py`: `SessionState` 加 `pending_subagent_models: list[str]` 字段 + load/save 序列化
- `karma/hooks/pre_tool_use.py`: if `tool_name == "Agent"` and `tool_input.get("model")` → `main_state.pending_subagent_models.append(model)` + save
- `karma/hooks/subagent_start.py`: load 主 state → pop 队首 → 写子 Agent state.model + save 主 state（清队列）+ save 子 state

### FIFO 假设

主 Agent 派多个并行子 Agent 时假设 SubagentStart 触发顺序跟主 PreToolUse 入队顺序一致（FIFO）。dogfooding 持续观察验证 — 如果真 Claude Code 协议层并行 Task 顺序非确定就需要换 agent_type 匹配（更复杂）。

### 验证

- 加 2 条 `tests/test_subagent_isolation.py` 守护测试：
  - `test_pending_subagent_models_fifo_queue`：3 个并行 Task FIFO 队列实际行为
  - `test_subagent_state_model_drives_threshold`：主 opus 80K + 子 sonnet 60K + 子 haiku 30K 各自独立阈值
- 测试 380 → **382 全过** + ruff 干净

### 闭环

v0.4.34 子 Agent 独立 state（agent_id 路由）+ v0.4.35 model_threshold 表 + v0.4.36 SessionStart 主 model 拿取 + v0.4.37 子 Agent model 捕获 = **完整按模型自动适应阈值架构**：

| Agent 类型 | model 来源 | 阈值路径 |
|---|---|---|
| 主 Agent | SessionStart payload.model | state.model → threshold_for_model |
| 子 Agent (主指定 model) | 主 PreToolUse Agent tool_input.model | pending 队 → SubagentStart pop → 子 state.model → threshold |
| 子 Agent (主没指定 model) | 拿不到 | 子 state.model=None → DEFAULT 60K fallback |

### 教训

- 不要凭印象猜协议字段名 — 我之前以为 tool_name 是 "Task"，实际是 "Agent"
- manual run 实验拿实测数据比派子 Agent 调研协议文档**更精准** — 文档可能滞后或漏字段
- 用户「你自己试一下就知道答案了」是智慧 — sticky #6 read-before-write 在协议层就是 manual run 实测数据

## [0.4.36] — 2026-05-15（fix — v0.4.35 真协议层 limitation 修：SessionStart 拿 model 写 state）

### 触发

子 Agent 协议查实揭 v0.4.35 盲区：

- ✅ **SessionStart payload 有 model 字段**（主 Agent 起手）
- ❌ **PreToolUse / PostToolUse / SubagentStart / SubagentStop / Stop 都没 model 字段**（Claude Code 本地协议）

v0.4.35 把 model 字段读取放在 PostToolUse hook 里 — 但 PostToolUse payload **没 model 字段** → state.model 永空 → 永走 DEFAULT 60K fallback。「按模型自适应」名不副实。

### 状态老实评估

| v0.4.35 功能 | 生效状态 |
|---|---|
| 默认阈值 8K → 60K | ✅ 生效（用户最高要求满足）|
| 按模型自适应（Opus 80K / Sonnet 60K / Haiku 30K）| ❌ **没生效** — payload 永没 model 永走 fallback |

### Fix

- `karma/hooks/session_start.py` 加从 payload 读 model 写 state.model — Claude Code 本地协议下唯一暴露 model 的事件
- 主 Agent state.model 在 SessionStart 时一次写入，后续 PostToolUse 用 `threshold_for_model(state.model)` 按模型阈值
- 子 Agent 模型仍盲区（SubagentStart 没 model 字段）→ 走 DEFAULT 60K fallback（保守诚实，不假装跟主 Agent 同模型）

生效证据：
```
echo '{"source":"startup","session_id":"test","model":"claude-opus-4-7"}' | python -m karma.hooks.session_start
cat ~/.claude/karma/session-state/test.json | grep model
→ "model": "claude-opus-4-7"  ✓
```

### 验证

- 加 `test_session_start_writes_model_to_state` 守护测试
- 测试 379 → **380 全过** + ruff 干净
- 复现脚本 SessionStart 写 state.model（CHANGELOG 含证据）

### 教训

- v0.4.35 实施假设「PostToolUse payload 有 model」是错的 — 没查实协议就实施
- 容错设计（`payload.get("model")` + fallback）救场 — 即使协议没字段也能用 60K fallback 不爆炸
- 协议查实必须 web 验证，不能凭印象（像 v0.4.32 8K 阈值是 Liu 2023 旧数据撑场，v0.4.35 假设 PostToolUse 有 model 是没查实）
- 子 Agent 模型识别路径还在演化（v0.4.37 候选：从主 Agent PreToolUse `tool_name="Task" tool_input.model="sonnet"` 截获 → SubagentStart 时对接 agent_id）

## [0.4.35] — 2026-05-15（feat — 中段注入阈值按模型自动适配 + 默认抬到 60K 跟当代 Claude 衰减区对齐）

### 触发

用户洞察连击两条：

1. **数字根因**：「当代 Claude Sonnet/Opus 4.6 衰减拐点 70K-200K 不是 8K，差距 10x，建议注入阈值改成至少 60K」
2. **多模型场景**：「子 Agent 经常用 Sonnet 或 Haiku 模型而主 Agent 用 Opus，能不能自动识别和自动适应不用用户手动调？」

v0.4.32 用 8K 阈值是 Liu 2023 旧模型数据撑场（GPT-3.5/Claude-1.3 时代）— web 调研发现当代 Claude 衰减拐点实际在 70K-200K，差 10x。8K 频率太密导致 Agent 表达扭曲（v0.4.32 commit 实证「真字癫狂」副作用）。

### 协议依据

不同模型衰减区入口（基于 Anthropic 公开 + RULER/MRCR/NIAH 2026 benchmark）：

- **Opus 4.x**：~70K-100K → 阈值 80K
- **Sonnet 4.x**：~50K-70K → 阈值 60K
- **Haiku 4.x**：~20K-40K → 阈值 30K
- **老模型** (GPT-3.5 / Claude-1.3 时代)：8K → 阈值 8K（向后兼容 Liu 2023 数据）
- **未知模型 fallback**：60K（按用户「至少 60K」保守原则）

### Fix（按模型自动适配，无需用户手动配）

- `karma/model_threshold.py` 新模块：`threshold_for_model(model: str | None) -> int` 关键词匹配 + 7 条守护测试覆盖（opus / sonnet / haiku / 老模型 / 未知 fallback / 大小写 / 关键词优先级）
- `karma/session_state.py` `SessionState` 加 `model: str | None = None` 字段 + load/save 序列化
- `karma/hooks/post_tool_use.py`：从 payload `model` 字段更新 `state.model` + `_build_smart_reinject` 阈值优先级 = sticky.yaml 显式配置 > `threshold_for_model(state.model)` 按模型 > DEFAULT 60K

容错设计：协议层有 model 字段就用，没字段就 fallback 60K（不依赖具体协议查实结果，向前向后兼容）。

### 验证

- `tests/test_model_threshold.py` 7 条守护测试全过
- `tests/test_post_tool_use_reinject.py` 加 2 条按模型适配测试（opus 80K vs haiku 30K 实际行为对比）
- 旧测试预设阈值改 sonnet 60K 实际行为
- 测试 370 → **379 全过** + ruff 干净

### 效果预估

| 模型场景 | 之前 v0.4.32 (8K) | 现在 v0.4.35 |
|---|---|---|
| Opus 跑长任务（典型 1 turn 50 tool call ≈ 100K context）| 12 次注入 | 1 次（80K 阈值）|
| Sonnet 子 Agent 跑长任务 | 12 次注入 | 1-2 次（60K 阈值）|
| Haiku 子 Agent 短任务 | 频繁 | 按 30K 衰减区刷新 |

「真字癫狂」副作用在 Opus 主场景几乎消除（每 turn 1 次提醒 = sticky 重要时刻）。

## [0.4.34] — 2026-05-15（feat — 子 Agent 独立 karma 监控架构 + v0.4.32 叙事对齐 + v3 第七步验证完成）

### 触发

用户洞察：「子 Agent 的行为能不能起一个临时 karma 监控并精准注入到子 Agent 的运行过程中，不影响主 Agent，并且子 Agent 结束运行就自动销毁。这本来就是两个完全不同的进程彼此互不干扰才对。」

v3 第七步验证发现：派 Explore 子 Agent 跑 `Bash sleep 1` → violations.jsonl 新增 1 条，但 **session_id 是主 session 下** —— 子 Agent 真违反污染主 session 的 stats / audit / force_block 累积。这是设计盲区。

### 根因 + 协议

子 Agent 协议查实（Claude Code 官方 hooks docs）：

- **agent_id 字段实际存在** — 主 Agent 字段缺失，子 Agent (Task tool 启动) 含 uuid
- **session_id 设计是子 Agent 共享主 session_id** — 区分主/子的唯一信号是 `agent_id` 字段有无
- karma 当前 `pre_tool_use.py:64` 只读 `session_id` 没读 `agent_id` → 根因

### Fix（基于 agent_id 字段路由）

按用户「彼此互不干扰 + 临时独立 + 自动销毁」原则，长期最优雅 split：

- **state（ephemeral 跨 hook 共享数据）** → 子 Agent 独立文件 + SubagentStop 销毁
- **violations.jsonl（历史审计数据）** → 单文件加 `agent_id` 字段区分（不销毁，保留历史 audit 区分主/子）

代码改动（约 60 行）：

- `karma/session_state.py`: `_state_path / load / save` 加 `agent_id` 可选参数 — 给的话路径加 `__<agent_id>` 后缀；新加 `purge_subagent_state(session_id, agent_id)` 销毁 + `SessionState` 加 `agent_id: str | None = None` 字段
- `karma/violations.py`: `Violation` 加 `agent_id` 字段 + `to_json` 序列化（None 不写省 jsonl 体积 + 向后兼容） + `detect()` 接受 `agent_id` 参数透传
- `karma/hooks/pre_tool_use.py`: 读 `agent_id = payload.get("agent_id")` + `state = session_state.load(session_id, agent_id=agent_id)` + Violation 写 agent_id
- `karma/hooks/post_tool_use.py`: 同上路由
- `karma/hooks/stop.py`: 同上路由
- `karma/hooks/subagent_stop.py`: 加 `purge_subagent_state(session_id, agent_id)` 销毁子 Agent 临时 state + 文案改「临时 state 已自动销毁」

### 验证

加 6 条 `tests/test_subagent_isolation.py` 守护测试：

- 主 Agent state 路径保持向后兼容 = `<session_id>.json`
- 子 Agent state 路径加 `__<agent_id>` 后缀
- 子 Agent state 跟主 Agent 完全独立 load/save 互不污染
- `purge_subagent_state` 删子 Agent state 文件
- 销毁子 Agent state 不影响主 Agent state
- Violation `agent_id=None` 时 to_json 不写字段（向后兼容）；非 None 时写

测试 364 → **370 全过** + ruff 干净。

### docs — v0.4.32 阈值叙事依据对齐 + v3 第七步验证完成（2026-05-15）

**v0.4.32 阈值叙事错配根因**（用户挑战「上下文衰减区间是不是 10K」触发 web 调研）：

我之前给 8K 阈值的依据「~5-10K token 开始衰减」是 Liu 2023 旧模型数据撑当代场。web 研究发现：

- **当代 Claude Sonnet/Opus 4.6 衰减拐点 70K-200K**（不是 8K）
- **Anthropic 200K 是原生可靠边界**（超 200K 收 2x 附加费）
- Liu 2023 的 8K 衰减数据来自 GPT-3.5/Claude-1.3 旧模型时代
- 严重衰减（50%+）只在 1M token + 多针检索极端场景

**叙事对齐**（不改数字改语义）：

karma 8K 阈值不是「模型开始忘」的判据，是「sticky 在 attention 里被新上下文**稀释**到该重新锚定」的判据 — 价值是**抗稀释**不是**抗遗忘**。Liu 2023 数据撑当代阈值依据是错的，但 8K 抗稀释频率在工程层仍合理。

文档 / 注释改：
- `karma/session_state.py` `tool_byte_seq` 字段注释加 v0.4.34 叙事对齐说明
- `karma/hooks/post_tool_use.py` `_build_smart_reinject` docstring 改「衰减」→「稀释」
- 中段注入 additionalContext 文案：「中段提醒 — context 累积 ~XK token，sticky 易衰减」→「锚定刷新 — context 累积 ~XK token，sticky 易被新上下文稀释」

**v3 第七步验证完成结论**（manual run 子 Agent 触发实验）：

派 Explore 子 Agent 跑 `Bash sleep 1`（触发 non-blocking-parallel sticky）— violations.jsonl 新增 1 条 `sess=2f563164 turn=4 [non-blocking-parallel]: 'sleep 1'`，**session_id 是主 session 下** ✓。

**根本结论**：**路径 A 生效** — 子 Agent 内 Bash 被主 PreToolUse hook 拦 + 写主 violations.jsonl + 主 Stop hook 也会扫子 Agent 完成响应文本。**karma 当前架构已自动监管子 Agent 内 tool 调用**，不需要写新 SubagentStop transcript scan 机制（路径 B）。

HANDOFF v3 第七步候选段从「待验证」改成「验证完成 — 不需要新机制」。



## [0.4.33] — 2026-05-15（fix — strip_shell_quoted_literals 复合 shell 嵌套根因）

### 触发

v0.4.32 commit + tag + push 都成功，但 `gh release create` 命令被自己的 deep-fix-not-bypass check 拦了 — release notes 里描述用户场景的 markdown 反引号包字面 `` `cat ~/.claude/karma/session-state/xxx.json` `` 被错当 shell command substitution 保留扫到外层 cmd。

### 根因

strip_shell_quoted_literals 函数 Step 顺序错：

- 之前：Step 0 双引号 hoist substitution → Step 1 indirect 抽 backtick / $() 到 placeholder → Step 2 heredoc 剥
- 问题：heredoc 内 markdown 反引号 `` ` ` `` 在 Step 1 被先抽到 placeholder → Step 2 heredoc 剥时 placeholder 已不在 heredoc 内容里 → Step 4 替回保留扫漏

附带：`_heredoc_prefix_command` 计算 heredoc head 命令时 boundary 不含 `(` → `$(cat <<EOF)` / `(cat <<EOF)` 子 shell 嵌套时 prefix 取错（取外层 `gh` 而不是真 heredoc 头 `cat`）。

### Fix

- strip Step 顺序：**heredoc 先于 indirect 处理** — 让 heredoc 内一切字面（含反引号 / 引号 / `$()`）跟 heredoc 一起按 prefix 命令决定剥/保留
- `_heredoc_prefix_command` 加 `(` 到 boundary 集合 — 正确识别子 shell 嵌套 heredoc 头
- 加 2 条守护测试：release notes markdown 反引号路径不漏 + `$(cat <<EOF)` 嵌套 prefix 识别 cat

### 验证

- 复现脚本 `gh release create --notes "$(cat <<'EOF' ...`cat ~/.claude/karma/session-state/...` ... EOF)"` strip 后**完全干净** ✓
- 测试 362 → 364 全过 + ruff 干净 + vulture 0 死代码
- v0.4.32 同时 release 触发 v0.4.33 根因 fix

## [0.4.32] — 2026-05-15（fix — bypass_karma `json.dumps` 假阳 + feat — 中段注入 token 启发式频率优化）

### 触发

接力 session 用户反馈两件事：

1. **「真」字防御性写作走火入魔** — 用户原话「真字癫狂真吓人，这是哪条规则把你吓成这样」。HANDOFF 第 7 类深层矛盾「sticky 长期注入扭曲 Agent 表达自然度」**复发预言中** — v0.4.24 中段注入今晚 60+ 次后 Agent 用「真」字防御性自证（根因 / 生效 / 完成）堆 30+ 次/response。
2. **bypass_karma 假阳拦 cat 读** — 用户调试时 `cat ~/.claude/karma/session-state/xxx.json | python -c "import json; d = json.load(...); print(json.dumps(d))"` 被 deep-fix-not-bypass 拦了。但这是纯 read-only 输出，没写任何 karma 文件。

### 根因 + 真 fix

**bypass_karma 假阳根因**：`_PYTHON_OR_SHELL_WRITE_RE` 里 `json\.dump` regex **没加 word boundary** `\b` → `json.dumps`（序列化为字符串纯输出）被误判 `json.dump`（写 file-like）。同样 `p\.write` 也缺边界（`p.writeable` 类字面会假阳）。

修：`r"json\.dump\b|p\.write\b"` 加 `\b`，加 3 条守护测试（cat 读 / json.dumps 假阳 / json.dump 写对偶）。

**中段注入频率根因 + 升级**（用户决策驱动）：

karma turn 定义 = `state.turn_count += 1` 在 user_prompt_submit hook = **1 turn = 1 次 user 提问 + Agent 全部响应**（哪怕跑 100 个 tool call）。所以「最近 5 turn 内触发 sticky 就注入」在长任务里**永远窗口内**，每个 PostToolUse 都注入 → 频率 60+/turn → Agent 表达扭曲。

用户决策的设计意图：

1. 中段注入是「抵御长 turn context 累积导致 sticky attention 衰减」补丁，不是惩罚机制
2. 每 turn 起手 user_prompt_submit 已全量注入 → 中段不该立即重复
3. 发生违反时 PreToolUse / Stop 已响亮提醒 → 中段不重复警告
4. 累积 token 达阈值（默认 8000）后下个 PostToolUse 注入一次「重新锚定」
5. 子 Agent 也按主 Agent 实际看到的最终 tool_response 算（不算子 Agent 内部 thinking）

实施：

- `karma/session_state.py` 加 `tool_byte_seq` + `last_reinject_byte_seq` 两字段 + load/save 序列化
- `karma/hooks/user_prompt_submit.py` 每 turn 起手 `tool_byte_seq=0` + `last_reinject_byte_seq=0` 归零
- `karma/hooks/post_tool_use.py` 加 `_estimate_tokens(tool_input, tool_response)` = `len // 3` 启发式 + 累积 + 阈值判定 + 注入后重置 last_reinject_byte_seq 节流
- `data/sticky.dev.example.yaml` 加 `reinject_every_n_tokens: 8000` 配置（待补，用户首装可调）

实测预估今晚 60+ 注入 → 降到 6-8 次（10x 减少），不丢「真违反时强干预」（PreToolUse / Stop hook 仍立即拦）。

加 `tests/test_post_tool_use_reinject.py` 7 条单元测试守护：
- _estimate_tokens 简单 Bash / sub-agent 都按主 Agent 实际看到的算
- 累积未达阈值不注入
- 累积达阈值 + 有最近触发 sticky 才注入
- 注入后重置 last_reinject_byte_seq 节流（不重复）
- 阈值达但无最近触发 sticky 不注入但仍更新 last_reinject_byte_seq（节流）
- turn=0 不注入

测试 355 → 362 全过 + ruff 干净 + vulture 0 死代码。

### 教训

- 「Agent 防御性写作扭曲」是 sticky 注入频率太密的真信号，不是 sticky 内容问题 — 不能靠改 sticky 文案治理，要从工程层降频率
- 「按 turn 计数」对长任务无效（turn 几乎不增长任务里），按 token 累积维度才合理
- 子 Agent context 是子 Agent 自己的事，不算主 Agent 衰减 — 这条用户洞察纠正了我先前「sub-agent 当 30K token」启发式的错估

## [0.4.31] — 2026-05-14（fix — subagent_start.py ensure_ascii bug + 加守护测试）

### 触发

v0.4.30 装机后实际跑子 Agent，主动跑 wrapper 实际行为验证发现 subagent_start.py
没用 `ensure_ascii=False`，子 Agent 收到的 additionalContext 是
`\\u4e2d\\u6587` 类 unicode 转义乱码看不懂。subagent_stop.py 是新写的用了
`ensure_ascii=False` ✓，subagent_start.py 是早期 stub 没改。

### 修

- `karma/hooks/subagent_start.py` 用 `ensure_ascii=False` 输出中文 +
  passthrough 抽公共函数 + 文本表达跟其他 hook 风格统一（去 emoji + 用
  `[karma 子 Agent 继承父 session 的核心方向]` 格式跟 SessionStart baseline
  对齐）
- 加 `test_subagent_hooks_output_real_chinese_not_unicode_escape` 守护测试
  检查 raw stdout 不含 `\\u4e` / `\\u5e` 类 unicode 转义字面 — 永防 ensure_ascii
  bug 复发

测试 351 → 352 + ruff 干净 + 装机后 wrapper 实际输出中文验证通过。

### 教训

装机层 「触发」证据收集要直接跑 wrapper 看实际输出 stdout，不能只看「主
Agent UI 显示了 system-reminder」 — 不同 hook event additionalContext 注入
位置不同（SessionStart / PostToolUse 进 system-reminder UI；SubagentStart
进子 Agent context；SubagentStop 进主 Agent context 但不一定显示成 UI 提醒）。
直接 manual run wrapper 才是协议层验证。

## [0.4.30] — 2026-05-14（feat — karma v3 第六步：SubagentStart/Stop 装机 + 删 PostCompact 幽灵代码）

### 触发

v0.4.29 后接力 session，子 Agent 调研 Claude Code 协议查实：

- **PostCompact 协议层不支持 `additionalContext`** — v0.4.29 留的 post_compact.py
  整段是「幽灵代码」（输出会被 Claude Code 静默丢），不是 karma 实现 bug 是
  Claude Code 协议设计本身。两端夹击 compact 失忆已由 PreCompact 落盘 +
  SessionStart(source=compact) 读盘覆盖（v0.4.29 落地），PostCompact 路径走
  不通
- **SubagentStart / SubagentStop 支持 `additionalContext`** — Claude Code
  支持这两个 hook event 让 sticky 跨子 Agent 边界传递

### 落地

- `karma/hooks/post_compact.py` **删** — 幽灵代码，留着是技术债
- `karma/hooks/subagent_start.py` 装 — 子 Agent 启动时注入 sticky baseline
  到子 Agent 上下文（注入位置是子 Agent 不是主 Agent）让子 Agent 跑长任务
  也按这些方向
- `karma/hooks/subagent_stop.py` 重写 — 早期 stub 用 substring match 扫子
  Agent transcript 假阳爆发（子 Agent 在分析问题里写「先打个补丁」字面也算
  违反），改成纯透明度提醒 + sticky id 回声「子 Agent X 已完成，sticky 仍
  生效，接结果时自检」。真违反检测交给主 Agent 处理子 Agent 结果时的
  PreToolUse / PostToolUse / Stop 三道 hook 自然兜
- `karma/backends/claude_code.py` `_HOOK_EVENTS` 加 SubagentStart / SubagentStop —
  install-hooks 现装 8 个 hook event（v0.4.29 是 6 个）

### 顺手治理

- `tests/test_cli.py` 3 处 `len(...) == 6` 硬编码改 `len(_HOOK_EVENTS)`
  动态算 — v0.4.28 / v0.4.29 / v0.4.30 三次加 hook 都得改这数字是反 pattern，
  按 sticky #1 长期根本永久消除
- `tests/test_locale_detect.py` 加 autouse fixture 清所有 LC_* 环境变量 —
  作者本机 LC_MESSAGES=en_US.UTF-8 干扰 setenv 类测试假 hit en，main 上历史
  fail 顺手修根因
- README / ARCHITECTURE / PRD 同步「8 个 hook event」+ 装机示例输出加新
  wrapper 名 + v3 第六步演化条目 + 测试数 351

测试 304 → 351 全过 + ruff 干净 + vulture 0 死代码。

## [0.4.29] — 2026-05-14（feat — karma v3 第五步：PreCompact 落盘 + 两端夹击 compact 失忆 / CI 修）

### 触发

用户指令：「别阻止自动 compact，这是个保护机制不是咱们应该干扰的机制，剩下两个
很好：PreCompact 落盘 sticky 完整状态 / SessionStart(source=compact) 重起强注入」。

同时 CI 4 个 job 全失败 — ruff 4 个错（karma 早期 stub 文件 unused import / var）：
- `karma/hooks/subagent_start.py:29` unused `agent_id`
- `tests/test_compact_hooks.py` 3 个 unused import (`Path` / `mock` / `Sticky`)

### Fix

**1. CI lint 修**：
- `subagent_start.py` 删 `agent_id = payload.get(...)` unused assign（改 `_payload`）
- `test_compact_hooks.py` 删 3 个 unused import
- `pre_compact.py` ruff F541 5 处 f-string 没占位符自动修

**2. karma v3 第五步落地** — PreCompact 升级（早期 stub 用 `continue: false`
想阻止 compact，错。compact 是 Claude Code 保护机制 karma 不该干扰。改成纯落盘 +
注入 reminder）：

- 落盘 sticky 完整状态到 `~/.claude/karma/pre_compact_snapshot.md`：
  - 完整 sticky.yaml 内容（id + 多行 preference）
  - 最近 5 turn 真违反清单（让 compact 后 Agent 知道之前撞过哪些 sticky）
  - compact 触发时间 + session_id
- 注入 `additionalContext` 让 Claude 看到「即将 compact — sticky 已落盘，重起会强注入」

**3. SessionStart(source=compact) 读盘**：
- 在 v0.4.28 baseline 注入基础上，compact 场景额外读 `pre_compact_snapshot.md`
  提取「compact 前最近 5 turn 违反过的 sticky」段附加注入
- compact 失忆两端夹击形成：PreCompact 落盘 + SessionStart 读盘

**4. backends 注册**：
- `claude_code.py` `_HOOK_EVENTS` 加 `"PreCompact": "pre_compact"`（matcher=`*`
  区分 manual / auto）— install-hooks 装 wrapper 到 `~/.claude/settings.json`
- 测试 `len(cc_wrappers) == 5` → `== 6`（含 PreCompact）

### 设计原则

不阻止 compact — compact 是 Claude Code 保护长 session 不爆 token 的机制，karma
做的是「让 sticky 跨 compact 不丢」不是「让 compact 不发生」。两个不同问题。

### 验证

352 测试全过 + ruff / mypy / vulture 全绿。CI 4 job 应该通过。

### 安装升级

已装用户跑：`karma install-hooks --backend claude-code` 重装加新 PreCompact 入口。

### karma v3 演化清单（5 步）

- v0.4.24 中段注入 anchor（PostToolUse 信道）
- v0.4.25 字面多样性元行为监测
- v0.4.26→v0.4.27 反思式语气改造
- v0.4.28 SessionStart sticky baseline
- **v0.4.29 PreCompact 落盘 + SessionStart 读盘两端夹击 compact 失忆**

## [0.4.28] — 2026-05-14（feat — karma v3 第四步：SessionStart 注入 sticky baseline）

### 触发

用户问：「claude 的 hook 接口还有好多个，研究下其他几个还没有使用的 hook 接口
有哪些对咱们 karma 有价值值得探索一下」。子 Agent 研究 9 个未用 hook 协议后
排序，**SessionStart 工程量最小价值最高**：

- 支持 `additionalContext` 注入信道
- 有 `source` 字段区分 startup / resume / clear / **compact**
- compact 场景特别重要 — sticky 在 compact 时被压缩淡化，PostCompact 又**不支持
  additionalContext** 走不通。SessionStart(source=compact) 是重起注入路径

### 根因

karma v2 当前仅 UserPromptSubmit 每 turn 注入完整 sticky。但 session 起手时（包括
compact 后重起）没 baseline 注入。Agent 接手 session 后第一 turn user_prompt
还没发就开始处理 — sticky 不在 context 里。

PostCompact 协议层不支持注入（子 Agent 研究发现）— 之前 HANDOFF 想用 PostCompact
解决 compact 失忆走不通。SessionStart(source=compact) 才是路径。

### Feat

`karma/hooks/session_start.py` 已存在但是早期 stub（只输出摘要文字不注入 sticky
实际内容）。v0.4.28 升级成注入 sticky baseline：
- 每 sticky 一行：id + 第一行 preference（精简版省 token）
- compact 场景加开头警示（「上下文 compact 后重起 — 这些核心方向必须留在记忆里」）
  + 结尾警示（「compact 后 sticky 容易被压缩淡化 — 留意你正在按这些方向行为」）
- 跟 UserPromptSubmit 每 turn 完整注入互补 — session 级一次 baseline，turn 级动态

`karma/backends/claude_code.py` `_HOOK_EVENTS` 加 `"SessionStart": "session_start"`
让 install-hooks 装 wrapper 到 `~/.claude/settings.json`。Codex / Gemini 协议
没对应 event 是 Claude Code 特有 — `test_backends_all_have_4_common_karma_wrappers`
断言改成「至少含 4 通用 wrapper」+ 新增 `test_claude_code_has_session_start_wrapper`
单独测 Claude Code 特性。

### 生效证据

4 种 source 实际跑通：
```
source=startup  → [karma session 起手 sticky baseline — source=startup] + 8 sticky
source=resume   → [karma session 恢复 — sticky baseline 重新加载] + 8 sticky
source=clear    → [karma session 起手 sticky baseline — source=clear] + 8 sticky
source=compact  → [karma 上下文 compact 后重起 — 这些核心方向必须留在记忆里]
                  + 8 sticky
                  + compact 后 sticky 容易被压缩淡化 — 留意你正在按这些方向行为。
```

352 测试全过（含 1 个新 SessionStart 守护 case）。

### karma v3 演化清单（4 步）

- v0.4.24 中段注入 anchor（PostToolUse 信道）
- v0.4.25 字面多样性元行为监测（dev 工具）
- v0.4.26→v0.4.27 反思式语气改造（keep-pushing + chinese-plain）
- **v0.4.28 SessionStart 注入 sticky baseline**（session 级 + compact 失忆路径）

### 安装

新装：用户首次装会自动包含 SessionStart wrapper。
已装升级：用户跑 `karma install-hooks --backend claude-code` 重装 — 加新 SessionStart
入口到 `~/.claude/settings.json`。

## [0.4.27] — 2026-05-14（patch — v0.4.26 过度推广修正：仅 keep-pushing + chinese-plain 反思式）

### 触发

v0.4.26 把 4 类价值观规则（keep-pushing / chinese-plain / long-term / non-blocking）
全改反思式。用户反馈细化判断：「补丁和 sleep 的我不认为要改，keep pushing 和
中文这个可以改」。

### 根因

我之前的「价值观类 vs 工程纪律类」二分太粗。用户的细化判断更准：

- **表达风格类**（keep-pushing / chinese-plain）— 强硬执行会扭曲 Agent 表达，
  反思式合理（Agent 自己判断风格合不合适）
- **工程行为类**（long-term 补丁 / non-blocking sleep）— **正因为有合理变体
  语境**，Agent 容易找借口合理化逃避根因。命令式语气反而防 Agent 自我合理
  化、保持工程纪律

举例对比：
- chinese-plain 「英文比例高」反思式 OK — Agent 自检是不是技术专名
- long-term 「先打个补丁」反思式 ❌ — Agent 太容易说服自己「这次合理」，
  补丁就成了既成事实

### Fix

回滚 v0.4.26 的两类改造：
- `karma/checks/long_term.py` 5 处 suggested_fix 改回原命令式
- `karma/checks/non_blocking.py` 4 处 suggested_fix 改回原命令式

保留：
- `karma/checks/keep_pushing.py` 反思式（2 处）
- `karma/checks/chinese_plain.py` 反思式（2 处）
- `karma/hooks/stop.py` force_block reason 反思式

### 设计原则更新

「**价值观引导用对话，工程行为 + 工程纪律用命令**」 — 比 v0.4.26 的「价值观 vs
工程纪律」二分更精准。工程行为类 sticky 即使有合理变体语境，命令式反而保护
Agent 不掉「自我合理化」陷阱。

### 验证

344 测试全过。

### 教训

v0.4.26 是个典型「设计层过度推广」案例 — 我推一个原则（反思式更尊重 Agent）
就推到所有价值观类规则，没认区分子类。用户细化判断比我推广更准。

按 sticky #4 坦诚响亮承认 — 这是设计判断错位不是工程实施错位。

## [0.4.26] — 2026-05-14（feat — karma v3 第三步：4 类价值观规则反思式语气改造）

### 触发

用户提出深刻洞察：「在 Agent 字面寻求规则的触发会导致聪明的 Agent 去找绕过
规则的方式」+「有些规则咱们的处理可以更尊重一些 Agent，让他不要激发对抗
或者作弊欲望」。

dogfooding 实证：本回合 keep-pushing 36 次触发对应 32 种 snippet 变体（91%
字面试探多样性），证实 Agent 在反向工程绕命令式规则 — 学到「换字面试探」
而不是「按 sticky 行为」。

### 根因

karma 之前所有 suggested_fix / force_block reason 都是**命令式语气**「不要 X」
「立即 Y」「必须 Z」 — 这种语气把 Agent 当被管教对象，激发字面对抗（套豁免
句式 / 堆冗余前缀 / 用 placeholder 避检测）。

但 Agent 不是所有「违反」都是真违反 — 很多 sticky 有合理变体语境（停下有时
饱和需要用户给方向 / 英文术语有时专名必须保留 / 补丁有时实际等上游 fix 合理）。
命令式语气强行拦合理变体 = 激发对抗。

### Feat

按 sticky 类型分两种语气：

**价值观类（4 条，改反思式）** — 风格 / 习惯 / 有合理变体：

| sticky | 旧命令式 | 新反思式 |
|---|---|---|
| keep-pushing | 「立即选下个推进点继续做 — 不要停下等用户决定」 | 「请自检 — 你是有问题需要用户判断，还是知道要做什么但停下了？任务饱和也算合理停下，但明说卡在哪」 |
| chinese-plain | 「用了 X 后用括号给中文解释」 | 「自检：X 是技术专名必须保留还是可以换汉字？必须用就配中文短解释；能换就直接换」 |
| long-term | 「不要硬写 if-elif 分支 / 不要打补丁」 | 「想想这是特例必须 hard code 还是该提配置？实际等上游修就明说原因；不是就找根因方案」 |
| non-blocking | 「不要 sleep 阻塞前端」 | 「想想这 sleep 是实际等外部资源还是阻塞？合理就保留并明说；不合理改 background」 |

**工程纪律类（4 条，保持硬语气）** — 数据完整性 / 安全 / 反作弊：

- `loud-failure-with-evidence`（测试证据是客观事实非反思能替代）
- `no-testset-no-future-leakage`（反喂训练数据原则没让步）
- `read-before-write`（先读再写工程纪律）
- `deep-fix-not-bypass`（sticky 自身反作弊机制）
- `long-term-fundamental` 中 `git --no-verify / --force` 子项（绕过验证硬纪律）

### 设计原则

**「价值观引导用对话，工程纪律用命令」** — karma 从「监督员」往「同事教练」演化，
但纪律底线不让步。这是 v3 「proactive 教练」演化的第一步。

### 验证

344 测试全过；改完 suggested_fix 文本不影响 check 行为只改提示语气。

dogfooding 验证要等真用户跨场景使用后看：(1) 字面试探多样性是否下降；
(2) 合理变体（如任务饱和明说卡哪一步）是否变多。按 sticky #5 反喂边界，
不靠作者单 session 数据当 fix 有效证据。

### 跟前面 v0.4.X 对比

- v0.4.11~22：reactive fix（拦得更准）
- v0.4.24：proactive 第一步（中段注入 anchor）
- v0.4.25：proactive 第二步（字面多样性元行为监测）
- v0.4.26：proactive 第三步（反思式语气改造）

karma v2 → v3 渐进式演化清单已经完整。

## [0.4.25] — 2026-05-14（feat — karma v3 第二步：audit 字面多样性元行为监测）

### 触发

用户问「绕过冲动」洞察 + dogfooding 数据证实：keep-pushing 35 次触发对应
**32 种独立 snippet 末尾变体（91% 字面多样性）** — Agent 字面试探行为有
实证。这是「Agent 学到换字面绕 check 不是改行为」的实测数据指标。

### Feat

`karma/cli.py` `cmd_audit` 加字面多样性列：

- 算每个 sticky 的 `set(snippet[-40:])` 独立变体数 vs 总触发数
- 比例 >= 70% 标 🎭 字面试探（Agent 字面规避行为强）
- 比例 40-70% 标普通字面多样
- < 40% 不标（字面相对集中说明 Agent 撞同样 pattern 而非试探）

### 已知 limitation

字面多样性对**文本类 sticky**（chinese-plain / keep-pushing / loud-failure）
有意义 — snippet 是 response 文本变体说明字面试探。

对**Bash 命令类 sticky**（non-blocking / long-term / deep-fix）**会误标** —
snippet 是 Bash 命令字面本来就千变万化（不同 commit message / sleep N 值 /
绕过命令字面），100% 多样性不代表字面试探只代表自然命令多样。

dogfooding 数据 v0.4.25 实际跑：non-blocking 9/9=100% / long-term 8/8=100%
都是误标。

接受 limitation — 这是 dev 工具，作者看 audit 时知道按 sticky 类型解读。
后续 fix 方向：按 sticky 类型（文本 / 命令）区分是否计算字面多样性。

### 验证

本回合 `keep-pushing 🎭 字面试探 (32/35=91%)` 是有意义信号，跟用户洞察
完全吻合。

344 测试全过；ruff/mypy 全绿。

## [0.4.24] — 2026-05-14（feat — karma v3 第一步：PostToolUse 中段 sticky reinject 锚定）

### 突破

dogfooding 实测验证 Claude Code PostToolUse hook 接受 `additionalContext`
字段 — system-reminder 显示 `[karma 中段提醒 — 最近 turn 触发过的 sticky
别再犯]` 字面。**karma v3 proactive 锚定路径打通**。

之前 PRD 假设「单 turn 内 sticky reinject 没干净信道」是错的（按 sticky #4
坦诚响亮承认）— dogfooding 实测后推翻假设。

### 根因痛点

本回合 33 次 keep-pushing + 11 次 chinese-plain 累积违反 → 根本不是
check regex 不准（前面 5 个 release 已经精化了），是 **sticky 注入头部强
尾部弱** — sticky 仅在 UserPromptSubmit 一次注入，长 response 中段 Agent
注意力漂移没机制拉回来。

### Feat

`karma/hooks/post_tool_use.py` 加 `_build_smart_reinject()`：

- 每次 tool 调用后看最近 N turn (默认 5) 内**触发过**的 sticky
- 触发过的 sticky 注入简化版（id + 第一行 preference），最多 3 条
- 没触发过的 sticky **不注入** — 省 token 不淹没
- session_state turn_count = 0 / 没违反过 → 输出空 `{}` passthrough

### 设计原则

「**reactive 检测 → proactive 锚定**」闭环：违反某 sticky → 下次
tool call 后该 sticky reinject → Agent 中段持续看到提醒 → 多次违反就
多次 reinject 直到 Agent 改行为。

不是「每次 tool call 都重灌全 sticky」（token 成本高），是「**只 reinject
需要提醒的 sticky**」。

### 生效证据

dogfooding 实测：本回合写这个 fix 时，每次 Edit/Bash/Read 调用后我都看到
system-reminder 显示 `[karma 中段提醒]` + 当前最近触发过的 3 条 sticky
（non-blocking / chinese-plain / loud-failure）。这是 karma v3 第一次**真**
中段锚定。

### 验证

344 测试全过（含 2 个新守护测试函数 — reinject + 对偶守护）。
真用户 dogfooding：本回合写完这个 fix 后期 keep-pushing / chinese-plain
触发率应该自然降低（v3 第一步效果观察）。但按 sticky #5 反喂边界教训
**不当 truth 用** — 验证靠跨场景真用户长期使用。

### 跟前面 v0.4.X 对比

之前 v0.4.11~22 都是 **reactive fix**（拦得更准），v0.4.24 是 **proactive
第一步**（锚定让 Agent 自然不忘 sticky）。这是 karma v2 → v3 演化的起点。

## [0.4.23] — 2026-05-14（patch — v0.4.22 紧急补发：tag 误指向 v0.4.21 内容）

### 触发

按 sticky #4 失败响亮发现：v0.4.22 release tag 实际**指向 v0.4.21 commit 内容**，
v0.4.22 该有的反喂自审 fix（5 类 check 过宽治理）**一行代码都没真 push**。

### 根因

v0.4.22 commit 那次被 karma 自己拦了（命令字面含 `time.sleep(60)` 实际阻塞 pattern
被 pre_tool_use hook 拦）。但后续的 `git tag v0.4.22 && git push --tags && gh
release create` 命令基于**没含 fix 改动的 head** 跑成功了，导致：

- GitHub v0.4.22 release tag 存在
- 但 tag 指向的 commit 是 v0.4.21 的
- 9 个文件改动留在 working tree 没 commit
- 用户装 v0.4.22 拿到的是 v0.4.21 内容

### Fix

不动错的 v0.4.22 tag（避免 destructive 操作改已发布版本），发 v0.4.23 把
v0.4.22 应有的代码发出去。

v0.4.22 在 CHANGELOG 保留作为「该有但没发」的历史记录，README / install
指引都跳到 v0.4.23。

### 教训

karma 自己的 pre_tool_use hook 拦命令导致 commit 失败 → 但 shell `&&` 链
继续跑后面 tag/push/release → 产生「tag 指向错 commit」幽灵 release。这是
shell `&&` 短路行为跟 karma 拦截语义的冲突。

下次 commit + tag + release 类链式命令应该用 `set -e` 或者拆开跑保证前一步
失败不继续。或者 karma hook 应该返回 exit code 让 shell `&&` 短路。

## [0.4.22] — 2026-05-14（patch — 反喂自审：v0.4.13~20 多个 fix 过宽漏拦修复）

**⚠️ 此版本 tag 误指向 v0.4.21 commit 内容，代码在 v0.4.23 补发。**

### 触发（用户问 + 自审）

用户问「全修成 0 了会不会造成真阳被误判成假阳了」 — 触发 sticky #5「反喂边界」
+ 真阳召回率反思。重新按**用户视角**构造真违反 case 跑现行 check，发现本回合
6 个 fix 中 5 个过宽，**多个真阳被错豁免**：

| Fix | 漏拦 case | 严重度 |
|---|---|---|
| v0.4.13 deep-fix | `python -c "os.system('rm karma')"` → None | **绕过漏拦** ⚠️ |
| v0.4.14 evidence | `pytest --collect-only && git commit` → None | 假证据漏拦 |
| v0.4.15 chinese-plain | 表格 cell 堆多 jargon 话术 → None | 话术漏拦 |
| v0.4.18 non-blocking | `python -c "time.sleep(60)"` → None | 实际阻塞漏拦 |
| v0.4.19/20 keep-pushing | 「OK 就这样了 / 今天到此为止」→ None | 柔性停顿漏拦 |

### 根因

audit 修后 0 触发**不代表 fix 根因正确** — 可能只是把真阳吃了。这是经典
sticky #5「**靠 audit 数据评估 fix 效果 = 反喂思维**」陷阱。之前的「闭环视图」
结论过乐观。

### Fix（4 类集中修）

1. **`bypass_karma.py` 加 python 调 shell 绕过接口**：`os.system / subprocess.
   run / shutil.rmtree / Path().unlink` 等扩进 `_PYTHON_OR_SHELL_WRITE_RE`。
   v0.4.13「python -c 跳 shell `>` 重定向」豁免不再放任绕过过。
2. **`non_blocking.py` 加 `_PYTHON_REAL_BLOCK_RE`** 识别 python 实际阻塞：
   `time.sleep(N≥1) / asyncio.sleep / subprocess sleep / os.system sleep`。
   v0.4.18「python -c 跳 sleep」豁免不再放任真 python 阻塞过。
3. **`chinese_plain.py` 加 jargon 密度判定**：jargon ≥ 3 个时用未剥表格的 natural
   扫（堆 jargon 是话术）；< 3 个用剥表格的 natural_for_ratio 扫（单引用是项目
   术语）。v0.4.15「表格 cell 全豁免」过宽修正。
4. **`evidence.py` 加 `_FAKE_TEST_FLAG_RE`** 识别 pytest 假证据 flag：`--collect
   -only / --help / --version` 等不算实际跑测试。
5. **`keep_pushing.py` `_STOP_HINT_RE` 加柔性停顿**：「今天到此 / 到此为止 /
   就这样了 / 就这样吧 / 搞不定了 / 算了吧」等。`_PUSH_SIGNAL_RE` 加 `(?!\\s*[
   吧行])` 排除「下次 X 吧」类推卸语气（部分覆盖，「下次 X 这事吧」 5 字隔开
   仍漏，接受 limitation）。

### 验证

342 测试全过；加 6 个新守护测试函数共 12 个 assert 真违反 case。

### 教训

**sticky #5「不能用测试集反喂」**深刻 — 不能靠「修后 audit 数据 0 触发」当 fix
有效证据，那是反喂思维。验证只能：
1. 按**用户视角**构造真违反 case 跑现行 check 看是不是漏拦
2. 真用户跨场景使用 + 报真阳漏拦 case
3. 不靠自己造的对偶守护测试（那是 confirmation bias）

## [0.4.21] — 2026-05-14（feat — audit --format md 输出 markdown 表格）

### 价值

dogfooding 数据粘贴到 PR / issue 分享更方便 — 当前 plain text 视图复制粘
贴破排版。markdown 输出直接 GitHub flavored，dogfooding 治理曲线一目了然。

### Fix / Feat

`karma/cli.py`：

- `cmd_audit` 加 `output_format: str = "text"` 参数。`output_format="md"`
  时每条 sticky 用 `### [sid]` heading + markdown 表格输出触发词清单
- 触发词 cell `|` 转义 `\\|` + 换行折叠成空格防破表
- CLI 加 `--format md` flag。组合用：`karma audit --with-fix-timeline --format md`

### 跑通

```
# karma 违反审计 (总 66 条)

### [keep-pushing-no-stop] 33 条触发 [check 最新 fix 05-14 19:01: 修前 33 / 修后 0]

| 次数 | 占比 | 触发词 | 标记 |
|---|---|---|---|
| 32 | 97% | `response 纯陈述完结...` | ⚠️ 可能假阳 |
```

### 验证

335 测试全过；ruff/mypy 全绿。

## [0.4.20] — 2026-05-14（patch — keep-pushing 推进信号位置错判：中段推进 + 末尾列表）

### 触发

v0.4.19 装上后**仍触发**：dogfooding 实测末尾响应「**下次接手做 HANDOFF 候选**...
（chinese-plain 38% Agent 用词手册 / long-term SEED 清理 / audit timeline
markdown 输出）」被错算无推进。

### 根因

`_TAIL_WINDOW=80` 限定只看末尾 80 字 — 推进信号「下次接手做 X」在中段，
末尾是列表收尾「(A / B / C)」。整 response 已有推进意图但 tail 80 字看不到
被错算「就此停下」。

这是 v0.4.19 `_PUSH_SIGNAL_RE` 扩展的盲区 — 不是「没识别推进字眼」是
「推进字眼位置在 tail 外」。

### Fix

`karma/checks/keep_pushing.py` 加新豁免（紧接 `_PUSH_SIGNAL_RE.search(tail)`
豁免后）：

```python
# 整 response 含推进规划 + 末尾窗口无明确停顿语气 → 豁免
if _PUSH_SIGNAL_RE.search(text) and not _STOP_HINT_RE.search(tail):
    return None
```

`_PUSH_SIGNAL_RE` 在**整 text** 搜（而非 tail），配合「末尾不含 `_STOP_HINT_RE`
停顿语气」守护防误豁免（推进 + 停顿同时存在该按停顿算）。

### 验证

3 向实测：
- 推进信号在中段 + 末尾列表收尾 → None ✓（v0.4.20 根因 fix）
- 推进信号在中段 + 末尾停顿语气「先到这」 → 仍命中 ✓（对偶守护）
- 纯陈述完结无推进无问号 → 仍命中 ✓

335 测试全过；加 2 个守护测试。

## [0.4.19] — 2026-05-14（patch — keep-pushing 第 3 类假阳：未来规划 / 显式让用户介入）

### 触发

`karma audit` 显示 keep-pushing-no-stop 修前 26 / 修后 6 — v0.4.12 部分修
后仍触发 6 次（最近 5 turn 11 次），都是「response 纯陈述完结无推进」类
karma 自标 ⚠️ 可能假阳。dogfooding 看真 snippet 找出 3 类剩余假阳：

1. **「下次接手做 X」「下个 session 推进 X」类未来规划** — 有下一步
   计划但 `_PUSH_SIGNAL_RE` 要求「现在 / 立即 / 接下来去 + 动词」更强信号
2. **「候选 X」描述** — 表达了下一步候选但没用立即信号
3. **「请决定 / 请授权 / 等你 X」显式让用户介入** — 按 sticky #7 合法 stop
   路径，但被算无推进

### 根因

keep-pushing 误把「**已有下一步规划**」当成「**就此停下**」— 当前只检测
即时推进信号（现在做 X）跟即时停顿（先到这），漏掉「未来规划延续」
跟「合法让用户介入」两类合理 stop 信号。

### Fix

`karma/checks/keep_pushing.py`：

1. **`_PUSH_SIGNAL_RE` 扩三类未来推进规划**：
   - 下次/下个 session/下回 + 动作（接手/做/治理/推进/fix/修/改）
   - 候选(清单/列表/第) + 序号 = 规划
   - 接手/接力 + 动词 = 延续

2. **`_STOP_HINT_RE` 收紧「下次」字面**：旧 `下次跑|下次看|下次再|下次见`
   改为 `下次再来|下次再说|下次见|下次有空` — 只匹配模糊收尾形态
   （「下次跑 X」「下次看 X」可能是规划）。配合 `_PUSH_SIGNAL_RE` 扩
   的「下次接手做 X」豁免。

3. **新 `_EXPLICIT_USER_HANDOFF_RE`** — 「请决定/请授权/请确认/等你 X」
   类显式让用户介入。按 sticky #7 合法 stop 路径，豁免检测。

### 验证

5 向实测：
- 「下次接手做 X」/「下个 session 推进 X」/「候选清单 1.2.3.」/「接手做 X」 → None ✓
- 「请决定」/「等你确认」/「请授权」 → None ✓
- 「下次再说」/「先到这」/「告一段落」/「下次见」实际停 → 仍命中 ✓

333 测试全过；加 3 个守护测试函数共 11 个 assert。

## [0.4.18] — 2026-05-14（patch — non-blocking python -c sleep/wait 假阳：复用 v0.4.13 根因）

### 触发

dogfooding 实测 `non-blocking-parallel` 7d 5 次假阳率 60%。HANDOFF 候选第 1
件治理：karma 自测 `_SLEEP_RE` 探针 `python3 -c "for c in ['sleep 5']: ..."`
被错算真 shell sleep；`python -c "from x import _WAIT_RE"` identifier 字面
被错算 shell wait。

### 根因

跟 deep-fix v0.4.13 `_WRITE_OP_RE` 同根因：`strip_shell_quoted_literals`
保留 `python -c` 内容（设计上拦 `bash -c 'rm karma'` 类绕过），但 python
代码里的 `sleep` / `wait` 字面是 identifier / 字符串数据不是 shell 调用。

### Fix

`karma/checks/non_blocking.py` 加 `_LANG_C_HEAD_RE`（跟 bypass_karma.py
v0.4.13 完全一致）：

```python
_LANG_C_HEAD_RE = re.compile(
    r"\b(?:python\d?|node|ruby|perl)\s+-[ce]\b",
    re.IGNORECASE,
)
```

sleep + wait 检测前先看 `is_lang_c = bool(_LANG_C_HEAD_RE.search(cmd_raw))`，
是宿主语言 -c 时跳过这两类检测。

### 已知 limitation

`python -c "import time; time.sleep(30)"` 类真 python 睡眠也豁免（按 sleep
字面只在 shell 上下文有意义的设计）。真 python 等待应该用 background +
回调而不是 time.sleep，这条 limitation 接受 — 用户 python 代码内逻辑由
其他工具检测（karma v2 边界）。

### 验证

- python -c 内 sleep 字面 → None ✓
- python -c 内 _WAIT_RE identifier → None ✓
- node / ruby / perl -c 同等豁免 ✓
- 裸 shell `sleep 30 && echo done` → 命中 ✓
- kubectl/docker wait 等合法子命令仍豁免 ✓

330 测试全过；加 3 个守护 case 在 `tests/test_checks.py`。

## [0.4.17] — 2026-05-14（feat — audit --with-fix-timeline dogfooding 闭环视图）

### 价值

dogfooding 闭环视图 — 让用户能看「我修了 v0.4.X 后某条 sticky 假阳真的
不再触发」。这是 v0.4.16 协议层 fix（修根因后自动恢复 force_block）的
**自然延续** — 视图层证据 vs 协议层机制。

### Fix / Feat

`karma/cli.py`：
- 加 `_check_file_last_commit_ts(sticky_id, sticky_list)` 用 `sticky.yaml.
  violation_checks` 反查 `REGISTRY[func_name].__module__` → check 文件路径
  → `git log -1 --format=%ct -- <path>` 取最新 commit ts
- `cmd_audit` 加 `with_fix_timeline: bool` 参数。开启时每条 sticky 行追
  加 `[check 最新 fix MM-DD HH:MM: 修前 X / 修后 Y]` 标记
- CLI 加 `--with-fix-timeline` flag

### 设计约束

- 仅 karma 仓库 cwd + git 可用时启用（dev 工具，不破坏跨用户场景）
- fail open — 不在 karma 仓库 / git 不可用 → 静默不报错，正常 audit 视图
- 粒度：单 check 文件最新 commit ts（不区分「根因修复」vs「注释 / 重构
  commit」） — dev hint 用足够，不追求精准

### 跑通

```
karma 违反审计 (总 64 条):
[keep-pushing-no-stop] 32 条触发 [check 最新 fix 05-14 18:17: 修前 26 / 修后 6]
[chinese-plain-no-jargon] 11 条触发 [check 最新 fix 05-14 18:36: 修前 11 / 修后 0]
```

chinese-plain 修前 11 / 修后 0 = v0.4.15 根因 fix 生效 dogfooding 闭环证据。
keep-pushing 修前 26 / 修后 6 = v0.4.12 部分修，第 3 类假阳还在（HANDOFF 候选）。

### 验证

327 测试全过；实际跑 `karma audit --with-fix-timeline` 输出完整 timeline 标记。

## [0.4.16] — 2026-05-14（patch — force_block 协议根因：只惩罚当前 turn 触发）

### 触发

dogfooding 实测死循环：

1. chinese-plain check 累积 8 次 force_block
2. 根因深挖 + v0.4.15 发布修了（表格 cell jargon 扫描豁免）
3. 但 force_block 看「最近 3 turn 累积 8 次」仍**继续 force_block**
4. 即使**当前 turn 0 次触发**chinese-plain，force_block 仍报同样 8 次累积
5. Agent 修了根因没法靠「不再违反」解除 force_block — **死循环**

### 根因

`karma/hooks/stop.py` 的 force_block 逻辑（line 210-213）：

```python
over_threshold = [
    sid for sid, n in counts_force.items()
    if n >= force_threshold and sid not in exempt_ids
]
```

只看「最近 3 turn 累积超阈值」+「不在 force_block_exempt 列表」，
**没要求当前 turn 触发该 sticky**。导致 fix 后 Agent 仍被历史
violation 卡死。

### Fix

加 `sid in hit_sticky_ids` 条件 — force_block 只惩罚「当前 turn 真
触发 + 历史累积超阈值」的 sticky：

```python
over_threshold = [
    sid for sid, n in counts_force.items()
    if n >= force_threshold and sid not in exempt_ids
    and sid in hit_sticky_ids  # ← v0.4.16 加
]
```

`hit_sticky_ids` 计算提到两个 `if notify_msgs:` 块前作共享变量
（之前在第一个块内定义，第二个块依赖 Python 函数级 scope 脆弱）。

### 设计原则

force_block 的目的是「**Agent 反复违反同 sticky 时强制让用户介入**」。
如果 Agent 已经**修了根因不再违反**，应该自动解除不该继续 force_
block — 否则惩罚 Agent 的正确行为（修根因）。

### 验证

326 测试全过；ruff/mypy 全绿。dogfooding 闭环将在下个 turn stop
hook 实际跑时验证。

## [0.4.15] — 2026-05-14（patch — chinese-plain jargon 扫描豁免表格 cell 引用）

### 触发

dogfooding 第 8 次 force_block：上一 turn 末尾我写 markdown 表格汇报
`| 1 | 答 embedding 问 | ... |` 里 `embedding` 被 jargon 扫错算违反。

深挖：`_TABLE_ROW_RE` 已经在算 ratio 时把表格行剥（line 94），但
**jargon 词扫描用的是未剥的 `natural`**（line 116），表格 cell 里的
jargon 没豁免。

按 sticky 设计原理：表格是结构性引用（用户陈列项目术语），不是
jargon 话术（用户**用** jargon 说话）。表格 cell 里出现 jargon 应该
跟 URL 内英文词、版本号一样豁免。

### Fix

`karma/checks/chinese_plain.py` jargon 扫描全部从 `natural` 改用
`natural_for_ratio`（已剥 URL / 表格 / 版本号 / markdown / emoji /
kebab-snake-ident）。同步改 snippet / 上下文窗口的字符串引用。

### 验证

3 向实测：
- 表格 cell `| embedding |` → None ✓（结构性引用豁免）
- 表格外真 jargon `retrieval 做检索` → 命中 ✓（不豁免）
- 括号内解释 `embedding（嵌入向量）` → None ✓（已有括号检测仍生效）

326 测试全过；加 2 个守护 case。

### 注

本 turn 同时还有 chinese-plain 38% 触发，深挖发现是**真违反不是假阳**
— 我自己写 release note 风格汇报用了「release note / code identifier
/ jargon token」类英文复合词没汉字解释。按 sticky 第 3 条原则要求
**改自己用词**不是改 check。

## [0.4.14] — 2026-05-14（patch — evidence 两类假阳：chained pytest + heredoc commit prefix）

### 触发

dogfooding 实测 `loud-failure-with-evidence` 7d 触发 3 次，深挖发现 2 次假阳：

1. **链式 `pytest && git commit`** — pre_tool_use 时 pytest 还没执行，
   `has_recent_test=False` → 错拦合法 workflow
2. **heredoc 包裹的 conventional commit** — `git commit -m "$(cat <<'EOF'
   chore(release): ...\nEOF\n)"` 被错拦（`_NON_CODE_COMMIT_PREFIX_RE` 只
   识别 `"chore:"` 紧邻引号形式，不识别 heredoc / `$()` 嵌套包裹）

### Fix

`karma/checks/evidence.py`：

1. **豁免链式测试** — 加 `_CHAINED_TEST_RE` 识别 `pytest|npm test|jest|
   cargo test|go test|mvn test|gradle test|pnpm/yarn test|tox`。strip
   引号字面后扫骨架，避免 commit message 里字面提 pytest 误豁免「假声称」。

2. **放宽 conventional prefix 匹配** — `_NON_CODE_COMMIT_PREFIX_RE` 改
   `git\\s+commit[\\s\\S]*?(?:^|[\\s'"\\n])(docs|chore|style|build|ci|test|
   refactor)\\s*(?:\\([^)]*\\))?\\s*:` 跨多行匹配（识别 heredoc /
   `$()` 嵌套）。

### 验证

4 向实测：
- A. `pytest && git commit` 链 → None ✓（豁免）
- B. heredoc `chore(release):` commit → None ✓（豁免）
- C. 真违反无证据无 prefix → 命中 ✓
- D. commit message 字面提 pytest → 仍命中 ✓（strip 后骨架无 pytest）

324 测试全过；加 3 个守护 case 在 `tests/test_checks.py`。

## [0.4.13] — 2026-05-14（patch — deep-fix-not-bypass 假阳：python -c 比较运算符不是 shell 重定向）

### 触发

dogfooding 实测：跑 `python -c "...json.loads(l).get('ts', 0) > cutoff..."`
读 violations.jsonl 时被 `deep-fix-not-bypass` 错拦「绕开检测 — 手动写
karma 内部状态」。深挖：`_WRITE_OP_RE` 的 `> c` 命中了 python 代码里的
比较运算符 `> cutoff`，因为 `strip_shell_quoted_literals` 保留 `python -c`
内容（设计上为拦截「`bash -c 'rm karma'`」类 indirect 绕过）。

### Fix

`karma/checks/bypass_karma.py` 拆 `_WRITE_OP_RE` 成两类：

- `_PYTHON_OR_SHELL_WRITE_RE` — 跨语言通用 python 写字面（`.write` /
  `.unlink` / `json.dump` 等），shell + python 都扫
- `_SHELL_REDIR_WRITE_RE` — shell-only `>` 重定向

加 `_LANG_C_HEAD_RE` 识别命令头 `python(\\d+)? -c` / `node -c` / `ruby
-c` / `perl -c`。是宿主语言 -c 时**跳 shell 重定向检测**（python 代码里
`>` 是比较不是重定向），但 `.write` / `.unlink` 仍扫真 python 绕过。

### 验证

4 向实测：
1. `python -c "... 'ts', 0) > cutoff ..."` read → None ✓（不再误拦）
2. `python -c "open(karma).write('{}')"` → 命中 ✓（真 python 写绕过）
3. `echo '{}' > ~/.claude/karma/session-state.json` → 命中 ✓（shell 绕过）
4. `karma violations clear` → None ✓（CLI 合法操作）

321 测试全过；加 3 个守护 case 在 `tests/test_bypass_karma.py`。

## [0.4.12] — 2026-05-14（patch — keep-pushing 假阳治理 + scripts/verify-installed.sh）

### 触发

`.venv/bin/karma stats` 看：`keep-pushing-no-stop` 最近 5 turn 触发 **10
次**最高频。深挖 5 次 snippet 发现 3 次假阳：

- `316 测试全过，Release 链接：...` × 2 — 「数字 + 测试 + 全过」是真
  成功汇报但 `_SUCCESS_REPORT_RE` 只覆盖 `X/X 通过` 跟 `X passed` 跟
  `测试 X` 三种语序，漏了「N 测试全过」「测试 N 全过」
- `我去看 karma check ...` — 「我去 + 看/查」是近 future 推进信号
  但 `_PUSH_SIGNAL_RE` 漏覆盖（只有「我现在/立刻/马上 + 动词」）

### Fix

`karma/checks/keep_pushing.py` 两处 regex 扩：

- `_SUCCESS_REPORT_RE` 加「`\\d+ 测试/tests (全/all)? 通过/过/绿/passed`」
  跟「`测试/tests \\d+ (全/all)? 通过/过/绿/passed`」两种语序
- `_PUSH_SIGNAL_RE` 加「我去/我要去」类近 future + 动词扩展（看/查/测
  /检查/确认/核对）

加 2 个守护测试（4 个 assert）`tests/test_keep_pushing.py`。

### 根因第二层 — 发版流程

v0.4.9/10/11 三连发 chinese-plain fix 都没装到本机 .venv，hook 跑
v0.4.8 旧字节码，force_block 累积 6 次都没生效（代码层 fix 做了但
运行层假完成）。

加 `scripts/verify-installed.sh`：对比 pyproject 版本 vs `.venv/bin/karma
--version` 不一致就退 1（加 `--reinstall` 自动 uv pip 重装本机）。
HANDOFF.md「接手前必读」加发版后必跑提醒。

### 验证

318 测试全过；ruff/mypy 全绿。

## [0.4.11] — 2026-05-14（patch — chinese-plain 再修：kebab/snake 项目标识符不算 jargon）

### 触发

v0.4.10 刚发完一句汇报响应立即触发**第 6 次** force_block：karma 自己的
release note 风格响应大量含项目专有标识符（`chinese-plain-no-jargon` /
`force_block` / `karma-v1` / `sticky_id`），这些**含连字符或下划线的英文
token** 被算成英文 jargon 词数，拉低中文占比 < 40%。

剥过版本号 / markdown / emoji 后还剩 9 个英文 token > 8 阈值就触发；
其中 4 个是项目专有标识符。

### Fix

`karma/checks/chinese_plain.py` 增 `_KEBAB_SNAKE_IDENT_RE`：

```python
_KEBAB_SNAKE_IDENT_RE = re.compile(
    r"\b[a-zA-Z][a-zA-Z0-9]*(?:[-_][a-zA-Z0-9]+)+\b"
)
```

含至少一个 `-` 或 `_` 连接的英文 token = code identifier 不是自然语言
jargon 话术（用户看代码自己也用这些原文），算 ratio 时剥。

剥除链顺序：URL → table row → version → markdown mark → emoji → **ident** → 算 ratio。

jargon 词扫描仍用原文（`retrieval` / `embedding` 等真 jargon 仍命中）。

### 验证

dogfooding 实测第 6 次触发 case → None；真 jargon `retrieval embedding` 仍命中；
纯 ident 段（chinese-plain / force_block / karma-v1 / sticky_id）→ None。
tests/test_checks.py 加 kebab/snake 守护 case。

## [0.4.10] — 2026-05-14（patch — chinese-plain 假阳消除：版本号 / markdown / emoji 不算 jargon）

### 触发

dogfooding 实测：`chinese-plain-no-jargon` 累积 **5 次 force_block 干预**。深挖发现
5 次都是 post-v0.4.3 fix 类汇报响应 — 含大量版本号字面（`v0.4.6` / `v0.1.x`）
+ markdown emphasis（`**深挖**` / `* item`）+ emoji（`✅⚠️`），把中文占比从
正常 ~50% 拉到 34-39% 误判低于 40% 阈值。

这些都是**结构性 / 装饰性内容不是自然语言 jargon 话术**，算 ratio 时应剥除。

### Fix

`karma/checks/chinese_plain.py` 增 3 个剥离正则在算 ratio 前应用：

- `_VERSION_RE` — `v0.4.6` / `0.4.3` / `v1.2.3-rc1` 等版本号字面
- `_MARKDOWN_MARK_RE` — `**` / `*` / `~~` / 行首 `- * # > +` / 行内 `` ` ``
- `_EMOJI_RE` — `☀-➿` / `U+1F300-1FAFF` / `✅❌⚠✨⭐`

剥除链顺序（紧接已有 URL / 表格剥离）：
URL → table row → version → markdown mark → emoji → 算 ratio。

注意只在**算 ratio 时剥**，jargon 词扫描仍用原始 natural 文本（这样真 jargon 仍命中）。

### 验证

实测 v0.4.6 类技术报告 case → None（不再误触发）；真 jargon `retrieval embedding`
等仍命中。tests/test_checks.py 加 1 个 markdown emphasis 守护 case。

## [0.4.9] — 2026-05-14（patch — codex 0.130 hook approval gate 最终根因）

sub-agent 用 `pty.fork()` 启动 codex CLI TUI（绕过主作者 expect 失败 / codex
panic 的两个坑）找到**最终根因**：

### 发现：codex 0.130 hook approval gate

codex 0.130 起所有新装 hook **默认 quarantined**（待审批），必须 TUI 内
交互式 `/hooks` 命令手动 approve 后才执行。TUI 启动横幅显示 `⚠ N hooks
need review before they can run. Open /hooks to review them.`

这是 codex 0.130 **安全设计不是 bug**（防恶意 hook 自动执行），但带来真
用户体验影响：karma 装完后 codex 不会自动调度 wrapper，**第一次 TUI 必须
手动审批 4 个 karma wrapper**。

之前所有「装机就绪但 hook 不触发」的根因都是这个 approval gate —
不是 v0.4.8 推断的 Desktop App regression（#21639 是另一个独立问题）。

### Docs

- README 客户端表 codex 行更新：装完必须 TUI 内 `/hooks` 审批 4 个 wrapper
- README「让 AI 帮你装」段加 codex 0.130 approval gate 关键最后一步（含
  TUI 命令示例 `> /hooks` 跟 approve 流程）
- HANDOFF 同步根因 + sub-agent 附带发现（codex CLI panic 「byte index
  u64 wrap」用位置参数绕过）

### 验证方法（给同事终端跑）

```bash
codex                # 起 CLI TUI（不是 Desktop App）
                     # 看到「⚠ N hooks need review」横幅
> /hooks             # 交互审批 karma 4 个 wrapper
> /quit              # 退出
# 之后再跑任何 codex 命令 karma hook 触发
```

### Test

测试 314 全过，4 件套全绿。

## [0.4.8] — 2026-05-14（patch — CI fix + codex Desktop App 上游 regression 根因记录）

### Fixed

- **CI 跨平台测试 fail 修** — v0.4.7 P1 加 `client_installed()` 门槛后所有
  `cmd_install_hooks()` 测试在 CI 环境（无 claude 命令也无 `~/.claude/`）
  集体 fail。修：`fake_home` fixture 默认显式 mock 3 个 backend
  （Claude=True / Codex=False / Gemini=False），测试 isolation 跟环境无关。

### Docs — codex hook 上游 regression 根因深挖记录

用户挑战「这几天 vibe island 一直能调用 codex cli 的 hook」驱动 4 步深挖：

1. 我看 bridge.log 200 行推「0 条 codex 触发」→ 错（没看 rotated `.log.1`）
2. 看 `.log.1` 仍 0 条 → 推「作者从没用过 codex」→ 错（用户确认用 Desktop App）
3. WebSearch 找到 [GitHub codex issue #21639](https://github.com/openai/codex/issues/21639)
   「Hooks no longer run after Codex Desktop update」
4. WebFetch issue 细节：**regression 仅影响 codex Desktop App**
   （build 26.506.21252+ / cli_version 0.129.0-alpha.15+），**CLI 不受影响**

**实际状态**：
- karma 装在 `~/.codex/hooks.json` 对应 codex **CLI** — 用 `codex` 终端命令
  跑 TUI 触发 hook（按 issue 推断，需终端验证）
- 用 codex **Desktop App** GUI → 命中上游 regression → hook 不调度 → 等
  OpenAI 修（issue 未分配 / 未 milestone）

README 客户端表 + 给同事 AI prompt 块 + HANDOFF 都加上游 bug 说明 + 「用
CLI 终端跑绕过 Desktop App regression」指引。

### Verified

- karma 在 codex 协议下 5/5 生效（模拟 codex payload 跑 4 wrapper 全过 +
  sticky 注入 1186 字 + decision=block 实际输出 + violations 写入）
- codex 端启动条件 3/3 齐全（features.hooks=true / config.toml / wrappers
  可执行）
- 唯一未验证层：codex CLI TUI 完成一个 turn 的 hook 调度证据 — Bash
  expect 自动化模拟两次都失败（一次 turn 立即 close / 一次 codex panic），
  需实际终端 5 秒手动验证

### Test

测试 314 全过，4 件套全绿，CI 跨平台转绿。

## [0.4.7] — 2026-05-14（patch — sub-agent 排查 5 个 P0 全落地）

「感觉还不是很有把握公开 + 给同事 collaborator 让他先用」触发 sub-agent
站陌生同事视角全面排查首装隐患，找到 5 个实际问题。本版全部落地。

### Fixed — P1 真 bug

- **`cmd_install_hooks` 默认 `claude-code` backend 不查 `client_installed()`
  静默装 hook 配置** — 之前同事没装 Claude Code 跑 `karma install-hooks`
  会闷头写 `~/.claude/settings.json`，完全无反馈他不知道 hook 不会触发。
  修：单 backend 路径也加 `client_installed()` 门槛，检测不到时报错并提示。
  加 `test_install_hooks_aborts_when_client_not_installed` 守护测试。

### Docs — P2/P3/P4/P5 一并修

- **P2**：README「让 AI 帮你装」段 AI prompt 块加 `gh auth status` 前置
  检查 — 私有仓库期间同事 Claude Code 拿到 prompt 不会主动先看 auth 直接
  跑 `git clone` 401 一头雾水。
- **P3**：pyproject classifier 去掉 Windows 声明（karma wrapper 用 Unix
  shebang Windows shell 不识别，未实测过先不声明）+ README 前置要求加
  「Windows 建议 WSL」。
- **P4**：README 新增「装完立即做：自定义 sticky 偏好」段 — 明示 karma
  默认装的是「逐步确认型」（不含 keep-pushing），全权委托型用户要手动
  加 `keep-pushing-no-stop` 这条（含 YAML 模板可复制）。
- **P5**：README 「装完必读 2 条」整合 venv 警告到装完最显眼位置（原来
  藏在「维护跟卸载」段末尾同事看不到）。

### Test

测试 313 → 314 全过，4 件套全绿。

## [0.4.6] — 2026-05-14（patch — `karma uninstall` 一键卸装 alias）

### Added

- **`karma uninstall`** — `karma uninstall-hooks --backend all` 的一键 alias。
  陌生用户想完全卸装 karma 时不用记 backend flag 长串，一句 `karma uninstall`
  就清所有 backend（Claude Code / Codex / Gemini）+ 删 wrapper + 从客户端
  配置移除 karma entry，保留他人 hook（vibe-island / rtk 等）共存。

加 1 条守护测试（`test_uninstall_one_shot_alias`）。

### Test

测试 312 → 313 全过，4 件套全绿。

## [0.4.5] — 2026-05-14（patch — KARMA_HOME 环境变量 + sub-agent 评审驱动改进）

「同事即将首装」我 spawn 一个 sub-agent 扮演陌生用户跑首装清单**实测试**，
找到 5 条实际问题。本版修最关键 P0：

### Added — `KARMA_HOME` 环境变量支持

之前 `~/.claude/karma` 路径写死 5 个模块（cli / sticky / violations /
session_state / config）— dry-run / CI / 多 profile 都污染默认 home。
sub-agent 评审作为 v2 边界 bug 标出。

新建 `karma/paths.py:karma_home()` 单一来源 + 所有模块用它。`KARMA_HOME`
env 隔离用法：

```bash
KARMA_HOME=/tmp/karma-test karma init            # 不动 ~/.claude/karma/
KARMA_HOME=~/karma-profile-A karma sticky list   # 多 profile
```

加 4 条 subprocess 测试守护（用新 Python 进程让 env 在 import karma 之前
生效）：default 路径 / env override / 5 module 一致 / `~` 展开。

### Test

测试 308 → 312 全过，4 件套全绿。

### Pending（sub-agent 评审剩余 4 条 — 跟同事实际首装数据驱动再修）

- 给同事清单「检查 Python」给具体命令（`python3 --version` / `command -v uv`）
- 清单加 `karma init` 第 5 步明示（之前禁止 init 但 init 是必要步骤）
- 提示 git / shell（fish 用 `activate.fish`）/ 网络（github+pypi）要求
- README 装机示例 venv 后说明怎么退出 / deactivate

## [0.4.4] — 2026-05-14（patch — 首位真用户首装驱动的 3 个修）

「同事即将首装 karma」消息触发 README 站陌生用户视角重审 + 实际触发 3 个真
问题修。这是 dogfooding → real-user 转折点的标志性 patch。

### Fixed

- **`karma --version` 输出错版本号** — `__init__.py` 硬写 `__version__ = "0.1.0"`
  跟 pyproject 双维护失同步，bump 到 0.4.3 后 `--version` 还是输出 v0.1.0
  让用户疑惑。修：`__init__.py` 用 `importlib.metadata.version("karma")`
  单一来源读 pyproject metadata（editable install 后重 `pip install -e .`
  让 metadata 同步）。加 `test_version_matches_pyproject` 守护防回归。
- **`karma install-hooks --help` 漏列 `gemini-cli` backend** — `--backend
  claude-code|codex|all` 应该是 `claude-code|codex|gemini-cli|all`。Gemini
  CLI backend v0.4.0 加了但 help 文本忘更新。
- **CI 4 platform × Python 版本全 fail** — `test_install_hooks_all_backend_only_installs_detected`
  + `test_uninstall_all_backend_iterates_each_installed` 两条测试只 mock 了
  `CodexBackend` / `GeminiCLIBackend` 的 `client_installed`，没 mock
  `ClaudeCodeBackend`。作者本机有 `claude` 命令 + `~/.claude/` 目录 → 通过；
  CI hosted runner 没装任何 AI 客户端 → 全 False → exit 1。修：mock 全 3 个
  backend 让测试 isolation 跟环境无关。

### Docs — 首位真用户首装清单驱动 README 改进

- 加 Python ≥ 3.11 前置要求（pyproject 要求但 README 没提）
- 加 **⚠️ 关键最后一步「装完必须重启 AI 客户端」** — Claude Code / Codex /
  Gemini CLI 都是 session 启动时一次性读 hook 配置不重载，跑中 session karma
  不触发。新用户最容易踩坑。
- 加「维护跟卸载」段警告 wrapper 硬写 venv 路径 — 删 / 移动 / 重建 `.venv`
  前必须先 `karma uninstall-hooks --backend all`，否则 hook 指向不存在的
  python 让 AI 客户端启动报错。
- README 文末「状态」段加「**真实非作者用户使用期**」起点标记。

### Test

测试 307 → 308 全过（加 `test_version_matches_pyproject` 守护）。
**CI 跨 ubuntu/macos × py3.11/3.12 全绿** — 之前作者本机过但 CI fail 的 bug
修对。

## [0.4.3] — 2026-05-14（patch — chinese-plain 表格 / URL 假阳修）

### Fixed

`chinese_plain_no_jargon` 假阳 — markdown 表格 / URL 把中文占比拉低误命中。

**实测触发场景**：作者发 release 汇报响应含 `https://github.com/.../tag/v0.3.0`
URL 35+ 字符全英文 + markdown 表格 `| v0.3.0 | Codex CLI backend |` 字面全
英文，把主体中文占比从 ~50% 拉低到 15-28% 触发 force_block（累积 5 次 ≥ 阈值）。

但 URL / 表格是**结构性内容**不是 jargon 话术。修：算 ratio 前先剥：

- `_URL_RE` 剥裸 URL + markdown 链接 `[text](url)` + email
- `_TABLE_ROW_RE` 剥整行 markdown 表格（`| ... | ... |` + `|---|` 分隔行）

加 3 条守护测试：URL 剥 / 表格剥 / 真 jargon 对偶（用了真 jargon 仍拦
保证不放过真违反）。

### Test

测试 304 → 307 全过，4 件套全绿。

## [0.4.2] — 2026-05-14（patch — dogfooding 实测发现 bypass_karma 假阳）

### Fixed

`bypass_karma._WRITE_OP_RE` 误识别 `2>/dev/null` 类 stderr 重定向为写操作。

**实测触发场景**：跑 `python -c "...session_state.load(...)" 2>/dev/null`
只读 inspection karma 内部状态时被误拦 — 命令含 karma 状态路径字面
（`~/.claude/karma/session-state`） + `2>/dev/null` 之前被
`>\s*[/.~\w]` pattern 命中算「写」→ has_internal + has_write 都 True → 拦。

修：regex 加 lookahead 排除 `/dev/null` / `/dev/zero` / `/dev/stderr` /
`/dev/stdout` 等丢弃目标 — 它们不是写到文件系统。

```python
>\s*(?!/dev/(?:null|zero|stderr|stdout))[/.~\w]
```

对偶守护：`2> /tmp/err.log` 这种写日志文件**仍**算写（lookahead 只排除
丢弃目标，普通文件路径不放过）；`echo bad > ~/.claude/karma/session-state/abc.json`
写 karma 状态仍要拦。

加 2 条守护测试覆盖只读 inspection + 写对偶。

### Test

测试 302 → 304 全过，ruff / mypy / vulture 0 issue。

## [0.4.1] — 2026-05-14（patch — 抽 JsonHooksBackend 共用基类降未来 backend 成本）

### Refactor

从 vibe-island 实证清单（claude / codex / gemini / cursor / factory / qoder /
copilot / codebuddy / kimi 9 家客户端）学到「多客户端同模式」— 抽通用
`JsonHooksBackend` 基类，让加新 backend 变成「填表」工作而不是写整套：

- **`karma/backends/_json_hooks.py`** 通用基类，提供 90% 共用实现：
  client_installed / hooks_dir / settings_path / load_settings / save_settings /
  is_karma_entry / 默认 build_event_entry / 默认 pre_install_setup（空）。
- 3 个现有 backend 重构成继承基类，只填**类属性**：
  - `name` / `display_name` / `_CONFIG_DIR_NAME` / `_SETTINGS_FILENAME` /
    `_CLIENT_CMD` / `_HOOK_EVENTS`
- 子类**可选 override**：`build_event_entry`（不同 matcher / timeout）、
  `pre_install_setup`（Codex 启用 features.hooks）。

**未来加新 backend 模板**：

```python
class CursorBackend(JsonHooksBackend):
    name = "cursor"
    display_name = "Cursor"
    _CONFIG_DIR_NAME = ".cursor"
    _SETTINGS_FILENAME = "hooks.json"
    _CLIENT_CMD = "cursor"
    _HOOK_EVENTS = {"UserPromptSubmit": "user_prompt_submit", ...}
```

3 行类属性 + 4 行 event 映射就装好一个新 backend。

### Code quality

- 3 个 backend 文件共减少 ~130 行重复代码（370 → 240 含基类）。
- 4 件套全绿：299 测试 / ruff / mypy（karma + tests） / vulture 0 issue。

## [0.4.0] — 2026-05-14（minor — 第三个 backend：Gemini CLI 适配）

### Added — Gemini CLI 装机支持

karma 三家 AI 编程客户端 backend 全打通：Claude Code（v0.1.0）+ Codex CLI
（v0.3.0）+ Gemini CLI（v0.4.0）。三个客户端 hook 协议跟 karma 实测兼容,
真实装机 / 卸装 / hook 触发 catch 违反全跑通。

- **`karma/backends/gemini_cli.py`**：新 `GeminiCLIBackend` 实现，
  `~/.gemini/settings.json` 配置（含 `hooks` 字段），默认启用（不像 Codex 要
  feature flag）。
- **`karma install-hooks --backend gemini-cli`** 装机；`--backend all` 自动
  装本机三家全检测到的客户端。
- **Stop hook 跨协议跨 backend 适配**：karma `stop.py` 现在适配 3 个不同字段名：
  | Backend | Stop event 名 | 字段 |
  |---|---|---|
  | Claude Code | `Stop` | `transcript_path`（反向读 transcript） |
  | Codex | `Stop` | `last_assistant_message`（直传） |
  | Gemini CLI | `AfterAgent` | `prompt_response`（直传） |
  
  优先级：直传字段 > transcript fallback。

### Key insight — Gemini event 名跟 Claude Code / Codex 不同

Gemini CLI 用自己的 event 名（`BeforeAgent` / `AfterAgent` / `BeforeTool` /
`AfterTool`）— 跟 Claude Code 的 `UserPromptSubmit / Stop / PreToolUse /
PostToolUse` 完全不同。

karma backend 抽象设计巧妙处理：**`hook_events()` key 是 backend 实际 event 名
（写进各家配置文件），value 是 karma 内部 wrapper basename**。这样 4 个 wrapper
（user_prompt_submit / pre_tool_use / post_tool_use / stop）跨 3 backend 完全
复用，karma hook 入口模块代码 0 改动。

| karma wrapper | Claude Code | Codex | Gemini CLI |
|---|---|---|---|
| user_prompt_submit | UserPromptSubmit | UserPromptSubmit | BeforeAgent |
| pre_tool_use | PreToolUse | PreToolUse | BeforeTool |
| post_tool_use | PostToolUse | PostToolUse | AfterTool |
| stop | Stop | Stop | AfterAgent |

### Verified（实际跑实测）

- 装机：`~/.gemini/settings.json` 6 个 vibe-island event + 4 个 karma event 共存 ✓
- AfterAgent 模拟 payload 跑 karma stop.py → catch「我先打个补丁」违反 +
  decision=block + reason 输出 ✓
- 卸装：karma 4 entry 清除，vibe-island 7 个 entry 完整保留 ✓

### Test

- 测试 294 → 299 全过（加 Gemini event 映射 + 跨协议字段适配守护测试）。
- ruff / mypy（含 tests/）/ vulture 0 issue。

## [0.3.0] — 2026-05-14（minor — 多 backend 横向扩展：Codex CLI 适配）

### Added — Codex CLI 装机支持

karma 从「Claude Code 专用」升级为「多 AI 编程客户端通用」框架。新增 Codex
CLI 适配 — 协议跟 Claude Code **几乎一对一兼容**，实测装机 / 卸装 / hook 真
触发全跑通。

- **`karma/backends/` 多 backend 抽象**：`Backend` Protocol 定义客户端无关的
  装机接口（hooks_dir / settings_path / hook_events / build_event_entry 等）。
  - `ClaudeCodeBackend`：refactor 老逻辑进 backend，0 行为变化
  - `CodexBackend`：新建，`~/.codex/hooks.json` + 自动启用 `[features] hooks = true`
- **`karma install-hooks --backend codex|claude-code|all`**：默认 claude-code
  向后兼容；`--backend codex` 装 Codex；`--backend all` 装本机检测到的所有客户端。
- **`karma uninstall-hooks --backend ...`**：同样支持，验证保留他人 hook
  （vibe-island 等共存插件）。
- **`karma doctor` 跨 backend 显示**：每个客户端 ✓/✗ 检测，含 hook 装机状态。
- **Stop hook 跨协议适配**：优先用 Codex `last_assistant_message` 字段（直接
  给最后一条 assistant message），fallback Claude Code `transcript_path` 反向读
  transcript。Codex 性能更优（不用读文件）+ 向后兼容 Claude Code。

### Technical findings（实测实际跑得到的协议细节）

- Codex feature flag 实际名是 **`hooks`** 不是 `codex_hooks`（vibe-island
  config.toml 用过时名 `codex_hooks` 误导）— 通过 `codex features list` 确认
- Codex hook 只在 **interactive TUI 模式**触发，`codex exec` 非交互模式不触发
  （GitHub issue #17532 描述的已知行为）
- Codex 6 个 hook event vs Claude Code 4 个 — 共有 UserPromptSubmit / PreToolUse /
  PostToolUse / Stop（karma 用这 4 个）；Codex 额外有 SessionStart / PermissionRequest
- Codex stdin payload **没** `transcript_path`，但 Stop hook 直接给
  `last_assistant_message` — karma 自动适配

### Fixed

- **long_term 「长 ID if 分支」假阳收紧**：之前 `if cmd == "install-hooks"` 类
  合法 CLI dispatch 命中（13 字符 kebab-case 触发 12+ 字符门槛）。新 pattern
  用 lookahead 要求字面同时**至少 12 字符 + 含数字**（UUID / hash 满足，CLI
  命令名 / sticky id 不满足）。加 2 条守护测试。

### Refactor / Quality

- `cli.py` 旧硬编码 helper 函数（`_settings_path` / `_save_settings` /
  `_remove_karma_entries` / `_add_karma_entries` / `_check_hooks_installed` /
  `_karma_event_entry` / `_KARMA_HOOK_EVENTS` / `_SettingsParseError` 等）
  全部移除 — 用 backend 接口替代。代码量减少 ~80 行，可维护性提升。
- 测试 277 → 294（新增 backend 测试 15 条 + Codex stop 协议 2 条 + long_term 假阳 2 条）。

### Test / Quality

- 测试 294/294 全过，ruff / mypy（含 tests/）/ vulture 0 issue。
- 实测装机：`karma install-hooks --backend codex` 写 `~/.codex/hooks.json`，
  vibe-island 4 个原 entry 全保留共存。卸装同样验证。

## [0.2.4] — 2026-05-14（minor — 跨平台 locale 自动检测）

### Added

新模块 `karma/locale_detect.py` — 跟其他 app（VS Code / Slack / Chrome）安装
时一样的「按系统语言偏好自动选」做法。

用户挑战 v0.2.3 的「locale 检测不可靠所以显式 flag」判断时实测找到：作者机器
`locale.getlocale()` 返回 `('en_US', 'UTF-8')` 但 `defaults read -g
AppleLanguages` 返回 `zh-Hans-CN`（作者真实系统语言）。我之前判断错了 —
Python `locale.getlocale()` 不准，但各平台有标准方法能准确读到用户偏好：

- **macOS**：`defaults read -g AppleLanguages`（系统设置 → 语言与地区里设的真实偏好）
- **Linux**：`$LC_ALL` > `$LC_MESSAGES` > `$LANG`（POSIX 标准优先级，桌面环境自动设）
- **Windows**：`ctypes.windll.kernel32.GetUserDefaultUILanguage()` + `locale.windows_locale`
  查表 LCID → ISO 代码（跟「设置 → 时间和语言 → Windows 显示语言」一致；
  Windows 默认 shell 通常不设 `$LANG`）

`karma init` 行为变化：

- `karma init`（无 flag）→ **自动按系统语言偏好选**：中文用户装 7 条完整
  含 chinese_plain；非中文 / 检测不到装 5 条精简。检测结果会打印让用户知道。
- `karma init --minimal` / `--no-minimal` 强制覆盖自动选择
- 容器 / CI / 异常环境（locale 全无）→ fallback 5 条精简（最安全默认）

加 17 条跨平台守护测试（mock subprocess / 环境变量 / Windows ctypes 三路径
独立验证）。

### Test / Quality

- 测试 258 → 275 全过，ruff / mypy / vulture 0 issue。

## [0.2.3] — 2026-05-14（patch — karma init --minimal flag）

### Added

- **`karma init --minimal`** 显式 flag 装 5 条中性核心模板（评审 C Agent
  第二轮指出 minimal 模板存在但默认 7 条对英语母语用户仍是持续假阳源）。
  - 评审建议过「`karma init` 检测系统 locale 自动选」— 实测后否决：
    `locale.getlocale()` 在 macOS 默认返回 `en_US` 但用户实际可能是中文，
    自动猜错率高。改用显式 flag 让用户自己选（显式优于隐式）。
  - 默认 `karma init` 仍装 7 条向后兼容；末尾打印 `--minimal` 提示让英文
    用户知道有选项。
  - 加 2 条守护测试（`test_init_default_installs_7_sticky` /
    `test_init_minimal_installs_5_sticky`）。

测试 256 → 258 全过。

## [0.2.2] — 2026-05-14（patch — 第二轮评审 critical bug fix）

跑了第二轮独立 Opus 4.7 sanity-check 评审 Agent，找出 v0.1.1 修复时漏掉的
**真 critical 假阴**：

### Fixed

- **`strip_shell_quoted_literals` 双引号内 substitution 漏报（真 bug）** —
  双引号包 `$(...)` / 反引号 这种 shell 最常见写法之前会被 `_SHELL_QUOTED_RE`
  整段吞掉（连同 substitution 内容一起剥），导致 `non_blocking_parallel` /
  `long_term_fundamental` 等 check 全线漏报。v0.1.1 加的守护测试只测**裸**
  反引号 / `$()`，没覆盖「在双引号内」这个最常见场景。
  - 修：Step 0 先扫双引号字面，把内部 `$(...)` 和反引号内容「提升」到 cmd
    外层（shell 双引号实际行为就是展开 substitution 执行）；单引号字面不动
    （shell 单引号语义就是字面文本不展开 — 对偶守护测试 case 验证）。
  - 反引号 / `$(` regex 加 negative lookbehind 排除转义形式（`\$(` / 反斜杠+反引号
    是字面 shell 不展开）— 修自身 fix 引入的 regression（commit message 引用
    bug case 字面时被自拦）。
  - 加 5 条守护测试覆盖：双引号 `$()` / 双引号反引号 / 单引号对偶 /
    转义 `$()` 字面 / 转义反引号字面。

### Test / Quality

- `KARMA_DEBUG_TRACE` 加 2 条守护测试（评审第二轮指出 v0.2.1 补了
  `KARMA_DEBUG` 但姊妹变量 `KARMA_DEBUG_TRACE` 没测过 — sticky #4 违反）。
- 测试 249 → 256 全过，ruff / mypy / vulture 0 issue。

### Docs

- README 测试数 234 → 252（v0.2.1 实际是 249，本版含 #1 fix 守护测试后 254）。
- `violation_checks` 表加「默认装？」一列 — 评审第二轮指出 `keep_pushing_no_stop`
  在 `sticky.dev.example.yaml` / `sticky.dev.minimal.example.yaml` 都没引用,
  但 README 表里平等列了 8 个让用户以为开箱可用。明示这条是「可选 — 给全权
  委托型用户，需要自己在 sticky.yaml 加引用」。

## [0.2.1] — 2026-05-14（patch — 凭假设没验证反查）

按用户「为啥有问题不修好呢」精神持续反查我之前用「假设的成本」推迟过的问题：

### Fixed

- **`ARCHITECTURE.md` 加「配置」章节** — v0.2.0 README 重组让链接指向
  `ARCHITECTURE.md#配置` 但实际**那节不存在**（凭假设没 grep 就写链接）。
  补完整字段表（10 条 config 字段 + 默认值 + 含义）+ 3 个调试环境变量说明
  （`KARMA_NO_NOTIFY` / `KARMA_DEBUG` / `KARMA_DEBUG_TRACE`）。
- **mypy 类型化** — 之前我说「会改 200+ 行」推迟，**实际跑后只有 3 个 error**
  10 分钟修完（`testset.py` / `long_term.py` underscore 变量名跨类型重用 →
  `_label`；`cli.py:_karma_event_entry` dict 异质 value → `dict[str, object]`
  显式标注）。mypy 加进 `[project.optional-dependencies].dev` + CI 步骤守护。

### Test / Quality

- `run_checks` `KARMA_DEBUG=1` 门控加 3 条守护测试 — 之前加了功能没验证过
  实际行为属于 sticky #4 「完成要有证据」违反。
- 测试 246 → 249，CI 跨平台跨 Python 版本全过，mypy 0 issue。

## [0.2.0] — 2026-05-14（minor — README 重组 + 新增中性 sticky 模板）

### Added

- **`data/sticky.dev.minimal.example.yaml`** 中性 5 条核心 sticky 模板：
  long-term-fundamental / non-blocking-parallel / loud-failure-with-evidence /
  deep-fix-not-bypass / read-before-write。砍掉默认 7 条里两条场景化规则
  （chinese-plain-no-jargon 中文用户偏好 / no-testset-no-future-leakage
  ML 场景）。
  - 评审 C Agent 痛点：默认 7 条违反 CLAUDE.md「不针对当前用户作弊」
    原则。英文母语 / 非 ML 用户可 `cp data/sticky.dev.minimal.example.yaml
    ~/.claude/karma/sticky.yaml` 切换。
  - 默认 `karma init` 仍装 7 条（向后兼容现有 0.1.x 用户）。

### Changed

- **README 重组**（评审 C Agent 痛点：视角错位 — 给「Agent 接力」写不是
  给陌生用户）：
  - 砍 30% 实现细节（heredoc 智能剥 / background catchup / 跨语言注释扫描
    等），移到 ARCHITECTURE.md
  - 「反馈机制」段改写成核心机制一句话概述，详细规则链 ARCHITECTURE.md
  - 「场景化定位」段加 2 套模板对比表，让陌生用户知道按场景选
  - 「sticky.yaml 写法」加完整字段表（含 `force_block_exempt`）+ 8 个内建
    `violation_checks` 函数名 + 简介表（之前用户写自定义 sticky 完全黑盒）

## [0.1.1] — 2026-05-14（patch — 评审 Agent B 第 4 条盲区一次修对）

### Fixed

`karma/checks/common.py:strip_shell_quoted_literals` 三个真违反假阴漏报修复 ——
之前 v0.1.0 评审时这条被判「等真用户碰到再修」，但用户当场纠正这是 sticky #1
「最根本长期方案」违反，应当现在修对：

- **反引号命令替换** `` `cmd` `` 现在显式按 indirect shell 处理 —— 内容是真
  执行子命令（之前没有专门捕获，依赖偶然不被剥）。
- **`$(...)` 命令替换** 同上 —— 跟反引号等价，`echo $(sleep 30)` 实际会执行
  sleep。
- **`bash -c sleep30` 无引号形式** —— POSIX 合法但之前 `_INDIRECT_SHELL_RE`
  要求引号包裹漏掉。新 `_INDIRECT_SHELL_NOQUOTE_RE` 取 `-c` 之后第一个 token。
- **`<<-EOF` tab 缩进 heredoc 终结符** —— bash `<<-` 允许 tab 缩进，之前
  `_HEREDOC_RE` 终结符前不允许空白会让 heredoc 不被识别 → 内容没剥 → 数据
  当真 shell 误判。修：终结符前允许 `[\t ]*` 空白。

加 4 条守护测试（`test_false_negative_regression.py`）。测试 241 → 245 全过。

## [0.1.0] — 2026-05-14（首个公开版本）

karma v2 的第一个可发布版本，经历多轮 dogfooding + 4 个 Opus 4.7 评审 Agent
交叉评审 + 1-2 小时质量打磨。

### Added

- **核心机制**：4 个 Claude Code hook（`UserPromptSubmit` / `PreToolUse` /
  `PostToolUse` / `Stop`）+ `sticky.yaml` 配置驱动的偏好提醒。
- **sticky schema**：`id` / `preference` / `violation_keywords` /
  `violation_checks` / `force_block_exempt`（详 `data/sticky.dev.example.yaml`）。
- **默认场景预设**：`sticky.dev.example.yaml` 7 条软件开发场景核心方向
  （长期方案 / 不阻塞 / 直白中文 / 完成证据 / 不喂测试集 / 不绕开检测 /
  先读再写）。
- **8 个工程检测函数**（`karma/checks/`）：`long_term_fundamental` /
  `non_blocking_parallel` / `chinese_plain_no_jargon` /
  `loud_failure_with_evidence` / `no_testset_no_future_leakage` /
  `read_before_write` / `keep_pushing_no_stop` / `bypass_karma_detection`。
- **session_state**：跨 hook 的 `turn_count` / 文件读写跟踪 /
  background 任务接证据 / 30 天自动清理。
- **violations.jsonl**：append-only 违反记录 + 5000 行自动 rotation。
- **CLI 命令**：`karma init` / `install-hooks` / `uninstall-hooks` /
  `doctor` / `stats` / `audit` / `reset` / `sticky list|edit|remove` /
  `violations recent|clear`。
- **桌面通知**：macOS（osascript） / Linux（notify-send） /
  Windows（msg）跨平台支持，`KARMA_NO_NOTIFY=1` 关。
- **累积告警 + 强制干预**：按 turn 维度（不是人类时钟）的违反累积，
  超阈值触发 Stop hook `decision=block`；`force_block_exempt: true`
  配置字段豁免「应该继续推进」类规则避免语义自我矛盾。
- **元层监管**：`bypass_karma_detection` check 拦 Bash 命令含 karma
  内部敏感字面 + 写操作（防 Agent 手改 session-state 绕检测）。
- **强提醒 fallback**：UserPromptSubmit hook 读上一 transcript 跑所有
  violation_checks，命中的注入「强提醒」段告诉本 turn Claude 上次违反。

### Fixed

- **Stop hook matcher 配置 bug**：`install-hooks` 给所有 event 加
  `matcher: '*'` → Stop / SessionStart / SessionEnd 等 event 不支持
  matcher → 被 Claude Code 无声忽略 → Stop hook 没装上。修：只对
  PreToolUse / PostToolUse / UserPromptSubmit 加 matcher。
- **`recent_turns / count_recent_turns` turn=None fallback bug**：
  老格式（turn 维度引入前）违反无 turn 字段时 `.get("turn", 0)`
  fallback 成 0，落入当前 turn 窗口造成 force_block 假阳。修：
  `if turn_raw is None: continue` 跳过。
- **force_block 跟「不阻塞 / 继续推进」类规则语义自我矛盾**：累积
  「停下太多」违反 → 触发 force_block 让 Agent「必须停下让用户介入」
  恰好再次违反规则本身。修：sticky schema 加 `force_block_exempt`
  配置字段，去硬编码 sticky id 名单。
- **`pyproject.toml` wheel 打包指向不存在文件**：`force-include` 指
  `sticky.example.yaml`（重命名后忘同步）。修正为 `sticky.dev.example.yaml`
  + `config.example.yaml`。

### 评审驱动的发布质量打磨

4 个独立 Opus 4.7 评审 Agent 跑出来的 P0 / P1 / P2 全部落地：

**安全 / 隐私**：
- `violations.py` 写入前 snippet 脱敏（`/Users/<name>/` → `~/`，长度上限 120 字符）
- `notify.py` argv 清洗（剥前导 `-` + 限长 + 折叠换行）防 notify-send / msg
  把用户 `violation_keywords` 当 flag 解析
- `cli.py install-hooks` JSONDecodeError 改 abort + 提示（之前静默覆盖会清空
  用户其他 settings.json 配置如 permissions / mcp / env）
- `_save_settings` 改 tmp + `os.replace` 原子写防中断 truncate
- 每次 install-hooks 额外写带时间戳备份（保留初次 `.before-karma` + ts 版本）

**假阳收紧（首装最高频痛点）**：
- `long_term --no-verify/--skip*/--force` 泛 flag 收紧到「git 危险动作 + 危险
  flag 同句」（之前 pytest --skip-broken / pip install --skip-existing /
  cmake --force / rsync --force 等合法 flag 全命中）
- `non_blocking._WAIT_RE` 改 `_is_blocking_wait` helper（拆子命令独立看，
  kubectl wait / docker wait / aws cloudformation wait / gcloud / az 豁免）
- `bypass_karma._WRITE_OP_RE` 移除 `cp/mv/rm`（用户备份 karma 状态文件 /
  清老 rotation 是合法自治，真 hack 路径用 `echo > / python write_text` 仍能 catch）
- `keep_pushing` 加 `_SUCCESS_REPORT_RE` 豁免「数字 + 通过词」类汇报
  （sticky #4「完成要有证据」鼓励的行为不该被 #7 罚）
- `read_first` 路径规范化（`./foo.py` / `foo.py` / `/abs/foo.py` / `~/foo.py` 等价）

**代码质量 refactor**：
- `karma/checks/_types.py` 抽 `CheckHit` / `CheckFn` Protocol —— 消除 8 处
  子模块函数体内反向 `from karma.checks import CheckHit` 循环依赖代码味道
- `violations.py` 抽 `_scan_tail_jsonl` 用 `collections.deque(maxlen=N)`
  真 tail（之前 `splitlines()[-N:]` 是全文件读再切片）；4 个 `recent_*`
  从 20+ 行重复减到 8-12 行调用 helper
- `run_checks` 加 `KARMA_DEBUG=1` 门控的 stderr trace（check 函数抛异常时
  打 traceback 让用户调试自定义 check 不再黑盒）

### Test / Quality

- 241 个测试全过；ruff lint 0 error；vulture 死代码扫 0 输出。
- `pip install -e ".[dev]"` 装 pytest + ruff + vulture。
- `.github/workflows/ci.yml` 跨 ubuntu / macOS × py3.11 / 3.12 跑 lint +
  vulture + pytest + wheel build。

[Unreleased]: https://github.com/jhaizhou-ops/karma/compare/v0.4.9...HEAD
[0.4.9]: https://github.com/jhaizhou-ops/karma/releases/tag/v0.4.9
[0.4.8]: https://github.com/jhaizhou-ops/karma/releases/tag/v0.4.8
[0.4.7]: https://github.com/jhaizhou-ops/karma/releases/tag/v0.4.7
[0.4.6]: https://github.com/jhaizhou-ops/karma/releases/tag/v0.4.6
[0.4.5]: https://github.com/jhaizhou-ops/karma/releases/tag/v0.4.5
[0.4.4]: https://github.com/jhaizhou-ops/karma/releases/tag/v0.4.4
[0.4.3]: https://github.com/jhaizhou-ops/karma/releases/tag/v0.4.3
[0.4.2]: https://github.com/jhaizhou-ops/karma/releases/tag/v0.4.2
[0.4.1]: https://github.com/jhaizhou-ops/karma/releases/tag/v0.4.1
[0.4.0]: https://github.com/jhaizhou-ops/karma/releases/tag/v0.4.0
[0.3.0]: https://github.com/jhaizhou-ops/karma/releases/tag/v0.3.0
[0.2.4]: https://github.com/jhaizhou-ops/karma/releases/tag/v0.2.4
[0.2.3]: https://github.com/jhaizhou-ops/karma/releases/tag/v0.2.3
[0.2.2]: https://github.com/jhaizhou-ops/karma/releases/tag/v0.2.2
[0.2.1]: https://github.com/jhaizhou-ops/karma/releases/tag/v0.2.1
[0.2.0]: https://github.com/jhaizhou-ops/karma/releases/tag/v0.2.0
[0.1.1]: https://github.com/jhaizhou-ops/karma/releases/tag/v0.1.1
[0.1.0]: https://github.com/jhaizhou-ops/karma/releases/tag/v0.1.0
