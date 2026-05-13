# karma v2 — 项目协作宪章

## 一句话定位

karma = 让 Agent 不在长任务中遗忘用户最重视的几条核心方向。

## 严格边界（不可破）

karma v2 从 v1 失败中学到的明确边界（详 [karma-v1/ARCHIVE.md](https://github.com/jhaizhou-ops/karma-v1/blob/main/ARCHIVE.md)）：

### 不做的事

- ❌ **不自动蒸馏新规则** — 用户手工维护核心方向，避免 LLM 蒸馏噪声 / 错位
- ❌ **不做 retrieval / cosine / scene** — 5-10 条全 always-on，不需要选
- ❌ **不抢记忆系统赛道** — 「关于用户的事实」交给 Claude Code auto-memory
- ❌ **v0 不用 LLM** — 全工程化（关键词 / 正则 / 计数）
- ❌ **不做奖惩 / RL / 评分** — 行为提示不是 reward function

### 严格 LLM 授权（如果 v1+ 用 LLM）

继承 v1 教训：

- ✅ 本机 mlx Qwen3.6 — 小型任务 + ≤4 并发
- ✅ OpenRouter qwen3.5-flash-02-23 nothinking — 唯一允许远程
- ❌ sonnet / claude API — 禁用

## 工作原则

### 1. 不针对当前用户作弊

karma v2 验证方法是作者自用。**绝不**为了让自己用得舒服而：
- 把作者特定的 sticky 规则写进默认模板
- 把作者实测的违反词列表硬编码进 hook
- 用作者的 session 数据训练任何东西

karma 的所有「默认」必须**跨用户合理**（CLAUDE.md / Anthropic best practice 级别的通用）。

### 2. 永远从「我作为用户」视角设计

每个改动问自己：
- 一个第一次装 karma 的用户能 5 分钟上手吗？
- yaml 配置直白吗？需要看 docs 才懂吗？
- hook 装上后第一次违反检测能让用户「啊原来如此」吗？

如果某功能只能作者用 → 砍掉。

### 3. 验证 > 精度数字

karma v1 沉迷追精度数字（67% inj 精度等），导致优化方向跑偏。

karma v2 的验证标准是**作者自用一周后能不能讲出 3 个具体案例**：
- 「某次长任务中我没说话 Agent 自己提醒了 X」
- 「某次 compact 后 Agent 还记得 Y」
- 「某次 Agent 想 Z 我看到 ⚠️ 提示就纠正了」

如果一周后讲不出这种案例 → karma 假设错，重新设计。

## 任务管理

karma v2 不维护复杂 task list。一次 milestone 一个 PR 思维。

### 当前 milestone: M0 骨架

- 项目初始化 ✓
- sticky.yaml schema
- 2 个 hook 原型
- karma CLI 骨架
- 5-10 条种子 sticky

## 提交规范

提交消息说明做了什么 + 为什么。简短直接：

```
feat: sticky.yaml 解析器 + schema 验证

支持单行 / 多行 preference，violation_keywords 数组
schema 校验 5-10 条上限 + id 唯一性
```

不需要复杂模板。但每个提交必须：
- 通过 lint
- 不引入新的 LLM 依赖（v0 阶段）
- 不超过 ~200 行（保持改动小可 review）

## 汇报风格

完成任务 1-3 句话汇报：**做了什么 + 测试结果 + push 状态**。
不要：
- 列长 todo
- 展开 diff
- 解释工具机制
- 写「接下来可能做的事」超 3 行

## 自主执行授权

继承 v1 授权：
- ✅ 完成任务直接 git add + commit + push
- ✅ 跑测试 / install 依赖 / 修 lint
- ✅ 创建评论 issue / PR
- ✅ 删除已合并的临时分支

仍需事前确认：
- `git push --force` / `git reset --hard` 已发布提交
- gh repo archive / settings 修改
- 数据销毁 (~/.claude/karma/ 清空)
- 跨仓库改动

## 失败处理

karma v2 第一原则是**诚实** — 跟 v1 一样：

- 如果 hook 没生效，明说，不伪装
- 如果违反检测漏了真违反，记下来，不掩盖
- 如果作者自用一周后没感觉到价值，明说重新设计，不为了维护 sunk cost 强行调

## 跟 v1 的关系

v1 在 [jhaizhou-ops/karma-v1](https://github.com/jhaizhou-ops/karma-v1) 归档保留。
任何 v1 的可复用资产（SEED 20 条 / qwen3.5 helper / 等）可以 reference，但**不强求复用**。

v2 是认知重启，不是 v1 重构。如果某些组件设计变了，砍掉 v1 的方案没关系。
