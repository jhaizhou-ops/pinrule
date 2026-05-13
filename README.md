# karma

> **让 Agent 不在长任务中遗忘你最重视的几条原则。**

karma 是 Claude Code 的一个轻量插件，把你**反复强调过但 Agent 总忘**的几条核心方向偏好「钉」在每次对话最显眼的位置，并在 Agent 违反时立即提醒你。

## 这是什么

你跟 Claude 长会话推进任务时，是不是经常遇到：
- 你**反复强调过**「用普适长期方案不要打补丁」，但 Agent 几个 turn 后又开始打补丁
- 你说过「不要前端阻塞 — 测试跑着我们继续别的事」，但 Agent 又默认 sleep 等
- 你要求「多 Agent 并发」，但 Agent 用了一会儿又串行了
- 你强调「用中文不要技术术语」，但 compact 后又开始 English + jargon

这些不是 Agent **不知道**你的偏好（你说过），是 **「在长上下文中漂移 + compact 后压缩成模糊词」**。

karma 解决的就是这个 — 不让你的最高优先级方向被淹没。

## karma 不做的事

为避免重蹈 [karma v1](https://github.com/jhaizhou-ops/karma-v1) 覆辙，karma 明确**不做**这些：

- ❌ **不自动蒸馏新规则** — 用户自己维护核心方向 (5-10 条上限)
- ❌ **不做 retrieval / cosine 召回** — 5-10 条全 always-on，不需要选
- ❌ **不抢记忆系统赛道** — 「关于用户的事实/偏好」交给 Claude Code auto-memory
- ❌ **不做奖惩 / 评分** — karma 是行为提示不是 RL

## 三层方案

### 1. 核心方向永驻

用户手工维护 `~/.claude/karma/sticky.yaml`，列 5-10 条**最高优先级方向**：

```yaml
- id: long-term-thinking
  preference: 用普适长期正确优雅方案，不打补丁不作弊不短视
  violation_keywords: [先打个补丁, 快速绕过, 硬编码, 先这样, 短期目标]

- id: no-blocking-frontend
  preference: 不要前端阻塞 — 测试 / 子 Agent 跑步时同步推进其他事
  violation_keywords: [等测试完, 等子 Agent, 先 sleep, 我先等]

- id: chinese-only-output
  preference: 用直白中文，非技术黑话
  violation_check: english_density_above_threshold

# ... 5-10 条上限
```

### 2. user_prompt_submit hook

每次用户发消息时，Claude Code hook 自动把这 5-10 条**前置注入** user_text 前面：

```
[karma sticky — 你的最高优先级方向]
1. 用普适长期正确优雅方案
2. 不要前端阻塞
3. 用直白中文
...

[你的实际消息]
开始下一步吧
```

跨 session / 跨 compact 永远存在，token 成本可控 (~150 token/turn)。

### 3. post_response hook

Agent 响应后，hook 扫违反触发词。检测到违反：
- 用户得到轻量提醒（CLI 角标 / 通知）
- 下次 user_prompt_submit 时**强化提示**该规则（加粗 + 标 RECENT VIOLATION）

## 安装

（待实施）

## 状态

- [PRD.md](./PRD.md) — 完整产品需求
- [ARCHITECTURE.md](./ARCHITECTURE.md) — 技术架构
- [karma v1 归档](https://github.com/jhaizhou-ops/karma-v1) — v1 探索过程与反思

karma v2 仍在设计阶段。第一个 milestone 是用 1 周时间做最小验证，作者自用观察是否真能减少 Agent 在长任务中的方向漂移。
