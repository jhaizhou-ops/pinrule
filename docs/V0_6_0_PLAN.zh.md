# pinrule v0.6.0 计划 — 拆 backward-compat 脚手架

**[🇬🇧 English](./V0_6_0_PLAN.md) · [🇨🇳 中文（当前）](./V0_6_0_PLAN.zh.md)**

**起草日期**：2026-05-15
**起草人**：Claude Opus 4.7（audit 驱动）
**状态**：✅ **v0.6.0 已实施（2026-05-15）** — Group A + Group B 全部删除完成，Group C（盘上数据兼容）按计划保留。加了 5 个 deletion-lock 回归测试。迁移 cookbook 见 [CHANGELOG.md v0.6.0](../CHANGELOG.md)。

---

## v0.6.0 为啥存在

v0.5.0 把 `sticky` 改名 `rule`，全代码库都加了向后兼容 alias（module、class、property、CLI 子命令、文件路径）。v0.5.13 清完**属性级**的 `.sticky_id` callsite，但后续 audit 发现 **module-level** 的 `from pinrule.sticky import ...` 在 6 处内部代码还在用 — 加上 `pinrule/rule.py` / `pinrule/cli.py` / `pinrule/checks/_types.py` / `pinrule/violations.py` 里十几个 alias。

v0.6.0 的工作：**把脚手架删掉**。结果是：codebase 里 `sticky` 字眼只出现在（a）历史 CHANGELOG 条目 (b) 处理老盘数据的 migration 路径（`sticky.yaml` → `rules.yaml`、老 `violations.jsonl` 行的 `sticky_id` key）。别的地方都没。

这是**对直接 import `pinrule.sticky` 或访问 `CheckHit`/`Violation.sticky_id` 的用户外部代码的破坏性改动**。废弃 warning 从 v0.5.0 起就在打了；v0.6.0 是悬崖。用户有整个 v0.5.x 周期迁移。

## v0.6.0 删什么

### Group A — 内部脚手架（零外部影响，纯代码清理）

只有 pinrule 自己代码引用，删除是纯内部重构。

| 项 | 位置 | v0.5.13 状态 |
|---|---|---|
| `MAX_STICKY = MAX_RULES` alias | `pinrule/rule.py:43` | `cli.py:54` 在用 |
| `Sticky = Rule` alias | `pinrule/rule.py:62` | 测试可能在用 |
| `StickyConfigError = RuleConfigError` alias | `pinrule/rule.py:76` | `cli.py:54`、`hooks/stop.py:24` 在用 |
| `EXAMPLE_STICKY = EXAMPLE_RULES` alias | `pinrule/cli.py:69` | 内部 |
| `EXAMPLE_STICKY_MINIMAL = EXAMPLE_RULES_MINIMAL` alias | `pinrule/cli.py:70` | 内部 |
| ~~11 处内部 `from pinrule.sticky import ...` callsite~~ | ~~`cli.py`（4 处）、`hooks/*.py`（6 处）、`pinrule/sticky.py` 自指~~ | ✅ **v0.5.15 已清**（11 处源代码 + 4 处测试文件迁到 `from pinrule.rule import ...`；`pytest -W error::DeprecationWarning` 全过 0 warning）|

**v0.6.0 动作**：`from pinrule.sticky` 清理已完成（v0.5.15）。现在可以安全删 alias 模块 + 下面 alias 不会自伤 pinrule 自己代码。

### Group B — public API 破坏性改动（废弃契约）

v0.5.0 起一直在 stderr 打 deprecation warning。v0.6.0 删除是兑现废弃契约。

| 项 | 删除效果 | 用户感知 |
|---|---|---|
| `pinrule/sticky.py` compat shim 模块 | `from pinrule.sticky import ...` 抛 `ModuleNotFoundError` | **有** — 用户自己写脚本 import `pinrule.sticky` 会破 |
| `Violation.sticky_id` @property（alias 到 `.rule_id`） | `violation.sticky_id` 抛 `AttributeError` | **有** — 分析脚本访问这个属性会破 |
| `CheckHit.sticky_id` @property（alias 到 `.rule_id`） | `hit.sticky_id` 抛 `AttributeError` | **有** — 自定义 violation_check 作者 |
| `pinrule sticky <subcommand>` CLI alias | `pinrule sticky list` 等退 1 报「未知命令」 | **有** — 肌肉记忆 / 跑 `pinrule sticky list` 的脚本 |

### Group C — 老盘数据 migration（保留 — 这些处理用户状态，不是 API 表面）

**v0.6.0 不要删这些。** 这些处理老 pinrule 版本写盘的数据；不是废弃 alias，是正确性补丁。

