# 安全策略

## 报告漏洞

发现 karma 安全问题 → **不要开公开 issue**，发邮件到项目维护者邮箱（`gh repo view jhaizhou-ops/karma` 看 contact）或私下 GitHub Security Advisory。

## karma 的真实威胁模型

karma 是 **本地 hook 工具** — 装在你机器、读你的本地配置、写本地文件。不连接外部服务（无 LLM API / 无 telemetry / 无网络调用）。威胁面有限但**不是零**：

### 真实威胁场景

| 场景 | 风险 | 缓解 |
|---|---|---|
| **`sticky.yaml` 含恶意 regex** | 用户复制不可信来源 sticky 模板，含 ReDoS pattern 卡 hook | karma 加载 sticky 时 `re.compile` 编译失败会 fail loud；用户应只复制可信源模板 |
| **hook wrapper 被篡改** | 攻击者替换 `~/.claude/hooks/karma_*.py` 注入恶意代码 | karma 自身不主动校验 wrapper 完整性 — 用 `karma install-hooks` 重装可恢复；按 OS 文件权限保护 hooks 目录 |
| **`violations.jsonl` 含敏感字符串** | 你 Bash 命令含 secret 触发 karma 检测时，secret 进 `~/.claude/karma/violations.jsonl` snippet 字段 | 不要在 Bash 命令明文 secret；karma 落盘前**不做 secret 检测**（不是它的职责） |
| **`pre_compact_snapshot.md` 含敏感内容** | compact 前 sticky 状态落盘到 `~/.claude/karma/pre_compact_snapshot.md`，含 sticky.yaml 你写的 preference 内容 | 不要在 sticky.yaml `preference` 字段写 secret；这文件 600 权限 + 用户家目录默认保护 |
| **跨 session state 污染** | `~/.claude/karma/session-state/` 多个 session JSON 文件含 read_files / edit_files / recent_bash 摘要 | 30 天自动清理（`session_state_max_age_days` 可调）；不会跨用户跨机器同步 |

### **不**属于 karma 安全责任

- **Claude / Codex / Gemini 模型本身的安全问题** → 找上游
- **sticky 注入到 Claude 后 Agent 行为** → 模型行为不在 karma 控制范围（karma 只注入 sticky 文本，不裁决 Agent 怎么执行）
- **你 `~/.claude/` 目录里其他工具的安全** → 找对应工具维护者
- **网络层 / 系统层威胁** → 不在 karma 威胁模型内

## 已知 limitation

karma 是 **regex 匹配 + 计数** 工程工具，不是 LLM 语义理解。这意味着：

- **不能识别 Agent 隐式绕开规则** — 用户改 `violation_keywords` 关键词列表是 trust-based，karma 不验证 keyword 合理性
- **不能检测 sticky.yaml 内容真实合法** — 如果用户写了「鼓励 Agent 写不安全代码」类 preference，karma 仍照样注入。**用户对 sticky.yaml 内容负责**
- **`bypass_karma_detection` check 拦的是「Bash 命令含 karma 内部状态字面 + 写操作」** — 不能阻止用户用其他工具（如 vim / cat / python script 不经过 Claude Code hook）改 karma 内部状态

## 响应时限

- **漏洞确认**：3 个工作日内回复
- **fix 发版**：高危 7 天 / 中危 30 天 / 低危下个 release 一起带

karma 是个人维护项目，没有专职安全团队，请理解响应时限可能受作者 availability 影响。

## 致谢

负责披露漏洞的研究者，欢迎在 fix release notes / 项目 contributors 名单致谢（如你接受公开）。
