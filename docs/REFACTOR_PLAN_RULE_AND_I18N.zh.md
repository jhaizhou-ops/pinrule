# pinrule 下阶段重点实施方案 — sticky → rule 改名 + `/pinrule rule` 自然语言录入 + 多语言支持

**[🇬🇧 English](./REFACTOR_PLAN_RULE_AND_I18N.md) · [🇨🇳 中文（当前）](./REFACTOR_PLAN_RULE_AND_I18N.zh.md)**

**起草日期**：2026-05-15
**起草人**：Claude Opus 4.7（应用户两个方向授权）
**审阅状态**：**全部阶段实施完成**（v0.5.0 ~ v0.5.4 已 release，v0.5.7 补 trigger_key 跨 locale 分组）

## 实施进展（2026-05-15 收尾）

- ✅ **阶段 A 完成** (v0.5.0) — `sticky` → `rule` 全代码库改名，向后兼容 alias 保留
- ✅ **i18n 文档翻译完成** — README / SECURITY / CODE_OF_CONDUCT / docs/PRD / docs/ARCHITECTURE / docs/REFACTOR_PLAN / docs/RULES_REDESIGN / HOWTO / CLAUDE.md / .github 模板全切英文默认 + 中文备份；`rules.dev.example.yaml` 英文默认 + `.zh.yaml` 备份；`pinrule init` 通过 `_select_rule_template()` 按用户 locale 自动选模板
- ✅ **阶段 B 完成** (v0.5.1) — `pinrule rule add` / `pinrule rule preview` CLI 子命令含 schema 校验 + id 唯一性 + 上限 + `violation_checks` REGISTRY 校验；Claude Code skill template 在 `skills/pinrule-rule.md` 7 步自然语言工作流
- ✅ **阶段 C 完成** (v0.5.2) — `pinrule/i18n.py` 模块含 `tr(key, **fmt)` lookup、`{placeholder}` 插值、locale resolution chain (`PINRULE_LOCALE` env > `config.yaml` `locale` 字段 > `is_chinese_user()` 自动检测 > `en` fallback)、缺 key fail-open；5 个 hook 注入路径 (`rule.py format_for_injection` / `post_tool_use` / `stop` / `user_prompt_submit` / `subagent_start`) 全部从写死中文切到 `tr()` lookup
- ✅ **阶段 D 完成** (v0.5.3 + v0.5.4) — 28 处 check `suggested_fix` 全 i18n 化 (v0.5.3)；28 处 `CheckHit.trigger` audit log 标签也 i18n 化 (v0.5.4)；v0.5.7 加 locale-agnostic `trigger_key` 字段让 `pinrule audit` 跨 locale 切换稳定分组

> **用户原话**：
> 1. 个性化规则高优好度录入和生效，建议直接做成 `/pinrule rule XXX` 命令。Agent 自动根据 pinrule 要求将用户自然语言深度优化成 pinrule 验证过的语气、内容和结构，并测试通过后写入规则文件。**将整个 pinrule 所有代码和文件的 sticky 字样改成 rule**。
> 2. 多语言支持：现在纯中文，希望支持其他主要语言。

---

## 一、规模评估

| 维度 | 数字 |
|---|---|
| **代码层「sticky」引用** | 340 处 |
| **源文件涉及** | 25 个 |
| **测试文件涉及** | 28 个 |
| **配置文件** | `~/.claude/pinrule/sticky.yaml`（作者本机）+ `data/sticky.dev.example.yaml` / `data/sticky.dev.minimal.example.yaml`（模板） |
| **CLI 命令** | `pinrule sticky list / remove / edit` 等 |
| **文档** | README / PRD / ARCHITECTURE / HANDOFF / CHANGELOG 等大量引用 |

**改名 + i18n 总改动量**：~500-800 处文本修改 + 新增 LLM 调用接口（自然语言录入）+ i18n 框架 + 英文翻译。

---

## 二、分阶段实施（4 个 release）

### 阶段 A：sticky → rule 全代码库改名（v0.5.0 — major breaking change）

