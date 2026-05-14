# Changelog

记录 karma 每个版本的重要变化。版本号遵循 [SemVer](https://semver.org/lang/zh-CN/)。

## [Unreleased]

## [0.1.0] — 2026-05-14（首个公开版本）

karma v2 的第一个可发布版本，经历多轮 dogfooding 修真 bug。

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

### Test / Quality

- 232 个测试全过；ruff lint 0 error；vulture 死代码扫 0 输出。
- `pip install -e ".[dev]"` 装 pytest + ruff + vulture。

[Unreleased]: https://github.com/jhaizhou-ops/karma/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/jhaizhou-ops/karma/releases/tag/v0.1.0
