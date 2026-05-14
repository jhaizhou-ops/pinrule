# Changelog

记录 karma 每个版本的重要变化。版本号遵循 [SemVer](https://semver.org/lang/zh-CN/)。

## [Unreleased]

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

[Unreleased]: https://github.com/jhaizhou-ops/karma/compare/v0.2.1...HEAD
[0.2.1]: https://github.com/jhaizhou-ops/karma/releases/tag/v0.2.1
[0.2.0]: https://github.com/jhaizhou-ops/karma/releases/tag/v0.2.0
[0.1.1]: https://github.com/jhaizhou-ops/karma/releases/tag/v0.1.1
[0.1.0]: https://github.com/jhaizhou-ops/karma/releases/tag/v0.1.0