**改动**：
1. **Python 代码层**：
   - `pinrule/sticky.py` → `pinrule/rule.py`
   - `class Sticky` → `class Rule`
   - `format_for_injection(sticky_list)` → `format_for_injection(rule_list)`
   - 所有 `sticky_id` 字段 → `rule_id`
   - `StickyConfigError` → `RuleConfigError`
   - `pinrule/checks/*` 里的 `sticky` 参数 / 变量名 → `rule`
   - `pinrule/hooks/*` 里 `sticky_list / sticky_id` → `rule_list / rule_id`

2. **配置文件层**：
   - `~/.claude/pinrule/sticky.yaml` → `~/.claude/pinrule/rules.yaml`（**注意**：单数 sticky → 复数 rules 体现「多条规则集」语义）
   - `data/sticky.dev.example.yaml` → `data/rules.dev.example.yaml`
   - `data/sticky.dev.minimal.example.yaml` → `data/rules.dev.minimal.example.yaml`

3. **CLI 层**：
   - `pinrule sticky list` → `pinrule rule list`
   - `pinrule sticky remove <id>` → `pinrule rule remove <id>`
   - `pinrule sticky edit` → `pinrule rule edit`
   - **保留 `pinrule sticky` 作为 alias 半年**（向后兼容，stderr 提示「已改名 pinrule rule，sticky alias 在 v0.6.0 移除」）

4. **violation 记录**：
   - `violations.jsonl` 里 `sticky_id` 字段 → `rule_id`
   - 自动 migrate：装机时检测旧 violations.jsonl 含 `sticky_id` 字段 → 整体改名 + 备份原文件

5. **文档层**：
   - README / PRD / ARCHITECTURE / HANDOFF / CHANGELOG / CLAUDE.md 等所有「sticky」引用 → 「rule」

**Migration（向后兼容）**：
- `pinrule init` 检测 `~/.claude/pinrule/sticky.yaml` 存在 → 自动 copy 为 `rules.yaml` + 重命名旧文件为 `sticky.yaml.bak`
- `pinrule/rule.py` 加载逻辑：先找 `rules.yaml`，找不到 fallback `sticky.yaml`（带 deprecation warning）
- `violations.jsonl` 加载时兼容旧 `sticky_id` 字段 → 自动映射到 `rule_id`

**测试**：
- 28 个测试文件改名相关 assertion
- 加 3 个 migration 测试（旧 sticky.yaml → 新 rules.yaml 自动迁移路径）

**Release**：v0.5.0（major version bump 标 breaking change）

**风险**：340 处改动一次 commit 难 review；建议拆 5-6 个 commit（核心代码 / 测试 / CLI / 配置文件 / 文档 / migration 各一）

---

### 阶段 B：`pinrule rule add` CLI 命令 + Claude Code `/pinrule rule` skill（v0.5.1）

**设计核心**：用户用自然语言描述规则 → Agent 走 pinrule 提供的结构化引导 → 优化成 yaml → 测试通过后写入。

**两层实施**：

#### B-1: pinrule CLI 层提供 `pinrule rule add` 命令

```bash
pinrule rule add --interactive    # 交互式向导
pinrule rule add --from-yaml <file>  # 从 yaml 文件读取后追加
pinrule rule add --from-prompt "我希望 Agent 完成代码后跑测试"  # 一行自然语言
pinrule rule preview <yaml>    # 测试规则 — 不写入，只跑 yaml schema 验证 + 模拟注入预览
pinrule rule test <id>         # 跑这条规则的 check function 对一组样本测试
```

#### B-2: Claude Code skill / slash command 层

pinrule 提供一个 **prompt template**（`data/rule-add-prompt.md`），让 Claude Code 用户跑 `/pinrule rule` 时 Agent 自动按 template 引导：

