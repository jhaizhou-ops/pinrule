# pinrule Hook 配置指南

**[🇬🇧 English](./HOOK_CONFIGURATION_GUIDE.md) · [🇨🇳 中文 (current)](./HOOK_CONFIGURATION_GUIDE.zh.md)**


`pinrule install-hooks` 把 hook 写进对应 AI 客户端的配置文件。本指南以 Claude 为例（8 个 hook 全覆盖最完整），Codex / Cursor 用相同命令切 `--backend`，hook 业务逻辑同源，仅 native event 数 + 写入路径不同。

| Backend | install 命令 | 写入位置 | Native event 数 |
|---|---|---|---|
| Claude（默认） | `pinrule install-hooks` | `~/.claude/settings.json` | 8 |
| Codex CLI | `pinrule install-hooks --backend codex` | `~/.codex/hooks.json` (+ `~/.codex/config.toml` 写 trusted_hash) | 6 |
| Cursor 1.7+ | `pinrule install-hooks --backend cursor` | `~/.cursor/hooks.json` | 12 |

## 快速开始

```bash
pinrule init                                       # 创建 ~/.pinrule/ + 复制规则模板
pinrule install-hooks                              # 默认 Claude（也可加 --backend codex/cursor 或 all）
pinrule doctor                                     # 验证装机（自动扫所有装机的 backend）
```

装完重启 AI 客户端，hook 立即生效。规则在 `~/.pinrule/rules.json`（跨 backend 共享） — 用 `pinrule rule edit` 编辑，或 `/pinrule <自然语言>` 让 skill 替你写。

---

## 8 个 hook 速查

| Hook | 何时触发 | 作用 | 用户感知 |
|---|---|---|---|
| **UserPromptSubmit** | 你提交 prompt 前 | 注入精简 anchor（id + 第一行 + 偏离标记，~490 tok）— v0.9.0 新设计 | 后台工作，无通知 |
| **PreToolUse** | Agent 调 tool 前 | 拦截违反核心方向的工具调用 | 命中时 ❌ 权限被拒（附理由） |
| **PostToolUse** | tool 调用成功后 | 跟踪 session 状态；session 累积到模型衰减拐点（Opus 60K / Sonnet 40K / Haiku 30K）全量 reinject 完整规则抗稀释 | 后台跟踪，无通知 |
| **Stop** | Agent 想停下前 | 检测违反 + 静默停止时启发继续推进 | ⚠️ stderr 提醒 + 桌面通知 |
| **PreCompact** | 客户端自动 compact 前 | 完整规则状态落盘 snapshot | 后台落盘，无通知 |
| **SessionStart** | session 起手 / compact 后重起 | **全量** baseline 注入完整规则（v0.9.0 唯一一次 ~1817 tok 注入进 history）；compact 重起时读 snapshot 强注入 | 后台注入，无通知 |
| **SubagentStart** | 启动子 Agent 时 | 子 Agent 自动继承完整规则 + 维护独立监控状态 | 子 Agent 头部看到规则注入 |
| **SubagentStop** | 子 Agent 结束时 | 子 Agent 临时状态自动销毁，不污染主 session | 后台清理，无通知 |

所有 hook 输出严格按 Claude 官方协议 schema — 不会被客户端 UI 报错。

---

## 配置路径

**跨 backend 共享**（用户级数据）：

```bash
~/.pinrule/rules.json           # 你的核心方向（手工编辑或 /pinrule skill）
~/.pinrule/config.json          # 阈值配置（不存在时走 DEFAULTS）
~/.pinrule/violations.jsonl     # 违反历史（auto-rotate at 5000 行）
~/.pinrule/session-state/       # 每个 session 一份 json（30 天自动清理）
~/.pinrule/pre_compact_snapshot.md  # compact 前规则 dump（SessionStart 重读）
```

**每个 backend 各自的 hook wrapper + settings**：

```bash
# Claude
~/.claude/hooks/pinrule_*.py          # 8 个 hook wrapper（install-hooks 自动生成）
~/.claude/settings.json               # Claude 配置（pinrule 写入 hooks 段）

# Codex CLI
~/.codex/hooks/pinrule_*.py           # 6 个 hook wrapper
~/.codex/hooks.json                   # hook 入口（pinrule 写这里）
~/.codex/config.toml                  # Codex 配置（pinrule 写 trusted_hash 这里）

# Cursor 1.7+
~/.cursor/hooks/pinrule_*.py          # 12 个 hook wrapper（含 4 个独立 gate）
~/.cursor/hooks.json                  # Cursor 配置（pinrule 写入 hooks 段）
```

