# Changelog

**[🇬🇧 English](./CHANGELOG.md) · [🇨🇳 中文（当前）](./CHANGELOG.zh.md)**

pinrule 每个版本一行说明。版本号遵循 [SemVer](https://semver.org/lang/zh-CN/)。每个 release 的完整设计权衡 / 根因分析 / 「诊断错教训」请看对应 [commit message](https://github.com/jhaizhou-ops/pinrule/commits/main)。

v0.5.1 起每个 release 双语发布。v0.1.0 – v0.5.0 的早期历史只在本中文 CHANGELOG。

## [Unreleased]

## [0.16.14] — 2026-05-17 — README 精修 + 两份外部 review 修 + `PINRULE_HOME` sandbox 回归测试守护 (851 测).
## [0.16.13] — 2026-05-17 — 4 个 check 假阳根因修 (long_term 否定上下文 / markdown code block / chinese_plain inline backtick / 全角标点) 配 ground-truth 回归测试.
## [0.16.12] — 2026-05-17 — `pinrule init` reinstall 检测根因修 (executable-bit 跟 doctor 对齐) + verbose 「缺啥」原因输出.
## [0.16.11] — 2026-05-17 — `PINRULE_HOME` 成为真 sandbox: install 根 / hook wrapper / settings / skill / Cursor rules 全 anchor 在 env 路径下.
## [0.16.10] — 2026-05-17 — 4 个 audit 修: dead `trigger_key` 真填, post_tool_use catchup 响亮失败, 未知命令单行报错, 测试 fixture 真 sandbox.
## [0.16.9] — 2026-05-17 — Round-3 audit 中优先级批: `i18n.tr()` 格式失败 stderr 警告, session-state lock 清理, locale 病句修, 缺失的 `cursor_timeout` 文案.
## [0.16.8] — 2026-05-17 — EN 模板 `chinese-plain-no-jargon` → `plain-language-no-jargon` (真本地化, 不是中文规则英文文本).
## [0.16.7] — 2026-05-17 — 双语 default rule 对称: zh 跟 en 模板都 ship 7 条 (之前 7/5 不对称).
## [0.16.6] — 2026-05-17 — 两轮多 Agent 代码审查 P0/P1 批修: Stop hook TOCTOU race, 所有 hook entry fail-open 契约, Cursor backend `post_install_message` 合并.
## [0.16.5] — 2026-05-17 — 修 issue #12: `karma` → `pinrule` 升级残留清理 (杀 daemon, 删 stale .pyc, 老 CLI 入口).
## [0.16.4] — 2026-05-17 — Demo SVG 内容真修 + `release-finalize.sh` 加 PyPI verify 步.
## [0.16.3] — 2026-05-17 — Demo SVG 按人类阅读速度重新调时 (约 20 秒, 原 42 秒).
## [0.16.2] — 2026-05-17 — Demo SVG 真根因修 (termtosvg `-M -m` 单位是毫秒不是秒, 之前 0.5 秒一闪而过).
## [0.16.1] — 2026-05-17 — `install-hooks` 默认装所有 backend + demo SVG 重调时 + scene 5 fixture 修.
## [0.16.0] — 2026-05-17 — **karma 改名 pinrule**: 干净 PyPI 包, 新 brand, 不背 karma legacy 包袱.
## [0.15.1] — 2026-05-17 — 品牌一致性扫一遍 + 可复现真测脚本 + 三端能力对照表.
## [0.15.0] — 2026-05-17 — Codex 原生 hook surface 对齐 + 干预语义跟 Claude 平价.
## [0.14.0] — 2026-05-17 — 共享 `~/.pinrule` home 目录跨所有 backend + Cursor 原生 event surface.
## [0.13.6] — 2026-05-17 — Cursor 跟 Claude 在 8 个 hook 位置全功能对齐.
## [0.13.3] — 2026-05-17 — Cursor ↔ Claude hook wrapper 对齐 (8/8 wrapper).
## [0.13.2] — 2026-05-17 — 砍 Gemini CLI backend, 专注 Claude Code / Codex CLI / Cursor.
## [0.13.1] — 2026-05-17 — Cursor dogfood 跟进: `beforeSubmitPrompt` mapping + transcript 要求.
## [0.13.0] — 2026-05-17 — Anchor 优化: 每 turn token 成本降 ~10× (compact anchor 格式).
## [0.12.3] — 2026-05-17 — Cursor 原生 `hooks.json` schema 真 dogfood 修复.
## [0.12.2] — 2026-05-17 — 砍 `sticky.yaml` legacy fallback (用户无 migration 需要).
## [0.12.0] — 2026-05-17 — Cursor backend 支持, 第 4 家 AI 客户端 wired end-to-end.
## [0.11.4] — 2026-05-17 — 双语 hook 输出 i18n + EN response-level `long-term-fundamental` pattern + 第一个社区 PR #7 + 5 场景双语 demo.
## [0.11.3] — 2026-05-16 — `pinrule audit --days N` 时间窗口过滤, dogfood 决策不被老数据稀释.
## [0.11.2] — 2026-05-16 — 修 v0.10.6 引入的 CI regression: turn/model 推进必须早于 rules 加载.
## [0.11.1] — 2026-05-16 — `deep-fix-not-bypass` 加 L3 时序层: 测试失败紧跟 Edit 没读源真拦.
## [0.11.0] — 2026-05-16 — `long-term-fundamental` engine 重新设计, 加 response-level 话术 pattern 让 engine 真触发.
## [0.10.6] — 2026-05-16 — `emit_context_injection` / `emit_stop_block` backend 契约 + `model_from_payload` hook 集成测试.
## [0.10.5] — 2026-05-16 — 4 视角 cross-audit sweep: 10 finding 修在 docs / functional / state / boundary 四类.
## [0.10.4] — 2026-05-16 — 优先用 Codex payload model + OpenAI/Codex 阈值表跨平台 attention 自适应.
## [0.10.3] — 2026-05-16 — Codex 简单 pipe 读识别 + `user_stop_hints` 「协作等候」类 + 文档措辞修正.
## [0.10.2] — 2026-05-16 — Codex 关掉对 Claude 平价主要缺口: SessionStart + `exec_command`→Bash + 自动信任 onboarding.
## [0.10.1] — 2026-05-16 — Codex shell-as-Read 全链路打通 + 跨 backend 契约测试.
## [0.10.0] — 2026-05-16 — Backend 架构: `protocol_adapter` 调度层 + 6 契约 method + Codex 所有权分工接手.
## [0.9.16] — 2026-05-16 — Codex `apply_patch` envelope 真 parser (捕获真 payload 锁字面); config `DEFAULTS` 缺字段不再静默丢用户配置.
## [0.9.15] — 2026-05-16 — Cross-model audit (GPT-5.5) 抓到 3 个 cross-backend 协议 critical bug (Claude-only 假设藏了整个 repo 生命周期).
## [0.9.14] — 2026-05-16 — 多 Agent 交叉互审抓到 v0.9.13 自己引入的回归: `pre_tool_use` `update_state` 漏套 try/except.
## [0.9.13] — 2026-05-16 — 全面 instrumentation audit: agent_id 字段往返 / turn 窗口 off-by-one / `pre_tool_use` catchup 无 save / zh `weak_claims` 覆盖缺口.
## [0.9.12] — 2026-05-16 — v0.9.11 audit `--by-check` 数据归类 bug: hook fallback 漏传 `trigger_key` 让 engine 命中被错归 keyword-only.
## [0.9.11] — 2026-05-16 — 可观察性: `pinrule audit --by-check` engine check 命中分布 + `/pinrule` 无参默认展示这个视图.
## [0.9.10] — 2026-05-16 — Onboarding 打磨: summary 改首段不再砍半句 + 加 footer 「token 成本上限 + `/pinrule` 入口」.
## [0.9.9] — 2026-05-16 — Onboarding: `pinrule init` 末尾展示默认规则简要列表, Agent 代装时能直接告知用户.
## [0.9.8] — 2026-05-16 — 跨进程并发 race + API 强制原子性 `update_state(sid, fn)`.
## [0.9.7] — 2026-05-15 — `PINRULE_HOME` 隔离 mode 下 bypass 检测失效 + v0.6.0 user-facing sticky 残留 + 加 regression 锁机制.
## [0.9.6] — 2026-05-15 — 第 5 个独立 CI fail: v0.6.0 BREAKING 重命名在 `verify wheel` step 留的残留.
## [0.9.5] — 2026-05-15 — 第 4 个独立 CI fail: 测试假设 zh locale, CI 跑 en.
## [0.9.4] — 2026-05-15 — 第 3 个独立 CI fail 根因: `signals.py` 的 mypy type error.
## [0.9.3] — 2026-05-15 — 真正让 CI 绿: 3 处死代码 + vulture whitelist.
## [0.9.2] — 2026-05-15 — `test_compact_hooks.py` 硬编码 `/Users/jhz/pinrule` 路径 → 动态解析 (issue #2 来自 @fyn1320068837-source).
## [0.9.1] — 2026-05-15 — v0.9.0 doc sync: PRD F2 / HOOK_CONFIGURATION_GUIDE / session_start docstring.
## [0.9.0] — 2026-05-15 — 注入架构重设计: SessionStart 全量 baseline + 每 turn 精简 anchor + 累积全量 reinject (**每 turn 节省 73% token**).
## [0.8.6] — 2026-05-15 — `agent_saturation` 加裸「真饱和」/ 英文「genuinely saturated」(当 turn dogfood).
## [0.8.5] — 2026-05-15 — 第 3 轮代码审查: 2 处高价值清理, codebase 确认干净.
## [0.8.4] — 2026-05-15 — v0.8.x 累积同步 + v0.8.2 audit 漏的 1 处死代码.
## [0.8.3] — 2026-05-15 — 长 hook main 函数拆 helper + `cli.py` 函数内重复 import 整理.
## [0.8.2] — 2026-05-15 — 代码审查: 死代码清理 + `sticky` → `rule` 命名一致化 + 漏的 i18n 补齐 + 1 个 bug fix.
## [0.8.1] — 2026-05-15 — `push_signals` 用 YAML DSL i18n: cartesian 模板 + 词集 + 平面字眼, 英文 Agent 推进信号识别.
## [0.8.0] — 2026-05-15 — i18n 信号系统: 检测字眼外部化, 英文用户完整覆盖, 加新语言只是提交一个 `.txt`.
## [0.7.4] — 2026-05-15 — `keep_pushing` 用户叫停字眼覆盖「满意 / 确认」类, 不只「累了 / 推卸」类.
## [0.7.3] — 2026-05-15 — 手工逐个 audit 全部 GitHub 可见文档: 营销话术 → 自然、老命令名 → 现行、缺归档标 → 标清楚.
## [0.7.2] — 2026-05-15 — 撤掉 `chinese_plain` Check 3 reactive 监控: 源已治根, 监控冗余.
## [0.7.1] — 2026-05-15 — 「真X」深度清理: 去掉不必要修饰同义词覆盖全仓库.
## [0.7.0] — 2026-05-15 — 治根: 改写 pinrule 源规则文本里「真X」防御性前缀堆叠.
## [0.6.1] — 2026-05-15 — `record_edit` 豁免非代码路径 (issue #1 用户 bug 根因修).
## [0.6.0] — 2026-05-15 — ⚠️ **BREAKING**: 删 `sticky` → `rule` 改名留的 backward-compat 脚手架.
## [0.5.20] — 2026-05-15 — rule-10 自审 follow-up: 补 v0.5.19 漏的 ARCHITECTURE + HANDOFF 同步.
## [0.5.18] — 2026-05-15 — `bypass_pinrule` 区分「读 pinrule 写别处」vs「写到 pinrule 路径」.
## [0.5.17] — 2026-05-15 — README narrative 重写: `/pinrule <NL>` skill 提升为顶级 section.
## [0.5.16] — 2026-05-15 — `/pinrule <自然语言>` skill 可用, 多 backend 装机.
## [0.5.15] — 2026-05-15 — v0.6.0 准备: 起草计划稿 + 内部 `pinrule.sticky` → `pinrule.rule` import 迁移.
## [0.5.14] — 2026-05-15 — `pinrule-rule` skill 教 Agent 用现有命令组合做 modify, 不加新 CLI.
## [0.5.13] — 2026-05-15 — Audit 驱动 dedup: 共享 `is_python_c_command` + sticky_id alias 清理 + doctor skill check.
## [0.5.12] — 2026-05-15 — `pinrule init` 自动装 `pinrule-rule` skill + 新加 `pinrule install-skill` 命令.
## [0.5.11] — 2026-05-15 — `skills/pinrule-rule.md` 清晰度 audit, 补 5 个 gap.
## [0.5.10] — 2026-05-15 — `pinrule --help` 补 `rule add` / `rule preview` 子命令列表.
## [0.5.9] — 2026-05-15 — Bash heredoc 豁免提到 `description_context.py`, 所有 Bash-aware check 共享.
## [0.5.8] — 2026-05-15 — testset check 豁免 Bash heredoc 写到描述上下文路径.
## [0.5.7] — 2026-05-15 — `CheckHit` + `Violation` 加 locale-agnostic `trigger_key`, audit 跨 locale 分组合并.
## [0.5.6] — 2026-05-15 — `keep_pushing` `_PUSH_SIGNAL_RE` 补「下一推进点 / 下一步是」类未来规划豁免.
## [0.5.5] — 2026-05-15 — testset check 补 `python -c` 豁免, 跟 `non_blocking` / `bypass_pinrule` 对齐.
## [0.5.4] — 2026-05-15 — Phase D 第三波: 28 处 `CheckHit.trigger` 双语切换.
## [0.5.3] — 2026-05-15 — Phase D 完成: 8 个 check 28 处 `suggested_fix` 双语切换.
## [0.5.2] — 2026-05-15 — i18n 基础设施 + 所有 hook 注入文本双语切换.
## [0.5.1] — 2026-05-15 — `pinrule rule add` 自然语言录入 + i18n 英文默认文档.
## [0.5.0] — 2026-05-15 — **MAJOR BREAKING**: `sticky` → `rule` 全代码库改名.
## [0.4.44] — 2026-05-15 — `SubagentStop` + `PreCompact` schema 合规, 跟 v0.4.43 Stop fix 同思路.
## [0.4.43] — 2026-05-15 — Stop hook schema 违规修 + 注入文本「合作默契」语气收尾 + sticky keyword 假阳治理.
## [0.4.42] — 2026-05-15 — 用户 task 1/2/3/4 元层 4 任务一波落地.
## [0.4.41] — 2026-05-15 — `keep_pushing` 加 user_prompt 上下文叫停检测.
## [0.4.40] — 2026-05-15 — 反思阈值降 + chinese-plain 分母精化 + 「真字狂魔」reactive 治理.
## [0.4.39] — 2026-05-15 — model 从 transcript_path 真路径协议层最优终极, 覆盖所有 hook.
## [0.4.38] — 2026-05-15 — `user_prompt_submit` 每 turn 跟踪主 model 跨 turn 切换.
## [0.4.37] — 2026-05-15 — 子 Agent model 从主 Agent Task tool input 捕获.
## [0.4.36] — 2026-05-15 — v0.4.35 协议层 limitation 修: SessionStart 拿 model 写 state.
## [0.4.35] — 2026-05-15 — 中段注入阈值按模型自动适配 + 默认抬到 60K (Claude 衰减区).
## [0.4.34] — 2026-05-15 — 子 Agent 独立 pinrule 监控架构.
## [0.4.33] — 2026-05-15 — `strip_shell_quoted_literals` 复合 shell 嵌套根因修.
## [0.4.32] — 2026-05-15 — `bypass_pinrule` `json.dumps` 假阳 + 中段注入 token 启发式频率优化.
## [0.4.31] — 2026-05-14 — `subagent_start.py` `ensure_ascii` bug + 加守护测试.
## [0.4.30] — 2026-05-14 — `SubagentStart/Stop` 装机 + 删 `PostCompact` 幽灵代码.
## [0.4.29] — 2026-05-14 — `PreCompact` 落盘 + 两端夹击 compact 失忆 / CI 修.
## [0.4.28] — 2026-05-14 — `SessionStart` 注入 sticky baseline.
## [0.4.27] — 2026-05-14 — v0.4.26 过度推广修正: 仅 keep-pushing + chinese-plain 反思式.
## [0.4.26] — 2026-05-14 — 4 类价值观规则反思式语气改造.
## [0.4.25] — 2026-05-14 — audit 字面多样性元行为监测.
## [0.4.24] — 2026-05-14 — `PostToolUse` 中段 sticky reinject 锚定.
## [0.4.23] — 2026-05-14 — v0.4.22 紧急补发: tag 误指向 v0.4.21 内容.
## [0.4.22] — 2026-05-14 — 反喂自审: v0.4.13~20 多个 fix 过宽漏拦修复.
## [0.4.21] — 2026-05-14 — `audit --format md` 输出 markdown 表格.
## [0.4.20] — 2026-05-14 — `keep-pushing` 推进信号位置错判: 中段推进 + 末尾列表.
## [0.4.19] — 2026-05-14 — `keep-pushing` 第 3 类假阳: 未来规划 / 显式让用户介入.
## [0.4.18] — 2026-05-14 — `non-blocking` `python -c` `sleep/wait` 假阳: 复用 v0.4.13 根因.
## [0.4.17] — 2026-05-14 — `audit --with-fix-timeline` dogfooding 闭环视图.
## [0.4.16] — 2026-05-14 — `force_block` 协议根因: 只惩罚当前 turn 触发.
## [0.4.15] — 2026-05-14 — `chinese-plain` jargon 扫描豁免表格 cell 引用.
## [0.4.14] — 2026-05-14 — `evidence` 两类假阳: chained pytest + heredoc commit prefix.
## [0.4.13] — 2026-05-14 — `deep-fix-not-bypass` 假阳: `python -c` 比较运算符不是 shell 重定向.
## [0.4.12] — 2026-05-14 — `keep-pushing` 假阳治理 + `scripts/verify-installed.sh`.
## [0.4.11] — 2026-05-14 — `chinese-plain` 再修: kebab/snake 项目标识符不算 jargon.
## [0.4.10] — 2026-05-14 — `chinese-plain` 假阳消除: 版本号 / markdown / emoji 不算 jargon.
## [0.4.9] — 2026-05-14 — codex 0.130 hook approval gate 最终根因.
## [0.4.8] — 2026-05-14 — CI fix + codex Desktop App 上游 regression 根因记录.
## [0.4.7] — 2026-05-14 — sub-agent 排查 5 个 P0 全落地.
## [0.4.6] — 2026-05-14 — `pinrule uninstall` 一键卸装 alias.
## [0.4.5] — 2026-05-14 — `PINRULE_HOME` 环境变量 + sub-agent 评审驱动改进.
## [0.4.4] — 2026-05-14 — 首位用户首装驱动的 3 个修.
## [0.4.3] — 2026-05-14 — `chinese-plain` 表格 / URL 假阳修.
## [0.4.2] — 2026-05-14 — dogfooding 实测发现 `bypass_pinrule` 假阳.
## [0.4.1] — 2026-05-14 — 抽 `JsonHooksBackend` 共用基类降未来 backend 成本.
## [0.4.0] — 2026-05-14 — 第三个 backend: Gemini CLI 适配.
## [0.3.0] — 2026-05-14 — 多 backend 横向扩展: Codex CLI 适配.
## [0.2.4] — 2026-05-14 — 跨平台 locale 自动检测.
## [0.2.3] — 2026-05-14 — `pinrule init --minimal` flag.
## [0.2.2] — 2026-05-14 — 第二轮评审 critical bug fix.
## [0.2.1] — 2026-05-14 — 凭假设没验证反查.
## [0.2.0] — 2026-05-14 — README 重组 + 新增中性 sticky 模板.
## [0.1.1] — 2026-05-14 — 评审 Agent B 第 4 条盲区一次修对.
## [0.1.0] — 2026-05-14 — 首个公开版本.