```
用户：/pinrule rule
Agent：好，跟你建立一条新规则。先聊聊你想拦住什么 Agent 行为？
用户：我希望 Agent 完成功能后跑测试再说完成
Agent：明白。这条规则属于「证据要求」类（已有 loud-failure-with-evidence
       规则覆盖部分场景），你的具体想加在哪个细节？
       1. Agent 不跑测试就说「fix 了」
       2. Agent 跑了测试但没看到 PASS 就声明完成
       3. Agent 跳过某条测试用 mock 替代
用户：1 + 2 都是
Agent：好，按 pinrule 的结构化语气优化成：

[预览 yaml]
- id: must-run-tests-before-done
  preference: |
    跟你协作的这位用户在你说「完成」时希望看到测试通过证据 — 不是看到
    你跑了测试就行，要看到 pass 数字。如果跳过测试用 mock 替代，
    老实说出来比假装完成更建立信任。
  violation_keywords:
    - 应该可以了
    - 跳过这个测试
  violation_checks:
    - loud_failure_with_evidence

跑 pinrule rule preview 模拟注入看效果？(y/n)

用户：y
Agent：[跑 pinrule rule preview --from-yaml /tmp/new-rule.yaml]
       预览输出：[pinrule — 你跟用户的长期默契]
                 ...
       看起来 OK 吗？写入 ~/.claude/pinrule/rules.yaml？(y/n)

用户：y
Agent：[pinrule rule add --from-yaml /tmp/new-rule.yaml]
      ✓ 规则已添加。下次 prompt 重启生效。
```

**关键设计点**：
- pinrule 不引入 LLM API — Agent 优化是 Claude Code 自身能力，pinrule 只提供 prompt template + CLI 命令
- pinrule 提供「pinrule 验证过的语气、内容、结构」作为 prompt 上下文（让 Agent 知道 pinrule 的合作默契语气 / 8 个内建 check 函数 / 字段格式等）
- 预览 + 确认机制保护用户（avoid Agent 误写）

**Release**：v0.5.1

---

### 阶段 C：i18n 基础设施（v0.5.2）

**设计**：
- `pinrule/i18n.py` 加载 + 切换 locale 接口
- `data/locales/zh.yaml` / `data/locales/en.yaml` — 所有用户可见文本的翻译
- 装机时 `pinrule/locale_detect.py`（已有）检测系统语言 → 写入 config.yaml `locale: zh|en`
- 所有 `print(...)` / `notify(...)` / sticky baseline 头部包装 / suggested_fix 文本 → `_(key)` lookup

**关键文本类别**（按 user-visible 优先级）：
1. CLI 输出（doctor / stats / audit）
2. hook 注入文本（sticky baseline 头部 + 偏离标记 + 强提醒 + 中段刷新 + Stop reason）
3. 8 个 check 的 suggested_fix 文本
4. 错误提示（StickyConfigError / 装机失败等）

**实施**：
- 抽出所有 hard-coded 中文文本 → key
- 写 `zh.yaml`（当前文本）+ `en.yaml`（翻译）
- 加 i18n 测试（切 locale 看输出对应语言）

**Release**：v0.5.2

---

### 阶段 D：英文 rule 模板 + 英文 hook 注入 + 英文 suggested_fix（v0.5.3 — 真多语言可用）

**改动**：
- `data/rules.dev.example.en.yaml` — 英文版 7 条核心方向（preference 翻译成英文 + violation_keywords 改成英文 idiom）
- 验证：英文母语用户安装 → 头部注入 / 拦截 / 反思全英文体验

**Release**：v0.5.3

---

## 三、关键决策点（等你拍板）

### 决策 1：rule.yaml 单数还是复数

- 选项 A: `rules.yaml`（复数 — 表达「多条规则的集合」）
- 选项 B: `rule.yaml`（单数 — 跟 sticky.yaml 单数一致）

**我推荐 A（rules.yaml）**：符合「这是一组规则」语义，跟 Python 风格 list 类型一致。

### 决策 2：sticky → rule 改名 release 节奏

- 选项 A: 一次性 v0.5.0 big bang（340 处一次改完，breaking change 标 major version）
- 选项 B: 渐进式（v0.4.x 加 alias 兼容，v0.5.0 才删 sticky）