> 设了 `PINRULE_HOME` 环境变量 → 上面所有路径都 anchor 在 `$PINRULE_HOME/` 下（真 sandbox 隔离，v0.16.11+）。试用 / CI / 多 profile 都用这个。

---

## 典型场景

### A. 长 session 跨 compact

**你在做**：多小时开发任务，Agent 累积 60K+ context。

**发生的事**：
1. Claude 自动触发 compact
2. **PreCompact hook**：完整 `rules.json` 状态落盘到 `pre_compact_snapshot.md`
3. compact 执行（Claude 自己的压缩）
4. **SessionStart hook**（compact 后重起触发）：读 snapshot 强注入完整规则

**结果**：规则跨 compact 不丢，Agent 不会把核心方向压成模糊词。

---

### B. 子 Agent 并发执行

**你在做**：起 2 个子 Agent 并行搜索代码 + 改 bug。

**发生的事**：
1. **SubagentStart hook**：完整规则注入到子 Agent context
2. 子 Agent 在自己 session 里仍然看得到约束 + 维护独立监控状态
3. 子 Agent 完成
4. **SubagentStop hook**：子 Agent 临时 session-state 自动销毁

**结果**：子 Agent 跟主 Agent 同等监管力度；多次起子 Agent 不会让主 session 数据混乱。

---

### C. 静默停止时被提示继续

**你在做**：给 Agent 多个明确步骤的方向，期待自主推进。

**发生的事**：
1. Agent 完成第 1 步，response 末尾纯陈述无下一步信号
2. **Stop hook** 检测到静默停止 → 输出 `decision=block` + 启发继续提示
3. Agent 看到提示后接着推进下一步
4. Safeguard：单 turn 内累积 block ≥ 2 次（`stop_block_max_per_turn` 可调）后让 Agent 停下，防死循环
5. 任务真饱和时 Agent 明说卡在哪 → pinrule 不再推

**结果**：Agent 完成一波后立刻找下个推进点继续，不再「下一步做什么」反复问。

---

## 常见问题

### Q：Hook 拒了我的操作怎么办？

看拒绝理由（stderr / 通知里都有）— 这通常说明你的规则认为这是违反。两种处理：
- 修 `rules.json`（调整规则措辞 / keyword / engine check）
- 明确告诉 Agent「绕一下先跑」（用户授权的例外）

如果你认为是 pinrule 误拦（假阳），跑 `pinrule audit` 看「⚠️ 可能假阳」标记，欢迎提 issue。

### Q：能关掉某个 hook 吗？

能。两种方式：
- `pinrule uninstall-hooks`（也接 `--backend` 拆指定 backend，或 `all`）
- 手工编辑对应 backend 的 settings 文件（`~/.claude/settings.json` / `~/.codex/hooks.json` / `~/.cursor/hooks.json` / `~/.hermes/config.yaml`），在 hooks 段删 / 注释掉对应 event

但建议先用一周看效果。

### Q：子 Agent 能绕过规则吗？

绕不了。`SubagentStart` 把完整规则注入子 Agent 头部，子 Agent 自己的 hook 也跑同样的检查。但**子 Agent 的状态隔离**意味着关键词检测是按子 session 独立计数 — 这是设计上的隐私 / 性能取舍。

### Q：自定义阈值怎么配？

`~/.pinrule/config.json`（不存在时走 `pinrule/config.py:DEFAULTS`）：

```json
recent_violation_turns: 5         # 偏离标记窗口
stop_block_max_per_turn: 2        # Stop hook 单 turn 启发上限
force_block_threshold: 5          # 累积强制查根因阈值
session_state_max_age_days: 30    # session 状态自动清理周期
```

`pinrule doctor` 会显示当前生效的所有阈值。

---

## 设计原则

1. **Fail open** — 配置错 / 加载失败 → hook 不会卡 Agent，静默继续
2. **零 LLM** — 全工程化（regex / 关键词 / 计数），无外部依赖
3. **可见化** — 拦截 / 启发都有 stderr + 桌面通知，不黑盒
4. **可调** — 你改 `rules.json` 下个 turn 立即生效

---

**官方协议参考**：
- Claude: https://code.claude.com/docs/en/hooks
- Codex: https://developers.openai.com/codex/hooks
- Cursor: https://cursor.com/docs/agent/hooks
