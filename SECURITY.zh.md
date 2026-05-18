# 安全策略

**[🇬🇧 English](./SECURITY.md) · [🇨🇳 中文（当前）](./SECURITY.zh.md)**

## 报告漏洞

发现 pinrule 安全问题 → **不要开公开 issue**。用 [GitHub 的私密 Security Advisory](https://github.com/jhaizhou-ops/pinrule/security/advisories/new) — 最快的通道。

## pinrule 的实际威胁模型

pinrule 是 **本地 hook 工具** — 跑在你机器上，读本地配置、写本地文件。不连外部服务（无 LLM API、无 telemetry、无网络调用）。威胁面有限但不是零：

### 实际威胁场景

| 场景 | 风险 | 缓解 |
|---|---|---|
| **`rules.json` 含恶意 regex** | 用户复制不可信来源的规则模板，含 ReDoS pattern 卡死 hook | pinrule 加载规则时 `re.compile` 失败会 fail loud；只从可信源复制模板 |
| **hook wrapper 被篡改** | 攻击者替换 `~/.claude/hooks/pinrule_*.py` 注入恶意代码 | pinrule 不主动校验 wrapper 完整性 — `pinrule install-hooks` 重装可恢复；用 OS 文件权限保护 hooks 目录 |
| **`violations.jsonl` 含敏感字符串** | 你的 Bash 命令含 secret 触发 pinrule 检测时，secret 进 `~/.pinrule/violations.jsonl` snippet 字段 | 不要在 Bash 命令里明文 secret；pinrule 落盘前不做 secret 检测（不是它的职责） |
| **`pre_compact_snapshot.md` 含敏感内容** | compact 前规则状态落盘到 `~/.pinrule/pre_compact_snapshot.md`，含你 `rules.json` 写的 preference | 不要在 `rules.json` 的 `preference` 字段写 secret；这文件 600 权限 + 家目录默认保护 |
| **跨 session 状态污染** | `~/.pinrule/session-state/` 多个 session JSON 含 read_files / edit_files / recent_bash 摘要 | 30 天自动清理（`session_state_max_age_days` 可调）；不跨用户跨机器同步 |

### **不**属于 pinrule 安全责任

- **Claude / Codex / Cursor 模型本身的安全问题** → 找上游
- **规则注入到客户端后 Agent 的行为** → 模型行为不在 pinrule 控制范围（pinrule 只注入规则文本，不裁决 Agent 怎么执行）
- **`~/.claude/` 目录里其他工具的安全** → 找对应工具的维护者
- **网络层 / 系统层威胁** → 不在 pinrule 威胁模型内

## 已知 limitation

pinrule 是 **regex 匹配 + 计数**，不是 LLM 语义理解。这意味着：

- **识别不了 Agent 隐式绕开规则** — 用户改 `violation_keywords` 列表是 trust-based，pinrule 不验证 keyword 合理性
- **检测不了 `rules.json` 内容本身的合法性** — 如果用户写了「鼓励 Agent 写不安全代码」类 preference，pinrule 仍照样注入。**`rules.json` 内容由用户负责**
- **`bypass_pinrule_detection` check 只拦「Bash 命令含 pinrule 内部状态字面 + 写操作」** — 阻止不了用户用其他工具（vim / cat / Python 脚本绕过客户端 hook）修改 pinrule 内部状态

## 响应时限

- **漏洞确认**：3 个工作日内回复
- **fix 发版**：高危 7 天 / 中危 30 天 / 低危跟下个 release 一起带

pinrule 是个人维护项目，没有专职安全团队 — 响应时限会受维护者 availability 影响，请理解。

## 致谢

负责披露漏洞的研究者，欢迎在 fix release notes / 项目 contributors 名单致谢（如你接受公开）。