**我推荐 A**：pinrule 还在早期，作者基本是唯一用户，breaking change 风险可控。一次性改完干净。

### 决策 3：`/pinrule rule` 是 Claude Code skill 还是 pinrule CLI subcommand？

- 选项 A: 纯 pinrule CLI（`pinrule rule add --from-prompt "..."`）— 用户在 Claude Code 内直接发命令
- 选项 B: Claude Code skill + pinrule CLI 组合（`/pinrule rule` slash command 触发 skill prompt template + 调 pinrule CLI 写入）

**我推荐 B**：skill template 引导 Agent 用 pinrule 验证过的语气优化用户自然语言，体验更好。但需要写 `~/.claude/skills/pinrule-rule.md` 类 skill 文件。

### 决策 4：i18n 框架用 Python gettext 还是简单 dict 映射

- 选项 A: Python 标准 gettext + .po 文件（OSS 翻译标准）
- 选项 B: 简单 yaml dict（{"en": {...}, "zh": {...}}）

**我推荐 B**：pinrule 还在早期，yaml dict 比 gettext 简单 — 翻译者编辑 yaml 比编辑 .po 友好。后期规模大了再迁 gettext。

### 决策 5：支持哪些语言（v0.5.3 起步）

- 选项 A: zh + en 两种起步
- 选项 B: zh + en + ja + ko + es + fr 等 6+ 种一波出
- 选项 C: 只 zh + en，社区贡献其他语言

**我推荐 C**：pinrule 当前作者一人维护，多语言翻译质量靠社区贡献更可靠。先 zh + en 两个标杆，留 i18n 框架开放给社区。

---

## 四、实施时间估算

| 阶段 | 工作量 | 风险 |
|---|---|---|
| A - sticky → rule | ~2-3 天（340 处改动 + 测试 + migration 验证）| 中等（一次性改完不会半成品，但 review diff 难） |
| B - `pinrule rule add` | ~2 天（CLI + skill template + 预览验证）| 低（独立功能不破坏现有） |
| C - i18n 基础设施 | ~3 天（抽 key + 切 locale + 测试）| 中等（涉及大量文本抽取，要彻底） |
| D - 英文翻译 + 验证 | ~2 天（翻译 + 英文用户场景测试）| 低（独立工作） |
| **总计** | **~10 天** | — |

---

## 五、推荐起手顺序 + 等你拍板

我建议立即开始 **阶段 A 第 1 步**：

1. **第 1 commit**: 改名核心类 `class Sticky → class Rule` + 字段 `sticky_id → rule_id` + 顶层 import alias（其他文件还用旧名跑通）
2. **第 2 commit**: 改名 `pinrule/sticky.py → pinrule/rule.py` + 所有 `from pinrule.sticky import` → `from pinrule.rule import`
3. **第 3 commit**: CLI `pinrule sticky` → `pinrule rule` + alias 保留
4. **第 4 commit**: 配置文件 `sticky.yaml` → `rules.yaml` + migration
5. **第 5 commit**: 测试文件 28 个改 assertion
6. **第 6 commit**: 文档全改（README / PRD / ARCHITECTURE / HANDOFF）

每个 commit 后跑 4 件套全过才进下一个 commit，避免半成品。

**v0.5.0 release** 含所有 6 个 commit。

**等你审：**
1. 决策 1-5 的选项确认
2. 是否立即开始（你说「开始」我就推阶段 A 第 1 commit）
3. 或者等明天 / 下个 session 再做

---

## 附录：sticky 改名后用户视角好处

1. **「规则」更直觉**：用户第一次看 README 看到「rule」立刻懂，看到「sticky」要解释「最高优先级方向」
2. **跟业界对齐**：CLAUDE.md / linting rules / firewall rules 都叫 rule，pinrule 跟主流概念一致
3. **`/pinrule rule` slash command** 自然 — `/pinrule sticky` 听起来怪
4. **rules.yaml 复数** 表达「这是一组规则」比 sticky.yaml 单数更准
