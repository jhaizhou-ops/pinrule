# Changelog

**[🇬🇧 English](./CHANGELOG.md) · [🇨🇳 中文（当前）](./CHANGELOG.zh.md)**

pinrule release notes, 按 minor 版本聚合. 版本号遵循 [SemVer](https://semver.org/lang/zh-CN/). 每个 patch 的具体细节 (CI 修 / 假阳调整 / audit 抓到的字段 bug) 可看 [git log](https://github.com/jhaizhou-ops/pinrule/commits/main) — commit message 带完整 reasoning.

v0.5.1 起双语发布. v0.1.0 – v0.4.x 早期历史只在本中文 CHANGELOG.

## [Unreleased]

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
