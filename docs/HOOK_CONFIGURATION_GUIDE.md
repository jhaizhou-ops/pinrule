# karma Hook 配置指南 — v0.5/0.6

本指南说明如何在 Claude Code 中启用 karma hook，以及每个 hook 的实际作用。

## 快速开始

karma 已在你的 Claude Code `settings.json` 中配置了 7 个 hook。如果你从未见过 karma，只需知道：

**karma = 让 AI Agent 在长 session 中不遗忘你的核心方向**

当你设置了 `~/.claude/karma/sticky.yaml`，这 7 个 hook 就会自动生效。

---

## 7 个 Hook 速查表

### 1️⃣ UserPromptSubmit（已有）
**何时触发**：你提交 prompt 前  
**作用**：把你的核心方向注入到 prompt 头部  
**你会看到**：无特殊通知（后台工作）

### 2️⃣ PreToolUse（已有）
**何时触发**：Agent 要调 tool（Bash/Edit/Read）前  
**作用**：拦截违反你核心方向的工具调用  
**你会看到**：❌ 权限被拒（有理由说明）

### 3️⃣ PostToolUse（已有）
**何时触发**：Tool 调用成功后  
**作用**：跟踪 session 状态，中段重新强化关键方向  
**你会看到**：无通知（后台跟踪）

### 4️⃣ Stop（已有）
**何时触发**：Agent 要停下回复前  
**作用**：检测违反，强制 Agent 继续修正  
**你会看到**：⚠️ 提醒（Agent 继续推进）

### 5️⃣ PreCompact（v0.5.0 新加）
**何时触发**：自动 context compact 前  
**作用**：检查 compact 会不会淡化你的 sticky  
**你会看到**：💡 提醒（compact 前告知 sticky 会重注）

### 6️⃣ PostCompact（v0.5.0 新加）
**何时触发**：Context compact 后  
**作用**：验证 sticky 还活着，丢失则补注  
**你会看到**：✓ 验证通过 或 ⚠️ 补注摘要

### 7️⃣ SessionStart（v0.5.0 新加）
**何时触发**：Session 恢复或启动  
**作用**：重加载 sticky 配置，防过期复活  
**你会看到**：💬 Session 恢复时的状态提醒

### 8️⃣ SubagentStart（v0.6.0 新加）
**何时触发**：启动子 Agent  
**作用**：子 Agent 继承父 session 的 sticky 约束  
**你会看到**：📋 子 Agent 收到的约束列表

### 9️⃣ SubagentStop（v0.6.0 新加）
**何时触发**：子 Agent 完成  
**作用**：检查子 Agent 有无违反，溅回主 session  
**你会看到**：✓ 无违反 或 ⚠️ 违反列表

---

## 配置路径

### sticky 规则配置
```bash
~/.claude/karma/sticky.yaml        # 你的核心方向（手工编辑）
```

### Hook 脚本位置
```bash
~/.claude/hooks/karma_*.py         # 9 个 hook wrapper（自动生成）
```

### Claude Code 设置
```bash
~/.claude/settings.json             # 包含 hooks 配置（自动注入）
```

---

## 真实场景

### 场景 A：长 session 中 compact

**你的 sticky**：「长期正确优雅」/ 「失败要响亮」

**你在做**：多小时的开发任务，Agent 已累积 50+ turns

**发生的事**：
1. Claude Code 自动 compact context（保省 token）
2. **PreCompact hook 触发**：检查 sticky marker 会不会被冲掉 → 允许 + 提醒
3. Compact 执行
4. **PostCompact hook 触发**：检查 sticky 还在不在 → 若丢失补注
5. **SessionStart hook 触发**（compact 后）：重新加载 sticky 版本

**结果**：你的 3-5 条核心方向跨 compact 仍然活跃，Agent 不会因为 compact 突然忘掉方向

---

### 场景 B：使用子 Agent 并行

**你的 sticky**：「不阻塞前端」/ 「读代码前先写」

**你在做**：启动 2 个子 Agent 搜索代码 + 改 bug

**发生的事**：
1. **SubagentStart hook 触发**（子 Agent 启动）：父 sticky 传到子 context
2. 子 Agent 在隔离 context 中仍然看得到父方向约束
3. 子 Agent 完成
4. **SubagentStop hook 触发**（子 Agent 结束）：检查子 Agent 有无「读代码前先写」违反
5. 若有违反，提醒主 Agent 「这个子任务没遵守约束」

**结果**：子 Agent 不会脱离你的核心方向独立判断，跨隔离仍保持约束

---

## 常见问题

### Q：Hook 拒了我的操作？
**A**：看拒绝理由，这通常意味着你的 sticky 规则认为这是违反。有两种处理：
- 修改 sticky.yaml（调整规则）
- 明确告诉 Agent「绕过这个 check」（Agent 会记录并解释为什么）

### Q：Compact 后 Agent 忘了方向？
**A**：这是 v0.5.0 之前的已知问题。现在 PreCompact/PostCompact 会防护。若仍遗忘，这是 karma bug 而非 Agent bug，请报告。

### Q：子 Agent 能绕过我的 sticky 吗？
**A**：不能。SubagentStart 把约束传进去，SubagentStop 检查有无违反。但子 Agent 的 hook 是独立的（各自 session），所以覆盖范围是启发式的（关键词检测），不是万金油。

### Q：能关掉某个 hook 吗？
**A**：能。编辑 `~/.claude/settings.json`，在 `hooks` 部分删除或注释掉对应 event 即可。但建议先用一周看效果再删。

---

## 设计原则

所有 hook 都遵循这些原则：

1. **Fail open**：配置错 / 加载失败 → hook 不会卡 Agent，静默继续
2. **启发式检测**：用关键词/正则，不用 LLM 判断（保省 token）
3. **可见化**：违反/拦截都有提醒，不黑盒
4. **可调整**：你随时改 sticky.yaml，下个 turn 立刻生效

---

## 下一步

- 查看 `~/.claude/karma/sticky.yaml` 看你的规则
- 运行 `claude` 启动一个 session
- 执行违反操作看 hook 拦截效果
- 改进 sticky 规则以适应你的风格

**文档生成**：2026-05-14  
**支持的 hook**：9 个（v0.5.0 + v0.6.0）  
**官方协议参考**：https://code.claude.com/docs/en/hooks
