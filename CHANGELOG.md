# Changelog

记录 karma 每个版本的重要变化。版本号遵循 [SemVer](https://semver.org/lang/zh-CN/)。

## [Unreleased]

## [0.4.5] — 2026-05-14（patch — KARMA_HOME 环境变量 + sub-agent 评审驱动改进）

「同事即将首装」我 spawn 一个 sub-agent 扮演陌生用户跑首装清单**真测试**，
找到 5 条真问题。本版修最关键 P0：

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
真生效）：default 路径 / env override / 5 module 一致 / `~` 展开。

### Test

测试 308 → 312 全过，4 件套全绿。

### Pending（sub-agent 评审剩余 4 条 — 跟同事真实首装数据驱动再修）

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
真修对。

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
`/dev/stdout` 等丢弃目标 — 它们不是真写到文件系统。

```python
>\s*(?!/dev/(?:null|zero|stderr|stdout))[/.~\w]
```

对偶守护：`2> /tmp/err.log` 这种真写日志文件**仍**算写（lookahead 只排除
丢弃目标，普通文件路径不放过）；`echo bad > ~/.claude/karma/session-state/abc.json`
真写 karma 状态仍要拦。

加 2 条守护测试覆盖只读 inspection + 真写对偶。

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

### Verified（真跑实测）

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

### Technical findings（实测真跑得到的协议细节）

- Codex feature flag 真名是 **`hooks`** 不是 `codex_hooks`（vibe-island
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
- 实测装机：`karma install-hooks --backend codex` 真写 `~/.codex/hooks.json`，
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

- **`karma init --minimal`** 显式 flag 装 5 条真中性核心模板（评审 C Agent
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
    外层（shell 双引号真行为就是展开 substitution 执行）；单引号字面不动
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
- **mypy 类型化** — 之前我说「会改 200+ 行」推迟，**真跑后只有 3 个 error**
  10 分钟修完（`testset.py` / `long_term.py` underscore 变量名跨类型重用 →
  `_label`；`cli.py:_karma_event_entry` dict 异质 value → `dict[str, object]`
  显式标注）。mypy 加进 `[project.optional-dependencies].dev` + CI 步骤守护。

### Test / Quality

- `run_checks` `KARMA_DEBUG=1` 门控加 3 条守护测试 — 之前加了功能没真验证过
  实际行为属于 sticky #4 「完成要有证据」违反。
- 测试 246 → 249，CI 跨平台跨 Python 版本全过，mypy 0 issue。

## [0.2.0] — 2026-05-14（minor — README 重组 + 新增真中性 sticky 模板）

### Added

- **`data/sticky.dev.minimal.example.yaml`** 真中性 5 条核心 sticky 模板：
  long-term-fundamental / non-blocking-parallel / loud-failure-with-evidence /
  deep-fix-not-bypass / read-before-write。砍掉默认 7 条里两条场景化规则
  （chinese-plain-no-jargon 中文用户偏好 / no-testset-no-future-leakage
  ML 场景）。
  - 评审 C Agent 真痛点：默认 7 条违反 CLAUDE.md「不针对当前用户作弊」
    原则。英文母语 / 非 ML 用户可 `cp data/sticky.dev.minimal.example.yaml
    ~/.claude/karma/sticky.yaml` 切换。
  - 默认 `karma init` 仍装 7 条（向后兼容现有 0.1.x 用户）。

### Changed

- **README 重组**（评审 C Agent 真痛点：视角错位 — 给「Agent 接力」写不是
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

[Unreleased]: https://github.com/jhaizhou-ops/karma/compare/v0.4.5...HEAD
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