| 项 | 位置 | 为啥保留 |
|---|---|---|
| `cmd_init` 内 `sticky.yaml` → `rules.yaml` 自动 migration | `cli.py:191-197` | 从 v0.4.x 升级的用户盘上仍有 `sticky.yaml` |
| `_extract_rule_id` 兜底读老 `sticky_id` jsonl 字段 | `pinrule/violations.py` | 历史 `violations.jsonl` 行从 v0.4.x 来的有 `sticky_id` 字段不是 `rule_id`。`pinrule audit` / `stats` 必须还能读 |
| `pinrule init` 内 legacy-sticky.yaml fallback 路径解析 `DEFAULT_PATH` | `pinrule/rule.py` | 同上 — 老装机路径 |

这些总共 ~20 行，永远留（或者将来单独发个「砍 v0.4.x 数据兼容」的 release 走它自己的废弃周期）。

## 执行顺序（v0.6.0 做的时候）

避免半路自己挂掉，顺序必须：

1. **v0.6.0 前置清理 commit**（可以做成 v0.5.15 纯文档之外的版本）：grep 验证 pinrule 自己代码里 0 处 `from pinrule.sticky`。有就先做成 v0.5.x release fix
2. **v0.6.0-rc1**：把 6 处内部 `from pinrule.sticky` import 换成 `from pinrule.rule`（Group A）。跑全测 — `pinrule.sticky` 还在工作的 shim 所以应该全过
3. **v0.6.0**：删 `pinrule/sticky.py`、删 `pinrule/rule.py` 里 4 个 alias（`MAX_STICKY` / `Sticky` / `StickyConfigError`）、删 `cli.py` 里 `EXAMPLE_STICKY` / `EXAMPLE_STICKY_MINIMAL`、删 `CheckHit` + `Violation` 上 `.sticky_id` @property、删 `cli.py` 里 `pinrule sticky` CLI alias dispatch。测试必须全过（步骤 2 后内部 callsite 应该 0 残留）

## 测试覆盖期待

v0.6.0 之后：
- v0.5.14 的 410 个测试应该全过（不该有测试依赖 alias — v0.5.13 已清）
- 任何测试破 = v0.5.x 清理漏了一项 — 改测试不是改代码
- 加 1 个回归测试确认 `import pinrule.sticky` 抛 `ModuleNotFoundError`（锁住删除）
- 加 1 个回归测试确认 `pinrule sticky list` 退 1 报「未知命令」（锁住 CLI 删除）

## 公告时机

- v0.5.14（当前）：本计划稿在 `docs/V0_6_0_PLAN.md`，搜仓库的用户能预览悬崖
- v0.5.15（建议下一步）：前置清理 commit + 给 `pinrule --version` / `pinrule doctor` 输出加一行 warning：「v0.6.0 将删除 `pinrule.sticky` 模块和 `.sticky_id` 属性 alias — 详见 `docs/V0_6_0_PLAN.md`」
- v0.6.0：破坏改动。CHANGELOG 条目必须置顶 + GitHub release notes 标 breaking change

## v0.6.0 不是什么

- 不是 feature release。没新功能。纯清 v0.5.0 改名脚手架
- 不是「永远删所有 backward compat」。Group C（盘上数据兼容）保留
- 不是趁机塞别的破坏性改动。SemVer major bump 意味着*一个*破坏性主题 — alias 删除 — 不是杂物间

## 风险评估

| 风险 | 缓解 |
|---|---|
| 用户脚本 import `pinrule.sticky` 升级就破 | 废弃 warning 从 v0.5.0 起就在打（≥ 1 个 release 周期预警）。迁移是机械的一行：`s/pinrule\.sticky/pinrule.rule/` |
| `pinrule sticky list` 肌肉记忆破 | CLI dispatch 可以在「未知命令: sticky」时加一行「你是不是想用 `pinrule rule list`？」hint — 3 行代码省用户困惑 |
| 老 `violations.jsonl` 数据读不了 | 已缓解 — Group C `_extract_rule_id` 兜底保留。用户所有历史 audit 数据都还能读 |
| 内部测试直接引用 `Sticky` 类 | 审计步骤 1（v0.6.0 前置清理）catch — 删除前先修 |

## 开放问题

1. **`pinrule sticky` CLI alias 要不要多活一个 release？** ✅ **v0.6.0 已解决** — 按计划删除，并在「未知命令」路径加了「💡 你是不是想用 `pinrule rule`？」hint（`pinrule/cli.py:1262`）。一行肌肉记忆救援，不需保留整个子命令分支。
2. **v0.6.0 要不要顺手默认关掉非中文用户的 `chinese_plain_no_jargon` check？** ✅ **判定 out-of-scope** — v0.6.0 不动（check 仍装着，`pinrule init` 模板选择仍剔除非中文用户）。如果下次 dogfood 摸到摩擦点再重新评估。
