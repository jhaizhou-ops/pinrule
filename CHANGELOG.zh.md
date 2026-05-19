# Changelog

**[🇬🇧 English](./CHANGELOG.md) · [🇨🇳 中文（当前）](./CHANGELOG.zh.md)**

pinrule release notes, 按 minor 版本聚合. 版本号遵循 [SemVer](https://semver.org/lang/zh-CN/). 每个 patch 的具体细节 (CI 修 / 假阳调整 / audit 抓到的字段 bug) 可看 [git log](https://github.com/jhaizhou-ops/pinrule/commits/main) — commit message 带完整 reasoning.

v0.5.1 起双语发布. v0.1.0 – v0.4.x 早期历史只在本中文 CHANGELOG.

## [Unreleased]

## [0.19.0] — 2026-05-19 — **Hermes Agent backend — 第 4 家客户端真支持 (源码 ground)**. NousResearch Hermes Agent v0.14.0+ (持久 server agent + plugin hooks) 真加入 Claude / Codex / Cursor 之外第 4 家 backend. 真 clone `NousResearch/hermes-agent` 源码, 每个协议细节都 ground 在 `agent/shell_hooks.py` (`_serialize_payload` 真 payload 构造 / `_parse_response` 真 block normalize) + `agent/conversation_loop.py` (`pre_llm_call` / `on_session_end` 真 kwargs), 不靠 docs 单边猜. 真 payload shape (`{hook_event_name, tool_name, tool_input, session_id, cwd, extra}`), block output 真接受 Claude `{decision: block, reason: ...}` (内部 normalize 到 Hermes 自己的 `{action: block, message: ...}`), `pre_llm_call` context 注入真用顶层 `{context: "..."}`, 配置真在 `~/.hermes/config.yaml`, skills 真在 `~/.hermes/skills/`, wrapper 真在 `~/.hermes/agent-hooks/`. 真 tool name 归一化: `terminal` / `shell` / `execute_shell` → `Bash`, `read_file` → `Read`, `write_file` → `Write`, `patch_file` / `edit_file` → `Edit`. 真 event 映射 (5 个 event): `pre_tool_call` → 拦截, `pre_llm_call` → context 注入, `post_tool_call` → 审计, `on_session_start` → baseline 注入, `on_session_end` → stop wrapper (Hermes 真不给 transcript_path 字段, 违反检测 graceful no-op, 跟之前 Gemini AfterAgent 同款 lifecycle limit). `protocol_adapter.detect_backend` 真加 `_HERMES_EVENT_NAMES` frozenset (snake_case event 名) + `/.hermes/` sys.argv 路径 fallback. 真本机端到端 dogfood 验证: `hermes -z "Use terminal: sleep 30"` → `pre_tool_call` hook 真 fire → pinrule 真 emit block decision → hermes 真拒执行 → `violations.jsonl` 真录 `non-blocking-parallel` 规则命中. 测试: 35 个新 Hermes 单元 + 16 个 contract parametrized + 跨 4 backend fixture 真更新 client_installed mock = 952 真 passing. **v0.19.0 已知 limit**: pinrule 自带 YAML subset parser 真不接受 Hermes 默认 `config.yaml` (含 `agent.personalities` 段 multi-line string 续行 + unicode escape continuation). `pinrule install-hooks --backend hermes` 真生成 wrapper 后, 用户当前需手工 append `hooks:` 段到 `~/.hermes/config.yaml` — line-based surgical operator v0.19.1 真补 (真无 PyYAML 依赖处理 Hermes 全 default YAML, 保持 0 runtime deps 承诺).

## [0.18.3] — 2026-05-18 — **真假阳 fix: Cursor Shell `block_until_ms` 默认值不再误拦**. 朋友 Cursor 试用真触发的高发假阳: Cursor SDK 给每次 Shell 调用都默认带 `block_until_ms=30000` 字段 (语义: 「最多等 30s 再转后台」). `normalize_tool_name` 把 Shell 映射 Bash 后, `non_blocking.py:116-127` 用 `block_until_ms >= 30_000` 当「命令会阻塞」代理判断 — 但这字段是工具调用等待上限, 跟命令本身阻塞与否无关. 结果: 每个 Cursor Shell 命令 (包括 `pinrule doctor` <1s 的) 都被拦. **Fix**: 删 `block_until_ms` 错误代理判断; 命令内容检测 (`_SLEEP_RE` / `_LONG_TASK_RE` / `_PYTHON_REAL_BLOCK_RE`) 真识别阻塞, 那部分保留. 加 2 个回归测试钉死: (a) Cursor SDK 默认 payload `block_until_ms=30000` + 真短命令 (`pinrule doctor` / `ls` / `echo` / `git status`) 不命中; (b) 同 Cursor payload 下真 `sleep 60` 仍被命令内容检测拦. 同时清 5 处 `sticky` 残留 (`docs/ARCHITECTURE.zh.md` 的 ASCII 框图注释 / violations.jsonl 示例 / 正文 / CheckHit 签名, `docs/PRD.zh.md` 正文) — v0.6.0 `sticky → rule` rename 漏的.

## [0.18.2] — 2026-05-18 — **首波朋友 dogfood 前的文档 / skill 精修** — v0.18.1 之后 6 个 docs commit, runtime 行为 0 改动. (1) **Path B Execution Checklist 10 行 → 8 行短骨架** (评委反馈: 每行内联长注解干扰低能力模型 attention; haiku 4.5 真两轮 dogfood verify v0.18.1 三处真 fix —— Backends-detected 3 行 template / Source A 诚实 / 没自我介绍段 —— 浓缩后真仍 stick). 加 2 个 lockdown 测试钉死 8 步骨架 + 单行 ≤100 字符. (2) **运行时边界精确化**: hero 段 `> 纯工程 · 零 LLM · 零联网 ...` → `> **运行时**: 纯工程 · 零 LLM ...` 加显式 "（场景规则包调研由你的 Agent 完成，见下面 Path B。）" —— 两位独立 reviewer 同款点了这处误读. (3) **诚实工具边界段从语言免责改"附测试证据"**: `pytest tests/test_check_fp_fixes_v0_16_13.py` (4 处历史假阳锁死) + `pytest tests/test_false_negative_regression.py` (30+ 假阴 case 钉死). 质疑者本机复现, 不靠语言免责. (4) **版本备注清残留**: README + SKILL.md 全删 `v0.17.1+ / v0.17.1 新 / v0.18.0+` 类版本备注 —— 用户只看当前状态, 不需要知道功能哪个版本进的. (5) **`os.rename` → `os.replace + fsync` 引用对齐**: CHANGELOG 0.18.0 entry + `cmd_rule_import_pack` docstring 同步实际实现. (6) **砍 walkthrough**: Path B 段砍 114 行 ML-research walkthrough example —— 过度具体的 example 真带偏 Agent attention.

## [0.18.1] — 2026-05-18 — **6 评委交叉评审 P0/P1 修复** — 关三个真 bug 跨独立评委确认. (1) **`_STICKY_ID` 数据 corruption fix**: 8 个 engine check 函数现在接 caller 传的 `rule_id` (fallback `_STICKY_ID`), Path B 跨场景规则真写用户自己的 rule.id 到 `violations.jsonl`, 不再硬编码 `read-before-write` 等 — 之前 Path B 每条挂 engine check 的规则真悄悄写 ghost rule id, `pinrule audit --by-check` 显示找不到对应规则. (2) **`import-pack` atomic 加固**: tmp 文件用 `tempfile.mkstemp` (唯一名同目录) 不再固定 `rules.json.tmp` → 真无并发竞态; 加 `os.fsync` 在 `os.replace` 前真落盘; backup 文件名加 pid + random suffix 真避免同秒撞. 新增 4 个原子性回归测试 (byte-for-byte / duplicate-id / 并发 / backup 唯一). (3) **`cursor_transcript_doctor` 跨平台**: 加 Linux (`~/.config/Cursor/logs`) + Windows (`%APPDATA%/Cursor/logs`) 路径分发; transcript_path regex 真接受 POSIX 和 Windows 路径. (4) **Engine check 诚实度**: README + SKILL.md 把「≡ same pattern / 同行为 pattern」改成「partially maps to operational pattern」, 显式说 `loud_failure_with_evidence` 的 `_ACTION_CONTEXT_RE` 偏 dev 词, non-code 场景靠 keyword 兜底. (5) **定位收口**: README 头从「通用 AI 行为规则约束框架」改「通用 AI 行为规则 runtime, 预置开发场景规则包, 其他场景由 Agent 现场生成」— runtime vs 内容边界更明确. (6) **Path B Execution Checklist**: Path B 段头加 10 步短路线 checklist 让 Agent 不漏关键步骤 (不用读完 800 行才知道关键路径). (7) **文档清残留**: SECURITY.zh.md `rules.yaml` → `rules.json`, ARCHITECTURE.zh.md `sticky #N` → `rule #N`, SKILL.md `os.rename` → `os.replace` (正确 primitive), 过时 `cp backup` 指令 → `--backup` flag 引用.

## [0.18.0] — 2026-05-18 — **`pinrule rule import-pack` 真原子批量写 CLI — Path B 场景切换的真保险**. 修 v0.17.1 朋友 review 抓的原子性 gap: 之前 Agent 串 `pinrule rule remove A && rule remove B && rule add new1 && rule add new2 ...` 切场景, 中间任何挂 (schema 拒/磁盘满/权限) → `rules.json` 处于半替换状态. 新 CLI: `pinrule rule import-pack --from-json <pack> --mode replace|append [--backup]` 先全量校验整 pack (schema / id 唯一性 / 硬上限 / `violation_checks` 注册表) **再写**, 然后 atomic 临时文件 + swap (0.18.1 强化为 `os.replace` + `fsync`). 任何校验挂 → `rules.json` 一字没动. SKILL.md Path B Step 10 改用这个 primitive — Agent 一行命令, pinrule 保证原子. 12 个新测试覆盖 schema-fail / 未知 check / 硬上限超 / 空 pack / 不存在文件 等 atomic guarantee. 净效果: 场景切换不会再让你半替换的规则库.

## [0.17.1] — 2026-05-18 — **`/pinrule` 成为通用入口** — 场景规则集生成 + engineering-first 设计原则. `/pinrule` 现在是一个命令搞定所有: 无参数 → audit dashboard (fast-path, 0 LLM 转述); `/pinrule <单条规则>` → Path A 7 步润色 + 写入 (现有); `/pinrule <场景描述>` → Path B 两阶段生成 (新) — Agent 综合 4 信号源 (你本机 CLAUDE.md / AGENTS.md / .cursor/rules / 联网 best practice via WebSearch / Karpathy CLAUDE.md baseline / Agent 跟你协作的 session 上下文), Phase 1 = 内容起草 + 审批, Phase 2 = 机制配置 (keyword + 跨场景 engine check 语义映射) + 审批, Step 10 原子批量写 + 自动备份. SKILL.md 根本设计原则: engineering-first — pinrule 已有的 primitive (`pinrule doctor` / `pinrule rule preview` / `pinrule rule add` 等) Agent 直接调, 不重新发明. Backend 检测走 `pinrule doctor` (内置新 `pinrule.cursor_transcript_doctor` 解析 Cursor Hooks 日志区分 桌面 Agent / CLI / transcript 状态), Phase 1 preview 必填 "Backends detected" 字段强制约束触发 — 6 轮 dogfood 真验证: 工程约束 (必填字段) 比 prompt 约束 ("mandatory first action" 文字) 有效得多. pinrule 本身仍然 0 运行时依赖 / 0 联网 / 0 LLM — 所有调研都在 Agent 现成工具集里跑. 净效果: pinrule = framework / runtime, 规则 = Agent 替每个用户研究他自己场景生成. 「一句话切场景」承诺真站住.

## [0.17.0] — 2026-05-18 — ⚠️ BREAKING — **0 运行时依赖**. 砍 PyYAML; 全部 config / rules / locales / examples 从 YAML 切 JSON (Python 标准库). `push_signals/{en,zh}.yaml` cartesian 模板转 Python 模块 (`{en,zh}.py`) — 嵌套模板数据用 Python 比 JSON 语义更清晰. CLI flag 改名 `--from-yaml` → `--from-json`. 配置/状态文件: `~/.pinrule/config.yaml` → `config.json`, `rules.yaml` → `rules.json`. 不自动迁移: 这是一次性 breaking 重启, 重装即可. 为什么这么做: dogfood 反馈发现 YAML 多行字符串 + 注释友好度没在被消费 — 规则是 LLM 通过 `pinrule rule add` 维护的, 不是手工编辑. 净收益: README 终于能写「0 运行时依赖」, wheel 体积更小, pip 装更快, 少一个版本冲突风险源.

## [0.16.18] — 2026-05-18 — **Windows 中文 GBK 控制台修复** (真用户 dogfood issue): `pinrule init` 在中文 Windows 默认控制台不再 `UnicodeEncodeError: 'gbk' codec can't encode character '▸'` 崩. 加 `pinrule/_io_encoding.py::force_utf8_stdio()` 共享 helper, 在每个 entry point (`__main__` / `cli.main()` / hook wrapper) 强制 stdout/stderr UTF-8. CI 加 Windows GBK 默认控制台 smoke test step (不设 PYTHONIOENCODING) 锁死回归. 同步修: `settings.json.before-pinrule` fresh-install 路径之前漏写空标记导致后续 backup 会保存 pinrule-修改过的 state (uninstall 路径实际坏了); init 自动装 hook 措辞改成「给所有检测到的客户端补装」; README 一行命令砍成 `pip install pinrule && pinrule init` (init 自动跑 install-hooks).

## [0.16.17] — 2026-05-18 — **Windows 原生支持**. Hook command 从裸 `wrapper-path` (依赖 Unix shebang) 改成 `python.exe wrapper-path` 走 `subprocess.list2cmdline` — 跨平台, 含空格 path 自动 quote. CI matrix 加 `windows-latest`; 3 个新 lockdown 测试覆盖 sys.executable 前缀 + 空格 quote + 三家 backend 一致性 (857 测).

## [0.16.16] — 2026-05-17 — README 全 redesign (双语 203 行, 节奏对齐 aider / open-interpreter / mem0 标杆) + PyPI metadata 精修 (description 跟 slogan 对齐, keywords 砍 `dogfooding` 加 `pinrule` / `claude-code` / `agent-rules`).

## [0.16.x] — 2026-05-17 (当前)

- **karma → pinrule 改名**: 干净 PyPI 包, 新 brand, 不背 karma legacy 包袱.
- `PINRULE_HOME` 成为 **真 sandbox** — install 根 / hook wrapper / settings / skill 路径 / Cursor rules 全 anchor 在 env 路径下, 真 `~/.claude/` / `~/.codex/` / `~/.cursor/` 一字节不动, 由回归测试守住.
- 两轮外部 review 打磨 (8.8 → 9.1/10): slogan 改硬, 装机边界文档精修, 「supported clients」说稳点, FAQ 加 pinrule vs memory 系统对比.
- Round-1/2/3 多 Agent 代码审查 + 社区 issue #8 关闭: 4 个 check 假阳真根因配 ground-truth 测试, init reinstall 检测真根因, 所有 hook entry fail-open 契约, demo SVG 按人类阅读速度重调. **854 测 CI 全绿**.

## [0.15.0] 系列 — 2026-05-17

- Codex 原生 hook surface 跟 Claude 干预语义对齐.
- 三端能力对照表 + 可复现真测脚本.

## [0.14.0] 系列 — 2026-05-17

- 共享 `~/.pinrule` home 目录跨所有 backend.
- Cursor 原生 event surface (12 个 event 全链路打通).

## [0.13.0] 系列 — 2026-05-17

- 每 turn token 成本降 **~10×** (compact anchor 注入格式).
- 砍 Gemini CLI backend, 专注 Claude / Codex / Cursor.
- Cursor 跟 Claude 功能对齐 (8/8 hook wrapper).

## [0.12.0] 系列 — 2026-05-17

- **Cursor backend 支持** — 第 4 家 AI 客户端 wired end-to-end (后续 v0.13.x 扩到 12 个 native event).

## [0.11.0] 系列 — 2026-05-16 / 17

- `long-term-fundamental` engine 重新设计: 加 response-level 话术 pattern 让 engine 真触发.
- 双语 hook 输出 i18n + 英文 `long-term-fundamental` response pattern.
- `pinrule audit --days N` 时间窗口过滤, dogfood 决策不被老数据稀释.

## [0.10.0] 系列 — 2026-05-16

- Backend 架构重构: `protocol_adapter` 调度层 + 6-method backend 契约 + Codex 所有权分工接手.
- Cross-model audit (GPT-5.5) 抓到 3 个 cross-backend 协议 critical bug (Claude-only 假设藏了整个 repo 生命周期).

## [0.9.0] 系列 — 2026-05-15 / 16

- 注入架构重设计: SessionStart 全量 baseline + 每 turn 精简 anchor + 累积全量 reinject — **每 turn 节省 73% token**.
- 可观察性: `pinrule audit --by-check` engine check 命中分布; `/pinrule` 无参默认展示这视图.
- 跨进程并发 race fix via API 强制原子性 `update_state(sid, fn)`.

## [0.8.0] 系列 — 2026-05-15

- **i18n 信号系统**: 检测字眼外部化, 英文用户完整覆盖, 加新语言只是一个 `.txt` 贡献.
- `push_signals` YAML DSL: cartesian 模板 + 词集做英文 push-phrase 识别.

## [0.7.0] 系列 — 2026-05-15

- 治根: 改写 pinrule 源规则文本里「真X」防御性前缀堆叠.
- 深度 refactor + 手工 audit 全部 GitHub 可见文档.

## [0.6.0] 系列 — 2026-05-15 ⚠️ BREAKING

- **删 backward-compat 脚手架** (v0.5.0 `sticky` → `rule` 改名留的).
- 第一个真用户 bug 通过 issue #1 关闭 (`record_edit` 豁免非代码路径).

## [0.5.0] 系列 — 2026-05-15 ⚠️ MAJOR BREAKING

- **`sticky` → `rule` 改名**, 全代码库.
- `pinrule rule add` 自然语言录入, 完整 i18n 基础设施 + 英文默认文档 (28 个 `suggested_fix` + 28 个 `trigger` 字符串全双语切换).
- `/pinrule <自然语言>` skill 自动装到每个检测到的 backend.

## [0.4.0] 系列 — 2026-05-14

- 第三个 backend: **Gemini CLI 适配** (v0.13.2 后砍掉).
- 抽 `JsonHooksBackend` 共用基类降未来 backend 成本.
- `PINRULE_HOME` 环境变量首次引入 + `pinrule uninstall` 一键卸装.
- 多轮 dogfood + sub-agent 评审驱动: chinese-plain / keep-pushing / non-blocking / deep-fix-not-bypass / evidence 检测假阳治理 + force_block 协议根因.
- pinrule v3 注入架构:`PostToolUse` 中段 reinject + `SessionStart` baseline + `PreCompact` 落盘 + `SubagentStart/Stop` 装机, 模型自适应阈值跟当代衰减区对齐.

## [0.3.0] 系列 — 2026-05-14

- 多 backend 横向扩展: **Codex CLI 适配**.

## [0.2.0] 系列 — 2026-05-14

- README 重组 + 中性 sticky 模板.
- 跨平台 locale 自动检测 + `pinrule init --minimal` flag.

## [0.1.0] 系列 — 2026-05-14

- 首个公开版本.
- 评审 Agent B 第 4 条盲区一次修对.
