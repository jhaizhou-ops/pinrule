# karma Hook 协议逆向工程 — 9 个剩余 hook 的真实协议

**日期**：2026-05-14  
**研究方法**：官方 Claude Code hooks 文档 (https://code.claude.com/docs/en/hooks)  
**目标**：完整协议 + karma 价值排序 + v0.5.0 优先级

---

## 已用 4 个 hook（baseline）

- **UserPromptSubmit**：注入 sticky 到 prompt 头部
- **PreToolUse**：拦截违反 tool 调用  
- **PostToolUse**：跟踪状态 + 中段 reinject sticky anchor（v0.4.24 验证）
- **Stop**：检测违反 + 强制干预

---

## 剩余 9 个 hook 协议速查表

### 1. **PreCompact** ⭐⭐⭐ karma 高优先级

| 字段 | 值 |
|-----|-----|
| **协议** | `trigger: "manual"\|"auto"` |
| **触发时机** | Context compact 前（自动或手工 `/compact`） |
| **能否 block** | ✅ 能 (`exit 2` 或 `continue: false`) |
| **additionalContext** | ✅ 支持（能注入到 Claude context） |
| **输出格式** | JSON: `{"continue": false, "stopReason": "msg", "hookSpecificOutput": {"additionalContext": "..."}}` |

**karma 用法**：Compact 前检查 sticky pool hash，防淡化

**工程代价**：小

---

### 2. **PostCompact** ⭐⭐⭐ karma 高优先级

| 字段 | 值 |
|-----|-----|
| **协议** | `trigger: "manual"\|"auto"` |
| **触发时机** | Context compact 后 |
| **能否 block** | ❌ 否（已执行） |
| **additionalContext** | ✅ 支持 |

**karma 用法**：Compact 后验证 sticky 还活着，丢失则补注

**工程代价**：小

---

### 3. **SessionStart** ⭐⭐ karma 中优先级

| 字段 | 值 |
|-----|-----|
| **协议** | `source: "startup"\|"resume"\|"clear"\|"compact"` |
| **能否 block** | ❌ 否 |
| **additionalContext** | ✅ 支持 |

**karma 用法**：`source=resume` 时重加载 sticky.yaml 版本检查

**工程代价**：小

---

### 4. **SubagentStart** ⭐⭐ karma 中优先级

**协议**：Matcher: Agent 类型  
**能否 block**：❌ 否  
**additionalContext**：✅ 支持

**karma 用法**：将父 sticky 传给子 agent

**工程代价**：中

---

### 5. **SubagentStop** ⭐⭐ karma 中优先级

**协议**：Matcher: Agent 类型  
**能否 block**：✅ 能  
**additionalContext**：✅ 支持

**karma 用法**：检查子 agent 违反，违反溅回日志

**工程代价**：中

---

### 6-9. 其他 hook ❌ 不做

- **Notification**：无 additionalContext 支持
- **StopFailure**：无控制力
- **PermissionRequest**：低价值（重复 PreToolUse）
- **PostToolUseFailure**：低价值

---

## v0.5.0 实现计划

### 优先级 1：Compact 防淡化（预计 3h）
1. PreCompact hook：拒绝可能淡化 sticky 的 compact
2. PostCompact hook：compact 后补注丢失的 sticky

### 优先级 2：Resume 状态恢复（预计 2h）
1. SessionStart hook (matcher=resume)：重加载 sticky.yaml + 版本检查

### 优先级 3：Subagent 隔离（预计 6h，v0.6.0）
1. SubagentStart：sticky 继承
2. SubagentStop：违反检查

---

**官方文档源**：https://code.claude.com/docs/en/hooks
