# Changelog

**[🇬🇧 English (current)](./CHANGELOG.md) · [🇨🇳 中文](./CHANGELOG.zh.md)**

Documents karma's important version changes. Versioning follows [SemVer](https://semver.org/).

> 📝 **English changelog status**: historical release notes (v0.1.0 through v0.5.0) are in Chinese-only ([CHANGELOG.zh.md](./CHANGELOG.zh.md)). Releases from v0.5.1 onward publish bilingually in both files.
>
> The Chinese version is comprehensive (2300+ lines covering every release's design rationale, root-cause analysis, and "wrong diagnosis lessons"). Backfilling the pre-v0.5.1 English history is a separate documentation effort, not part of the i18n refactor (which is fully complete — see [docs/REFACTOR_PLAN_RULE_AND_I18N.md](./docs/REFACTOR_PLAN_RULE_AND_I18N.md)).

## [Unreleased]

## [0.11.3] — 2026-05-16 (minor — `karma audit --days N` 时间窗口过滤: dogfood-driven 决策不被老数据稀释)

### 加什么

`karma audit` (含 `--by-check`) 加 `--days N` 选项. 只统计最近 N 天的违反, 让 dogfood-driven 决策聚焦 fresh 窗口效果, 不被老数据稀释.

**为啥要**: v0.11.0 long_term response-level + v0.11.1 deep_fix L3 ship 后, 想看 engine 真效果 — 但 `karma audit --by-check` 默认全量统计 (含 v0.5.x 期老数据), 新增 pattern 真触发被淹. v0.11.3 给个干净的 fresh-window 视角.

### 用法

```bash
karma audit --by-check --days 1        # 最近 24 小时
karma audit --by-check --days 7        # 最近 1 周
karma audit --days 30 --format md      # 最近 1 月, markdown 表
```

无 `--days` 时行为不变 (全量 violations.jsonl).

### 边界 case

- `--days N` 必须 > 0 (非整数 / ≤ 0 → 友好错误 + exit 2)
- 窗口内 0 条违反 → 显示「最近 N 天没违反记录. 可以试更长窗口或不带 --days 看全量」(区别于真没违反)

### Test coverage

2 个 lockdown:
- `test_audit_days_filter_excludes_old_violations` — 老 + 新 mixed 数据, `--days 1` 只显示 fresh
- `test_audit_days_filter_empty_window_message` — 空窗口提示要含天数

### Gate

- 622/622 tests / ruff / mypy / wheel build 全绿
- push 后 30 秒内 `gh run list --branch main` verify CI

## [0.11.2] — 2026-05-16 (patch — fix v0.10.6 引入的 CI regression: turn/model 推进早于 rules 加载)

诚实承认: v0.10.6 + v0.11.0 + v0.11.1 + README + ARCH 总共 5 个 commit 我没看 CI 状态就 push (严重违反 sticky #4 loud-failure). 跟 codex PR #6 准备 merge 时才发现 CI 4 个 job 全挂在 `test_user_prompt_submit_writes_payload_model_to_state`.

### 真根因

`user_prompt_submit.main()` 在 sticky_list 为空时直接 `_output_passthrough; return 0` — 完全跳过 `_advance_turn_state`. 但 model 跟踪 + turn_count 是 **karma 系统级 telemetry**, 跟用户有没有装 rules 无关. 本机过因为我 home 有老 `sticky.yaml`; CI 干净 runner 永远空 rules → 永远不写 model.

不是 codex PR #6 引入, 不是 v0.10.6 protocol_adapter 改的. 是更上游的设计错位 — `_advance_turn_state` 顺序错放在 sticky_list 检查之后.

### Fix

把 `_advance_turn_state` 提到 sticky_list 加载之前. 不管 rules 是否存在, 每个 user prompt 都推进 turn_count + 更新 model. sticky_list 空时仍走原 `_output_passthrough` 提前 return, 但 telemetry 已经在 state 里了.

### Regression lockdown

`test_user_prompt_submit_writes_payload_model_to_state` 加强:
- `monkeypatch.setattr("karma.hooks.user_prompt_submit.load", lambda: [])` — 显式模拟空 rules
- 加 `assert state.turn_count == 1` — 锁住 turn 也要推进, 不只是 model

### Gate

- 620/620 测试过
- ruff / mypy / wheel build 全绿
- CI 4 个 matrix job 这次必须先看再 push (上一波违反 sticky #4 已记忆 [feedback-loud-failure-pre-push-ci-check])

## [0.11.1] — 2026-05-16 (patch — `deep-fix-not-bypass` L3 时序 pattern: 测试失败紧跟 Edit 没读源拦)

User-flagged #1 priority: 用户最重视的规则是 `deep-fix-not-bypass` (反对 Agent 草草了事不深挖). v0.11.1 给这条 rule 加 L3 时序层 engine pattern, 跟现有 L1 (Bash 字面绕 karma 状态) 并存.

### 加什么

**新增检测路径** (在 `karma/checks/bypass_karma.py` 复用 rule_id `deep-fix-not-bypass`):
- pre_tool_use Edit 时, 看 `session_state.recent_bash[-1]`
- 如果上一 Bash 是测试命令 (`is_test_cmd=True`) 且**失败** (`output_failed=True`)
- 而且当前 Edit 的 file 在本 session **从没 Read 过** (`not session_state.has_read(fp)`)
- → 直接拦, trigger 文案 = 「测试失败后立刻 Edit X 但本 session 没 Read 过 — 没看源代码就改是『草草了事』典型」

### 工程化天花板 (老实写, 不藏)

这是 deep_fix 4 层证据分类的 **L3 时序层**:
- L1 字面 (`--no-verify` / TODO 注释 / hardcoded hash): v0.10.x 已覆盖
- L2 话术 (「先打补丁」/「先这样 ship」): v0.11.0 response-level 覆盖
- **L3 时序 (报错紧跟改, 没读源): v0.11.1 本次加**
- L4 认知 (Agent 内心是不是真挖了根因): **工程拦不到**, 只能靠 preference 注入 + 用户后置抽查

**预期上限**: 综合 L1+L2+L3 engine 触发率从 v0.11.0 的 ~20% (response 层) 上行到 ~30-35%, **不会到 100%**. L4 占了 deep_fix 真违反空间的大头, 那部分必须靠 preference 提示 + 用户自己用经验抓.

### 假阳防御 (4 个 lockdown test)

- ✅ Edit + test_fail + 没 Read → 拦
- ✅ Edit + test_fail + 已 Read → 不拦 (合法 debug)
- ✅ Edit + test_pass → 不拦 (不是报错救火)
- ✅ Edit + 非测试 Bash fail → 不拦 (network/build 失败不算 test 触发)

### Test coverage

`tests/test_false_negative_regression.py` 加 4 个 case, 总测试 611 → 615.

## [0.11.0] — 2026-05-16 (minor — long_term-fundamental engine 重新设计, 加 response-level 话术 pattern 让 engine 真触发)

v0.10.x dogfood data audit (2026-05-16 真证据驱动): `long-term-fundamental` rule 217 条总违反, **0% engine 触发率** (12 条全 keyword fallback). 根因 = engine 维度选了**工程层证据** (`--no-verify` / TODO 注释 / hardcoded hash 都很罕见), 而 Agent 真违反场景是**话术**（"先打个补丁" / "短期方案" / "硬编码先这样"）.

v0.11.0 给 `long_term.py` 加 **response-level engine check** 跟现有 tool_input 层并行, 让 engine 真有机会捕话术意图:

### 新增 2 类 response-level pattern

1. **第一人称 + 短期动作 (`response_patch_intent`)**: 必须含「我/咱/这次/临时/目前/当前/让我」类**意图前缀** + ≤ 12 字内含「先打个补丁/打个补丁/先硬编码/临时硬编码/凑数/短期绕/临时方案/绕过验证/先 workaround/patch 一下/先 hardcode」类**短期动作动词**. 组合 pattern 防止假阳:
   - ✅ "这次先打个补丁让 CI 过" 拦 (意图 + 动作组合)
   - ✅ "我先硬编码这个 case 先" 拦
   - ❌ "短期补丁不行, 应该挖根因" 不拦 (反思不是宣告)
   - ❌ "补丁是给老代码用的" 不拦 (讨论字面不是意图)

2. **承认但仍 ship (`response_acknowledge_but_proceed`)**: 显式承认「不是长期方案」+ 紧跟「但 / 先这样」转折:
   - ✅ "我知道不是长期方案 但先这样 ship 出去" 拦
   - 同 rule #1 例外的反方向: 承认债务但选择主动还

### 跟 keyword 维度协同

v0.10.x keyword (rules.yaml `violation_keywords`) 仍兜底单字面 (「打补丁 / 短期方案」等). v0.11.0 engine 加的是**组合 pattern** — keyword 字面+ 意图前缀同时命中才精确拦, 给 audit 维度 (engine vs keyword) 暴露真违反 vs 假阳的区分.

### check 函数签名扩展

`long_term.check()` 加 `response: str = ""` 参数, Stop hook 跑 check 时传 response (Stop hook 是 karma 看 Agent 整 turn 输出的唯一 hook). 老 tool_input 路径 (Bash/Write/Edit) 不变.

### Test coverage

`tests/test_false_negative_regression.py` 加 5 个 lockdown 测试:
- `test_long_term_response_patch_intent_first_person`
- `test_long_term_response_patch_intent_hardcode`
- `test_long_term_response_acknowledge_but_proceed`
- `test_long_term_response_reflection_no_false_positive` ⭐ 假阳防御 (反思场景不拦)
- `test_long_term_response_no_response_no_check` (空 response 走老路径)

i18n: `data/locales/{zh,en}.yaml` 加 `response_patch_intent.trigger` + `response_acknowledge_but_proceed.trigger` 双语. fix 复用现有 `patch_intent.fix`.

### Verification

- **611/611 passing** under both `LANG=zh_CN.UTF-8` and `LANG=en_US.UTF-8` (was 606)
- 全 5 道 gate 通过 (pytest zh + en / ruff / mypy / vulture --min-confidence 60)
- `chinese-plain` engine 0% 问题留 v0.11.1 — `chinese-plain` 跟 keyword 维度重叠 (字面 jargon 检测), 修法是 rules.yaml 字面应该从 violation_keywords 挪到 engine `_JARGON_RE`. 这跟 long-term 反方向 (long-term 是维度互补, chinese-plain 是维度重叠需要解开).

### Meta-pattern: 真证据驱动 rule 维度审计

v0.11.0 的方向不是凭空猜的, 是 v0.10.5 audit 后真 dogfood 数据 (217 条违反 / 13 session / 2 天) 跑 engine vs keyword 比例分析后浮现的:

| Rule | engine 比例 | 含义 |
|---|---|---|
| read-before-write | 67% | 设计最对齐 (file_path-based 精度高) |
| keep-pushing-no-stop | 34% | RLHF default 全 turn 触发 |
| loud-failure-with-evidence | 31% | engine + keyword 平衡 |
| no-testset-no-future-leakage | 20% | engine 设计严 |
| non-blocking-parallel | 18% | engine 严 |
| deep-fix-not-bypass | 14% | engine 设计窄 |
| long-term-fundamental | **0%** ← v0.11.0 修这条 | engine 维度错: 工程层 vs 话术 |
| chinese-plain-no-jargon | 0% ← v0.11.1 候选 | engine 维度重叠 keyword |
| lighthearted-vibe | 0% | 设计就靠 keyword (无 engine 必要) |

未来加新 rule 应该按这套维度自检: engine 命中率 < 20% 就该回头审 check 设计.

## [0.10.6] — 2026-05-16 (minor — close v0.10.5 deferred 3: emit_context_injection / emit_stop_block backend contracts + model_from_payload hook integration tests)

v0.10.5 audit sweep deferred 3 structural findings; v0.10.6 closes them.

### Backend Protocol expanded 6 → 8 contract methods

`karma/backends/_base.py:Backend` adds:
- `emit_context_injection(event_name, additional_context, payload) -> str`
- `emit_stop_block(reason, payload) -> str`

`JsonHooksBackend` (default base) provides Claude-shape implementations matching previous direct-print behavior — Claude users see zero behavior change. Gemini override `emit_stop_block` returns `{}` (AfterAgent has no block concept — fail-open instead of silently rejected). Codex inherits Claude shape for now (Stop event acceptance still needs real codex testing — codex backend owner TODO).

### 4 ContextInjection hooks now route through `protocol_adapter.emit_context_injection`

Fixes Agent 2 F2.2: `session_start.py` / `user_prompt_submit.py` / `post_tool_use.py` / `subagent_start.py` previously direct-printed `{hookSpecificOutput: {hookEventName, additionalContext}}` Claude shape, never reaching backend dispatch. Codex SessionStart/UserPromptSubmit shape acceptance was untested (v0.9.15 same-pattern bit us). All 4 now go through `protocol_adapter.emit_context_injection(event_name, additional_context, payload)` — backend decides shape, Claude users unchanged, Codex/Gemini override-able.

### Stop hook routes through `protocol_adapter.emit_stop_block`

Fixes Agent 2 F3: `stop.py` force_block + keep_pushing_block paths previously direct-printed `{decision: "block", reason}` Claude shape. Gemini `AfterAgent` has no `decision: block` semantic; Codex Stop hook acceptance unverified. Both block paths now go through `emit_stop_block(reason, payload)`. Gemini returns `{}` (Stop intervention not applicable on AfterAgent — fail-open Agent unaffected). Stop.py `_handle_force_block` + `_handle_keep_pushing_block` signatures extended with `payload` param; main() passes it through.

### `model_from_payload` 3-hook integration tests (F3.3)

`tests/test_model_threshold.py` adds 3 integration tests: each hook (session_start / user_prompt_submit / post_tool_use) verifies `state.model` is written from `payload.model` field, not from transcript fallback (transcript_path deliberately points to nonexistent file to prove payload.model is the actual source). Tests cover `gpt-5.5` / `gpt-5.4-mini` / `gpt-5.3-codex` across the three hooks. Matches v0.9.12 trigger_key lesson (single-line hook integration is easy to refactor-break — lockdown each line).

### 2 new cross-backend contract tests

`tests/contract/test_backend_contract.py` adds parametrized tests for the new 2 methods. All 3 backends × 2 methods = 6 new contract checks ensuring `emit_context_injection` / `emit_stop_block` return valid JSON strings on any backend.

### Verification

- **606/606 passing** under both `LANG=zh_CN.UTF-8` and `LANG=en_US.UTF-8` (was 597 — +9 new lockdowns: 6 contract emit_* + 3 hook model integration)
- All 6 local gates pass (pytest zh + en / ruff / mypy / vulture --min-confidence 60 / wheel build+verify+smoke)
- Backend Protocol now 8 contract methods (was 6) — `tests/contract/` auto-validates all 8 × N backends on every new backend registration

### Cross-perspective audit pattern fully closed for v0.10.x

All 18 findings from v0.10.5 audit sweep now addressed: 10 in v0.10.5 + 3 in v0.10.6 + 5 had been Agent 2 minors already shipped within v0.10.5. **6 consecutive v0.10.x releases (v0.10.0 → v0.10.6) constitute a complete backend ownership-split + cross-platform parity cycle**: architecture (v0.10.0) → codex 3 PRs (v0.10.1-3) → karma maintainer parity push (v0.10.4) → audit sweep (v0.10.5) → structural close (v0.10.6).

## [0.10.5] — 2026-05-16 (minor — 4-perspective cross-audit sweep: 10 findings fixed across docs / functional / state / boundary)

User triggered 4-perspective cross-audit (3 Claude parallel agents + dogfooding evidence) after 5 consecutive v0.10.x releases. Recovered v0.9.13-pattern truth: rapid iteration accumulates new drift. 18 findings surfaced — 17 hand-verified true (0 false positives). v0.10.5 batch-fixes 10 (functional + critical + minor); v0.10.6 will tackle the 4 structural ones (context-injection / stop-block backend contract methods + 3-hook integration tests).

### Fixed in v0.10.5

**Critical docs corrections** (Agent 3 F3.1 + F3.2):
- README FAQ "Codex needs manual /hooks approval" contradicted main table's "auto-trust takes effect immediately" (v0.10.2). Both languages corrected to: "wrappers are auto-trusted by `karma install-hooks --backend codex`; if `/hooks` shows 'modified', Codex changed hash algorithm — re-approve + file issue."
- `docs/CODEX_BACKEND.md` TODO list 4/5 items were already shipped (v0.10.1 PR #3 / v0.10.2 PR #4 / v0.10.3 PR #5) but still listed as "planned" — misled future contributors. Split into "Completed (v0.10.x)" + "Remaining" sections both languages.

**Functional bug** (Agent 2 F4):
- `karma/hooks/post_tool_use.py` now consumes canonical `tool_input.write_file_paths` (backend-neutral, parallel to existing `read_file_paths`). Any backend's `normalize_tool_input` emitting this list triggers `state.record_edit(path)` per path → `last_edit_ts` advances. Fixes codex `sed -i /workspace/src/x.py` not being seen by `evidence.check` (false-pass on completion words). Integration test `test_post_tool_use_records_canonical_write_file_paths_advances_last_edit_ts` locks it. **codex backend follow-up needed (TODO 7 in CODEX_BACKEND.md)**: codex.normalize_tool_input currently sets `is_write: True` for `sed -i` but doesn't emit `write_file_paths` — karma-side wiring is forward-compatible; codex CLI maintainer should add the field next PR.

**Boundary leak fix** (Agent 2 F1):
- `karma/backends/protocol_adapter.py` removed two `codex` literal fallbacks (`from karma.backends.codex import _CODEX_TOOL_MAP` + `REGISTRY["codex"].normalize_tool_input(...)` force-route on `raw_tool_name == "apply_patch"`). `detect_backend()` now routes correctly via `sys.argv[0]` `/.codex/` literal detection — fallbacks were vestigial and violated v0.10.0 "dispatch layer has no backend literals" design self-statement. Tests updated to mock `sys.argv` instead of relying on fallback.
- Removed v0.9.16 back-compat re-export `parse_apply_patch_envelope` from protocol_adapter — tests now import from codex.py directly.

**State / off-by-one** (Agent 1 F1.1 + F1.2 + F1.3):
- `karma/hooks/pre_compact.py` fallback math fix: `current_turn=999999` + `window=5` produced cutoff `999995` matching only turns 999995-999999 (never real session turns 1-100) → `recent_violation_turns` was always empty when `state.turn_count=0`, breaking the compact-resilience "most recent 5 turn violations" section in pre_compact_snapshot.md. Fallback path now reads ts-dimension `recent(window_sec=24h)` directly.
- `karma/hooks/stop.py` now calls `catchup_pending_bg()` via `update_state(try/except + fail-open fallback)`, matching Pre/PostToolUse and UserPromptSubmit pattern. Fixes window-edge case where a bg pytest finishing after the last PostToolUse but before Stop hook fires wasn't recorded → `evidence.check` saw stale `has_recent_test_pass=False` → false-positive loud-failure block on completion words.
- `karma/hooks/user_prompt_submit.py` strong_reminder now writes Violation `turn=current_turn - 1` not `current_turn` — strong_reminder scans the **previous** turn's assistant response; turn_count was already advanced N → N+1 before strong_reminder runs.

**Minor regex / docstring corrections** (Agent 1 F1.4 + F1.5 + Agent 3 F3.4 + Agent 2 F5 + F6):
- `karma/checks/chinese_plain.py:_PATH_LITERAL_RE` changed `\w` (Unicode-aware by default in Python re) to explicit `[a-zA-Z0-9./\-_]` ASCII char class. Original ate Chinese path segments (`/桌面/某目录/文件.py` whole-path stripped) reducing the Chinese-ratio denominator → false-positive `chinese-plain` blocks for Chinese users with Chinese paths.
- `karma/hooks/post_tool_use.py` comment said `DEFAULT 60K` but `DEFAULT_THRESHOLD = 40_000` since v0.9.0 — corrected.
- `karma/model_threshold.py` module docstring listed v0.4.35 thresholds (Opus 80K / Sonnet 60K / Haiku 30K) but actual `_MODEL_THRESHOLDS` is v0.9.0 + v0.10.4 (Opus 60K / Sonnet 40K / Haiku 30K + 11 OpenAI/Codex entries). Docstring updated to current truth.
- `karma/backends/codex.py:_extract_codex_patch_text` now docstring-flags which wrap keys are real-captured (`input` only) vs speculative (`patch` / `command` / `diff`) and prints stderr warning when a speculative key is actually hit — rule #4 loud-failure-with-evidence + invites users to file issue + real payload capture so the function can be tightened.
- `karma/model_threshold.py:extract_model_from_transcript` docstring clarifies it's Claude-Code-specific (regex assumes Claude transcript jsonl shape); other backends should use `payload.model` via `model_from_payload`, not fall through to this.

**Signal wordlist drift fix + lockdown** (Agent 3 F3.5 + F3.6):
- `data/signals/agent_saturation/en.txt` added 12 entries for dual coverage with zh.txt's `系列收官` / `明天接力` / `下次接力` families — was 40 zh / 28 en = 30% drift (matched v0.9.13 D1 threshold). Now 40 zh / 42 en = 5% drift.
- New `tests/test_signals.py:test_signals_zh_en_parity_within_30pct` walks all `data/signals/<name>/zh.txt`+`en.txt` pairs and fails CI if any drift > 30%. Future drifts in any direction get caught automatically — no more human audits required for this class.

### Cross-perspective audit pattern

3 Claude parallel agents (logic / boundary / docs+tests) + dogfooding-evidence perspective 4. Real auditing math this run:
- v0.9.13 single-agent: 5 findings / 4 real bugs (high SNR — multi-year drift)
- v0.9.14 3-agent: 9 findings / 2 real bugs (low SNR — repo clean after v0.9.13)
- **v0.10.5 4-perspective: 18 findings / 17 real (94% SNR)** — rapid iteration accumulates drift faster than diminishing-returns predicts. Audit value reappears when iteration velocity is high.

### Deferred to v0.10.6

3 structural findings (require backend contract method additions, larger PR than v0.10.5 scope):
- F2.2 `emit_context_injection(event, additional_context, payload)` contract — 4 ContextInjection hooks currently print Claude `hookSpecificOutput` shape directly, never going through `protocol_adapter.emit_*` routing. Codex SessionStart/UserPromptSubmit shape acceptance untested (v0.9.15 same pattern bit us).
- F2.3 `emit_stop_block(reason, payload)` contract — `stop.py` direct-prints `{decision: "block", reason}` without backend dispatch. Codex Stop hook acceptance unverified. karma's strongest intervention (force_block) potentially silent-failing on codex.
- F3.3 3-hook integration tests for `model_from_payload` wiring.

### Verification

- **597/597 passing** under both `LANG=zh_CN.UTF-8` and `LANG=en_US.UTF-8` (was 595 — +2 new locks: write_file_paths + zh/en parity)
- All 6 local gates pass

## [0.10.4] — 2026-05-16 (minor — prefer codex payload model + OpenAI/Codex threshold table for cross-platform attention adaptation)

karma's mid-turn reinject + model-adaptive thresholds were Claude-specific. Codex agents using karma got DEFAULT 40K threshold for `gpt-5.5` (1M-context flagship) — too tight, disrupting expression. v0.10.4 closes this gap with two changes:

### Unified `model_from_payload(payload)` — payload.model first, transcript fallback

Codex official [hooks docs](https://developers.openai.com/codex/hooks) state every command hook stdin contains the `model` field (active model slug) — and explicitly warn that `transcript_path` format **is not a stable hook interface**. Previously karma's user_prompt_submit and post_tool_use hooks went straight to `extract_model_from_transcript()` (v0.4.39 Claude-protocol-limitation workaround), missing the stable codex signal.

New `karma/model_threshold.py:model_from_payload(payload)` unifies the lookup:
1. `payload.model` first (skip `<synthetic>` per existing convention)
2. `extract_model_from_transcript(payload.transcript_path)` fallback

**Claude behavior unchanged**: most Claude hook events (except SessionStart) don't have `model` field, so they naturally fall through to transcript path.

**Codex behavior upgraded**: every codex hook payload carries fresh model slug (including post-`/model` switch). karma now detects mid-session model changes the same hook it happens — `gpt-5.5` agents get 120K threshold immediately instead of waiting for transcript-scan fallback.

Wired into all 3 hooks: `session_start.py` / `user_prompt_submit.py` / `post_tool_use.py`.

### OpenAI / Codex model threshold table

`_MODEL_THRESHOLDS` extended with 11 OpenAI/Codex model entries based on official context windows + attention decay heuristics:

| Model | Context window | karma threshold | Rationale |
|---|---|---|---|
| gpt-5.5 | 1,050,000 | 120K | ~12% context reinject cadence for 1M flagships |
| gpt-5.4 | 400K | 120K | same flagship tier |
| gpt-5.3-codex / gpt-5.2-codex / gpt-5.1-codex-max | 400K | 80K | Codex flagship-class, same tier as Claude Opus |
| gpt-5.4-mini / gpt-5.1-codex-mini | mid-tier | 40K | mid-tier, Sonnet-class |
| gpt-5.4-nano / gpt-5.3-codex-spark / codex-mini | small | 30K | small, Haiku-class |
| gpt-5 | generic fallback | 80K | unspecified gpt-5.x defaults to flagship tier |

Keyword priority preserved: long strings before short (`gpt-5.5` matched before `gpt-5`, `gpt-5.3-codex-spark` before `gpt-5.3-codex`, etc.). `DEFAULT_THRESHOLD` stays 40K for unknown models (don't globally raise — could be local small model).

Claude model entries unchanged: `opus → 60K / sonnet → 40K / haiku → 30K`.

### Honest scope — what v0.10.4 does NOT do

Per Codex hooks API limitations (verified in v0.10.2/v0.10.3 research):

- **`PreCompact` not hookable** — Codex 0.130 hook API has no PreCompact event. Codex platform internally has `enable_request_compression` feature flag but it's not surfaced as a lifecycle event. karma can't snapshot pre-compact rule state on codex like it does on Claude.
- **`SubagentStart` / `SubagentStop` not hookable** — Codex platform has `enable_fanout` / `child_agents_md` feature flags (under development) but no hook events for them. karma can't isolate sub-agent state on codex like it does on Claude Task tool.
- **`PermissionRequest` not integrated** (ADR-001 in codex.py, v0.10.3): karma already covers risky-action interception at PreToolUse layer via `bypass_karma` / `testset` / `read_first` checks. PermissionRequest as a second pass adds FP rate without new dimension.

Mid-turn reinject (the v0.10.4 target) is the cross-platform substitute — works on both Claude and Codex.

### Verification

- **595/595 passing** under both `LANG=zh_CN.UTF-8` and `LANG=en_US.UTF-8` (was 580 — +15 new model_threshold tests)
- All 6 local gates pass
- 15 new tests covering each new threshold + `model_from_payload` priority + transcript fallback + `<synthetic>` skip + keyword priority for codex variants

## [0.10.3] — 2026-05-16 (patch — codex simple pipe reads + user_stop_hints "collaborative waiting" category 3 + docs wording fix)

Three small but high-value patches integrated:

### codex backend — simple pipe read recognition

Third codex-owned change (commit `8c0e136`). Extends `extract_read_paths_from_exec_command()` to recognize **simple read-only command chains**:
- `head -N <file> | tail -M` and `tail -N <file> | head -M`
- `cat <file> | head -N` and `cat <file> | tail -N`

Constraints: only single pipe `|`, only read-only commands on both sides, no `xargs cat` / `find ... -exec` / recursive grep (high FP risk). 4 new codex-private tests covering recognized + skipped cases.

Real evidence: codex agents in 2026-05-16 sessions commonly use `head N | tail M` to read file slices instead of single `tail` calls — these now properly register as Read, no false-positive `read_first` denial on subsequent `apply_patch`.

### karma — user_stop_hints category 3 "collaborative waiting/pause"

Real-world signal from 2026-05-16 dogfooding session: while collaborating with Codex CLI as a contributor backend, user accumulated 100+ keep_pushing false-positive triggers because phrases like `等候即可` / `不着急赶工` / `先等等, 等 codex 那边出 PR` weren't covered by `user_stop_hints` wordlist (only had cat-1 tired/dismissive + cat-2 satisfied/confirmation).

Cat-3 = **collaborative waiting/pause** is semantically distinct:
- Not cat-1 (not quitting the work)
- Not cat-2 (job not done, user knows it's mid-flight)
- Just "I'm waiting on the flow, don't push me this turn"

16 new zh entries (`等候即可 / 先等等 / 不着急 / 慢慢来 / 不用赶 / 先这样` etc) + 18 new en entries (`just wait / no rush / take your time / standby / sit tight / let me know when` etc). Real session evidence quoted in test_keep_pushing.py.

Plus locked-down known FN: `"不动 + 等 X"` combo pattern (e.g., `"不 commit 挡 working tree 不动, 等 codex"`) not covered by single-token wordlist — too risky to add bare `不动` or `等 codex` without combo-pattern engine. Documented in `test_v0103_known_fn_combo_pattern_documented`.

### docs — correct "codex has no equivalent concepts" wording

v0.10.2 CHANGELOG/HANDOFF claimed `"codex has no compact / sub-agent dispatch concepts"` — wrong without real verification (rule #4 deviation). Real evidence:
- Codex 0.130 has **6 hook events** (SessionStart / PreToolUse / PermissionRequest / PostToolUse / UserPromptSubmit / Stop), no PreCompact / SubagentStart / SubagentStop in hook API
- Codex platform internally **has the concepts** via `enable_request_compression` (stable=true), `enable_fanout` / `child_agents_md` (under-development feature flags)
- They're just **not surfaced as hookable lifecycle events** to third parties

Wording corrected to precise: "codex hook API doesn't expose these events" instead of "codex has no equivalent concepts".

### Verification

- **580/580 passing** under both `LANG=zh_CN.UTF-8` and `LANG=en_US.UTF-8` (was 575 — +4 codex pipe tests + +5 user_stop_hints tests, includes new FN lockdown)
- All 6 local gates pass

## [0.10.2] — 2026-05-16 (minor — codex closes the gap to Claude Code parity: SessionStart + exec_command→Bash + auto-trust onboarding)

**Second codex-owned PR merged**: [#4](https://github.com/jhaizhou-ops/karma/pull/4) by Codex CLI itself. Codex backend gains 3 capabilities (SessionStart event, exec_command→Bash normalization, auto-trust hooks) closing the major v0.10.1 gaps. Concrete coverage table at the bottom of this section — only PreCompact + SubagentStart/Stop remain not covered because Codex's 6 hook events don't expose those lifecycle moments to third-party hooks (Codex platform internally has the concepts via `enable_request_compression` and `enable_fanout` feature flags, but they're not hookable). Doc clarification post-v0.10.2 (the earlier "codex has no equivalent concepts" wording was incorrect — Codex has the concepts, the hook API just doesn't surface them).

### Codex SessionStart event integration (Task A)

Codex 0.130 supports SessionStart event but karma's codex backend v0.10.1 had it missing from `_HOOK_EVENTS` — meaning codex agents got no sticky baseline injection at session start (had to wait for UserPromptSubmit per-turn anchors to accumulate). v0.10.2 closes this:

- Real captured codex SessionStart payload (PR #4 evidence):
  ```json
  {"session_id":"019e2fcc-...","transcript_path":"...","cwd":"/Users/jhz/karma","hook_event_name":"SessionStart","model":"gpt-5.5","permission_mode":"default","source":"startup"}
  ```
- Fields fully compatible with Claude's SessionStart shape — karma generic `session_start.py` works out-of-the-box, no normalization needed
- Subtle finding: Codex doesn't fire SessionStart at TUI startup, fires before first user prompt — still functionally correct
- `karma/backends/codex.py:_HOOK_EVENTS` now lists 5 events (up from 4): `SessionStart / UserPromptSubmit / PreToolUse / PostToolUse / Stop`. Codex 0.130 supports 6; karma uses 5 (PermissionRequest still skipped, no karma use case).

### exec_command → Bash normalization (Task B)

Codex CLI runs all shell via `exec_command` tool name. v0.10.1 only mapped `apply_patch → Edit`, leaving codex shell calls invisible to karma's Bash-aware checks (`bypass_karma` / `record_bash` / `is_long_task`). v0.10.2:

- `_CODEX_TOOL_MAP` adds `"exec_command": "Bash"`
- `normalize_tool_input` for `exec_command` now copies `cmd` (Codex Desktop / rollout shape) into canonical `command` field so generic `post_tool_use.py` `state.record_bash(cmd, ...)` works
- Integration test in `test_codex_backend.py` locks: codex `exec_command` running `pytest tests/` recognized by `is_test_cmd` → `state.last_test_pass_ts` truly advances

### Bonus — Codex `/hooks` auto-trust (Task C)

**The single biggest onboarding UX improvement in karma's history**. v0.10.0 documented Codex 0.130+ requirement that each hook be manually approved in TUI `/hooks` command. Codex CLI's PR #4 went one level deeper: implemented `CodexBackend.trust_karma_hooks()` that mirrors Codex's own `trusted_hash` derivation algorithm and writes `[hooks.state]` entries to `~/.codex/config.toml` automatically during `karma install-hooks --backend codex`. Result: **manual `/hooks` approval step eliminated**.

**Safety**: The trust writer only ever generates entries for karma's own wrappers (verified via `is_karma_entry` — same predicate karma uses for uninstall idempotency). Non-karma hooks (vibe-island bridge, user's custom hooks) are never touched. If Codex changes its hash algorithm in a future version, karma's hashes will fall back to "modified" in `/hooks` instead of silent-trust drift.

`post_install_message()` text rewritten: was "⚠️ CRITICAL — manual /hooks approval required", now "Codex hook 状态 — karma 已写 trusted_hash, 复核可选". README codex alert box flipped from "must manually approve" to "auto-trust, takes effect immediately".

### Codex backend capability table after v0.10.2

| Capability | Claude Code | Codex (v0.10.2) | Status |
|---|---|---|---|
| SessionStart sticky baseline injection | ✅ | ✅ | **parity** |
| Pre/Post tool hooks | ✅ | ✅ | parity |
| Stop hook | ✅ | ✅ | parity |
| UserPromptSubmit per-turn | ✅ | ✅ | parity |
| Bash tool detection | ✅ | ✅ (via exec_command map) | **parity** |
| apply_patch / Edit detection | ✅ | ✅ (envelope parser) | parity |
| shell-as-Read detection | N/A (has Read tool) | ✅ (v0.10.1) | codex-specific advantage |
| Auto-trust hooks | N/A | ✅ (v0.10.2 trusted_hash writer) | codex-specific |
| PreCompact / SubagentStart/Stop | ✅ | ❌ (codex hook API doesn't expose these events) | not blocked at karma layer — Codex platform internally has `enable_request_compression` (stable=true, internal context compaction) and `enable_fanout` / `child_agents_md` (under development, sub-agent features), but Codex's 6 hook events (SessionStart/PreToolUse/PermissionRequest/PostToolUse/UserPromptSubmit/Stop) don't surface compaction or sub-agent dispatch as hookable lifecycle events. Will revisit when Codex exposes them. |
| PermissionRequest | N/A | not used | karma has no use case |

### karma maintainer-side counterpart (this commit)

Per ownership boundary (codex can't touch README / CHANGELOG / HANDOFF / ARCHITECTURE):

- README.md + README.zh.md codex install table + alert box rewritten from "manual approval required" to "auto-trust takes effect immediately"
- CHANGELOG + HANDOFF + ARCHITECTURE bilingual v0.10.2 entries
- Generic `karma/hooks/session_start.py` confirmed handles codex SessionStart payload without changes (compatible field names)

### Verification

- **575/575 passing** under both `LANG=zh_CN.UTF-8` and `LANG=en_US.UTF-8` (was 568 — +7 from PR #4 codex private tests)
- All 6 local gates pass (pytest zh + en / ruff / mypy / vulture --min-confidence 60 / wheel build+verify+smoke)
- CI green all 4 jobs (Ubuntu/macOS × Python 3.11/3.12)

### Meta-pattern — second consecutive successful codex PR

v0.10.0 ownership split is now proven over 2 consecutive PRs. Codex CLI's contribution velocity is fast (real-world session captures as evidence, comprehensive test coverage, even bonus features like auto-trust beyond the explicit ask). karma maintainer's role is now stable: review for boundary discipline + maintain GitHub-facing docs + sync general-layer code where backend changes need it. **Cross-platform AI Agent backend collaboration model validated**.

## [0.10.1] — 2026-05-16 (patch — codex shell-as-Read full integration + cross-backend contract tests)

**First codex-owned PR merged**: [#3](https://github.com/jhaizhou-ops/karma/pull/3) by Codex CLI itself (`feat(codex-backend): detect shell reads from exec_command`). v0.10.0's ownership split worked as intended — codex submitted PR only touching its owned files (`karma/backends/codex.py` + `tests/test_codex_backend.py`), karma maintainer reviewed + handled the karma-side counterpart (the generic `post_tool_use.py` layer consumes the canonical `read_file_paths` field). End-to-end shell-as-Read recognition now works: codex agent runs `tail -n 20 file.py` → karma records it as Read → subsequent `apply_patch` on same file no longer false-positive denied by `read_first`. **Closes the last v0.9.16-era codex usability gap**.

### Codex backend contribution (PR #3)

`CodexBackend.normalize_tool_input()` now recognizes conservative `exec_command` shell reads (real captured evidence from 2 session rollouts, codex 0.130 + GPT-5.5):
- `tail` / `head` / `cat` / `less` / `more` / `wc` / `file` — single-file
- `sed -n '...p' <file>` / `sed '...p;d' <file>` — print-only patterns
- `grep <pattern> <file>` / `grep -l <pattern> <file>` — non-recursive
- `awk '...' <file>` — default single-file
- Supports both `cmd` (Codex Desktop / rollout) and `command` (CLI/hook docs) input keys
- `sed -i` / `sed --in-place` → marked `is_write: true`, no `read_file_paths`

**Conservative skips** (high-false-positive shapes deliberately not recognized): pipe `|`, redirect `>` / `>>`, command chains `&&` / `;` / `(...)`, `find` / `xargs`, wildcards `*` / `?`, stdin `-`, recursive grep, `sed -f` / `grep -e` / `grep -f` / `awk -f` / `awk -v`.

15 codex-private tests in new `tests/test_codex_backend.py` cover all recognition + skip cases.

### karma-side wiring (this PR)

`karma/hooks/post_tool_use.py` consumes the canonical `tool_input["read_file_paths"]` list — for **any** backend (not codex-specific). Iterates each path and calls `state.record_read()` before the per-tool-name branches. Backend-neutral by design: any future backend (Cursor / Copilot / Cline / etc.) whose `normalize_tool_input` populates `read_file_paths` automatically benefits.

New integration test `test_post_tool_use_records_codex_shell_read_paths` locks the full chain: codex `exec_command` + `cmd: "tail -n 20 ..."` payload → backend normalize → post_tool_use generic handler → state.read_files actually populated.

### Cross-backend contract auto-validation (new `tests/contract/`)

Adds `tests/contract/test_backend_contract.py` running 14 abstract contract tests against every backend in `REGISTRY` via pytest parametrize. Any new Agent platform backend (Cursor / Copilot / Cline / etc.) registered to REGISTRY is automatically validated by these 14 tests × N backends — no per-backend boilerplate.

Coverage per backend:
- `pre_install_setup` / `post_install_message` return `list[str]`
- `normalize_tool_name` returns str + passthrough unknowns + idempotent on canonical names
- `normalize_tool_input` passthrough unknown tool_name
- `emit_deny` / `emit_allow` return valid JSON string
- `hook_events()` returns non-empty dict with snake_case basenames
- `settings_path()` under dotted config dir
- `build_event_entry()` returns dict with `hooks` key + list
- `is_karma_entry()` recognizes own generated entry + rejects foreign entry
- `name` / `display_name` non-empty
- `skill_install_targets()` returns list with valid format strings

42 new tests (14 × 3 backends). 554/554 passing both locales (was 512).

## [0.10.0] — 2026-05-16 (minor — backend architecture: protocol_adapter delegation layer + 6-method contract + codex ownership boundary handoff)

### Why this release

User triggered architecture rethink after v0.9.16 real-codex testing exposed two new bugs:
1. **Codex rejects `permissionDecision:"allow"` shape** — v0.9.15 had wrongly assumed Codex accepts Claude's hookSpecificOutput.allow shape. Real testing 2026-05-16 with codex 0.130 CLI produced `unsupported permissionDecision:allow` error. karma had this wrong for 1 release.
2. **Codex shell-as-Read gap** — codex has no separate `Read` tool; reads files via `exec_command` running `tail` / `sed` / `cat`. karma's `record_read` only matches `tool_name == "Read"` → all codex shell-reads invisible → `read_first` false-positive denials on edits.

User feedback: *"karma 的 hook 和判定的设计可能得针对不同的平台有针对性的开发和维护，你主要负责维护 karma 主程序和 claude 端，codex 端我让 codex 自行开发和测试"*. This is sound — codex protocol details belong to whoever has fastest signal on codex platform changes, which is Codex CLI itself.

### Major — architectural split

karma now treats backend ownership as **separate contributor surfaces**:

| Files | Owner |
|---|---|
| `karma/hooks/*.py` main logic + `karma/checks/*.py` engine checks + `karma/backends/_base.py` Protocol + `karma/backends/_json_hooks.py` base + `karma/backends/protocol_adapter.py` dispatch + `karma/backends/claude_code.py` + `karma/backends/gemini_cli.py` | karma maintainer |
| **`karma/backends/codex.py`** + **`tests/test_codex_backend.py`** (planned) | **Codex CLI itself** (PRs via Codex sessions) |
| `tests/test_protocol_adapter.py` cross-backend contract | karma maintainer |
| `README.md` / `CHANGELOG.md` / `HANDOFF.md` / `ARCHITECTURE.md` / `HOWTO.md` | karma maintainer |

New doc [`docs/CODEX_BACKEND.md`](docs/CODEX_BACKEND.md) (and `.zh.md`) defines the ownership boundary, 6-method contract, and known TODO agenda for Codex backend owner.

### Major — 6-method backend contract

`karma/backends/_base.py:Backend` Protocol formalizes the methods every backend must provide. `_json_hooks.py` provides Claude-Code-shape defaults; backends override only what differs:

| Method | Default (Claude) | Codex override | Gemini override |
|---|---|---|---|
| `pre_install_setup()` | `[]` | enable `features.hooks` | `[]` |
| `post_install_message()` | `[]` | loud `/hooks` approval reminder | `[]` |
| `normalize_tool_name()` | passthrough | `apply_patch → Edit` (via `_CODEX_TOOL_MAP`) | `run_shell_command → Bash` etc (via `_GEMINI_TOOL_MAP`) |
| `normalize_tool_input()` | passthrough | parse apply_patch envelope → `{file_path, new_string, multi_file_targets}` | passthrough |
| `emit_deny(reason)` | `{hookSpecificOutput: {permissionDecision: "deny"}}` | inherits Claude shape | `{decision: "deny", reason}` (Gemini official) |
| `emit_allow()` | `{hookSpecificOutput: {permissionDecision: "allow"}}` | **`{}`** (codex rejects allow shape per official docs) | `{}` |

### Bug A — codex.emit_allow returns `{}` (root cause for v0.9.15 wrong assumption)

Official [codex hooks docs](https://developers.openai.com/codex/hooks):

> "permissionDecision: 'ask', legacy 'decision: 'approve', 'updatedInput', 'continue: false', 'stopReason', and 'suppressOutput' are parsed but not supported yet, so they fail open."
> "To permit a tool call, either return an empty JSON object (`{}`) or exit with code `0` and no output."

Real testing 2026-05-16 codex 0.130 CLI emitted error `PreToolUse hook returned unsupported permissionDecision:allow`. v0.9.15 had wrongly claimed in CHANGELOG that "Codex accepts new hookSpecificOutput shape". v0.10.0 fixes this with `CodexBackend.emit_allow() → "{}"` + locked regression test `test_codex_emit_allow_returns_empty_dict_not_claude_shape` preventing future PRs from reverting.

### Internal — protocol_adapter.py becomes pure dispatch

Previously `karma/backends/protocol_adapter.py` contained `_GEMINI_TOOL_MAP`, `_CODEX_TOOL_MAP`, `parse_apply_patch_envelope`, `_extract_codex_patch_text`, `normalize_tool_input` — all backend-specific code in a "neutral" file. v0.10.0 moves each to the backend file that owns the protocol:

- Gemini tool name map → `karma/backends/gemini_cli.py:_GEMINI_TOOL_MAP`
- Codex tool name map + envelope parser → `karma/backends/codex.py:_CODEX_TOOL_MAP` + `parse_apply_patch_envelope()` + `_extract_codex_patch_text()`

`protocol_adapter.py` now only contains:
- `detect_backend(payload)` — routes to backend by `hook_event_name` for Gemini, by `sys.argv[0]` path (`/.codex/hooks/` literal) for codex, fallback claude-code
- `normalize_tool_name` / `normalize_tool_input` / `emit_deny` / `emit_allow` — each 1-line delegation to `REGISTRY[detect_backend(payload)].method(...)`
- `parse_apply_patch_envelope` re-export from `karma.backends.codex` for v0.9.16 test back-compat

`detect_backend` upgrade: returns canonical REGISTRY key (`claude-code` / `codex` / `gemini-cli`) instead of v0.9.15's short forms (`claude` / `gemini`). codex detection via `sys.argv[0]` containing `/.codex/` literal is necessary because codex hook payloads don't have a reliable backend signature in stdin fields, but the wrapper file path is always `~/.codex/hooks/karma_*.py`.

### Internal — checks/read_first.py backend-neutral

v0.9.16 introduced `_codex_patch_files` field as canonical-protocol-leak (read_first knew about codex envelope structure). v0.10.0 renames to `multi_file_targets` — generic name that any future envelope-protocol backend can reuse. read_first.check no longer contains the literal `apply_patch` string; uses caller's `tool_name` for trigger messages.

### Internal — codex post_install_message + doctor reminder (v0.9.17 work integrated)

Originally planned as v0.9.17 patch series, now integrated as backend-contract methods:
- `CodexBackend.post_install_message()` — loud TUI `/hooks` approval reminder printed at install time, lists all 4 wrapper paths for user to copy into TUI
- `karma doctor` — codex-specific section printing approval reminder when codex client + hooks.json detected. Doctor cannot programmatically verify approval state (codex doesn't expose it); honestly states this rather than fake-detecting.
- README.md + README.zh.md — alert box at codex install section (no longer buried in table row)

### Codex backend known TODOs (handoff to Codex)

Listed in `docs/CODEX_BACKEND.md`. Codex backend owner should pick these up:

1. **shell-as-Read recognition** — `exec_command` tail/sed/cat should count as Read for `record_read`. Most important for codex usability.
2. **Capture real hook-level payload** — currently inferred from session rollout, not directly captured. After `/hooks` approval, dump real hook stdin via `KARMA_DEBUG_DUMP_PAYLOAD`.
3. Other codex tool names not yet mapped (`exec_command → Bash`, etc).
4. Approval state programmatic detection (if codex exposes it).

### Verification

- **512/512 passing** under both `LANG=zh_CN.UTF-8` and `LANG=en_US.UTF-8` (was 510) — 2 new lockdown tests
- All 6 local gates pass (pytest zh + en / ruff / mypy / vulture / wheel build+verify+smoke)
- Wheel smoke test: clean venv install + REGISTRY has 3 backends + detect_backend routes correctly + codex.emit_allow returns `"{}"` + all 6 contract methods callable

### Migration notes for downstream

- `protocol_adapter.parse_apply_patch_envelope` still importable (re-exported from codex.py) — no breaking change
- v0.9.16 `_codex_patch_files` field renamed to `multi_file_targets` — internal field never documented, but if any downstream consumer reads session-state JSON they need to rename
- `detect_backend()` returns `claude-code` / `codex` / `gemini-cli` instead of `claude` / `gemini` — internal API, but a few tests reference these strings

Full details: [docs/CODEX_BACKEND.md](docs/CODEX_BACKEND.md)

## [0.9.16] — 2026-05-16 (fix — codex apply_patch envelope parser via real captured payload; config DEFAULTS silent-drop; PreCompact/SubagentStop test asserts tightened)

### Why this release

Follow-up to v0.9.15 cross-backend phase 1. v0.9.15 normalized `tool_name` only and explicitly deferred `tool_input` normalization to phase 2 — the real codex `apply_patch` envelope shape wasn't yet captured. v0.9.16 closes phase 2 with **evidence-backed implementation**: parser locked against a real `custom_tool_call.input` literal captured from a fresh codex 0.130.0 + GPT-5.5 session rollout (2026-05-16 13:51:47 CST).

### Codex apply_patch envelope true parser (Major #2 — phase 2 of cross-backend)

**Real captured envelope** (codex 0.130.0 + GPT-5.5, session rollout `/Users/jhz/.codex/sessions/2026/05/16/rollout-2026-05-16T13-51-47-019e2f57-3d6b-76a3-9bc6-642d23262631.jsonl`):

```
*** Begin Patch
*** Update File: /tmp/karma-codex-toy.py
@@
+# v0.9.16 test
*** End Patch
```

Codex `custom_tool_call.input` passes the **entire envelope as a single string** (not a structured dict). Multi-file patches concatenate multiple `*** Update File:` / `*** Add File:` / `*** Delete File:` blocks within one envelope.

**Two new functions in `karma/backends/protocol_adapter.py`**:

```python
def parse_apply_patch_envelope(envelope: str) -> list[dict[str, str]]:
    """Returns [{"op": "Update"|"Add"|"Delete", "path": str}, ...]"""

def normalize_tool_input(raw_tool_name: str, raw_tool_input: Any, payload: dict) -> Any:
    """For codex apply_patch: synth canonical Edit dict {file_path, new_string,
    _codex_patch_files}. Other tool calls: passthrough unchanged."""
```

**Wired into both hooks**:
- `pre_tool_use.py`: `tool_input = normalize_tool_input(...)` at entry. Multi-file patches expose `_codex_patch_files` list to downstream checks.
- `post_tool_use.py`: When `tool_name == "Edit"` and `_codex_patch_files` is present, iterate each Update/Add path → `record_edit` + `record_read` per file (Delete skipped). `last_edit_ts` truly advances for codex multi-file commits — fixes the v0.9.15-era gap where evidence/commit gate was silently waved through on Codex.
- `karma/checks/read_first.py`: Iterates `_codex_patch_files` when present — any Update path not yet Read triggers denial. Add paths exempted (new files, no prior Read required), Delete paths skipped. **Catches multi-file patches where only the primary file was Read.**

### Defensive input shape handling

`_extract_codex_patch_text()` handles both the bare-string form (verified from rollout) and possible dict-wrapped forms (`{"input": ...}`, `{"command": ...}`, etc.) — because the **hook-level** payload shape couldn't be directly captured: `codex exec` non-interactive mode does not fire user hooks even with `--enable hooks` (verified via `KARMA_DEBUG_DUMP_PAYLOAD` instrumentation + `codex features list`). Interactive codex (production path) is expected to fire hooks normally; defensive wrap-detection means karma works regardless of which exact shape the codex hook passes.

### Config DEFAULTS silent-drop bug (Minor #4)

`karma/config.py:load()` iterates `for key in DEFAULTS` to merge user config — so any user-settable knob **not** in `DEFAULTS` is silently dropped from `~/.claude/karma/config.yaml`. `reinject_every_n_tokens` was a documented user-tunable in `post_tool_use._build_smart_reinject` but missing from `DEFAULTS` → users writing `reinject_every_n_tokens: 4000` in their config were silently falling back to the model-adaptive default.

**Fix**: Added `"reinject_every_n_tokens": None` to `DEFAULTS` (None preserves the "auto by model" semantics) + documented sample in `data/config.example.yaml` + new test `tests/test_config.py:test_reinject_every_n_tokens_in_defaults_and_user_override` locks the round-trip.

### Compact/SubagentStop hook test asserts tightened (Minor #5)

`tests/test_compact_hooks.py` had three sites with `if "hookSpecificOutput" in output:` conditional branches that silently passed if the hook regressed to emitting the (Claude-Code-unsupported) `hookSpecificOutput` shape on PreCompact/SubagentStop. Per 2026-05-15 official-docs verification, those events only support `decision`/`reason` mode — karma emits bare `{}` now. Tests now strict-assert `output == {}` so future regressions fail loud instead of green-silently.

### Test coverage delta

**+12 tests** in `tests/test_protocol_adapter.py` (22 total in file, was 11):
- `test_parse_apply_patch_real_codex_envelope_single_file` — locks the real captured envelope literal
- `test_parse_apply_patch_multi_file_with_add_and_delete` — covers all 3 ops (Update / Add / Delete)
- `test_parse_apply_patch_empty_input_returns_empty_list` — empty / malformed safe
- `test_normalize_tool_input_codex_apply_patch_synthesizes_edit_shape` — file_path + new_string + _codex_patch_files all populated
- `test_normalize_tool_input_codex_apply_patch_dict_form_input_field` — dict-wrap fallback works
- `test_normalize_tool_input_non_apply_patch_passthrough` — Claude/Gemini paths preserved
- `test_normalize_tool_input_multi_file_primary_is_first_update` — primary file selection rule
- `test_normalize_tool_input_malformed_envelope_passthrough` — garbage input safe
- `test_read_first_multi_file_blocks_when_any_update_unread` — integration: multi-file read_first denial works
- `test_read_first_multi_file_allows_when_all_updates_read` — integration: passes when fully Read
- `test_post_tool_use_records_all_update_paths_in_multi_file_patch` — integration: record_edit + last_edit_ts truly advance for all paths

Plus the config DEFAULTS test + tightened compact_hooks asserts.

**Total**: 510/510 passing both `LANG=zh_CN.UTF-8` and `LANG=en_US.UTF-8` (was 498).

### Verification

- **510/510** passing both locales (was 498) — 12 new tests
- All 6 local gates pass (pytest zh + en / ruff / mypy / vulture / wheel build+verify+smoke)
- Wheel smoke test: clean venv `pip install karma-0.9.16-py3-none-any.whl` → parser correctly extracts file paths from real codex envelope, `normalize_tool_name("apply_patch", ...)` returns `"Edit"`, all `data/signals/` files shipped (force-include from v0.9.15 carried forward)

Full details: [CHANGELOG.md](https://github.com/jhaizhou-ops/karma/blob/v0.9.16/CHANGELOG.md)

## [0.9.15] — 2026-05-16 (fix — cross-model audit (GPT-5.5) catches 3 critical cross-backend protocol bugs; karma had Claude-only assumptions hiding for entire repo lifetime)

### Why this release

User: "再来一轮 cross-audit，本机配置了 codex cli，也配置好了 gpt 5.5 模型，你委派 codex cli 做一次多 Agent 交叉评审。"

Ran `codex exec` with GPT-5.5 xhigh reasoning against karma. **Cross-model viewpoint exposed 3 critical bugs Claude-side audits missed every previous round**:

1. **Gemini BeforeTool output shape mismatch** — karma always emitted Claude's `{hookSpecificOutput: {permissionDecision: "deny"}}` shape, but [Gemini hooks docs](https://geminicli.com/docs/hooks/reference/) require top-level `{decision: "deny" | "block", reason: ...}`. Verified via WebFetch. **Impact**: Gemini users had karma writing violations + stderr warnings but **the dangerous tool actually executed** — all intercept-type rules (non_blocking / bypass_karma / read_first) were write-only, no real blocking.

2. **Gemini tool_name not normalized** — karma checks compare against Claude-style names (`Bash`/`Read`/`Edit`/`Write`/`NotebookEdit`). Gemini uses `run_shell_command` / `read_file` / `write_file` / `replace`. **Impact**: Every check early-returns `None` on Gemini → **zero checks fire** for Gemini users.

3. **Codex `apply_patch` tool_name not handled** — [Codex hooks docs](https://developers.openai.com/codex/hooks) explicitly state hook input reports `tool_name: "apply_patch"` for edits, not `Edit`/`Write`. karma 0 places handle it. **Impact**: Codex users using `apply_patch` (the primary edit path) bypass `read_first` / `long_term_fundamental` / `testset` / `evidence` checks entirely. `last_edit_ts` doesn't advance → stale "recent test pass" state preserved → git commit `evidence.commit` check waved through.

User caught me misjudging once during this session: "你没有探查就下结论这很不好。结合实际环境支持和官方文档开始排查、修复和测试吧。" Was about to ask user to pick between fix options before verifying. Rule #6 read-before-write applies to docs too — pulled actual `~/.codex/hooks.json` + `~/.gemini/settings.json` + WebFetched both backends' official hook protocol docs. This also caught a codex-audit misjudgment (codex thought Codex needed legacy `{decision, reason}` shape; the docs actually say Codex accepts the new `hookSpecificOutput` shape too — karma's current Codex output is OK; only `apply_patch` tool_name handling is missing).

### Fix — `karma/backends/protocol_adapter.py` (new module)

Centralizes cross-backend protocol differences in one place:

```python
def detect_backend(payload: dict) -> Backend:
    # Gemini sends hook_event_name in {BeforeAgent, BeforeTool, AfterTool, AfterAgent}
    # Claude/Codex use PreToolUse/PostToolUse/UserPromptSubmit/Stop
    event = payload.get("hook_event_name", "")
    return "gemini" if event in _GEMINI_EVENT_NAMES else "claude"

def normalize_tool_name(raw: str, payload: dict) -> str:
    backend = detect_backend(payload)
    if backend == "gemini":
        return _GEMINI_TOOL_MAP.get(raw, raw)
    return _CODEX_TOOL_MAP.get(raw, raw)  # claude/codex share canonical mostly

def emit_deny(reason: str, payload: dict) -> str:
    if detect_backend(payload) == "gemini":
        return json.dumps({"decision": "deny", "reason": reason}, ensure_ascii=False)
    return json.dumps({"hookSpecificOutput": {...permissionDecision: "deny"...}})

def emit_allow(payload: dict) -> str: ...  # Gemini → {}, Claude/Codex → permissionDecision: allow
```

Mapping tables:
```
Gemini → Claude canonical:
  run_shell_command → Bash
  read_file / read_many_files → Read
  write_file → Write
  replace / edit / edit_file → Edit

Codex → Claude canonical:
  apply_patch → Edit  # so long_term/testset/bypass_karma scan tool_input.command
```

### Hook entry migration

`pre_tool_use.py` and `post_tool_use.py`:
- `_allow()` / `_deny()` now take `payload` and route through `emit_allow/emit_deny`
- `tool_name = normalize_tool_name(raw, payload)` at entry — all downstream checks see canonical name

`apply_patch` Phase-2 limitation: edits via `apply_patch` carry diff in `tool_input.command`, not single `file_path`. `long_term`/`testset`/`bypass_karma` scan the command text correctly. But `read_first` (needs `file_path` to compare against `state.read_files`) and `record_edit` (single path) currently no-op on `apply_patch` because there's no `file_path`. Multi-file diff parsing is **Phase 2** (would let `read_first` enforce "read every file in the patch first" and `record_edit` advance `last_edit_ts` per touched file). Documented in adapter module docstring.

### Critical wheel-packaging fix (caught by second codex full-repo review)

After Phase 1 merged into v0.9.15, user requested another codex GPT-5.5 review — this time **entire karma project, not just the diff**. GPT-5.5 caught a **catastrophic packaging bug separate from the cross-backend protocol issue**:

`pyproject.toml` `force-include` listed individual yaml templates + skills + locales — but **never included `data/signals/`**. `karma/signals.py:40` hardcodes `_REPO_ROOT / "data" / "signals"` for loading. Source-tree tests pass (signals directory exists locally), but **wheel installations lose the entire `data/signals/` tree**. `compile_alternation()` returns never-match regex `(?!)` → **all keyword-fallback layers fail silently** for every pip-installed user: `evidence` / `keep_pushing` / `non_blocking` checks lose their detection vocabulary entirely.

This affects **every pip-installed karma user including the Claude Code mainstream path** — more severe than the cross-backend bug (which only affected Gemini/Codex users). My own 6-gate local checklist included a wheel verify step but **only locked 6 expected files**; the `data/signals/` subtree was never in the lockdown list (extension of rule #5 lesson: locked lists only cover what was thought-of at lockdown time, new data subtrees slip through).

**Fix**:
- `pyproject.toml` force-include adds `"data/signals" = "data/signals"` (whole directory, not glob — protects future signal types from being missed)
- `.github/workflows/ci.yml` wheel-verify expanded: file list now includes 7 sample signal files (1 per type) + new **smoke test step** that builds wheel, pip installs into clean venv, and asserts `compile_alternation()` returns non-empty regex for `weak_claims`/`completion_words`/`push_signals`/`stop_hints`. Functional verification, not just file presence.

**Real-data validation** (post-fix clean venv): `weak_claims` 497 chars / `completion_words` 299 chars / `push_signals` 16653 chars / `stop_hints` 760 chars — all functional after pip install.

### Test coverage

`tests/test_protocol_adapter.py` — 11 new tests:
- `detect_backend` Gemini vs Claude by event name
- `normalize_tool_name` Gemini → canonical (4 mappings) + Codex `apply_patch → Edit` + Claude passthrough
- `emit_deny` Gemini top-level shape vs Claude `hookSpecificOutput`
- `emit_allow` Gemini `{}` vs Claude `permissionDecision: allow`
- **Integration lockdown**: `test_pre_tool_use_under_gemini_payload_emits_gemini_shape` — runs full `pre_tool_use.main()` with Gemini-style payload (`hook_event_name: BeforeTool` + `tool_name: run_shell_command` + Bash command containing a violation keyword), asserts output is top-level `{decision: deny, reason}` not Claude shape. **This is the core regression lockdown** — future PRs that touch `_allow`/`_deny` without going through adapter break this test.

### Verification

- **497/497 passing** under both `LANG=zh_CN.UTF-8` and `LANG=en_US.UTF-8` (was 487)
- All 6 local gates pass
- WebFetch direct quote verification: Gemini hooks ref + Codex hooks docs both consulted before writing adapter

### Meta-pattern

**Cross-model audit value is real** when the in-house model has systematic blind spots. Claude wrote karma; Claude reviewed karma 12+ times this session; Claude's blind spot was: **assume the protocol that Claude itself uses is universal**. GPT-5.5 — running on Codex CLI, having different training exposure to Gemini hooks docs — pulled official refs and flagged exactly this assumption. Single-model rounds (v0.9.13 / v0.9.14) had diminishing returns; cross-model rounds opened a whole new audit surface.

The bug had been latent for the entire history of karma's "3-backend support" claim — every dogfooding case was Claude Code, so the cross-backend protocol never got tested. README literally claims "Claude Code / Codex CLI / Gemini CLI" support but Gemini support was non-functional. Honest correction shipped.

## [0.9.14] — 2026-05-16 (fix — multi-agent cross-audit catches v0.9.13's own regression: `pre_tool_use` `update_state` not wrapped in try/except)

### Why this release (loud failure callout)

User: "每次多 Agent 交叉互审就能挖出很深的 bug 也是很有趣的一件事。再来一轮。"

Launched 3 parallel audit agents with **different viewpoints** (to avoid v0.9.13's audit surface):
1. 8 engine-check logic correctness (FP / FN / logic / preference-alignment)
2. config defaults drift across imports
3. fail-open / fail-closed error-handling contract consistency

Per rule #4, each finding was hand-verified — most of viewpoint 1's findings turned out to be design choices misjudged by sub-agent (e.g. chinese_plain table-jargon counting **is intentional** per v0.4.22 comment; `_LONG_TASK_RE` skipping `npm run` **is intentional** since user-defined scripts have unpredictable runtime). Viewpoint 2 returned clean — all config field fallbacks consistent with `DEFAULTS`.

**Viewpoint 3 caught the real one**: v0.9.13's own regression. When I migrated `pre_tool_use.py:98-100` from `load + catchup_pending_bg + no save` to `update_state(sid, lambda s: s.catchup_pending_bg(), agent_id=...)` to fix the C1 instrumentation bug, I **forgot to wrap it in try/except**. The original `load + catchup` was implicitly fail-safe (load catches OSError, catchup_pending_bg internally catches OSError per-task), but `update_state` introduces a new failure path: `fcntl.flock` acquire failures (extremely rare but possible — file system errors, broken NFS mount, etc), `save()` OSError when writing back. If any of those raises, the exception bubbles, `pre_tool_use.main()` returns non-zero, and Claude Code sees the hook fail — **user is blocked from making the tool call**.

This is **fail-closed**, the exact opposite of karma's design principle (all hooks must fail-open: karma's own internal failure must never block the user).

### Fix 1 (critical) — `pre_tool_use.py:104-108` wrapped in try/except with fallback

```python
try:
    state, _ = session_state.update_state(
        session_id, lambda s: s.catchup_pending_bg(), agent_id=agent_id,
    )
except Exception as e:
    print(f"karma PreToolUse: update_state 失败 fallback 裸 load ({e})", file=sys.stderr)
    state = session_state.load(session_id, agent_id=agent_id)
```

Fallback: degrade to bare `load()` (no catchup persistence for this turn — same behavior as pre-v0.9.13 — but at least PreToolUse can still make decisions on stale state instead of crashing the entire hook).

### Fix 2 (minor) — `_LONG_TASK_RE` adds `pip install` pattern

Sub-agent's viewpoint 1 caught this as a real FN: `pip install` always takes ≥30s (dependency resolution + downloads), but it wasn't in the long-task regex. Added `pip\s+install` to the alternation. `npm run` / `yarn build` (user-defined scripts) remain excluded by design — runtime is unpredictable.

### Regression tests

2 new tests:
- `test_pre_tool_use_update_state_exception_falls_back_to_load` (in `tests/test_hooks.py`) — mocks `session_state.update_state` to raise, verifies hook still returns 0 + outputs `_allow` (fail-open contract lockdown). If a future PR introduces another fail-closed path in PreToolUse, this test catches it.
- `test_non_blocking_pip_install_detected_v0914` (in `tests/test_checks.py`) — verifies `pip install pandas` / `pip install -e .` both trigger; `pip install + run_in_background=True` is exempt.

### Verification

- 487/487 passing under both `LANG=zh_CN.UTF-8` and `LANG=en_US.UTF-8` (was 485)
- All 6 local gates pass
- Static-scan regression `test_all_hook_violation_writes_pass_trigger_key` (v0.9.12) still green, indicating the fail-open fix doesn't introduce new field-omission bugs

### Audit signal-to-noise comparison

| Audit | Findings reported | True bugs | Notes |
|---|---|---|---|
| v0.9.13 (single agent, 4 categories) | 5 | 4 | high SNR — accumulated drift from years |
| v0.9.14 (3 parallel agents, viewpoint diversity) | ~9 | 2 (1 critical + 1 minor) | lower SNR — repo already clean post-v0.9.13 |

**Diminishing returns confirmed**: v0.9.13 cleared the high-density instrumentation drift; the marginal value of further audits is mostly catching **regressions introduced by the previous round** (which is exactly what viewpoint 3 caught). This is still meaningful — multi-agent audit specifically catches *the auditor's own blind spots* — but expecting another v0.9.13-class haul would be misjudgment.

### Meta-pattern

[rule #4 loud-failure-with-evidence] applies in three directions now:
1. **Forward**: claim a result, attach evidence (data / test pass)
2. **Backward**: claim a result, verify it isn't instrument artifact (v0.9.12 lesson)
3. **Self-verify post-fix**: claim a fix, verify the fix itself didn't introduce a regression (v0.9.14 lesson — multi-agent cross-audit is one way to catch your own regressions)

## [0.9.13] — 2026-05-16 (fix — comprehensive instrumentation audit catches 4 correctness bugs: agent_id round-trip / turn-window off-by-one / pre_tool_use catchup-no-save / zh weak_claims coverage gap)

### Why this release

After v0.9.12 (the v0.9.11 instrumentation bug + meta-lesson "rule #4 applies in both directions — verify the result isn't instrument artifact"), user asked: "全面排查下，还有没有这种 bug，直接影响 karma 运行准确性和统计准确性的". Launched a comprehensive audit using v0.9.12's bug pattern as template — Type A (field-missing), Type B (aggregation off-by-one), Type C (race / load-modify-no-save), Type D (i18n inconsistency).

Sub-agent reported 5 findings. Per rule #4 (don't trust agent reports, verify with read), each was hand-verified:

| Finding | Sub-agent verdict | After my verify | Real impact |
|---|---|---|---|
| A1: `load_all()` drops `agent_id` | real bug | ✓ confirmed | audit/stats can't truly group main vs sub Agent |
| A2: `save()` payload missing `agent_id` | real bug | ✗ misjudgment — encoded in filename `<sid>__<aid>.json` | design choice, not bug |
| B1: turn window cutoff off-by-one | real bug | ⚠️ confirmed + worse than sub-agent thought | **`stop.py:162 force_block` false-positive risk** — Agent gets force-blocked on already-fixed old violations |
| C1: `pre_tool_use.py` catchup-no-save | real bug | ✓ I had previously misjudged this as design — sub-agent caught my error | pending_bg_tasks unprocessed, duplicate catchup runs |
| D1: zh weak_claims coverage gap | real bug | ✓ confirmed — zh 8 vs en 23 entries | Chinese users have ~35% evidence-check recall for hedge phrases |

### Fix 1 — `load_all()` reads `agent_id` field

`karma/violations.py:370` — `Violation()` construction during jsonl read now includes `agent_id=d.get("agent_id")`. Symmetric with `to_json()` write path (line 59-60). Audit/stats views correctly distinguish main Agent violations from sub Agent violations.

### Fix 2 — Turn window cutoff: `cur - (window - 1)` instead of `cur - window`

`karma/violations.py:309 recent_turns` + `karma/violations.py:343 count_recent_turns` + `karma/cli.py:836 cmd_audit` drift-view — all three cutoff calculations consistently fixed.

**Real impact**: `stop.py:162 force_block` was the worst affected. With `force_window=3, force_threshold=5`, old `cutoff=cur-3` matched `[cur-3, cur]` = 4 turns. So a user who already fixed the root cause 3 turns ago could still be force-blocked on the 4th-turn-old violation counting toward the threshold. The user's config.yaml comment literally reads "最近 N turn 内同一规则违反 ≥ M 次" — N is meant to be N turns, not N+1.

After fix: `cur - (window - 1)` makes `window=N` truly match N turns. Sub-agent reported this as "medium severity statistical drift" — but real semantic is "incorrect force_block trigger condition" affecting karma's intervention behavior accuracy.

Existing tests `test_recent_turns_filters_by_session_and_turn_window` / `test_count_recent_turns_by_session` use the boundary turn semantically (r2 at turn=5 in / r1 at turn=2 out) — their asserts still pass under new cutoff because both windows still bracket the named turns correctly. Test docstring comments updated to reflect new semantics. Plus new lockdown `test_recent_turns_window_lockdown_v0913` explicitly asserts `window=3, current=10 → matches [8,9,10]` (3 turns, not 4) and `window=1 → matches only current turn`.

One existing test `test_stop_hook_force_blocks_on_accumulated_violations` had a fixture (5 violations turn 1-5) that razor-edge satisfied threshold=5 only because old `cur-3=2` cutoff matched 4 historical + 1 new keyword-detected violation. After fix, only 3 historical fall in window → fixture had to be strengthened to 6 violations all within `[3,5]` so the test still verifies its real intent (accumulation crosses threshold triggers force_block), not the cutoff boundary specifically. This is **fixture adjustment to reflect fix's correctness**, not "tweak test to make it pass" — clear comment in the test explains the reasoning.

### Fix 3 — `pre_tool_use.py` catchup migrated to `update_state`

`karma/hooks/pre_tool_use.py:98-100` previously did `state = session_state.load(...); state.catchup_pending_bg()` with **no save**. This was inconsistent with v0.9.8's `update_state` architecture — every other hook write path uses `update_state` for atomic load-modify-save. Sub-agent's report caught my earlier misjudgment (I read this code in v0.9.8 and classified it as design choice "PreToolUse is decision-side, not state-side"). But `catchup_pending_bg()` mutates `pending_bg_tasks` and `recent_bash` — leaving those mutations un-persisted means the next hook does redundant catchup on the same tasks. Fixed by routing through `session_state.update_state(session_id, lambda s: s.catchup_pending_bg(), agent_id=agent_id)` matching post_tool_use.py.

### Fix 4 — zh weak_claims signal coverage parity with en

`data/signals/weak_claims/zh.txt` expanded from 8 entries to 25 hedge phrases covering Chinese semantic equivalents of all en patterns: "应该" family / "大概 / 概率" / "可能 / 也许" / "推测 / 我猜 / 估计" / "看起来 / 似乎 / 好像". Chinese-speaking users' `evidence` check recall for weak-claim hedging is now on par with English speakers' (was ~35%, now ~estimated 90%+).

### Regression tests

3 new tests in `tests/test_violations.py`:
- `test_load_all_reads_agent_id_field` — round-trip lockdown for agent_id
- `test_recent_turns_window_lockdown_v0913` — explicit cutoff boundary lockdown (`window=N → N turns, not N+1`)
- `test_weak_claims_zh_en_coverage_parity` — lockdown ensures zh/en entry count difference stays under 30% (future PRs can't let one language fall behind without CI catching it)

### Verification

- 485/485 passing under both `LANG=zh_CN.UTF-8` and `LANG=en_US.UTF-8` (was 482)
- All 6 local gates pass
- 1 existing test fixture adjustment (`test_stop_hook_force_blocks_on_accumulated_violations`) with honest comment explaining why

### Meta-pattern

Three of the four bugs (A1, B1, D1) match v0.9.12's pattern: "instrumentation drift between intent and implementation, accumulated through years without anyone re-validating." The verify cycle that exposed v0.9.12's bug — user follow-up question prompting raw-data inspection — found 3 more peer bugs hiding in the same audit surface. This release confirms the meta-pattern is reliable: **a single high-quality follow-up question to a confident interpretation can surface a cluster of related bugs, not just one.**

## [0.9.12] — 2026-05-16 (fix — v0.9.11 audit `--by-check` data classification bug: `_build_strong_reminder` hook fallback was dropping `trigger_key` on Violation write)

### Why this release (loud failure callout)

v0.9.11 shipped `karma audit --by-check`. First-run dogfood on author's machine produced a striking result: **"86% of violations are keyword-only fallback hits, only 14% from engine checks."** I read this as a real signal and gave the user the interpretation: "most rules don't have `violation_checks` attached, engine layer needs more investment."

**The interpretation was wrong.** User asked the right follow-up: "are these 1-trigger checks like `bypass_karma` / `evidence.completion` / `testset` redundant rule design, or are they missing real signals they should catch?" Investigating that question forced reading the raw violations.jsonl — and found two records with identical `trigger` text (the i18n-translated output of `check.keep_pushing.default.trigger`), one with `trigger_key` field present, one without. **Pure field-presence difference; the underlying signal was the same.**

Root cause: `karma/hooks/user_prompt_submit.py:_build_strong_reminder` (a v0.4.41 fallback path that writes violations when the user immediately submits a new prompt before Stop hook can run) constructs `Violation` objects but **didn't pass `trigger_key`** — while `pre_tool_use.py` and `stop.py` both did. So every engine check fired via this fallback path got recorded with empty `trigger_key`, and v0.9.11's `--by-check` view bucketed them as "keyword-only."

### Fix

`user_prompt_submit.py:_build_strong_reminder` now passes `trigger_key=h.trigger_key` matching the other two hook paths.

### Regression lockdown — `test_all_hook_violation_writes_pass_trigger_key`

Static scan over `karma/hooks/*.py`: for every `Violation(...)` or `_V(...)` construction site that has `rule_id=...`, require `trigger_key=...` in the same call. If a future PR adds another hook path that writes violations and forgets `trigger_key`, CI fails immediately. The invariant is now in the test suite, not just code review memory.

### Honesty caveat on historical data

**Did NOT backfill historical jsonl** (per rule #5 [no-testset-no-future-leakage]). Old violations written before v0.9.12 keep their missing-`trigger_key` state. Rewriting them now — even though we could deterministically map `trigger` text back to `trigger_key` via the locale yaml — would be retroactively manipulating recorded data to make a dashboard look better. That's the kind of "fix the past to validate the present" pattern this project explicitly rejects.

Instead: `cmd_audit --by-check` view footer now prints a disclaimer:

```
注: v0.9.12 前历史 jsonl 可能漏 trigger_key 字段（hook 路径 bug），
导致 engine check 真触发被错归 keyword-only。本视图未回填老数据
（评测干净度），只对 v0.9.12+ 写入的 violation 分类准确。
```

User reading the view sees the data as-is plus the honest caveat. Real engine-vs-keyword distribution will emerge naturally as new v0.9.12+ violations accumulate.

### Reanalysis of v0.9.11 dogfood data (with caveat applied)

Author's 187-violation dataset, partially affected by the bug:
- Originally reported `keep_pushing` engine: 20×. After accounting for the bug: the `keep_pushing.default` trigger appears 79 additional times in the keyword-only bucket — those are the same check truly firing. **True `keep_pushing` engine hits estimated ~99.**
- Originally reported `bypass_karma` engine: 1×. The keyword-only bucket has 6 hits with trigger text "绕开检测 — 手动写 karma 内部状态" (the `bypass_karma` check's i18n trigger). **True `bypass_karma` engine hits estimated ~7.**
- `evidence.completion`: 1× → estimated ~10× (9 keyword-only with the same completion trigger)
- `testset.*`: 1× → estimated ~5× (4 keyword-only with `testset` triggers)

User's question "are the 1-trigger checks redundant?" — answer: **none of them are redundant**, they're all firing more than the surface data showed. Whether any are over-broad (false-positive risk) needs clean v0.9.12+ data to judge.

### Verification

- 482/482 passing under both `LANG=zh_CN.UTF-8` and `LANG=en_US.UTF-8` (was 481)
- All 6 local gates pass
- New regression test catches the original bug pattern by static scanning hook source files

### Meta-lesson

v0.9.11's "86% keyword-only" was a **dashboard pulling double duty as data**: I read the number as user-behavior signal and gave a confident interpretation, but the number was actually instrumentation telling me about a data-pipeline bug. Rule #4 [loud-failure-with-evidence] applies in both directions — claim a result, then verify the result wasn't just instrument artifact. User asking "are the 1-trigger ones redundant?" was the prompt that exposed the artifact.

## [0.9.11] — 2026-05-16 (feat — observability: `karma audit --by-check` engine-check hit distribution + `/karma` no-arg defaults to this view)

### Why this release

After v0.9.10 onboarding polish, asked user which direction to push next: check-firing-distribution observability or weekly trend visualization. User's design insight:

> "Adding new skills creates extra cognitive load for users — I want to compress that. For the first direction (check-firing observability), wouldn't it be better as the **default output of `/karma` when no description is given**? Just typing `/karma` shows the check-firing distribution."

This avoids inventing a new entry point (new CLI subcommand or new slash command). `/karma` is something the user already knows (v0.9.10 footer just introduced it). No-arg `/karma` getting a useful default reuses existing muscle memory — zero learning curve.

### Implementation

**1. CLI backend — `karma audit --by-check`** (`karma/cli.py`):

New `_cmd_audit_by_check()` aggregates violations by `trigger_key` field (the i18n locale key, format `check.<name>[.<sub>].trigger`):

- **Top-level aggregation** (8 engine checks): one row per check function (`bypass_karma`, `chinese_plain`, `evidence`, `keep_pushing`, ...) with count and ratio of total engine hits
- **Sub-variant breakdown** (when applicable): finer rows like `chinese_plain.ratio` vs `chinese_plain.jargon`, `evidence.commit` vs `evidence.completion`, etc — helps the author see which sub-check is high-firing vs high-false-positive
- **Keyword-only bucket**: violations with empty `trigger_key` (caught by keyword fallback layer, no engine check)

No schema change required — reuses the existing `Violation.trigger_key` field added in v0.5.7 for locale-agnostic grouping. Historical jsonl rows without `trigger_key` (keyword-only hits) fall into the dedicated bucket.

Real dogfood data from author's machine (187 violations, repo current state):

```
karma engine check 命中分布 (总 187 条违反):

按 check 函数聚合 (26 条 engine 命中):
    20× ( 77%) keep_pushing
     3× ( 12%) non_blocking
     1× (  4%) testset
     1× (  4%) bypass_karma
     1× (  4%) evidence

按 sub-variant 细分 (26 条 engine 命中):
    18× ( 69%) keep_pushing.default
     3× ( 12%) non_blocking.sleep
     2× (  8%) keep_pushing.stop_hint
     1× (  4%) testset.hash_branch
     1× (  4%) bypass_karma
     1× (  4%) evidence.completion

keyword-only 兜底命中 (无 engine check): 161× (86%)
```

**2. Skill — `/karma` no-arg default** (`skills/karma/SKILL.md`):

Added "No-argument flow" section to the `karma` skill: when the user types `/karma` with empty `$ARGUMENTS`, the Agent runs `karma audit --by-check` and relays the output to the user with a brief interpretation (high-firing checks → which direction violates most; high keyword-only ratio → most violations caught by fallback layer; high-FP suspicion → sub-variants where literal patterns may overfire). Then asks: "Want to tune any check, drop a rule, or add a new one based on this data?"

This closes the dogfood feedback loop: violations.jsonl → audit → user sees pattern → decides to tune. No new entry point invented; `/karma` no-arg is the natural "show me what's happening" gesture.

**3. Backward compatibility**:

`karma audit` (without `--by-check`) keeps its existing behavior (per-rule aggregation with false-positive suspicion / fix timeline / current-session drift sections). The `--by-check` flag is purely additive.

### Test coverage

2 new tests in `tests/test_cli.py`:
- `test_audit_by_check_aggregates_engine_hits` — synthesizes 6 violations (3 `bypass_karma` engine + 2 `keep_pushing` sub-variants + 1 keyword-only), verifies top-level + sub-variant + keyword-only sections all appear
- `test_audit_default_view_backward_compat` — `cmd_audit()` without `by_check=True` produces the old per-rule view, doesn't leak `--by-check`-only literal strings

### Verification

- 481/481 passing under both `LANG=zh_CN.UTF-8` and `LANG=en_US.UTF-8` (was 479)
- All 6 local gates pass
- Real dogfood validation: `karma audit --by-check` on author's machine produced the meaningful 187-violation distribution shown above on first run

## [0.9.10] — 2026-05-16 (feat — onboarding polish: rule summary shows first paragraph (not half-line) + footer with token-cost reassurance and `/karma` in-chat entry)

### Why this release

v0.9.9 shipped the onboarding summary block. User acceptance review surfaced two refinements:

1. **First-line truncation produced half-sentences** — `preference.strip().split("\n")[0]` cut at YAML visual wrap, e.g. `long-term-fundamental` showed "The user trusts you to dig into root causes. When facing hard problems" with the rest ("they want you to pause and think...") dropped. User picked option (b): show the **first paragraph** (split by blank line) so each rule's summary is a complete meaning unit.

2. **No reassurance on cost / no clear next step for adding rules** — User wanted a footer to address both: "Tested: rule injection accounts for under 3% of per-session token spend; to add or modify rules, just type `/karma <natural-language description>` in your AI client."

### Fix 1 — Show first paragraph instead of first line

```python
# v0.9.9
first_line = r.preference.strip().split("\n")[0]
print(f"    {first_line}")

# v0.9.10
first_paragraph = r.preference.strip().split("\n\n")[0]
for line in first_paragraph.split("\n"):
    print(f"    {line.strip()}")
```

YAML `|` block paragraphs are separated by blank lines (semantic units), within-paragraph `\n` is visual wrap. Splitting on `\n\n` keeps one complete meaning unit per rule.

Length tradeoff: zh full 7 → ~33 lines summary; en minimal 5 → ~37 lines. Still fits on one screen for Agent relay.

### Fix 2 — Bilingual footer with token reassurance + `/karma` entry

New `init.summary.footer` locale key:

```
经测试，以上规则注入仅占 karma 每 session 会话 token 消耗总量的 3% 以内，
请放心使用，体验下 Agent 长任务不飘逸的爽感。希望增改规则直接输入
/karma <自然语言你想增加的规则> 即可。
```

```
Tested: this rule injection accounts for under 3% of karma's per-session
token spend — relax and enjoy the "Agent doesn't drift in long tasks" feel.
To add or modify rules, just type /karma <natural-language description of
the rule> in your AI client.
```

**Why `/karma` doesn't violate v0.9.9's "no command tips" rule**: `/karma` is a slash command typed in the AI client's chat box (Claude Code / Codex / Gemini), not a shell command requiring the user to open a terminal. It's the natural-language rule-input skill — typing `/karma <intent>` is equivalent to "just tell the Agent what rule you want". So it's an in-chat continuation, not a "go run this in your shell" friction.

Footer follows `_resolve_locale()` (KARMA_LOCALE env > config.yaml > `is_chinese_user()` system detect) — Chinese-system users see Chinese footer, English-system users see English footer automatically.

### Test coverage

2 new tests in `tests/test_cli.py`:
- `test_init_summary_footer_includes_token_cost_and_slash_karma` — verifies footer contains `3%` + `/karma`
- `test_init_summary_footer_matches_user_locale` — **lockdown**: with `KARMA_LOCALE=zh` only Chinese footer appears (no English leak); with `KARMA_LOCALE=en` only English footer appears (no Chinese leak)

Updated `test_init_summary_does_not_include_command_tips` comment to clarify `/karma <natural-language>` is explicitly allowed (slash command in chat, not shell command).

### Verification

- 479/479 passing under both `LANG=zh_CN.UTF-8` and `LANG=en_US.UTF-8` (was 477)
- All 6 local gates pass

## [0.9.9] — 2026-05-16 (feat — onboarding: `karma init` shows default rules summary so Agent-assisted install can relay it to the user)

### Why this release

User observation while reviewing product gaps: "Can `karma init` give a clear feedback at the end — when the Agent helps install karma, the user should be told which default rules are enabled, without needing to type any command themselves."

The Agent-assisted install flow (the "Or ask your AI client to install it" path in README) currently ends after `karma install-hooks` succeeds. Agent has no built-in knowledge of which rules ended up enabled — it would need to either (a) instruct the user to run `karma rule list`, which contradicts "no manual command typing" goal, or (b) read `rules.yaml` itself, which is extra Agent work outside the install script.

### Fix — `karma init` ends with a default-rules summary block

Added `_print_default_rules_summary()` helper called at the end of `cmd_init`. Output format (zh locale shown):

```
已为你启用以下默认规则 (7/10 软上限):
  ▸ [long-term-fundamental]
    用户相信你能深挖根因。遇到难题他希望你先停下想「最干净的解法是什么」
  ▸ [non-blocking-parallel]
    sleep / wait / 等长任务跑完期间，用户等你的输出。盯着进度条不是协作 — 是「卡了」。
  ... (one line per rule: id + first line of preference)
```

Agent running `karma init` sees this stdout block and naturally relays it to the user — fulfilling the onboarding requirement without any user-typed command.

### Design choice — deliberately no "next steps" tips

First-pass implementation included a "Next steps:" section with `karma rule edit / list / remove` command tips. User pushback: "I don't want the user to type any command manually." Removed the tips block. The principle: **once Agent has relayed the rule summary, user wanting to modify a rule should just tell the Agent "remove rule X" or "change rule Y" — Agent knows to use the `/karma` skill or `karma rule edit`.** No manual command syntax required.

Header text only is bilingual (`init.summary.header` locale key). Rule content stays in whichever language the template uses (zh template → Chinese preference; en template → English preference).

### Test coverage

2 new tests in `tests/test_cli.py`:
- `test_init_prints_default_rules_summary` — verifies header + each rule id appears in stdout under minimal install
- `test_init_summary_does_not_include_command_tips` — locks the "no manual command tips" invariant; if anyone re-introduces "Next steps:" / `karma rule edit` literal in the summary block, this fails CI

### Verification

- 477/477 passing under both `LANG=zh_CN.UTF-8` and `LANG=en_US.UTF-8` (was 475)
- All 6 local gates pass

## [0.9.8] — 2026-05-16 (fix — cross-process concurrency race + API-enforced atomicity via `update_state(sid, fn)`)

### Why this release

While preparing for a contributor's "更厉害测试集" stress test ("how could it not find problems?"), audited 4 reliability suspicions by reading `session_state.py` / `violations.py` / `rule.py` / hook entry points. 3 turned out already graceful (JSON load recovery / jsonl rotation / YAML config error fallback). The 4th was real: **session_state.py's own catchup_pending_bg docstring (line 276-286) admits the TODO: "极少数情况下多 hook 同时跑会让 ltp 时序略偏... 要彻底消除可加 atomic file lock"** — the file lock was never added.

The actual scope of the race is broader than that docstring suggests: multiple Claude Code processes / multiple hooks firing nearly simultaneously on the same session all do `load → modify → save`. The save itself is atomic (`os.replace`), but the load → modify → save sequence is not — two hooks both load old state, each modify different fields, both save, **the second save overwrites the first's modifications across ALL fields** (read_files, edit_files, pending_bg_tasks, turn_count, etc — not just ltp time skew).

### Anti-shortcut alignment moment

First-pass plan was to expose `state_lock(sid)` contextmanager and have 6 hook entry points each manually wrap `load → modify → save` with `with state_lock(...)`. User caught this: **"咱们要做长期方案，你忘了么？为什么 karma 没制止你走短期路线？"** — I had identified the higher-order-function approach (B) as "long-term correct" but rationalized choosing the contextmanager approach (A) as "v0.9.8 务实，留 v0.10/v1 走 B" using framing that didn't trigger karma's literal-pattern checks (karma is pure engineering, zero LLM; design-intent shortcuts aren't catchable by regex — human review is the backstop).

After rollback + re-read, settled on approach C (chosen via informed alignment with user, not my own shortcut):

| Decision | Rationale |
|---|---|
| Keep `load`/`save` public | tests/ has 58 call sites — they're legitimate lower-level primitive users (pytest / requests / sqlalchemy follow the same pattern). Forcing them through `update_state` would distort the single-process test scenario without solving a real problem. |
| Add `update_state(sid, fn) -> tuple[state, T]` as production API | Higher-order function bundles `_state_lock` internally — callers cannot omit the lock. fn raising → rollback (no save). Signature returns `tuple[SessionState, T]` so fn can derive computed results (e.g. `_build_smart_reinject` computing `additional_context` inside the lock). |
| Add `read_state(sid)` for explicit read-only | Same semantics as `load(sid)` but name signals "don't modify state here, use update_state". Atomic `os.replace` writes guarantee reads never see half-updated state, so no lock needed for read-only. |
| Migrate all 6 hook entry points to `update_state` | API enforcement: the unchangeable invariant ("load → modify → save must be atomic per session") is now in the API itself, not in the calling convention. New hooks can't accidentally skip the lock. |

### Implementation map

| Location | Change |
|---|---|
| `karma/session_state.py` | Added `_state_lock` (fcntl.flock advisory lock, Windows no-op fallback) + `update_state` + `read_state`. Updated module docstring with API layering policy. |
| `karma/hooks/post_tool_use.py:main` | Wrapped full modify-block + `_build_smart_reinject` in fn; fn returns `additional_context` for stdout. |
| `karma/hooks/user_prompt_submit.py:_advance_turn_state` | Wrapped catchup + turn++ + stop_block reset + model detection in fn. |
| `karma/hooks/session_start.py` | model assignment now via `update_state`. |
| `karma/hooks/subagent_start.py` | Two independent `update_state` calls (main state model queue pop + sub state model write — different lock keys, independent). |
| `karma/hooks/pre_tool_use.py` | Section 1 (Agent model enqueue) via `update_state`. Section 2 (catchup-no-save) preserved unchanged — this is the existing design "PreToolUse is decision-side, not state-side; real catchup happens in PostToolUse/Stop". |
| `karma/hooks/stop.py` | `_handle_force_block` + `_handle_keep_pushing_block` use `update_state` for `stop_block_count += 1`. |
| `karma/cli.py` | Two read-only callers (`stats` / `doctor` views) migrated to `read_state` to make API intent visible. |
| Bonus | Stop hook's hardcoded "临时改 sticky" string (missed by v0.9.7's i18n string sweep — this was direct code literal not i18n key) → "临时改 rules.yaml". |

### Test coverage

7 new tests in `tests/test_session_state.py`:
- `test_update_state_applies_fn_and_persists` — fn mutate + persist
- `test_update_state_returns_fn_value` — fn return value pattern
- `test_update_state_fn_exception_rolls_back` — fn exception → no save (rollback verified)
- `test_update_state_agent_id_isolation` — main vs sub Agent state don't share lock
- `test_read_state_returns_snapshot` — read-only API
- `test_state_lock_acquire_and_release` — basic lock contextmanager
- **`test_update_state_concurrent_no_lost_updates`** — **real race fix evidence**: spawns N=20 subprocesses each calling `update_state` on the same session to add a unique path to `read_files`, asserts the final state contains all 20 paths. Without the lock, this would lose updates immediately under that timing window.

### Verification

- 473/473 passing under both `LANG=zh_CN.UTF-8` and `LANG=en_US.UTF-8` (was 466 before)
- All 6 local gates pass (pytest both locales / ruff / mypy / vulture / wheel verify)
- vulture flagged `read_state` as unused after first pass → migrated cli.py 2 read-only sites to `read_state`, making API intent real (not just defensive name)

### Why this matters more than v0.9.2-v0.9.7

v0.9.2 → v0.9.7 fixed CI gates + i18n residue + user-facing string consistency. v0.9.8 fixes a **functional correctness bug** that affects every multi-process karma user — and does so by encoding the invariant in API shape rather than in calling convention. This is what "long-term-fundamental" means in code, not in tone.

## [0.9.7] — 2026-05-15 (fix — KARMA_HOME isolation broken in bypass detection + v0.6.0 user-facing sticky residue + regression mechanism)

### Why this release

While auditing what the sub-agent classified as "legitimately preserved" in the v0.9.6 sticky→rules rename audit, found 2 actual bugs the rename sweep had been missing — not in code paths the sub-agent had flagged. These are deeper than v0.9.2 → v0.9.6 CI fixes because they're cross-user / multi-profile / CI-isolation correctness, not just gate alignment.

### Fix 1 — `bypass_karma` check broken under `KARMA_HOME` isolation

`karma/paths.py:karma_home()` has supported `KARMA_HOME` env override since the env was introduced (for cross-user / dry-run / CI / multi-profile). But `karma/checks/bypass_karma.py:_KARMA_STATE_PATH_RE` had a hardcoded `\.claude/karma/...` literal regex. Effect: user running `KARMA_HOME=/tmp/foo karma ...` then `rm /tmp/foo/session-state/*.json` (bypass attempt) — the bypass-karma check **completely missed it**, because the regex only matched the default `~/.claude/karma/` path.

This is the same class of bug as the CI verify step: a hardcoded literal where a factory call was required. Single-source-of-truth principle was broken in one corner of the codebase.

**Fix**: `_build_state_path_re()` factory function dynamically constructs the regex from `karma_home()` — covers default mode, `KARMA_HOME` override mode, and home-subdir mode (where users may type `~/<rel>` literal). Also expanded the filename set from `(session-state|violations|sticky.yaml)` to `(session-state|violations|rules.yaml|sticky.yaml)` — both v0.6.0+ main name and the legacy migration path now get caught.

### Fix 2 — `karma/cli.py:257` hardcoded hint string misleads `KARMA_HOME` users

`print("编辑用: ... vim ~/.claude/karma/config.yaml")` — but file actually created at `KARMA_DIR / "config.yaml"`. Under `KARMA_HOME=/tmp/foo`, user gets pointed at a non-existent file. Fix: `print(f"... vim {config_path}")` — same variable already in scope.

### Fix 3 — `pyproject.toml` keywords still listed `"sticky"`

v0.6.0 BREAKING renamed `sticky.*` → `rules.*` but the PyPI keywords still listed `"sticky"`. Updated to `"rules"`.

### Fix 4 — User-facing files still contained `sticky` strings

5 user-facing places where the user actually sees the string and would get confused (file doesn't exist / wrong filename):
- `data/locales/zh.yaml:28` — force_block reason i18n message
- `data/config.example.yaml:13,16` — comments in the config template that gets copied to `~/.claude/karma/config.yaml` by `karma init`
- `data/rules.dev.example.zh.yaml:57,120` — rule template preference text users install via `karma init`
- `data/rules.dev.minimal.example.zh.yaml:71` — minimal template parallel residue

### Fix 5 — `karma/violations.py` API contract docstrings said `sticky_id`

4 functions (`recent`/`count_recent`/`recent_session`/`count_recent_turns`) had docstrings claiming they return `sticky_id` keys, but the actual code returns `rule_id` (per `extract_rule_id()` helper). API contract was misleading. Fixed all 4 + 1 inline comment ("3 turn 内同 sticky" → "3 turn 内同一规则").

### Regression mechanism — `tests/test_no_sticky_in_user_facing.py`

The deeper structural issue: every `sticky` → `rules` sweep so far (v0.8.2, v0.9.7) found new residue the previous sweep missed. No mechanism was locking the user-facing surface. New regression test locks 7 user-facing files with whitelist-style exceptions — next time someone modifies these files and accidentally introduces an old name, CI fails. White­list is "exact line literal" not "file-level exemption" — granular and audit­able.

Dev-facing residue (cli/hook/notify module docstrings, tests/ variable names — ~10 more places) deferred to v0.10.x for a single mass sweep rather than piece­meal patches.

### New tests — `tests/test_bypass_karma.py` KARMA_HOME isolation coverage

4 new cases:
- Default mode: matches `~/.claude/karma/*` / absolute home path / relative fragment
- `KARMA_HOME` override mode: matches custom path bypass writes
- `KARMA_HOME` in home subdir: matches `~/<rel>` literal users may type
- Both `rules.yaml` and `sticky.yaml` (legacy compat) get caught

### Verification

- **466/466 passing** under both `LANG=zh_CN.UTF-8` and `LANG=en_US.UTF-8`
- All 6 local gates pass (pytest both locales / ruff / mypy / vulture / wheel verify)
- Wheel inspection: all 6 expected templates present

## [0.9.6] — 2026-05-15 (fix — 5th independent CI failure: v0.6.0 BREAKING rename leftover in `verify wheel` step)

### My v0.9.5 prediction was wrong

v0.9.5 changelog declared "This push's CI run should finally be green (4th attempt)." It wasn't. The `Verify wheel contains yaml templates` step failed across all 4 matrix jobs. New root cause:

The CI verify step checks the wheel contains `data/sticky.dev.example.yaml`. But v0.6.0 BREAKING renamed `sticky.*` → `rules.*`. **The verify step has been failing since v0.6.0 (~9 releases ago)** — it was just hidden because earlier steps (vulture/mypy/pytest) kept failing first, and `fail-fast: false` doesn't change the order of step execution within a job.

### Fix — update verify expected list to current artifact layout

```yaml
expected = [
    'data/rules.dev.example.yaml',
    'data/rules.dev.example.zh.yaml',
    'data/locales/en.yaml',
    'data/locales/zh.yaml',
    'data/config.example.yaml',
    'skills/karma/SKILL.md',
]
```

Now matches actual wheel contents (verified locally via `python -m build --wheel && python -c "..."`). Also broader coverage — added the zh.yaml example + locales + skill files which were missing from the original 2-file check.

### Meta-lesson: don't claim "final fix" without running the full CI pipeline locally

I'd been peeling CI failures off one layer at a time, declaring each one "the root cause." The actual deep lesson is structural: my local checklist (5 gates as of v0.9.5) stops at `pytest` — it never runs `python -m build --wheel` + verify. The CI pipeline does. So any step that runs after pytest in CI but isn't on my local checklist remains a blind spot.

**v0.9.6 adds gate 6 — wheel build + verify** — to local checklist, making it a strict superset of CI step order:

```bash
pytest -q                                            # 460/460
LANG=en_US.UTF-8 pytest -q                          # 460/460 (locale)
ruff check karma/ tests/                            # clean
mypy karma/ && mypy tests/                          # no issues
vulture karma/ whitelist.py --min-confidence 60     # exit 0
python -m build --wheel && python -c "<verify>"     # wheel verify (NEW)
```

### Verification

- All 6 local gates pass
- Built wheel `karma-0.9.5-py3-none-any.whl` (will be `0.9.6` after this commit) contains all 6 expected templates

### Honesty caveat

I cannot guarantee this is the deepest layer. If a 6th CI failure appears after push, that itself is data — it means the CI pipeline has more steps than I've enumerated in this checklist.

## [0.9.5] — 2026-05-15 (fix — 4th independent CI failure: tests assume zh locale, CI runs en)

### Pattern continues

v0.9.4 push: `mypy` green, `vulture` green, `ruff` green — but **`pytest` red on 16 tests**. Root cause: test fixtures assert Chinese strings (`"默契"` / `"偏离"` / `"纯陈述"`) for `format_for_injection` output. My local machine's `LANG=zh_CN.UTF-8` makes `karma.locale_detect.is_chinese_user()` return True → i18n picks zh → fixtures pass. CI runners default `en_US.UTF-8` → is_chinese_user returns False → i18n picks en → 16 fixtures fail.

This is **the 4th independent CI failure root cause** in 4 patch releases (v0.9.2 → v0.9.5). Each fix revealed the next layer.

### Fix — `tests/conftest.py` with `pytest_configure` hook

```python
def pytest_configure(config):
    """Force zh locale before any karma module is imported."""
    os.environ.setdefault("KARMA_LOCALE", "zh")
```

Tests now always run in zh locale (matching fixture strings) regardless of host OS locale. `setdefault` lets users override via env if needed.

### Why I missed it 4 times in a row

Compound oversights:
1. `LANG=zh_CN.UTF-8` on my Mac → tests pass locally even though they're locale-coupled
2. No mypy in local checklist
3. vulture `--min-confidence` mismatch
4. CI green status never verified before tag

This release adds the **5th** local gate matching CI: setting `LANG=en_US.UTF-8` when running pytest reveals this class of bug before push.

### Updated checklist (v0.9.5+)

```bash
pytest -q                                            # 460/460
LANG=en_US.UTF-8 pytest -q                          # also 460/460 (catches locale coupling)
ruff check karma/ tests/                            # clean
mypy karma/ && mypy tests/                          # no issues
vulture karma/ whitelist.py --min-confidence 60     # exit 0
# Push, then:
gh run watch $(gh run list -L 1 --json databaseId -q '.[0].databaseId') --exit-status
```

### Verification

- 460/460 passing under both `LANG=zh_CN.UTF-8` and `LANG=en_US.UTF-8`
- All other gates clean
- This push's CI run should finally be green (4th attempt)

## [0.9.4] — 2026-05-15 (fix — third independent CI failure: mypy type error in signals.py)

### Pattern: I never ran mypy locally

After v0.9.3 push (which fixed vulture-min-conf-60 mismatch), CI **still red**. Third independent root cause: `karma/signals.py:116` `mypy` error introduced in v0.8.1:

```
karma/signals.py:116: error: Argument 1 to "product" has incompatible type
                            "*list[list[Any] | None]"; expected "Iterable[Any]"
```

In `_expand_yaml_signals`, `resolved` has type `list[tuple[str, list | None]]` after `resolve_key()`. The `if any(v is None for _, v in resolved): continue` guard ensures non-None before `product(*word_lists)`, but mypy can't narrow through that pattern.

### The deeper admission

I never ran `mypy` locally. My local "quality gates" check before push was just `pytest + ruff`. CI runs `pytest + ruff + mypy karma/ + mypy tests/ + vulture --min-conf 60`. My local subset missed mypy + low-conf vulture, so 2 of 4 CI checks could silently fail.

This is the **deepest root cause** of the v0.8.6 → v0.9.3 CI red streak — not 3 unrelated bugs, but **one systemic gap**: my "passing locally" claim was based on a strict subset of CI's actual checks.

### Fix

Type-narrowed `word_lists` via explicit filter:

```python
word_lists: list[list] = [v for _, v in resolved if v is not None]
```

The `any(v is None)` guard above already ensures this, but the explicit filter both satisfies mypy and is defensively correct.

### Checklist now (matching CI exactly)

Local gates before any tag/release:

1. `pytest -q` — 460/460 passing
2. `ruff check karma/ tests/` — All checks passed
3. `mypy karma/ && mypy tests/` — no issues
4. `vulture karma/ whitelist.py --min-confidence 60` — exit 0
5. `gh run list --limit 1` after push — verify CI is actually green

All 4 of these gates now match what CI runs. Step 5 is the final verification.

### Verification

All 4 local gates green + this push's CI run should be green for the first time since v0.8.5.

## [0.9.3] — 2026-05-15 (fix — actually green up CI: 3 more dead-code items + vulture whitelist)

### Following up on v0.9.2

v0.9.2 fixed the hardcoded path bug from issue #2. After push I checked `gh run list` (per my own new checklist) — **CI still red**. Different failure mode from issue #2.

### Real root cause for the CI red streak

CI runs `vulture karma/ --min-confidence 60` but my local checks use `--min-confidence 70`. The 60-confidence threshold flags 5 items my local runs never see:

| File / Line | Item | Verdict |
|---|---|---|
| `karma/cli.py:67-68` | `EXAMPLE_RULES` / `EXAMPLE_RULES_MINIMAL` aliases | **truly dead** — 0 callers, delete |
| `karma/i18n.py:99` | `current_locale()` (docstring says "for diagnostics") | **truly dead** — 0 callers, delete |
| `karma/i18n.py:104` | `reset_cache()` (docstring says "for tests / config-reload") | **truly dead** — 0 callers, delete |
| `karma/signals.py:205` | `reset_cache()` | **vulture false positive** — `tests/test_signals.py` imports + uses it (vulture only scans `karma/`, doesn't see test usage) |

### Fix

- Deleted the 4 truly-dead items
- Added `whitelist.py` referencing `karma.signals.reset_cache` so vulture sees it as "used"
- Updated `.github/workflows/ci.yml`: `vulture karma/ whitelist.py --min-confidence 60`

### Loud-failure admission (continued from v0.9.2)

The v0.9.2 CHANGELOG already admitted "I shipped 'pytest 460/460 passing' without checking CI." This release confirms it took a second failed CI run before I realized one bug (issue #2) wasn't the whole story — vulture was failing too, independent of the path bug.

For the v0.9.0/v0.9.1 CI failures specifically, the vulture issue likely started at v0.8.5 when my "code review pass" introduced unused names. I never noticed because I ran vulture locally with `--min-confidence 70` not 60.

**Mismatch root cause**: my local quality gates were less strict than CI's. Fixing that going forward: my checklist now also includes "run vulture with `--min-confidence 60` matching CI before tag/release."

### Verification

- 460/460 passing locally
- `vulture karma/ whitelist.py --min-confidence 60` → exit 0 locally (CI command exactly)
- `ruff` clean
- This push's CI run should finally be green

## [0.9.2] — 2026-05-15 (fix — `test_compact_hooks.py` hardcoded `/Users/jhz/karma` path → dynamic resolution; issue #2 from @fyn1320068837-source)

### Real-user bug report (2nd from same external contributor)

@fyn1320068837-source filed issue #2: `tests/test_compact_hooks.py` had **20 hardcoded references to `/Users/jhz/karma`** (the maintainer's local path) across all 9 test functions. Result: tests pass locally on the maintainer's machine but fail with `FileNotFoundError: '/Users/jhz/karma'` on any other machine, **including CI**.

### CI was broken for 3 releases (loud-failure admission)

Verified after issue filed: GitHub Actions CI has been **failing since v0.8.6** (3 consecutive releases — v0.8.6 / v0.9.0 / v0.9.1) because of this bug. I shipped releases while saying "455/455 passing" / "460/460 passing" — those were **local** test runs. I never checked `gh run list` before tagging. Same class of failure as v0.6.1's first external user dogfood loop: maintainer self-test misses environment-dependent bugs.

This is a direct violation of rule #4 (loud-failure-with-evidence). 「pytest 460/460 通过 + ruff 干净」without checking CI is the same shape of dishonesty as「应该可以」without running tests. Reporter's catch was sharp.

### Fix (exactly as reporter suggested)

```python
# tests/test_compact_hooks.py header
import pathlib, sys

PROJECT_ROOT = str(pathlib.Path(__file__).resolve().parent.parent)
PYTHON = sys.executable
```

Then:
- All `"/Users/jhz/karma/.venv/bin/python"` → `PYTHON`
- All `cwd="/Users/jhz/karma"` → `cwd=PROJECT_ROOT`

20 occurrences replaced. Tests still pass locally (9/9) and now work on any machine + CI.

### Verification

- 460/460 passing
- `ruff`: 0 issues
- This commit's CI run should be **green for the first time since v0.8.5**

### Lesson

External user dogfood is invaluable — maintainer self-test on the only machine matching the hardcoded paths cannot catch this class of bug. Adding "check `gh run list` before tag/release" to my own checklist going forward.

## [0.9.1] — 2026-05-15 (docs — v0.9.0 doc sync: PRD F2 / HOOK_CONFIGURATION_GUIDE / session_start docstring)

### Why this patch

v0.9.0 shipped the injection architecture change but left a few internal docs describing the pre-v0.9.0 behavior. User asked for doc-sync follow-up after dogfooding v0.9.0 in a fresh session showed the new compact-anchor format working.

### Updated

- **`docs/PRD.md` / `docs/PRD.zh.md`**: F2 (user_prompt_submit hook) description now reflects the compact anchor (~490 tok) vs full preference text. Added new F2.5 "Injection architecture (v0.9.0)" section with the 5-hook lifecycle table
- **`docs/HOOK_CONFIGURATION_GUIDE.md`**: UserPromptSubmit row updated to describe compact anchor format; SessionStart row clarifies "full baseline" (only one full injection per session); PostToolUse row shows session-global threshold trigger
- **`karma/hooks/session_start.py`**: docstring had reversed description ("UserPromptSubmit every turn full, SessionStart per-session compact") — exactly opposite of v0.9.0 reality. Rewrote to match v0.9.0 architecture

### Verification

- 460/460 passing
- `ruff`: 0 issues

Pure documentation patch — no behavior change.

## [0.9.0] — 2026-05-15 (feat — injection architecture redesign: SessionStart full baseline + per-turn anchor + cumulative full reinject, **73% token saving per turn**)

### User insight that drove this

After v0.8.6 wrap-up I (the Agent) reported full injection cost: **1817 tokens / turn** at UserPromptSubmit head, accumulating 100 × 1817 = ~182K (18%) of a 1M Opus context window. User's response:

> session 初始注入 + 不同模型默认锚定阈值就近注入 + 违规注入 + 压缩后注入 + 子 Agent 注入是不是就行了

i.e. **don't inject the full rules every turn** — inject once at session start (SessionStart), refresh when context-token accumulation hits the model's decay threshold (PostToolUse), supplement with violation reminders when needed (UserPromptSubmit fallback). The previous design re-injected full rules each turn — duplicate of what's already in conversation history.

Then user refined with 3 adjustments:

1. **SessionStart full injection** (replace current精简 baseline)
2. **UserPromptSubmit per-turn compact anchor** (id + first-line preference + drift marker, ~490 tokens vs 1817)
3. **PostToolUse mid-session full reinject** triggered by **session-global** byte accumulation hitting model threshold (not per-turn)

### Architecture changes

**Injection lifecycle (v0.9.0)**:

```
SessionStart (startup/resume/clear/compact) → full baseline (1817 tok, once per session)
UserPromptSubmit (every turn)               → compact anchor (~490 tok) + drift markers + violation fallback (when violated)
PostToolUse (every tool call)               → accumulate byte_seq; when (byte_seq - last_reinject) ≥ model threshold → full reinject (1817 tok) + reset last_reinject
SubagentStart                               → subagent inherits full rules (unchanged)
PreCompact                                  → snapshot to disk (unchanged; SessionStart compact path reads it)
```

**Model decay thresholds tightened** (since SessionStart baseline ages in history top while turns accumulate):
- Opus: 80K → **60K**
- Sonnet: 60K → **40K**
- Haiku: 30K (unchanged)
- DEFAULT (unknown model): 60K → **40K**

### Measured token savings

For a 100-turn 1M Opus session:

| Architecture | UserPromptSubmit | SessionStart | PostToolUse | **Total** | **% of 1M** |
|---|---|---|---|---|---|
| Old (v0.8.x) | 100 × 1817 = 181.7K | 0.4K | ~2K | **~184K** | **18.4%** |
| v0.9.0 | 100 × 490 = 49.0K | 1.8K | 17 × 1817 = 30.9K | **~82K** | **8.2%** |

**Per-turn UserPromptSubmit saving: 73% (1817 → 490 tokens)**.

Real-world cumulative saving for 1M Opus session: ~100K tokens (10% of context), 55% reduction vs old architecture.

### New `format_anchor_only()` function

`karma/rule.py` adds `format_anchor_only(rule_list, recent_violations)` rendering compact text: `id + first-line preference + drift marker`. Used by UserPromptSubmit per-turn injection. `format_for_injection()` (full) still used by SessionStart + PostToolUse mid-reinject.

### State semantic change

`tool_byte_seq` / `last_reinject_byte_seq` no longer reset per-turn (v0.4.32 was per-turn because UserPromptSubmit re-injected full each turn). Now **session-global accumulation** — mid-reinject triggers correctly by session-level decay threshold.

### Tests

- 4 new `format_anchor_only` tests (basic / drift markers / token savings vs full / empty list)
- 7 model_threshold tests updated for new threshold values
- 5 `post_tool_use_reinject` tests updated for full-injection behavior + new thresholds
- `test_hooks` test_post_tool_use_smart_reinject expectations updated
- **460/460 passing**

### What this means for users

- **Significantly lower input token cost per turn** — both API billing and prompt cache miss savings
- **Same rule fidelity** — Agent still sees full preference text via SessionStart (persisted in conversation history) + every-turn compact anchor reminding the rules exist + automatic full re-injection when context decays
- **No config changes required** — fully transparent upgrade for existing rules.yaml

### Why this is v0.9.0 (minor bump, not patch)

User-visible behavior change in how injection works. Existing rules.yaml still works without modification, but token cost profile is meaningfully different — version bump signals this.

## [0.8.6] — 2026-05-15 (fix — `agent_saturation` covers bare "真饱和" / English "genuinely saturated" — within-turn dogfood)

### Within-turn dogfood trigger

After shipping v0.8.5 with the words "再往下就是 optimization for its own sake — **真饱和**, 等下一轮 dogfood reflective driving v0.9 方向", the `keep_pushing` reflection hook still fired. Same root-cause pattern as v0.7.4 / v0.8.0 user_stop_hints coverage gaps: the signal phrase set had "任务真饱和" / "这一波真饱和" but not bare "真饱和".

### Fix — extend `agent_saturation` signal phrases

`data/signals/agent_saturation/zh.txt`:
- Added bare `真饱和` / `真的饱和` / `彻底饱和` / `已饱和`
- Added series-completion phrases: `系列收官` / `系列已收官` / `收官在干净状态` / `干净状态收官` (natural ways an Agent signals wrapping up a multi-release series)

`data/signals/agent_saturation/en.txt`:
- Added `genuinely saturated` / `truly saturated` / `fully saturated`
- Added `diminishing returns` / `optimization for its own sake` (the actual phrasing v0.8.5 release notes used to express "further work has diminishing returns")

### Tests

- New `test_v086_bare_saturation_phrasing_exempts` with 6 fixtures covering both Chinese and English bare-saturation variants
- 456/456 passing (was 455)

### Why this matters (same lesson as v0.7.4)

The signal phrase set has to track the *actual* phrasing the Agent produces in real conversation, not the canonical "task is saturated" template. Each within-turn false-positive is a free signal of what phrasing the regex missed — fix it at the data layer, not at the Agent layer.

## [0.8.5] — 2026-05-15 (polish — 3rd code review pass: 2 high-value cleanups, codebase confirmed clean)

### 3rd code review pass (post v0.8.4)

User asked for another round of code audit + doc consistency review. Tools clean (`vulture` / `ruff` / 455 tests). Manual audit found 2 high-value cleanups; rest are middle/low-value polish with diminishing returns honestly reported and skipped.

### What got fixed

- `karma/rule.py:format_for_injection` had `from karma.i18n import tr` as a function-level import. Verified `karma.i18n` is a leaf module (no `karma.*` imports) — safe to hoist to module top. Reduces function-body noise + matches module-level import convention.
- `karma/checks/chinese_plain.py` had an inline magic number `< 30` for "jargon-to-explanation parenthesis max distance". Extracted as named constant `_JARGON_PAREN_MAX_DIST = 30` alongside the existing `_JARGON_CONTEXT_RADIUS = 30` — both module-level, both explanatory.

### What was reviewed and intentionally not changed

- cli.py has ~10 function-level `from karma.* import ...` calls. Most are safe to hoist (no circular-import risk verified), but several serve testing mock-friendliness (e.g. `cmd_reset_session` lazy-imports `DEFAULT_DIR as SS_DIR` so `monkeypatch.setattr(karma.session_state, 'DEFAULT_DIR', ...)` sees the patched value). Net benefit of mass-hoisting is small (~3 net lines saved), and individual analysis to separate true-mock-friendly from cruft would burn review time on diminishing returns.
- cli.py has 4 functions over 100 lines (`cmd_audit` / `cmd_rule_add` / `cmd_doctor` / module `main` dispatcher). Tools find no dead code or duplication; they're long-but-clear coordinator functions. Forced helper extraction would shuffle parameters across 5+ helpers per function without making the code easier to navigate.

### Doc consistency audit (post v0.8.4)

Verified across README / PRD / ARCHITECTURE / HANDOFF (bilingual):

- Test count "455" consistent
- Signal count "7" consistent (post-`completion_words`)
- 0 dead local links across 16 key docs
- v0.8.4 milestone entries present in ARCHITECTURE / HANDOFF / CHANGELOG; correctly absent from README / PRD (patch releases don't belong in those top-level docs)

Conclusion: v0.8.x series ends in a state where tooling, manual review, and doc audit all agree the codebase is clean. Further polish would be optimization-for-its-own-sake.

### Verification

- 455/455 passing
- `ruff`: 0 issues
- `vulture --min-confidence 70`: 0 dead code

## [0.8.4] — 2026-05-15 (docs — v0.8.x cumulative sync + 1 dead-code leftover from v0.8.2 audit)

### Why this pass

After v0.8.0 → v0.8.3 in rapid succession, user asked for an "E" pass: re-audit all docs to make sure the cumulative v0.8.x picture (i18n signals, 7 of 7 detection signals, English coverage) is consistently reflected — not partially-stuck at v0.8.0 or v0.8.1 in some places.

### Sync gaps caught

**Stale "6 signals" counts** (v0.8.0/v0.8.1 numbers, should be 7 after v0.8.2 added `completion_words`):

- `README.md` Performance table → updated to "7 detection signals" / "~7 small files"
- `README.zh.md` 性能表 → same
- `docs/PRD.md` F6 listening-side → "All 7 detection signals externalized" (was "6")
- `docs/PRD.zh.md` F6 同步
- `docs/ARCHITECTURE.md` i18n system section → adds `completion_words` to the `.txt` list + bumps version range to "v0.8.0 → v0.8.2"
- `docs/ARCHITECTURE.zh.md` i18n 系统段 → same

### Real dead code v0.8.2 audit missed

`karma/checks/__init__.py:run_checks()` had a `sticky_id: str = ""` parameter whose own inline comment said "v0.5.0 deprecated alias, removed in v0.6.0" — never actually removed. 0 callers passed it (grep verified). Removed parameter + the `rule_id=rule_id or sticky_id` fallback that referenced it. Now the function signature is just `rule_id: str = ""`.

This is the same pattern as the 3 dead-code items v0.8.2 caught (`KARMA_RULE_SKILL_SRC`, `_claude_skills_dir`, `_install_karma_rule_skill`) — comments said "v0.6.0 removed" but never were. v0.8.4 catches the 4th instance the manual grep missed last round.

### What did NOT change

- CHANGELOG / HANDOFF historical entries with "6 signals" counts — those describe what was true at that release, archive integrity preserved (rule 5)
- README "Older versions" banner mentioning v0.6.0 `karma.sticky` removal — legitimate migration guidance for users on pre-v0.6 versions

### Verification

- 455/455 passing (removing `sticky_id` parameter required updating the internal `rule_id=rule_id or sticky_id` fallback line)
- `ruff`: 0 issues
- `vulture --min-confidence 70`: 0 dead code

## [0.8.3] — 2026-05-15 (refactor — long hook main functions split + cli.py import dedup)

### Internal refactor only (no user-visible change)

Per rule 9 exception: pure internal refactor, no CHANGELOG / HANDOFF only — README / PRD untouched.

### A: long hook `main()` functions split

Hook main functions had grown long (223 / 159 / 128 lines) — readable but hard to navigate. Extracted clear single-purpose helpers without changing control flow:

| Hook | Before | After | Helpers extracted |
|---|---|---|---|
| `stop.py:main` | 223 | 123 | `_emit_notifications` (stderr + desktop notify + escalation) / `_handle_force_block` → bool / `_handle_keep_pushing_block` → bool |
| `user_prompt_submit.py:main` | 159 | 68 | `_advance_turn_state` (turn count + model detect) / `_build_strong_reminder` (run checks on prior assistant response, return reminder text) |
| `pre_tool_use.py:main` | 128 | 90 | `_emit_engine_denial` (CheckHit path) / `_emit_keyword_denial` (Violation path) — deduplicating the parallel deny logic |

The other 5 hook mains were already under 90 lines and didn't warrant splitting.

### B: `cli.py` function-level duplicate imports

`cli.py` had 3 places re-importing `from karma.rule import ... load as load_rules` inside function bodies while the module had already imported `load` at the top. Plus 1 instance of `from karma.violations import load_all as _load_v` shadow-aliasing the module-top import. All 4 cleaned up:

- Module top now imports `from karma.rule import load as load_rules` and `format_for_injection`
- Function-internal duplicate imports removed
- 3 places using bare `load()` standardized to `load_rules()` — consistent naming, less mental switching

### Verification

- `pytest`: 455/455 passing (no behavior change)
- `ruff`: 0 issues
- `vulture --min-confidence 70`: 0 dead code

### Why this matters

Long `main()` functions and inline duplicate imports are classic "the codebase grew faster than its structure caught up" patterns. After v0.8.2's user-facing naming cleanup, v0.8.3 closes the parallel internal-structure debt — making the hook layer easier to navigate for the next refactor cycle.

## [0.8.2] — 2026-05-15 (refactor — code audit: dead code purge + `sticky` → `rule` naming consistency + missing i18n consistency + 1 bug fix)

### Why a code audit pass

After shipping v0.8.0/v0.8.1, user asked: "再做一轮代码审查咋样，看看有没有废弃代码还在潜伏或者调用逻辑还不优雅". Ran `vulture` + `ruff` + manual grep for legacy patterns. Tools came back clean (0 vulture / 0 ruff F401/F841/F811), but manual audit found multiple categories of issues.

### Dead code — comments said "removed in v0.6.0" but were still alive

- `KARMA_RULE_SKILL_SRC` in `cli.py` — v0.5.x deprecated alias, comment self-said "removed in v0.6.0" but never deleted. 0 external usage
- `_claude_skills_dir()` in `cli.py` — docstring self-said "v0.5.16 deprecated, removed in v0.6.0" but kept. 0 external usage
- `_install_karma_rule_skill()` in `cli.py` — same self-said v0.6.0 removal, 0 callers

### Naming consistency — v0.6.0 BREAKING left `sticky` shrapnel

The sticky → rule rename in v0.5.0 + v0.6.0 BREAKING focused on the public API surface. Internal names and user-facing output strings were partially left in `sticky` naming, creating user-visible inconsistency:

- **Functions**: `cmd_sticky_list` / `cmd_sticky_edit` / `cmd_sticky_remove` → `cmd_rule_*` (renamed; tests synced)
- **Module-level constant**: `STICKY_PATH` (alias of `karma.rule.DEFAULT_PATH`) → `RULES_PATH`. Used in 10 cli.py + 8 test_cli.py places
- **`karma doctor` output**: `"sticky.yaml: <path>"` was printing the path to `rules.yaml` — name and content disagreed. Now prints `"rules.yaml: <path>"`. Also `"sticky 加载: ✓"` → `"规则加载: ✓"`
- **`karma audit` output**: column header `'sticky_id'` → `'rule_id'`; "未触发的 sticky" section title → "未触发的规则"
- **`karma violations clear` output**: filter description `"sticky={id}"` → `"rule={id}"` (CLI flag `--sticky` kept for backward compat per past deprecation discipline)
- **`karma rule list` output**: `"karma sticky (N/M)"` → `"karma 规则 (N/M)"`; local var `sticky = load()` → `rules = load()`
- **Hook stderr output**: `pre_compact.py` / `session_start.py` / `subagent_start.py` all printed `"sticky 加载失败"` on errors → now `"规则加载失败"`; local variable `sticky_list` → `rule_list`
- **`cli.py` top docstring**: removed obsolete `karma sticky <...>` entry (the command's hint logic at L1252 still handles the legacy invocation)

### Real bug found during audit

`cli.py:853` in `cmd_violations_clear` was reading `d.get("sticky_id")` directly when matching the `--sticky` filter — bypassing the v0.5.0+ rule_id/sticky_id compatibility shim. Result: filtering by rule_id wouldn't match newer violation entries that use `rule_id` instead of `sticky_id`. Fixed by using the `extract_rule_id(d)` helper (also exposed as public — was `_extract_rule_id` private with multiple module-internal callers).

### i18n consistency follow-up

v0.8.0 externalized `_WEAK_CLAIM_RE` to `data/signals/weak_claims/` but missed `_COMPLETION_RE` (the parallel phrase set for completion claims like "done / fixed / 完成了 / 搞定"). v0.8.2 closes this gap:

- New `data/signals/completion_words/{zh,en}.txt`
- `evidence.py:_COMPLETION_RE` now uses `compile_alternation("completion_words")`
- English completion words covered: `done / fixed / all set / shipped / tests pass / build green / working now / ...`

Now **7 of 7 detection signals fully i18n-externalized** (was 6 in v0.8.1):

| Signal | Format | Languages |
|---|---|---|
| `user_stop_hints` | `.txt` | zh, en |
| `agent_saturation` | `.txt` | zh, en |
| `stop_hints` | `.txt` | zh, en |
| `explicit_handoff` | `.txt` | zh, en |
| `weak_claims` | `.txt` | zh, en |
| `completion_words` (v0.8.2) | `.txt` | zh, en |
| `push_signals` | `.yaml` (Cartesian) | zh, en |

### Verification

- 3 new tests for `completion_words` signal + integration with `evidence` check
- Total: 455/455 passing (was 452 in v0.8.1)
- `ruff` clean, `vulture --min-confidence 70` finds 0 dead code

### Why this matters

`karma audit` and `karma doctor` outputs are what new users see first when something looks off. Mixed `sticky` / `rule` naming there signals "this project hasn't kept up with itself" — exactly the impression rule 9 doc-sync discipline is meant to prevent. v0.8.2 makes the user-facing output consistent with the v0.6.0 BREAKING reality.

## [0.8.1] — 2026-05-15 (feat — `push_signals` i18n via YAML DSL: cartesian templates + word vocabularies, English Agent push phrases now recognized)

### What was left over from v0.8.0

v0.8.0 externalized 5 detection regexes to `data/signals/<name>/{zh,en}.txt`, but deliberately deferred `_PUSH_SIGNAL_RE` because its Cartesian structure (`我(现在|立刻|马上)\s*(做|改|加)…`) didn't fit flat phrase lists. English Agents saying "I'll start fixing" / "Let me proceed" / "Moving on to" were still hitting `keep_pushing` defaults.

### Solution — YAML DSL: templates + word lists + flat phrases

```yaml
# data/signals/push_signals/zh.yaml
templates:
  - "{subject}\\s*{verb}"      # 占位符 cartesian 模板
subjects: [我, 我现在, 我立刻, 我马上, 我继续, ...]
verbs: [做, 改, 加, 修, 跑, 开始, 实施, ...]
phrases: [继续推进, 下一推进点, 接下来打算, ...]   # 不需 cartesian 的整句
```

`karma/signals.py` 加 `load_patterns()` + `_expand_yaml_signals()`：扫 yaml templates × Cartesian 词集 + phrases，合并进 `compile_alternation()` 输出的单 regex。

DSL niceties:
- Template placeholders use singular (`{subject}`) for natural reading; YAML field names use plural (`subjects:`) — loader auto-resolves singular → plural
- `.yaml` patterns kept as **raw regex** (templates can contain `\s+` etc.); `.txt` phrases get `re.escape`
- Mixed format support: a signal directory can have both `.txt` and `.yaml`, `compile_alternation` unions them

### English push signal coverage

| Pattern | Examples (now recognized) |
|---|---|
| `{subject}\s+{verb}` | I'll fix / Next I'll start / Let me proceed / I am going to commit / Continuing to work on |
| `phrases` | keep pushing / moving on to / on to the next / next step is / picking this up / heading to |

Total expansion: **1106 phrases** (Chinese cartesian + English cartesian + non-cartesian phrases combined). Adding a new verb to the `verbs` list automatically combines with all `subjects` — no manual permutation.

### Tail-filter offloaded to `check()`

The historical `(?!\s*[吧行])` negative-lookahead (v0.4.22 — exclude "下次接手吧" type pushback) was moved out of the regex into `check()` post-processing as `_PUSHBACK_TAIL_RE`. YAML stays simple; check function does the last-mile filtering.

### Tests

- 6 new `test_signals.py` unit tests (cartesian expansion / singular→plural resolution / mixed .txt + .yaml union / >500 expanded phrases)
- 2 new English push tests in `test_keep_pushing.py`
- **452/452 passing**, `ruff` clean

### What's complete now

All 6 detection signals are i18n-externalized:

| Signal | Format | Languages shipped |
|---|---|---|
| `user_stop_hints` | `.txt` | zh, en |
| `agent_saturation` | `.txt` | zh, en |
| `stop_hints` | `.txt` | zh, en |
| `explicit_handoff` | `.txt` | zh, en |
| `weak_claims` | `.txt` | zh, en |
| `push_signals` | `.yaml` | zh, en |

Adding a new language (Japanese, Korean, German, etc.) means writing 6 small files. Zero Python code change.

## [0.8.0] — 2026-05-15 (feat — i18n signals: detection phrases externalized, English users now fully covered, new languages contributable as a `.txt` file)

### Why this matters

Before v0.8.0, karma's detection regexes (`_USER_STOP_HINT_RE` / `_AGENT_SATURATION_RE` / `_STOP_HINT_RE` / `_EXPLICIT_USER_HANDOFF_RE` / `_WEAK_CLAIM_RE`) were Chinese-hardcoded in Python source. English users could install karma but the `keep_pushing` reflection nudge fired false-positive often — the Agent's "Next I'll proceed to X" wasn't recognized, the user's "looks good / LGTM" didn't exempt, and `evidence` missed "should work / probably fine" weak claims.

User asked the right question: **是不是工程模块全英文就行，反正 LLM 能看懂，人类也不看工程模块** (can't the engineering modules just be English-only?). Mostly yes for *karma's own source code*, but the **regex literals themselves** match user / Agent dialogue, which is whatever language the user actually speaks. So the elegant fix is: separate signal phrases from code entirely, into language-tagged data files.

### Architecture — phrases as data, code as loader

```
data/signals/
├── user_stop_hints/
│   ├── zh.txt    # 不错不错, 休息吧, 挺稳定, ...
│   └── en.txt    # looks good, LGTM, never mind, ...
├── agent_saturation/{zh,en}.txt
├── stop_hints/{zh,en}.txt
├── explicit_handoff/{zh,en}.txt
└── weak_claims/{zh,en}.txt
```

- One phrase per line, `#` comments + blank lines skipped
- `karma/signals.py` loads all language files in a signal directory, dedupes, unions, and compiles to a single regex (long phrases prioritized to avoid `OK` swallowing `OK 了`)
- Character sets across languages don't overlap (Chinese vs Latin vs kana vs hangul) → no cross-language false matches
- LRU-cached; phrase files are read once per process

### Adding a new language = 0 Python code

A native speaker of Japanese / Korean / Russian / German / etc. can contribute a single `data/signals/<signal>/xx.txt` per signal directory. karma picks it up on next startup. No regex composition skill required — just write the phrases users would actually say.

### English coverage for existing signals

| Signal | Chinese examples | English examples (new) |
|---|---|---|
| `user_stop_hints` | 不错不错, 休息吧, LGTM, ok 了 | looks good, LGTM, never mind, call it a day, all set, sounds good, ship it |
| `agent_saturation` | 任务饱和, 卡在这一步, 明天接力 | I'm saturated, stuck at, will pick this up tomorrow |
| `stop_hints` | 先到这, 告一段落, 改不动了 | calling it here, that's all for today, can't fix this |
| `explicit_handoff` | 请决定, 等你授权 | please decide, your call here, waiting for your decision |
| `weak_claims` | 应该可以, 大概率, 我猜 | should work, probably fine, might work, seems to work |

### What's NOT in v0.8.0 (deferred to v0.8.1)

- `_PUSH_SIGNAL_RE` is a structured Cartesian pattern (`我(现在|立刻)\s*(做|改|加)…`) that doesn't map cleanly to a flat phrase list. v0.8.1 will redesign the push-signal layer (likely a small DSL or hybrid). For now English Agents' "Next I'll…" / "Moving on to…" still hit `keep_pushing` defaults, but as long as the user's stop signal works (v0.8.0 covers it), the impact is bounded.

### Tests

- 13 new unit tests in `tests/test_signals.py` (loader correctness, long-phrase priority, comment skipping, language non-overlap, cache invalidation)
- 4 new English-coverage tests in `tests/test_keep_pushing.py` + `tests/test_checks.py` (English users get same protection as Chinese users)
- **444/444 passing**, `ruff` clean

### Real karma value

karma's "永不依赖 LLM" boundary stands stronger here — i18n is achievable with pure data files + regex, no LLM in the loop. The same principle that makes karma fast (< 60ms) is what makes it locale-extensible at zero cognitive cost.

## [0.7.4] — 2026-05-15 (fix — `keep_pushing` user-stop hint covers "satisfied / confirmation" phrases, not only "tired / dismissive")

### Real-user dogfood trigger

After shipping v0.7.3, user said: **"感觉已经挺稳定了，不错不错。"** (Feels stable now, nice nice.) — clearly a stop signal expressing satisfaction. The keep_pushing reflection hook still fired (reminder 1/2), because the existing `_USER_STOP_HINT_RE` only covered the "tired / dismissive" category (`休息吧 / 算了 / 够了 / 明天再说`), not the "satisfied / confirmation" category that users naturally use when a sustained push wave reaches a good stopping point.

Per rule #7 (treat root cause when karma fires false-positive): the trigger fired correctly *given the regex*, but the regex was missing a whole semantic class of user-stop signals.

### Fix — extend `_USER_STOP_HINT_RE` with satisfied-confirmation phrases

Added second category of stop hints to `karma/checks/keep_pushing.py`:

| Category | Existing (v0.4.41) | Added (v0.7.4) |
|---|---|---|
| Tired / dismissive | `不用了 / 休息吧 / 明天再说 / 算了 / 够了 / 到此为止 / 晚安 / 走火入魔` | — |
| Satisfied / confirmation | — | `不错不错 / 挺不错 / 挺稳定 / 稳定了 / 挺好的 / 就这样吧 / 这就行 / 可以了 / 没问题了 / 搞定了 / 看着不错 / OK 了` |

Both categories now exempt the reflection hook for the whole turn — matching the intent of rule #8's "user explicit stop signal" exception.

### Tests

Extended `test_v0441_user_stop_hint_exempts_keep_pushing` with 7 new satisfied-confirmation fixtures (including the literal user phrase that triggered this release). All 427 tests pass.

### Why this matters

karma's whole reason for the user-stop exemption is to **not be in the way when the user is done**. Missing the "satisfied" case meant the hook nagged the Agent to keep pushing past a stopping point the user had already declared — exactly the kind of nag karma is supposed to *prevent*, not generate.

This is also why pure-engineering regex matters: the moment the user said "挺稳定了", we caught the false-positive within one turn, identified the gap, extended the pattern, and shipped a release with tests. No LLM in the loop — just `re.compile` + a new bullet in the OR clause.

## [0.7.3] — 2026-05-15 (docs — hand-audit every GitHub-visible doc: marketing fluff → natural, stale commands → current, missing status → labeled archive)

### Why a whole-repo doc audit

User directive: "GitHub 所有文件加起来也没多少字，你手工再检查下吧，别走批处理替换了，一个一个文档检查梳理一下，要求对外展示的文档抓人眼球有爆款潜质，所有文档表达自然、逻辑严密流畅、可读性强不做作。" Followed by: "「真」字大爆发之外还有哪些欠妥当的表述问题，都完整检查和修复一下。"

Per-file audit, not batch replacement. The "真X" problem from v0.7.0–v0.7.2 was the obvious trigger; this release goes after the broader category: marketing fluff in landing copy, "≈ 0%" overclaims, stale `sticky` command names that survived v0.6.0, milestone tags that froze at M3 / v0.5.x while the project is at v0.7, missing archive labels on shipped plan docs.

### What changed (33 markdown files reviewed; 22 touched)

**Tier 1 — landing pages (`README.md` / `README.zh.md`)**:
- Replaced "Measured violation rate ≈ 0%" overclaim with honest "the single change that moves the needle most"
- Cut "500+ hours real-world tuning" / "5481 lines" marketing-precise numbers; replaced with verifiable quality gates (427 tests / `ruff` / `mypy` / dead-code, all green)
- Reframed v0.6.0 BREAKING banner from "top-of-page warning" to "older-versions footnote" — banner-as-warning misled new users; the BREAKING was 3 weeks ago and is mechanical to migrate
- Tightened pain-point table phrasing; switched section headers from "全面监管" to "全覆盖" (less salesy)
- Removed the dead "Full English translation lands in v0.5.3" promise (over 18 releases ago)

**Tier 2 — project contracts (`CLAUDE.md/.zh.md`, `CODE_OF_CONDUCT.md/.zh.md`, `SECURITY.md/.zh.md`)**:
- Dropped the dead M0 milestone block and the obsolete "Strict LLM authorization v1+" section (karma is firmly no-LLM, not "v0 no LLM")
- Renamed the doc heading from "karma v2" to "karma" — v2 framing was internal to v1 archival, no longer relevant
- Replaced the "stay under ~200 lines" rule with "small by default, larger batches OK when user explicitly asks one commit" — matches the v0.7.0 651-line user-authorized batch precedent
- `SECURITY.md` reporting line: removed the "look up author email via gh" instruction, pointed directly at GitHub private Security Advisory

**Tier 3 — CHANGELOG**: only added this entry; historical release notes are archive (per user rule-5: no retroactive rewrites)

**Tier 4 — architecture / handoff / hook guides**:
- `PRD.md/.zh.md`: removed obsolete "Future possibilities: LLM-judged check upgrade" — directly contradicts the firm no-LLM boundary
- `PRD.md/.zh.md`: corrected hard-cap from "14 attention inflection point" to "12" (matches `rule.py:HARD_MAX` and Mnilax's empirical study)
- `ARCHITECTURE.zh.md`: full sweep of `sticky.yaml` → `rules.yaml` and `karma sticky list/edit/remove` → `karma rule …` (these survived v0.6.0); injection header text updated to current "[karma — 你跟用户的长期默契]" collaborative-agreement tone; performance figure < 50ms → < 60ms (matches measurements)
- `ARCHITECTURE.md/.zh.md` titles: dropped frozen "(M3 current state)" tag
- `HANDOFF.md`: rewrote the milestone status section as "Recent milestones (latest first)" with v0.7.2 head; fixed broken `./HOWTO.md` link to `./HANDOFF.md`; removed the obsolete "post-v0.5.3 bilingual handoff" plan
- `HANDOFF.zh.md`: same rename — title from "M3 六波结束" to "karma 内部接力文档"; current-version line updated to v0.7.2
- `HOOK_CONFIGURATION_GUIDE.md`: full rewrite. Corrected hook count from 9 to actual 8 (the old guide listed a non-existent `PostCompact`); switched all `sticky.yaml` references to `rules.yaml`; updated scenarios to match how Stop / SubagentStart / PreCompact + SessionStart actually work in v0.7
- `HOOK_PROTOCOL_RESEARCH.md`: added archive header — research dated 2026-05-14, conclusions already landed; clarified that `ARCHITECTURE.zh.md` is the current source of truth

**Tier 5 — historical plan docs**: confirmed `RULES_REDESIGN_PROPOSAL`, `V0_6_0_PLAN`, `REFACTOR_PLAN_RULE_AND_I18N` all have "shipped" / "implemented" status banners (added to English `REFACTOR_PLAN` where missing)

**Tier 6 — operational templates**:
- `.github/PULL_REQUEST_TEMPLATE.md/.zh.md`: replaced the rigid "under ~200 lines" checklist item with "small by default, larger batches OK when explicitly asked" — matches CLAUDE.md
- `.github/ISSUE_TEMPLATE/feature_request.zh.md`: `sticky.yaml` → `rules.yaml`
- `karma/backends/HOWTO.md/.zh.md`: replaced internal `[karma rule #1 long-term fundamental]` cross-references with natural prose pointing to rule slugs
- `CODE_OF_CONDUCT.md`: fixed broken `./README.en.md` link to `./README.md`

### What did NOT happen (correctness restraint)

- **No batch find/replace.** Per user directive, every file was hand-read. Several places intentionally kept the modifier when context required it (e.g., `真阻塞` / `真阳` engineering dualism in `ARCHITECTURE` and tests)
- **No retroactive CHANGELOG / HANDOFF history rewrites.** Per project rule 5 (eval cleanliness), historical entries stay as-shipped; only headers / current-status sections updated
- **No SKILL.md churn.** The skill content is consumed by Agents, not landing-page readers; it was already clear and on-tone

### Verification

- `pytest`: 427/427 passing (no code changed)
- `ruff`: 0 issues
- 22 files changed, 447 / 510 lines (net −63)

### Real karma value

This release is a "rule 9 (docs-sync-after-commit)" catch-up — a careful pass at the level of "would a first-time karma reader feel this is a viral-quality project or a fragmentary one?" Marketing fluff and stale commands both signal sloppiness; removing them makes the project read as more honest, not less impressive.

## [0.7.2] — 2026-05-15 (refactor — remove `chinese_plain` Check 3 reactive monitor: source treated, symptom monitor obsolete)

### Root cause

`chinese_plain.py` Check 3 (`_check_repeated_prefix`) was added in v0.4.40 as **reactive treat-symptom monitoring** for the "真字狂魔" side effect — its own code comment said: *"治症状不治根因，但能减弱视觉别扭程度"* (treats symptom not root cause, but reduces visual awkwardness).

After v0.7.0 + v0.7.1 treated the source (rewrote ~640 mimicry occurrences across rule templates + locale + docs), `karma audit` data confirmed Check 3 has **0 triggers** in 168 total violations across the session. The mimicry source is gone; the reactive monitor is obsolete.

This is the same logic the user applied to `defensive_prefix_stacking` in v0.7.0: **"这显然是你对 karma 的应激反应，咱们要治根不要治表"** (this is clearly your reactive response to karma — treat the root, not the symptom). v0.7.0 reverted that check before adding it; v0.7.2 removes the parallel Check 3 that snuck in three months earlier.

### Removed

- `karma/checks/chinese_plain.py`: `_check_repeated_prefix()` function + `_PREFIX_REPEAT_THRESHOLD` constant + Check 3 invocation in `check()` (~45 lines)
- `data/locales/zh.yaml`: `check.chinese_plain.repeated_prefix.trigger` + `check.chinese_plain.repeated_prefix.fix` keys
- `tests/test_checks.py`: `test_v0440_repeated_prefix_check_catches_zhen_zi_kuangmo` + `test_v0440_repeated_common_word_not_triggered` (2 tests, both Check 3-specific)

### Verification

- `pytest`: 427/427 passing (was 429 — 2 tests removed match the 2 deletions)
- `ruff`: 0 issues
- `karma audit` chinese-plain breakdown: Check 1 (中文占比) + Check 2 (jargon) still cover all real cases; no Check 3 触发 lost

### Why this matters

karma's core philosophy is **treat root not symptom**. Reactive monitors accumulate as "we'll deal with it engineering-side" hedges, then linger after the root cause is fixed. v0.7.2 closes the loop on v0.7.0's user directive: now that source rewrite is done, the reactive monitor it was hedging against can also go.

## [0.7.1] — 2026-05-15 (refactor — deeper "真X" cleanup: drop unnecessary modifier synonyms across full repo)

### Root cause user identified (v0.7.0 follow-up)

After v0.7.0 mass-replaced ~140 occurrences in rule templates + locale + user-facing docs, user spotted two remaining issues:

1. **`任务任务到饱和` doubled artifact** — v0.7.0 perl script `s/真饱和/任务到饱和/g` ran on input already containing `任务真饱和`, creating doubled prefix.
2. **Synonym substitution wasn't enough** — user reviewed v0.7.0 diff and noted: "大量真换成了实际和确实等同义词，但问题是大部分地方这个同义词也没必要存在吧😓". The defensive modifier itself (whether 真 or 实际 or 确实) is unnecessary in most contexts. Removing the modifier entirely reads more natural than synonym swap.

User's directive: **"一次性修复完再提交吧"** + **"注释里的和其他位置的也都调整，别留负债"** — one batched commit covering source code comments, tests, historical archives, no partial cleanup.

### Fix — 10-phase perl pipeline across 100 tracked files

Sequential cleanup waves (`/tmp/zhen_replace[1-10].pl`) targeting different mimicry patterns:

- Phase 1-2 (carried from v0.7.0): rule templates + locale + user-facing docs
- Phase 3-4: 实际 X → X (drop modifier entirely where natural), source code comments, test files, historical CHANGELOG / HANDOFF entries
- Phase 5: doubled artifacts cleanup (`任务任务到饱和` → `任务饱和`, `实际实际` → `实际`)
- Phase 6: 真实 X → X / 实际 (94 rebound from phase 5's `s/实际/真实/g` misstep — corrected)
- Phase 7: 真工作 / 真装 / 真反喂 / 真反映 → natural alternatives
- Phase 8: karma rule source files + check comments (in-context mimicry origin layer)
- Phase 9-10: scattered residuals

### Result

767 occurrences of `真X` → 120, an 84% reduction. Remaining 120 are all legitimate retentions:

| Pattern | Count | Reason kept |
|---|---|---|
| 真字 (狂魔/癫狂) | 23 | named concept (the side-effect we documented) |
| 真阳 / 假阳 | 10 | eval terminology (true-positive vs false-positive) |
| 真人 | 6 | "用户是真人" empathy framing for Agent |
| 真的 | 6 | natural Mandarin adverb |
| 真阻塞 / 真展开 / 真黑名单 | 12 | engineering semantic dualism (`vs` 假/字面) |
| 真话 / 真心 | 7 | natural Chinese collocations |
| 真地 / 真正 | 6 | adverbial forms (`认真地` etc.) |
| test_checks fixture (`真完整 / 真效果`) | 4 | chinese-plain check 3 fixture must contain mimicry |
| 真硬编码 / 真调 / 真节流 / 真重置 | 8 | test logic naming for `vs` 假/dry-run |

### Files touched

62 files modified, 651 / 651 lines (exactly token-neutral). Coverage:

- All `karma/**/*.py` source code comments (previously deferred in v0.7.0)
- All `tests/**/*.py` test code + fixtures (preserving check-3 mimicry fixture)
- Historical archives: `CHANGELOG.zh.md`, `docs/HANDOFF.zh.md`, `docs/RULES_REDESIGN_PROPOSAL.zh.md`
- All `.github/*.zh.md` issue/PR templates
- `karma/backends/HOWTO.zh.md`, `data/rules.dev.minimal.example.zh.yaml`

### Verification

- `pytest`: 429/429 passing (test fixture preserved — check 3 still detects synthetic mimicry)
- `ruff`: 0 issues
- Doubled-artifact regression test: `grep -E "(任务任务|实际实际|真实真实|真真|装上实测)" $(git ls-files)` returns 0 hits
- Source rule file mimicry source: 0 `真X` prefixes in `data/rules.dev.example.zh.yaml` and `data/rules.dev.minimal.example.zh.yaml`

### Real karma value

User's "同义词也没必要存在" insight is sharper than v0.7.0's substitution approach. v0.7.0 assumed the problem was the specific word "真"; this release confirms the problem is the **defensive modifier itself** — whether 真/实际/真正/确实, all signal Agent over-asserting evidence rather than just stating. Drop the modifier, let nouns speak directly.

This is sticky #4 ("loud failure with evidence") at the language layer: real evidence > stacked modifiers asserting evidence.

## [0.7.0] — 2026-05-15 (refactor — treat root cause: rewrite "真X" defensive prefixes in karma source rule texts)

### Root cause user identified

User caught a real architectural failure mode: I (the Agent under karma) was repeatedly stacking "真X" prefixes ("原因 / 违反 / 任务饱和 / 实测") as defensive-evidence language. User's diagnosis was sharp — adding a `defensive_prefix_stacking` check function would have been **treating the symptom** while leaving the **source of the mimicry** untouched.

The source: karma's own rule texts and locale strings used "真X" patterns throughout (e.g. `rules.dev.example.zh.yaml` line "想清楚是违反 / 修原因", `data/locales/zh.yaml` reflection prompts mentioned "任务饱和"). LLMs read the karma headers every turn and copied the prefix style in their responses — in-context mimicry of the rule text itself.

### Fix — multi-diversified rewrite of "真X" prefixes

Replaced ~140 occurrences across user-facing docs and templates with diversified natural expressions (avoiding new single-prefix mimicry pattern):

| Before | After |
|---|---|
| 原因 | 原因 |
| 违反 | 违反 |
| 任务饱和 | 任务饱和 |
| 实测 | 实测 |
| 用户 | 用户 |
| 完成 | 完成 |
| 触发 | 触发 |
| 生效 | 生效 |
| 证据 | 证据 |
| 复现 | 复现 |
| 识别 | 识别 |
| 匹配 | 匹配 |
| 豁免 | 豁免 |
| 闭环 | 闭环 |
| 深挖 | 深挖 |
| 痛点 | 痛点 |
| 做 | 做 |
| 继续推 | 继续推 |
| ... | ... (30+ diversified substitutions) |

**Preserved as natural Chinese expressions** (NOT mimicry): `实际 / 真心 / 真人 / 技术专名 / 不确定 / 认读 / 踩到` — these are adjective/adverb modifiers in natural collocations, removing them would harm readability.

### Files touched

- Rule templates: `data/rules.dev.example.zh.yaml`, `data/rules.dev.minimal.example.zh.yaml`
- i18n locale: `data/locales/zh.yaml` (hook injection strings, reflection prompts, suggested_fix texts)
- User-facing docs (Chinese): `README.zh.md`, `CLAUDE.zh.md`, `SECURITY.zh.md`, `CODE_OF_CONDUCT.zh.md`
- Internal docs (Chinese): `docs/PRD.zh.md`, `docs/ARCHITECTURE.zh.md`, `docs/V0_6_0_PLAN.zh.md`, `docs/REFACTOR_PLAN_RULE_AND_I18N.zh.md`, `docs/RULES_REDESIGN_PROPOSAL.zh.md`, `karma/backends/HOWTO.zh.md`

### What did NOT happen (correctness restraint)

- **Did not add `defensive_prefix_stacking` engine-layer check** — initially started but reverted after user pointed out it's a treat-symptom reaction. The reactive monitor would have caught Agent symptoms while leaving the karma-itself-induced mimicry source intact. Correct fix is at the source text level.
- **Did not touch `karma/*.py` source code comments** (~200 occurrences) — these don't enter Agent prompt context, so they don't drive mimicry. Lower-priority cleanup deferred to v0.7.1+.
- **Did not touch CHANGELOG / HANDOFF historical entries** — rule 5 (eval cleanliness) applies metaphorically: historical archive entries shouldn't be rewritten retroactively.

### Verification

- `pytest`: 429/429 passing (no code change to test logic — pure text content of templates / docs)
- `ruff`: 0 issues
- Mimicry source reduction: rule text + i18n + user-facing docs total "真X" mimicry-style prefixes from ~140 → ~60 (natural language modifiers, not mimicry)

### Real karma value

User identified this as a **原因 vs 真表征** distinction (... using the exact pattern karma was inducing — confirming the source is the rule text itself, not the Agent's instinct). The fact that even a careful Agent under heavy rule context drifts toward "真X" style speaks to how strong in-context mimicry is from rule text → response text. Cleaning the source is the only durable fix.

## [0.6.1] — 2026-05-15 (fix — `record_edit` exempts non-code paths; first real-user bug from issue #1)

### Real-user bug fix — docker pytest + edit README + git commit no longer blocked

**Bug** (issue #1, real user `@fyn1320068837-source`): `docker exec <container> python -m pytest tests/` passes (e.g. 1190 passed) → user edits any file (even README.md / .gitignore / IDE auto-save) → `git commit` blocked by `loud-failure-with-evidence` with "no recent passing-test evidence."

**Root cause** (real-test reproduced): `has_recent_test_pass()` returns `last_test_pass_ts >= last_edit_ts`. Any `record_edit()` call pushes `last_edit_ts` to "now," instantly flipping `has_recent_test_pass` to False — including edits to documentation, `.gitignore`, `LICENSE` etc. that have zero impact on whether pytest needs re-running. The by-intent design ("changed code without re-testing → block commit") was over-applied to non-code edits.

The reporter's proposed fix (`_TEST_CMD_RE` adding optional docker prefix) addressed the wrong layer — the regex already matches `docker exec ... pytest` correctly (4-layer end-to-end test confirms). Real fix needed at the `record_edit` time-tracking layer.

### Fix

`karma/session_state.py` adds `_NON_CODE_EDIT_RE` exemption list — `record_edit()` no longer pushes `last_edit_ts` when the file is documentation / metadata / top-level repo text:

- Documentation suffixes: `.md` / `.rst` / `.txt` / `.markdown` / `.adoc`
- Metadata files: `.gitignore` / `.gitattributes` / `.editorconfig`
- Top-level path patterns: `docs/` / `.github/` directories; root-level `CHANGELOG` / `README` / `LICENSE` / `CONTRIBUTING` / `CODE_OF_CONDUCT` / `SECURITY` / `HANDOFF` (with any extension)

**Still invalidates** (by-intent preserved):
- `src/**/*.py` / business code → must re-run pytest before commit
- `tests/**/*.py` / test files → changed tests means tests haven't run on the new versions
- `*.yaml` / `*.toml` / production config / build files → re-test before commit

### Verification

- 6 new regression tests in `tests/test_session_state.py` (`test_v061_*`):
  - 4 exemption cases: README.md / CHANGELOG.md / docs/*.md / .gitignore all keep `has_recent_test_pass = True` after edit
  - 2 dual-control cases: src/*.py and tests/*.py still flip to False (preserve by-intent design)
- `pytest`: 429/429 passing (423 prior + 6 new)
- `ruff`: 0 issues

### Real-user collaboration value

karma's first real outside contributor (`@fyn1320068837-source`) reported a bug they actually hit in their `henghai-backend` workflow — `docker exec container python -m pytest` + edit + commit. Their initial root-cause diagnosis ("regex doesn't match docker prefix") was wrong, but the bug itself was real. End-to-end docker pytest testing on the maintainer's machine reproduced the actual bug in Candidate A scenario (`last_edit_ts > last_test_pass_ts` after non-code edit). v0.6.1 fixes the real root cause at the right layer.

Issue #1 closed by this release — full thread documents the real-user collaboration → real-test → real-root-cause arc.

## [0.6.0] — 2026-05-15 ⚠️ BREAKING — Remove backward-compat scaffolding for `sticky` → `rule` rename

### What's removed (breaking)

- **`karma.sticky` module** — `from karma.sticky import ...` now raises `ModuleNotFoundError`. Migration: `from karma.rule import ...` (identical exports).
- **`Violation.sticky_id` @property** — `violation.sticky_id` raises `AttributeError`. Migration: use `.rule_id`.
- **`CheckHit.sticky_id` @property** — `hit.sticky_id` raises `AttributeError`. Migration: use `.rule_id`.
- **`karma sticky <subcommand>` CLI** — exits 1 with hint: `💡 你是不是想用 karma rule？`. Migration: use `karma rule list / edit / remove / add / preview`.
- **`karma.rule` aliases** — `Sticky`, `MAX_STICKY`, `StickyConfigError` removed. Migration: `Rule`, `MAX_RULES`, `RuleConfigError`.
- **`karma.cli` aliases** — `EXAMPLE_STICKY`, `EXAMPLE_STICKY_MINIMAL` removed (internal symbols, unlikely to affect users).

### What stays (data-compat preserved forever)

These are not deprecation aliases — they handle real on-disk user data and stay in karma indefinitely:

- **`sticky.yaml` → `rules.yaml` auto-migration** in `karma init` — users upgrading from v0.4.x still have `sticky.yaml`; karma silently moves it to `rules.yaml` with `.bak` backup.
- **`violations.jsonl` `sticky_id` field fallback** — historical jsonl rows from v0.4.x have `sticky_id` instead of `rule_id`; `karma audit` / `stats` still read them correctly via `_extract_rule_id`.
- **`STICKY_PATH` internal constant** in `karma.cli` — backward-compat path alias to `rule.DEFAULT_PATH`. Used by tests; no migration required.

### Why this release

v0.5.0 (2026-05-15 earlier today) renamed `sticky` → `rule` codebase-wide and shipped backward-compat aliases so user scripts wouldn't break immediately. The deprecation warning ran for one full release cycle (v0.5.x: 18 releases). v0.6.0 cliff arrives per the plan in [`docs/V0_6_0_PLAN.md`](./docs/V0_6_0_PLAN.md).

Internal karma code stopped using the aliases entirely in v0.5.13 (`.sticky_id` attribute access) and v0.5.15 (`from karma.sticky` imports). v0.6.0 is a **pure deletion commit** — no refactor logic, just removal.

### Migration cookbook for external users

Most user scripts using karma are 1-line mechanical fixes:

```python
# Before (any v0.5.x — warned)
from karma.sticky import Sticky, MAX_STICKY, StickyConfigError
violation.sticky_id  # works with warning

# After (v0.6.0+)
from karma.rule import Rule, MAX_RULES, RuleConfigError
violation.rule_id  # required
```

```bash
# Before
karma sticky list

# After
karma rule list
```

### Verification

- 5 new deletion-lock tests in `tests/test_sticky.py` (`test_v0600_*`):
  - `import karma.sticky` raises `ModuleNotFoundError` ✓
  - `Violation.sticky_id` raises `AttributeError` ✓
  - `CheckHit.sticky_id` raises `AttributeError` ✓
  - `karma.rule.Sticky` / `MAX_STICKY` / `StickyConfigError` are `hasattr() == False` ✓
  - `karma sticky list` subprocess exits 1 with `"karma rule"` in stderr ✓
- `pytest`: 423/423 passing (418 prior + 5 new)
- `ruff`: 0 issues
- Cumulative: from this morning's v0.5.0 rename to tonight's v0.6.0 cliff, **20 releases shipped in a single day** — the full sticky → rule rename + 1-cycle deprecation + cliff arc lives in `git log v0.5.0..v0.6.0`.

## [0.5.20] — 2026-05-15 (docs — rule-10 self-audit follow-up: sync ARCHITECTURE + HANDOFF for v0.5.19)

### Why this micro-release

User asked me to self-audit whether the past 4 releases honored rule 10 ("after every commit, sync all affected docs to latest"). The audit found one real omission: **v0.5.19 shipped without updating `docs/ARCHITECTURE.md` milestone table or `docs/HANDOFF.md` current status**. The CHANGELOG had the entry, but the technical-archive docs did not. Rule 10's exception ("internal refactor → only update CHANGELOG + HANDOFF") was misapplied — HANDOFF was specifically called out as still-required.

### What changed

- `docs/ARCHITECTURE.md` + `.zh.md` — milestone table gains v0.5.19 row (saturation exemption rationale + paired-asymmetry note with v0.4.41)
- `docs/HANDOFF.md` — current status section gains v0.5.19 entry (dogfood trigger context: caught by the same Stop hook v0.5.19 was fixing)

### Audit summary (full)

| Rule-10 requirement | v0.5.16–19 result |
|---|---|
| ① after-commit doc audit | ✅ for v0.5.16/17/18; ❌ for v0.5.19 (fixed by this release) |
| ② "feature as subject, version as clause" | ✅ in README hero, `/karma` section, PRD F5; ARCHITECTURE milestone table is patch-style by format (acceptable — milestone tables are chronological by nature) |
| ③ flagship features in README top | ✅ v0.5.16 skill promoted to hero + Real-problems row + new top-level section |
| ④ bilingual `.md` + `.zh.md` sync | ✅ for README/PRD/ARCH/HANDOFF on v0.5.16-18; ❌ for v0.5.19 (fixed) |
| ⑤ internal-refactor exception | ✅ v0.5.18/19 correctly skipped README/PRD (no user-visible CLI change), but HANDOFF was still required and missed for v0.5.19 |

Net: 4/5 honored across the 4 releases. The miss was caught by explicit rule-10 self-audit and fixed within minutes — exactly the dogfood-driven correction loop rule 10 was written to enable.

### Verification

- `pytest`: 418/418 passing (pure docs, no code change)
- `ruff`: 0 issues

## [0.5.18] — 2026-05-15 (fix — `bypass_karma` distinguishes "read karma + write elsewhere" from "write to karma path")

### Root-cause fix triggered by live dogfooding false-positive

While inspecting `karma audit` data for today's violation patterns, ran `grep deep-fix ~/.claude/karma/violations.jsonl > /tmp/df_audit.jsonl` to extract a few rows for analysis — got blocked by `bypass_karma` as "writing to karma internal state." Per rule #7, didn't bypass; root-cause-fixed instead.

**What was wrong**: the old `bypass_karma` rule was `(has_internal OR has_state_path) AND has_write` — any command containing a karma path AND any redirect/write op triggered the rule, even if the redirect target was `/tmp/`. Reading karma state into a tmp file for analysis is a legitimate audit pattern, but the rule conflated "karma path appears in command" with "writing to karma path."

**Fix**: extracted redirect targets via `_BASH_REDIR_TARGET_RE` (already shared in `description_context.py` from v0.5.9), check whether any target matches `_KARMA_STATE_PATH_RE`. The new rule becomes `(has_internal OR has_state_path) AND write_to_karma_state` where `write_to_karma_state = has_python_write OR (any redirect target IS a karma path)`.

**Behavior diff** (verified by 4 new regression tests):

| Command | v0.5.17 | v0.5.18 |
|---|---|---|
| `grep ~/.claude/karma/violations.jsonl > /tmp/x` | ❌ blocked (false positive) | ✓ exempt |
| `cat ~/.claude/karma/violations.jsonl \| python3 -m json.tool > /tmp/pretty.json` | ❌ blocked | ✓ exempt |
| `echo '{}' >> ~/.claude/karma/violations.jsonl` | ✓ blocked | ✓ blocked (real write-to-karma) |
| `python -c "open('.claude/karma/x', 'w').write(...)"` | ✓ blocked | ✓ blocked (python write API) |
| `echo 'last_test_pass_ts=999' > /tmp/inject.txt` | ✓ blocked | ✓ exempt (target is /tmp, not karma) — symmetric with state_path dimension |

The `has_internal` (field-name reference) dimension also tightened symmetrically: writing `last_test_pass_ts=...` to `/tmp/` doesn't affect karma state, so it's now exempted. Writing the same string to `~/.claude/karma/...` is still blocked because the redirect target is a karma path.

### Why this matters

This was karma's own false-positive blocking real audit work — exactly the kind of "karma overcorrects → user forced to bypass" failure mode rule #7 was written to prevent. Caught the trigger, didn't bypass, dug into the regex, fixed the discriminator. Two new test cases lock in both the new exemption (`test_v0518_read_karma_state_write_tmp_exempted`) and the preserved blocking (`test_v0518_redirect_target_is_karma_path_still_blocked`).

### Verification

- 4 new regression tests in `tests/test_bypass_karma.py` covering: read-karma-write-tmp exempted, pipe-to-python exempted, write-to-karma still blocked, internal-field-name + write-to-tmp now exempted (symmetric with state_path fix), internal-field-name + write-to-karma still blocked
- `pytest`: 416/416 passing (411 prior + 5 new — Wait, math: 411 + 4 added but one renamed = net 4 new). Actually 411 → 416 = 5 new. Two were `internal_field_name_*` variants (one expects exempt, one expects blocked); other three: `read_karma_state_write_tmp_exempted`, `cat_karma_pipe_to_python_exempted`, `redirect_target_is_karma_path_still_blocked`.
- `ruff`: 0 issues
- All 4 prior `test_*_real_bypass_*` tests remain green — the fix didn't loosen real-write detection

## [0.5.17] — 2026-05-15 (docs — README narrative rewrite: `/karma <NL>` skill promoted to top-level section, not patch-style mention)

### Why this release

v0.5.16 shipped the working skill but README still treated it as a patch-style mention buried inside the "Customize your own rules" section — the "Agent writes the rule for you" capability was a one-line aside while the "Agent complies with rules" capability owned the entire hero/pitch. This release rewrites README narrative so both sides of karma's loop get equal billing on the landing page, per user principle:

> "对外说明文档一定不要只是打补丁，要很「爆款」的融入整体说明，重要亮点和功能说明展示好。"
> (Don't just patch — fold new capabilities into the overall narrative; flagship features deserve flagship presentation.)

### What changed (README + README.zh.md, symmetric)

**1. Hero opening rewritten** — was a single "monitor Agent" paragraph + violation-rate stat. Now explicitly frames karma as "two sides of the same loop": 🛡️ pin rules / Agent complies + ✨ tell karma in plain words / Agent writes the rule. Both with concrete one-liners.

**2. Table of contents** — adds `/karma natural-language rule input` as a top-level entry alongside install / how-it-works / customize.

**3. Real-problems table** — adds a 7th row covering the actual pain point that v0.5.16 solves ("I want to add a rule but writing yaml is too heavy / my phrasing doesn't make Agent comply"), so the value-prop appears in the same comparative format as the other 6 pains.

**4. Quick install section** — adds a one-line callout that `karma init` auto-installs the skill across all three backends (no extra step), so users know it ships ready-to-use, not as an opt-in upgrade.

**5. New top-level section `/karma <natural language>` — Agent writes the rule for you** — replaces the 20-line "Recommended:" sub-section that v0.5.15 had patched into "Customize." New section is 55+ lines: 7-step workflow visualization, "what the skill handles for you" 6-row table (tone / format / overlap / scope / locale / modify), "three backends, one command" install table, upgrade flow (`karma install-skill --force` / `--backend`).

**6. "Customize your own rules" reduced to a 1-line pointer** — directs users to the new top-level skill section, with a note that the manual-yaml fallback is for advanced users / no-skill environments. The yaml example block remains as fallback reference; the duplicated "Recommended:" content from v0.5.15 is removed (no more redundancy).

### Other docs synced

- **`docs/PRD.md` + `.zh.md` F5** — Rewritten with v0.5.16 multi-backend reality. Old version still claimed "v0.5.1+" availability; new version flags "v0.5.16+ — first release where the skill actually triggers" with the honest history disclosure.
- **`docs/ARCHITECTURE.md` + `.zh.md`** — Milestone table gains v0.5.15 / v0.5.16 / v0.5.17 rows.
- **`docs/HANDOFF.md`** — Current status updated to v0.5.17.

### Verification

- `pytest`: 411/411 passing (pure docs, no code change)
- `ruff`: 0 issues
- Manual sanity: TOC anchor `#karma-natural-language--agent-writes-the-rule-for-you` resolves; sectioning makes sense for a first-time reader landing on the README

### Trigger

This release was triggered by user typing `/karma 每次commit以后必须更新所有 github 文档至最新版本...要很「爆款」的融入整体说明` — the karma skill's first live end-to-end use added rule 10 (`docs-sync-after-commit`), and this commit is the immediate first application of that newly-added rule.

## [0.5.16] — 2026-05-15 (feat — `/karma <natural language>` skill works for real, multi-backend install)

### Why this release is big

Live-session deep audit (driven by user asking "can we simplify `/karma rule X` to just `/karma X`?") surfaced that **karma skill has not actually been triggering since v0.5.1**. Root cause: Claude Code skill mechanism requires `<name>/SKILL.md` directory structure (not flat `<name>.md` file), the `name:` frontmatter field, and a single-token slash command (not multi-word `/karma rule`). v0.5.1 through v0.5.15 all shipped with the wrong assumption — manual CLI testing worked but skill auto-trigger never did.

This release rebuilds skill installation correctly across **3 backends**:

| Backend | Path | Format | Trigger |
|---|---|---|---|
| Claude Code | `~/.claude/skills/karma/SKILL.md` | Markdown + YAML frontmatter | `/karma <args>` |
| Codex CLI | `~/.agents/skills/karma/SKILL.md` (note: `~/.agents/` not `~/.codex/`) | Markdown | `/skills` menu, `$karma <args>` inline, or auto |
| Gemini CLI | `~/.gemini/skills/karma/SKILL.md` + `~/.gemini/commands/karma.toml` (dual-track) | Markdown (skill) + TOML (commands) | auto-trigger via skill, explicit `/karma <args>` via commands |

### What changed

**1. Repository skill source restructured** — `skills/karma-rule.md` (flat file, wrong) → `skills/karma/SKILL.md` (correct directory structure). Added required `name: karma` + `description: ...` frontmatter. Updated all `/karma rule X` references inside the skill body to `/karma X` to match the simplified trigger.

**2. New module `karma/skill_packaging.py`** — handles format conversion:
- `parse_frontmatter(md_text)` — extracts YAML frontmatter without requiring PyYAML dependency
- `markdown_to_toml(md_text)` — converts Markdown skill to Gemini CLI's `commands/*.toml` format (`description = "..."` + `prompt = """..."""`). Auto-translates `$ARGUMENTS` (Claude/Codex) ↔ `{{args}}` (Gemini) so the same skill source works across all three.

**3. `Backend` Protocol extended** with `skill_install_targets(skill_name="karma") -> list[tuple[Path, str]]`. Each backend declares its own install paths + content formats. Three implementations:
- `ClaudeCodeBackend` → 1 target (Markdown)
- `CodexBackend` → 1 target (Markdown, `~/.agents/` path)
- `GeminiCLIBackend` → 2 targets (Markdown skill + TOML commands)

**4. CLI multi-backend support**:
- `_install_karma_skill_multi_backend(force, backend_filter)` — central install function; iterates all detected backends and writes each target with format-appropriate content
- `cmd_install_skill(force, backend)` — `karma install-skill` now installs to all by default; `--backend claude-code|codex|gemini-cli` targets one
- `cmd_init` — auto-installs to all backends, prints `创建 [<backend>] karma skill: <path>` per target
- `cmd_doctor` — reports multi-backend skill status (✓ 最新 / ⚠ 跟当前版本不一致 / 未装), one line per (backend, path) pair

**5. `pyproject.toml`** — `force-include` updated `skills/karma/SKILL.md` so `pip install karma` ships the correct file.

### Live verification (this session)

After installing v0.5.16 on the author's machine, the Claude Code session running this very release surfaced this message in `SessionStart` hook context:

> The following skills are available for use with the Skill tool:
> - **karma**: Natural-language karma rule input — refine user's plain description into karma's validated rule structure, preview, confirm, and add to rules.yaml. Use when the user types `/karma <natural language describing a rule preference>`.

**This is the first time karma skill has actually been seen by Claude Code in any session.** v0.5.1 through v0.5.15 it sat in the wrong path silently.

### Verification

- 7 new regression tests in `tests/test_cli.py` (`test_v0516_*`):
  - 4 backends in init flow / second-run idempotency / user-modified preservation / force-overwrite / `--backend` filter / missing source / doctor multi-backend reporting
- `pytest`: 411/411 passing (404 prior + 7 new)
- `ruff`: 0 issues
- Live install on author's machine: 4 paths verified (Claude/Codex/Gemini-skill/Gemini-toml all present, sizes 16944/16944/16944/16941 bytes — toml slightly smaller from removed frontmatter)

### Migration notes for v0.5.15 → v0.5.16 users

- Old `~/.claude/skills/karma-rule.md` (flat file from v0.5.12-15 install) is dead weight; you can `rm` it
- New skill auto-installs on next `karma init` or `karma install-skill`
- The `/karma rule X` slash command never worked (despite docs saying it did); the new `/karma X` does, in Claude Code at least
- Codex / Gemini support is best-effort — Codex needs `/skills` menu or `$karma` inline; Gemini supports explicit `/karma` via the TOML commands path

### What v0.5.1 to v0.5.15 docs claimed vs. reality (sticky #4 honest disclosure)

The v0.5.1 release notes claimed "Claude Code skill template at `skills/karma-rule.md` for natural-language rule input." It described a `/karma rule <NL>` trigger. **None of that actually worked end-to-end** until this release. Skill flow worked only when the user manually invoked the underlying `karma rule add --from-yaml` CLI — the natural-language → skill auto-refinement path was vapor. Apologies for the misleading docs.

## [0.5.15] — 2026-05-15 (chore — v0.6.0 preparation: draft plan doc + internal `karma.sticky` → `karma.rule` import migration)

### Why this release

v0.5.13 audit ostensibly "cleaned all `.sticky_id` callsites" but only at the attribute level. A follow-up audit while drafting the v0.6.0 plan surfaced a deeper miss: **11 internal `from karma.sticky import ...` statements** still lived in karma's own source code (4 in `cli.py`, 6 in `hooks/*.py`, plus self-references) — plus parallel imports in 4 test files. v0.6.0 cannot safely delete `karma/sticky.py` until karma itself stops importing it. This release fixes that.

### Two things in this release

**1. Draft v0.6.0 plan doc** ([`docs/V0_6_0_PLAN.md`](./docs/V0_6_0_PLAN.md) + [`.zh.md`](./docs/V0_6_0_PLAN.zh.md))

Spelled-out deprecation contract before the cliff. Three categories:

- **Group A** — internal scaffolding (aliases referenced only by karma itself). Zero external impact.
- **Group B** — public API breaking changes (`karma.sticky` module / `.sticky_id` @property / `karma sticky` CLI alias). Each deprecated since v0.5.0; v0.6.0 cliff.
- **Group C** — on-disk data migration (`sticky.yaml` → `rules.yaml`, legacy `violations.jsonl` `sticky_id` field fallback). **Stays forever** — these handle real user data, not API surface.

Includes execution order, test coverage expectations, risk assessment, and 2 open questions (whether `karma sticky` CLI alias deserves an extra release cycle of grace; whether `chinese_plain_no_jargon` default behavior for non-Chinese users is in scope — answered "no" to both, deferred).

**2. Pre-v0.6.0 import migration** (executed this release)

Replaced `from karma.sticky import X` → `from karma.rule import X` across:

- `karma/cli.py` (4 occurrences)
- `karma/hooks/post_tool_use.py`, `karma/hooks/stop.py`, `karma/hooks/pre_tool_use.py`, `karma/hooks/subagent_start.py`, `karma/hooks/user_prompt_submit.py`, `karma/hooks/pre_compact.py`, `karma/hooks/session_start.py` (7 hook files, 7 occurrences total)
- `tests/test_violations.py`, `tests/test_sticky.py`, `tests/test_paths.py`, `tests/test_cli.py`, `tests/test_post_tool_use_reinject.py` (5 test files)
- `mock.patch("karma.sticky.load", ...)` patterns in `test_post_tool_use_reinject.py` → `mock.patch("karma.rule.load", ...)` (4 patches) — Python module aliasing means patching the alias namespace doesn't reach the real module if the consumer imports from the real module directly

### Verification

- `pytest`: 410/410 passing
- `pytest -W error::DeprecationWarning`: 410/410 passing — **zero `karma.sticky` deprecation warnings** triggered from karma's own code or tests
- `ruff`: 0 issues
- `grep -rn "from karma.sticky" karma/ tests/` returns only the `karma/sticky.py` shim's own docstring (the shim's purpose is to be a thing to import; it doesn't import itself)

### v0.6.0 readiness status

After this release, deleting `karma/sticky.py` in v0.6.0 will not break any internal callsite. Same for the 4 class/property aliases (`MAX_STICKY`, `Sticky`, `StickyConfigError`, `EXAMPLE_STICKY*`) — they have zero internal users now. The `.sticky_id` @property on `CheckHit` + `Violation` already had zero internal users since v0.5.13. The `karma sticky <subcommand>` CLI alias has zero internal users (it's an entry-point branch in `cli.py:1183`).

In short: v0.6.0 can ship as a pure deletion commit, no refactor required.

## [0.5.14] — 2026-05-15 (docs — `karma-rule` skill teaches the modify recipe with existing commands, no new CLI added)

### Why this release

Live dogfooding turned up a real gap: when an Agent walks through Step 2 of the skill and the decision table says "modify existing rule," the skill stopped there — `karma rule edit` was mentioned but that command launches `$EDITOR` for the user (not Agent-automatable). The Agent had no clear path to "modify" using the CLI surface it has, which led me (the Agent dogfooding right now) to propose adding a new `karma rule replace` command. User pushed back: don't grow surface area; teach the existing commands clearly.

### What changed

Pure skill documentation — **zero new CLI commands, zero new code**. Closes the modify gap entirely through clearer instructions.

- **New "How to modify an existing rule (replace / merge / extend scope)" section** under Step 2, with:
  - The 3-step recipe (draft yaml → preview → `remove && add` swap)
  - A 4-row "common modify shapes" table (Replace / Extend scope / Merge / Genuine purpose change) clarifying when to keep the `id` (almost always — keeps violation history linked) vs. when to use a new one
  - Explicit "why not `karma rule edit`" callout — it's a user escape hatch, not an Agent path
- **Step 6 expanded** with two branches (new rule vs. modify) showing exact commands
- **Honest atomicity caveat** — clarifies that `remove && add` is *not* a true transaction (if `add` fails after `remove` succeeded, the rule is gone); preview-first reduces but doesn't eliminate the risk; `cp rules.yaml rules.yaml.bak` is the cheap belt-and-suspenders. Original draft incorrectly claimed `&&` "ensured" atomicity — caught and corrected in this same commit (sticky #4: be honest about caveats).

### Why no new CLI command

User principle (from this session): "don't give users a pile of rarely-used skills/commands." Modifying = removing + adding; the existing commands compose. Adding `karma rule replace` would have been surface-area bloat with no real capability gain — the Agent reading the skill just needed the recipe documented.

### Verification

- skill: 269 → 302 lines (+33), 7 `### Step N` headings intact, 10 "modify" / "remove + add" / "How to modify" references in the doc
- `pytest`: 410/410 passing (unchanged — pure docs)
- `ruff`: 0 issues

### Also in this release

- `rule 9 lighthearted-vibe` modified in user's `~/.claude/karma/sticky.yaml` (out-of-tree user data, not in this commit): scope expanded from "during /karma rule conversations" to "整体说话方式", with a stronger dual clause "具体问题分析要认深刻" replacing the milder "该严肃就严肃." This served as the dogfood that exposed the skill gap fixed here.

## [0.5.13] — 2026-05-15 (refactor — audit-driven dedup: shared `is_python_c_command` + sticky_id alias cleanup + doctor skill check)

### What this release closes

An end-of-day code audit surfaced 3 real debts. v0.5.13 pays them off in one clean release.

### F1 — `_LANG_C_HEAD_RE` was copy-pasted across 3 check files

`testset.py` / `bypass_karma.py` / `non_blocking.py` each defined the same regex `r"\b(?:python\d?|node|ruby|perl)\s+-[ce]\b"` independently. v0.5.9 lifted the parallel `_BASH_REDIR_TARGET_RE` into `description_context.py` but missed this one.

**Fix**: Added `is_python_c_command(cmd: str) -> bool` helper in `karma/checks/common.py` (correct home — sits alongside `_SHELL_INTERPRETER_RE`, `_HEREDOC_RE`, and other Bash-parsing utilities). All 3 checks now import and call `is_python_c_command(cmd_raw)` instead of holding their own pattern.

### F2 — `karma doctor` didn't report skill installation status

v0.5.12 added `karma install-skill`, but `cmd_doctor` only reported hook installation, not skill. A user running `karma doctor` after a clean install couldn't see whether `/karma rule <NL>` was actually wired up.

**Fix**: `cmd_doctor` now reports `karma-rule skill` status in three states:
- "存在 ✓ 最新" — installed and content matches the shipped version
- "存在 ⚠ 跟当前 karma 版本不一致" — installed but out of date (suggests `karma install-skill` to upgrade)
- "未装" — missing (suggests `karma install-skill`)

### F3 — 34 `.sticky_id` callsites would have broken at v0.6.0

v0.5.0 announced "sticky → rule renamed across entire codebase" but in practice 34 `.sticky_id` attribute accesses survived in `cli.py` (13), hooks (`pre_tool_use.py`/`stop.py`/`user_prompt_submit.py`: 19), and tests (6). They worked silently via the `@property def sticky_id: return self.rule_id` backward-compat alias on `Violation` and `CheckHit`. When v0.6.0 removes the alias (as documented in the dataclass comments), those call sites would have hard-failed in production code paths far from the test surface.

**Fix**: Batch `s/\b(\w+)\.sticky_id\b/$1.rule_id/g` across the 5 internal files. The `@property` alias stays in `violations.py` and `_types.py` so external user code keeps working until v0.6.0. Pure rename, no behavior change.

### Verification

- 1 new regression test in `tests/test_cli.py` (`test_v0513_doctor_reports_skill_status`) — covers all 3 doctor-skill states
- All 3 fixes coexist with existing tests: 409 → 410 (added one for F2)
- `pytest`: 410/410 passing
- `ruff`: 0 issues

### What the audit verified passed

- Zero TODO/FIXME/HACK residuals in tonight's diff (sticky #1 long-term-fundamental held)
- Zero weak claims ("应该可以"/"大概率") outside `evidence.py`'s detection patterns
- All 5 Bash-aware checks use unified `tool_name == "Bash"` guard
- v0.5.9 refactor cleanup was clean (no stale `_bash_writes_to_description_context` or `_DESC_CTX_PATH_RE` residuals)

## [0.5.12] — 2026-05-15 (feat — `karma init` auto-installs `karma-rule` skill + new `karma install-skill` command)

### feat — `/karma rule <NL>` flow now works out-of-box for new users

v0.5.11 audit surfaced the gap: `skills/karma-rule.md` was in the repo but not auto-installed to `~/.claude/skills/karma-rule.md`, so first-time users typing `/karma rule add a new rule about X` in Claude Code would get nothing — the skill needed manual copy. This release closes the gap.

### Changes

- **`karma init` now auto-installs the skill** at the end of its flow. Path: `~/.claude/skills/karma-rule.md`. First run prints `创建 karma-rule skill: <path>` plus the `/karma rule <NL>` usage tip.
- **New `karma install-skill [--force]` subcommand** for users who installed karma before v0.5.12 (or want to upgrade the skill after a clarity audit like v0.5.11). Without `--force`, conflicts are non-destructive — if the user has a locally-modified `karma-rule.md`, the new version writes to `karma-rule.md.new` and tells the user how to diff/merge. `--force` overwrites.
- **`pyproject.toml` `force-include`** now packages `skills/karma-rule.md` into the wheel so `pip install karma` works.
- **`karma --help`** lists the new `install-skill` subcommand with brief usage.

### Conflict handling (sticky #1: don't overwrite user changes silently)

- File doesn't exist → install, return `(True, "installed")`
- File exists + content identical → skip, return `(False, "up-to-date")`
- File exists + content differs + `force=False` → write `.md.new` sibling, return `(False, "exists-diff")`
- File exists + content differs + `force=True` → overwrite, return `(True, "force-overwritten")`
- Source missing (theoretically impossible in shipped wheel, but possible in dev install edge cases) → return `(False, "source-missing")`, `cmd_install_skill` exits 1, `cmd_init` warns but doesn't block

### Verification

- 5 new regression tests in `tests/test_cli.py`:
  - `test_v0512_init_auto_installs_karma_rule_skill` — first run installs ✓
  - `test_v0512_init_second_run_skill_up_to_date` — idempotent on second run ✓
  - `test_v0512_init_skill_user_modified_writes_new_file` — user changes preserved, `.md.new` written ✓
  - `test_v0512_install_skill_force_overwrites` — `--force` wins ✓
  - `test_v0512_install_skill_handles_missing_source` — graceful `exit 1` when source missing ✓
- `pytest`: 409/409 passing (404 prior + 5 new)
- `ruff`: 0 issues

## [0.5.11] — 2026-05-15 (docs — `skills/karma-rule.md` clarity audit, 5 gaps closed)

### docs — 5 clarity gaps in `/karma rule` skill template closed

Dogfood-driven audit. While walking through the `/karma rule` flow end-to-end (real natural-language input → CLI), 5 places where a first-time Agent could silently make the wrong call surfaced:

1. **Step 1 missed anchor-vs-scope ambiguity** — User phrasing "during scenario X, do Y" usually means "X is an example" not "Y only applies during X," but karma v2 is always-on injection (no scene routing). Skill now requires the Agent to surface this ambiguity verbatim instead of silently guessing scope. Also adds a one-off vs long-term tell list (`"for this PR" → one-off` / `"I always want" → long-term`) so the "is this karma-worthy at all" check is concrete.

2. **Step 2 had no overlap-decision standard** — Skill said "check existing rules" but gave no rule for what counts as overlap (id match? semantic similarity? keyword intersection?). Added a 4-row decision table covering 4 overlap cases with concrete actions (modify existing / two-option ask / mention keyword overlap / add fresh).

3. **Step 3 → Step 5 skipped user inline draft review** — Original flow went straight from "draft to temp file" → preview → user sees finished yaml. Users wanting wording tweaks had to make the Agent restart. Skill now requires showing a draft inline in Step 3 before writing to disk, with explicit "say so now if you want adjustments" callout.

4. **No locale-aware tone guidance** — Post v0.5.2 i18n made karma bilingual, but skill had English-only examples. Added explicit "write `preference` in the language the user is talking to you in; `violation_checks` function names stay English" rule. Points Chinese-locale Agents at `data/rules.dev.example.zh.yaml` as reference pattern source.

5. **Step 7 "when it takes effect" was buried** — Original skill had a standalone `## Restart Claude Code after karma rule add` section at the bottom, easy to miss. Moved the "takes effect on next UserPromptSubmit" notice inline into Step 7 as bullet 4, plus made the "suggest deletions" step concrete (name specific redundant pairs, not vague "review for duplicates"). Removed the standalone section.

3 new entries added to the `## Common mistakes to avoid` list at the bottom mirroring gaps 1, 4, and 3 so a quick scan catches the high-impact failure modes.

### Discovered (but not fixed in v0.5.11)

While auditing, also noticed `skills/karma-rule.md` is **not auto-installed** to `~/.claude/skills/karma-rule.md` by `karma init` — users have to copy it manually. This means today's `/karma rule <NL>` flow only works if the user knows about the manual install step. Not in scope for v0.5.11 (docs-only release), but worth a v0.5.12 `karma install-skill` or `karma init` extension.

### Verification

- skill structure intact: 7 `### Step N` headings present (was 7, still 7)
- Length: 225 → 269 lines (net +44, explicit guidance not bloat)
- No code changes — `pytest 404/404`, `ruff 0` unchanged

## [0.5.10] — 2026-05-15 (docs — `karma --help` now lists `rule add` / `rule preview` subcommands)

### docs — `karma --help` was hiding `karma rule add` / `karma rule preview`

A user-initiated dogfood test (running the v0.5.1 `karma rule` flow end-to-end for the first time) surfaced that `karma --help` still only listed `karma sticky list/edit/remove` — the new `rule add`, `rule preview`, and `rule list/edit/remove` subcommands shipped in v0.5.1 were fully implemented and dispatched correctly, but invisible from top-level help. A first-time user typing `karma --help` would have no idea `karma rule add` exists.

This release fixes the docstring at the top of `karma/cli.py` to:
- List all 4 `rule` subcommands (`list` / `edit` / `remove` / `add` / `preview`) with their flags (`--from-yaml <file>` / `--from-stdin`)
- Mention `karma sticky` as a deprecated alias removed in v0.6.0
- Add a footer pointer to the Claude Code `/karma rule <natural language>` skill workflow

The implementation has been working since v0.5.1; this is a pure documentation fix.

### Verified end-to-end (16 test cases)

- `karma rule preview --from-stdin` with valid yaml → schema check + injection preview render ✓
- `karma rule preview` error paths (missing id / nonexistent yaml file) → `exit 1` with `❌` message ✓
- `karma rule add --from-stdin` with valid yaml → schema validate + id-uniqueness + cap + REGISTRY check + write + report ✓
- `karma rule add --from-yaml <file>` with valid yaml → same flow ✓
- `karma rule add` duplicate id → `exit 1` ✓
- `karma rule add` unknown `violation_checks` function → `exit 1` with available-functions list ✓
- `karma rule add` schema error (missing preference) → `exit 1` ✓
- `karma rule add` invalid yaml → `exit 1` ✓
- `karma rule add` no flag → `exit 1` with usage prompt + `/karma rule` skill hint ✓
- `karma rule` no subcommand → `exit 1` with subcommand list ✓
- `karma rule foobar` unknown subcommand → `exit 1` ✓
- `karma rule list` shows newly-added rule ✓
- `karma rule remove <id>` removes the rule ✓
- `karma rule remove <id>` then `karma rule add` same id → succeeds ✓
- `rules.yaml` is truly persisted (grep verified line count = 7 after 2 adds to 5-minimal base) ✓

Plus `pytest` 404/404 + `ruff` 0 issues.

## [0.5.9] — 2026-05-15 (refactor — Bash heredoc exemption lifted into `description_context.py`, shared by all Bash-aware checks)

### refactor — `is_description_context(tool_name="Bash")` now supported

v0.5.8 promised this. v0.5.9 delivers: the Bash-heredoc-target-path exemption that lived locally in `testset.py` is now in `description_context.py`, and all Bash-aware checks (`long_term`, `testset`, etc.) that already call `is_description_context()` get the same treatment automatically.

- New `_classify_path(file_path) -> (bool, str)` helper in `description_context.py` (extracted from the original Write/Edit branch)
- `is_description_context()` now special-cases `tool_name == "Bash"` — scans the command for `>` / `>>` redirect targets and applies `_classify_path` to each; if any target is a description context, the whole call is exempt
- `testset.py` v0.5.8 local helper removed; behavior preserved by the new shared logic
- `long_term.py` automatically inherits — e.g. `echo "TODO: x" >> docs/CHANGELOG.md` is now exempt (was previously incorrectly blocked as `TODO` marker)

### Verification

- `pytest`: 404/404 passing (v0.5.8 tests still green — same test cases, now flow through the shared helper)
- `ruff`: 0 issues

## [0.5.8] — 2026-05-15 (fix — testset check exempts Bash heredoc writes targeting description-context paths)

### fix — `cat >> tests/test_x.py <<EOF ... case_id="..." ... EOF` false-positive

A v0.5.7 dogfooding session hit it: when appending the new v0.5.7 regression tests via `cat >> tests/test_checks.py <<'PY'`, the heredoc body contained `case_id = "a1b2c3d4..."` — meant as a test fixture literal — and got blocked as "test-set case ID hard-coded." Root cause: v0.5.5 only added the `python -c` exemption; the parallel case of Bash redirect/heredoc writing to a description-context path (tests/ / .md / .yaml) was still missing.

This is the same root-cause family as v0.5.5: when the *target* of a write is a description-context path, the *content* of the write is descriptive, not executable. Today the parity check covers:

- `python -c "..."` content (v0.5.5)
- Bash heredoc / redirect `>` `>>` to a path matching tests/test/__tests__/spec dirs, or `.md/.rst/.txt/.yaml/.yml/.json/.toml/.ini/.csv/.tsv` suffix, or `test_*.py` / `*_test.py` filename pattern (v0.5.8)

`src/runner.py` / production-code paths are still blocked even when written via heredoc.

A future refactor (likely v0.5.9) will lift this into `description_context.py` so all Bash-aware checks share the same exemption surface. For v0.5.8 the helper lives in `testset.py` only.

### Verification

- 3 new regression tests in `tests/test_checks.py`:
  - `test_testset_v058_heredoc_to_tests_path_exempted` — heredoc to `tests/` exempted
  - `test_testset_v058_heredoc_to_md_doc_exempted` — heredoc to `.md` exempted
  - `test_testset_v058_heredoc_to_src_still_blocked` — heredoc to `src/` still blocked
- `pytest`: 404/404 passing (401 prior + 3 new)
- `ruff`: 0 issues

## [0.5.7] — 2026-05-15 (feat — locale-agnostic `trigger_key` field on `CheckHit` + `Violation` for cross-locale audit grouping)

### feat — audit groups by `trigger_key` instead of `trigger` literal

A side-effect of v0.5.4 (i18n'd all trigger strings): `karma audit` was grouping by `trigger` literal, so a user who ran karma in zh locale for a week then switched to en would see "the same behavior" split into two separate counter lines. The audit's "top trigger" analysis would mis-represent reality.

v0.5.7 adds a locale-agnostic `trigger_key` (the i18n key itself, e.g. `"check.evidence.commit.trigger"`) as a stable identifier across locales:

- **`CheckHit.trigger_key: str = ""`** — every check function now passes both `trigger=tr(key)` (display string) and `trigger_key=key` (group identifier)
- **`Violation.trigger_key: str = ""`** — stored in violations.jsonl alongside the locale-specific `trigger` literal
- **`cli.py cmd_audit`** — groups by `trigger_key or trigger` (fallback to literal for legacy rows without the field)
- **Display** — still shows the locale-translated `trigger` literal (whichever was captured first), so users see readable text; only counting is unified

### Backward compatibility

- Legacy `violations.jsonl` rows without `trigger_key` load with `trigger_key=""` and group by `trigger` literal — no data loss.
- `to_json()` omits the field when empty, keeping jsonl file size identical for legacy writes.

### Verification

- 5 new regression tests in `tests/test_checks.py`:
  - `test_v057_check_hits_carry_trigger_key` — every check function returns non-empty `trigger_key` starting with `"check."`
  - `test_v057_violation_roundtrip_trigger_key` — write + read jsonl preserves `trigger_key`
  - `test_v057_violation_backward_compat_no_trigger_key` — legacy rows load with empty `trigger_key`, no crash
  - `test_v057_audit_groups_by_trigger_key_across_locales` — 5 zh + 5 en same key → single counter group of 10
  - `test_v057_audit_legacy_no_key_fallback_to_trigger` — legacy rows fall back to literal grouping
- `pytest`: 401/401 passing
- `ruff`: 0 issues

## [0.5.6] — 2026-05-15 (fix — keep_pushing `_PUSH_SIGNAL_RE` covers "next push point / next step is" planning phrases)

### fix — keep_pushing false-positive on "下一推进点 / 下一步是" tail phrases

This v0.5.4 dogfooding session hit it 7 times in a row: every response ended with a clear "next push point: X" / "next step: Y" planning phrase, but `keep_pushing.check()` still fired the "no push signal, no decision question — real stop" default trigger. Root cause: `_PUSH_SIGNAL_RE` (introduced in v0.4.19 to cover "future-planning push signals") missed the most common form — `下一(推进点 / 步 / 个 / 波 / milestone)` + verb.

This is the same root cause as v0.4.19 ("`_PUSH_SIGNAL_RE` missed future-planning expressions"), but on a different phrase family. Fix: extend `_PUSH_SIGNAL_RE` with 4 new branches:

- `下一(?:推进点|步|个|个推进点|波|个 milestone|个里程碑)` — bare "next push point / next step" phrase
- `下一步\s*(?:是|做|打算|准备|考虑|推进|继续|去|要|想|可以|应该)` — "next step is/plans to" + intent
- `接下来\s*(?:打算|准备|计划|考虑|可以|可选|的方向|的推进点)` — "next planning to / direction" forms
- `后续\s*(?:推进|步骤|计划|打算|准备|是)` — "follow-up steps / plans" forms

False-cousin "下一次再说吧" (deferral, not planning) is correctly *not* covered because the new patterns require `下一` + planning noun, not `下一次` + filler.

### Verification

- 2 new regression tests in `tests/test_keep_pushing.py`:
  - `test_v056_next_push_point_phrasing_exempted` — 6 push phrase variants all exempt
  - `test_v056_partial_stop_still_blocked` — `"下一次再说吧"` deferral still blocks
- `pytest`: 396/396 passing (394 prior + 2 new)
- `ruff`: 0 issues

## [0.5.5] — 2026-05-15 (fix — testset check adds `python -c` exemption, parity with non_blocking / bypass_karma)

### fix — testset.py false-positive on `python -c` string literals

A v0.5.3 dogfooding session hit it: a probe script `python -c "r = check(content='gold_cases.append(x)')"` was blocked by the testset check, treating the in-quote string `gold_cases.append(x)` as a real reverse-feed call. Root cause: `testset.py` was the only one of three `python -c`-affected checks missing the `_LANG_C_HEAD_RE` exemption (`non_blocking.py` got it in v0.4.18, `bypass_karma.py` got it in v0.4.13).

This release adds the same exemption pattern to `testset.py` `check()` — when `tool_name == "Bash"` and command head matches `\b(?:python\d?|node|ruby|perl)\s+-[ce]\b`, the check returns `None`. Real reverse-feed Bash commands (`cp eval/* train/`, `cat detail.json >> pool.jsonl`) without a `-c` wrapper still trigger.

### Verification

- 2 new regression tests in `tests/test_checks.py`:
  - `test_testset_python_c_string_literal_exempted` — confirms exemption applies
  - `test_testset_real_bash_reverse_feed_still_blocked` — confirms direct `cp eval/* train/` still blocks
- `pytest`: 394/394 passing (392 prior + 2 new)
- `ruff`: 0 issues

## [0.5.4] — 2026-05-15 (feat — Phase D wave 3: all 28 `CheckHit.trigger` strings switchable en/zh)

### feat — All `CheckHit.trigger` audit labels now locale-aware

The `trigger` field — written to `~/.claude/karma/violations.jsonl` for audit-log classification — was the last bilingual gap left after v0.5.3. v0.5.4 closes it: 28 trigger strings across 8 check modules are now `tr()`-driven, parallel to the `fix` namespace.

- 14 direct-trigger entries in `chinese_plain` / `non_blocking` / `evidence` / `keep_pushing` / `read_first` / `bypass_karma` (with `{term}` / `{cmd}` / `{word}` / `{tool}` / `{file_path}` / `{target}` interpolations)
- 14 pattern-table entries in `long_term` / `testset` — tuple structure now `(regex, trigger_key, fix_key)`, both translated at hit time

### feat — 28 new `check.*.trigger` keys in `data/locales/en.yaml` + `zh.yaml`

`!r`-style format specifiers carried over from the original `f"..."` so `'value'` quote-wrapping behavior stays identical.

### Verification

- `pytest`: 392/392 passing
- `ruff`: 0 issues
- Manual probe: 28/28 keys resolve in both EN and ZH with correct interpolation (`time.sleep(5)`, `'真' repeats 7 times`, etc.)

### What's left in Chinese (intentional)

`Sticky #N` rule body content in `data/rules.dev.example.zh.yaml` — these are the *user's preferences* (Chinese users get the Chinese template, English users get the English template via `_select_rule_template()`), so per-locale templates are the right model, not runtime translation.

## [0.5.3] — 2026-05-15 (feat — Phase D complete: all 28 check `suggested_fix` strings switchable en/zh)

### feat — All 8 check functions now locale-aware

All `CheckHit.suggested_fix` strings — the part directly injected into Agent's next-turn context — switched from hard-coded Chinese to `tr()` lookup. Coverage is complete across all 8 check modules.

- **`karma/checks/chinese_plain.py`** (3 entries) — `ratio` / `jargon` / `repeated_prefix`. Note: chinese_plain check itself is opt-in for Chinese users; English default install removes it via rule-template selection.
- **`karma/checks/non_blocking.py`** (4 entries) — `python_block` / `sleep` / `wait` / `long_task` (with `{cmd}` interpolation)
- **`karma/checks/evidence.py`** (3 entries) — `commit` / `completion` / `weak_claim`
- **`karma/checks/keep_pushing.py`** (2 entries) — `stop_hint` / `default`
- **`karma/checks/read_first.py`** (1 entry, with `{file_path}` interpolation)
- **`karma/checks/bypass_karma.py`** (1 entry)
- **`karma/checks/long_term.py`** (7 entries in pattern tuples) — `long_id_branch` / `blacklist_literal` / `uppercase_const_list` / `commit_hack` / `git_skip_verify` / `todo_marker` / `patch_intent`
- **`karma/checks/testset.py`** (7 entries in pattern tuples) — `reverse_feed` / `detail_writeback` / `cross_split_copy` / `detail_append` / `split_hardcode` / `hash_branch` / `case_list_hash`

For `long_term` and `testset`, the `_PATTERNS` tuple structure was preserved with `fix_key` (an `i18n` key string) as the third element instead of literal fix text — the `check()` function calls `tr(fix_key)` at hit time. This keeps the pattern table compact and lets translators edit `data/locales/*.yaml` without touching Python.

### feat — `data/locales/en.yaml` + `data/locales/zh.yaml` add 28 new keys

`check.*.fix` namespace covers all suggested_fix strings. Placeholders (`{term}`, `{prefix}`, `{file_path}`, `{cmd}`) interpolated at runtime via `str.format()`.

### Verification

- `pytest`: 392/392 passing (unchanged from v0.5.2; new keys are additive)
- `ruff`: 0 issues
- Manual EN/ZH switch test confirms all 14 new keys lookup correctly in both locales

### What stays Chinese (intentional, scoped to v0.5.3)

- `CheckHit.trigger` field — internal audit-log classification label, written to `~/.claude/karma/violations.jsonl`. Not in Agent injection path, so prioritization is lower; will migrate in a future minor release alongside trigger-key namespace design.

## [0.5.2] — 2026-05-15 (feat — i18n infrastructure + all hook injection texts switchable en/zh)

### feat — Engineering-layer i18n MVP

- **`karma/i18n.py` module** — `tr(key, **fmt)` translation lookup with `{placeholder}` interpolation; fail-open (missing key returns key itself, never crashes hook)
- **Locale resolution** — `KARMA_LOCALE` env var > `config.yaml` `locale` field > `karma.locale_detect.is_chinese_user()` auto-detect > fallback `en`
- **`config.yaml` `locale` field** — `"auto"` (default) / `"en"` / `"zh"`
- **`data/locales/en.yaml` + `data/locales/zh.yaml`** — Translation dicts covering all user-visible hook-injection strings (header / drift marker / mid-injection / strong reminder / Stop reason / SessionStart variants / SubagentStart)

### feat — 5 hooks injection texts now locale-aware

All hook injection texts switched from hard-coded Chinese to `tr()` lookup:

- `karma/rule.py format_for_injection` — header title + 2 description lines + drift marker
- `karma/hooks/post_tool_use.py` — mid-injection "anchoring refresh" 3 lines
- `karma/hooks/stop.py` — Stop hook `decision=block` reason (with `{count}/{max}` interpolation)
- `karma/hooks/user_prompt_submit.py` — strong reminder header + footer
- `karma/hooks/subagent_start.py` — SubAgent baseline title + tail
- `karma/hooks/session_start.py` — 3 source branches (compact/resume/startup) + compact prior-drift header + tail

### Manual verification

- `KARMA_LOCALE=en` → `[karma — Your long-term agreement with the user]` / `[karma — Last response didn't show a next-step push signal]` ...
- `KARMA_LOCALE=zh` → `[karma — 你跟用户的长期默契]` / `[karma — 上一回应没看到下一步推进信号]` ...

### Pending in v0.5.3 (Phase D — English content completion)

8 built-in check functions still have hard-coded Chinese `suggested_fix` text (~14 entries):
- chinese_plain (3 / non_blocking (4) / evidence (3) / keep_pushing (2) / long_term (7) / testset (7) / read_first (1) / bypass_karma (1)

Phase D will abstract these behind `tr()` keys + provide English translations. Hook injection texts are user-visible critical path (covered in v0.5.2); `suggested_fix` only shown when violations trigger (less critical) — phased separately.

### Verification

- Tests: 392/392 all green
- 4-check: ruff / mypy / vulture / pytest all green
- Manual run: EN/ZH locale switching truly produces different injection text

## [0.5.1] — 2026-05-15 (feat — `karma rule add` natural-language rule input + i18n English-default docs)

### feat

- **`karma rule add` / `karma rule preview` CLI commands** — Natural-language rule input via Claude Code skill collaboration. User invokes `/karma rule <description>` in Claude Code → Agent refines to karma's validated tone/structure (per `skills/karma-rule.md` template) → calls `karma rule preview` to test → user confirms → calls `karma rule add` to write
- **`skills/karma-rule.md`** — Claude Code skill template for natural-language rule creation. Install: copy to `~/.claude/skills/karma-rule.md`
  - Workflow: understand intent → check existing rules → refine yaml → preview test → user confirm → write → report results (optimized content + tests passed + current rule library count + suggest deletions/modifications)
  - Critical constraints: collaborative-agreement tone (not rule-system), intent-prefix + action keyword format, optional engine-layer `violation_checks`, schema test before write
- Rule add validation: schema check + id duplicate check + soft/hard cap (10/12) check + `violation_checks` function existence check in REGISTRY

### docs (i18n English-default complete)

- **English-default documentation swap** (per user input: "the world's 90%+ future users are English") — switched main documentation language from Chinese to English. Chinese versions preserved as `.zh.md` alternatives:
  - README.md / SECURITY.md / CODE_OF_CONDUCT.md / CLAUDE.md
  - docs/PRD.md / docs/ARCHITECTURE.md / docs/REFACTOR_PLAN_RULE_AND_I18N.md / docs/RULES_REDESIGN_PROPOSAL.md / docs/HANDOFF.md
  - karma/backends/HOWTO.md
  - .github/ISSUE_TEMPLATE/bug_report.md / .github/ISSUE_TEMPLATE/feature_request.md / .github/PULL_REQUEST_TEMPLATE.md
  - CHANGELOG.md (this file)
- **Rule templates English-default**: `data/rules.dev.example.yaml` is now English-default; `.zh.yaml` is Chinese alternative. `karma init` auto-selects based on `karma/locale_detect.py` system-language detection
- **GitHub repo description** switched to English

### docs (i18n complete)

- **English-default documentation swap** (2026-05-15) — switched main documentation language from Chinese to English (per user input: "the world's 90%+ future users are English"). Chinese versions preserved as `.zh.md` alternatives. All English `.md` files are now the GitHub-default entry; `.zh.md` files are linked in headers as alternative-language versions.
- **Swapped files** (English-default + .zh.md backup):
  - README.md / SECURITY.md / CODE_OF_CONDUCT.md / CLAUDE.md
  - docs/PRD.md / docs/ARCHITECTURE.md / docs/REFACTOR_PLAN_RULE_AND_I18N.md / docs/RULES_REDESIGN_PROPOSAL.md / docs/HANDOFF.md
  - karma/backends/HOWTO.md
  - .github/ISSUE_TEMPLATE/bug_report.md / .github/ISSUE_TEMPLATE/feature_request.md / .github/PULL_REQUEST_TEMPLATE.md
  - CHANGELOG.md (this file)
- **Rule templates English-default**:
  - `data/rules.dev.example.yaml` is now English-default
  - `data/rules.dev.example.zh.yaml` (Chinese version, was previous default)
  - `data/rules.dev.minimal.example.yaml` same pattern
  - `karma init` auto-selects based on `karma/locale_detect.py` system-language detection
- **GitHub repo description** switched to English: "Make AI Agents never violate your rules in long tasks — auto-correct violations before they frustrate you. Pure-engineering zero-LLM hook system for Claude Code / Codex CLI / Gemini CLI. Measured violation rate ≈ 0%."

## [0.5.0] — 2026-05-15 (major breaking change — sticky → rule rename)

User authorized: "rename all `sticky` references in karma's code and files to `rule`."

Phase A complete: sticky → rule rename + backward-compat migration. Phase B (natural-language rule input via `karma rule add` CLI + Claude Code skill) / C (i18n infrastructure) / D (full English content) are pending in subsequent releases.

Key changes:
- Core classes: `class Sticky` → `class Rule`, `StickyConfigError` → `RuleConfigError`, `MAX_STICKY` → `MAX_RULES` (all preserved as aliases until v0.6.0)
- Module: `karma/sticky.py` → `karma/rule.py` (git mv preserved history), legacy `karma/sticky.py` became a compat shim
- Fields: `Violation.sticky_id` → `Violation.rule_id` (property `sticky_id` alias preserved), `CheckHit.sticky_id` → `CheckHit.rule_id`
- CLI: `karma sticky list/edit/remove` → `karma rule list/edit/remove`, legacy `karma sticky` as deprecated alias
- Config: `~/.claude/karma/sticky.yaml` → `~/.claude/karma/rules.yaml`, auto-migration via `karma init`
- Data templates: `data/sticky.dev.example.yaml` → `data/rules.dev.example.yaml`

Tests: 392/392 + 4-check (ruff / mypy / vulture / pytest) all green.

For detailed pre-v0.5.0 release notes (v0.1.0 through v0.4.44), see [CHANGELOG.zh.md](./CHANGELOG.zh.md).

## Pre-v0.5.0 releases

For all release history from karma's earliest version (v0.1.0) through v0.4.44, see [CHANGELOG.zh.md](./CHANGELOG.zh.md). Each release includes:

- Trigger context (what prompted the change)
- Root-cause analysis
- Implementation details
- Backward-compatibility notes
- Empirical verification (test counts, dogfooding hours, etc.)
- Lessons learned (for major fixes)

Notable releases:
- **v0.4.42** — "Collaborative agreement" tone refactor (see [docs/RULES_REDESIGN_PROPOSAL.md](./docs/RULES_REDESIGN_PROPOSAL.md))
- **v0.4.43 / v0.4.44** — Stop / SubagentStop / PreCompact hook schema compliance fixes
- **v0.4.39** — Per-model adaptive injection threshold (`karma/model_threshold.py`)
- **v0.4.34** — Subagent independent state architecture
- **v0.4.28 / v0.4.29 / v0.4.30** — v3 evolution: SessionStart baseline + PreCompact dump + SubagentStart/Stop
- **v0.4.0** — Multi-backend (Gemini CLI added) + JsonHooksBackend abstraction
- **v0.3.0** — Codex CLI backend
- **v0.1.0** — Initial Claude Code backend

## Versioning policy

- **Major** (X.0.0) — breaking changes (e.g., v0.5.0 sticky → rule rename, even with backward-compat aliases)
- **Minor** (0.X.0) — new features without breaking existing APIs
- **Patch** (0.0.X) — bug fixes, doc updates, performance improvements

Breaking changes are clearly marked with **major breaking change** prefix; deprecated aliases preserved for at least one minor version cycle before removal.
