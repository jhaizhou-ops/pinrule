# pinrule — 项目协作宪章

**[🇬🇧 English](./CLAUDE.md) · [🇨🇳 中文（当前）](./CLAUDE.zh.md)**

## 一句话定位

pinrule 让用户最看重的几条方向，在 Agent 长任务里不被遗忘。

## 严格边界（不可破）

下面这些边界从 v1 教训提炼（详见 [karma-v1/ARCHIVE.md](https://github.com/jhaizhou-ops/karma-v1/blob/main/ARCHIVE.md)）。每一条都堵了一条已经证明代价昂贵的路：

### 不做的事

- ❌ **不自动蒸馏新规则** — 用户手工维护核心方向；LLM 蒸馏会产生噪声跟错位
- ❌ **不做 retrieval / cosine / scene** — 5-10 条全 always-on，不需要选择层
- ❌ **不抢记忆系统赛道** — 「关于用户的事实」交给客户端自带记忆
- ❌ **不依赖 LLM** — 纯工程（关键词 / 正则 / 计数）。决策是坚定的，不只是 v0 阶段
- ❌ **不做奖惩 / RL / 评分** — 行为提示不是 reward function；给规则打分会让模型优化分数而不优化行为

## 工作原则

### 1. 不针对当前用户作弊

pinrule 靠作者自用验证。为了让信号保持诚实，**绝不**为了短期顺手做这些：
- 把作者特定的规则写进默认模板
- 把作者实测的违反词硬编码进 hook
- 用作者的 session 数据训练任何东西

pinrule 的所有「默认」必须**跨用户合理** — 在 CLAUDE.md / Anthropic best practice 级别的通用程度上。

### 2. 永远从「我作为用户」视角设计

每个改动问自己：
- 一个第一次装 pinrule 的用户能 5 分钟上手吗？
- yaml 配置直白吗？需要看 docs 才懂吗？
- 第一次违反检测能让用户「啊原来如此」吗？

如果某功能只能作者用 → 砍掉。

### 3. 验证 > 精度数字

pinrule v1 沉迷追精度数字（67% 精度等），导致优化方向跑偏。

pinrule 的验证标准是**作者自用一周后能不能讲出 3 个具体案例**：
- 「某次长任务中我没说话 Agent 自己提醒了 X」
- 「某次 compact 后 Agent 还记得 Y」
- 「某次 Agent 想 Z 我看到 ⚠️ 提示就纠正了」

如果一周讲不出这种案例 → 假设错了，重新设计。

## 提交规范

提交消息说明做了什么 + 为什么。简短直接：

```
feat: rules.json 解析器 + schema 验证

支持单行 / 多行 preference，violation_keywords 数组
schema 校验 5-10 条上限 + id 唯一性
```

不需要复杂模板。但每个提交必须：
- 通过 lint 跟测试
- 不引入 LLM 依赖
- 默认保持小、可 review；用户明确要求「一次性 commit 完别拆碎」时一波到位也合理

## 汇报风格

完成任务 1-3 句话汇报：**做了什么 + 测试结果 + push 状态**。
不要：
- 列长 todo
- 展开 diff
- 解释工具机制
- 写「接下来可能做的事」超 3 行

## 自主执行授权

下面这些默认自主完成：
- ✅ 完成任务直接 git add + commit + push
- ✅ 跑测试 / 装依赖 / 修 lint
- ✅ 创建 issue / PR / comment
- ✅ 删已合并的临时分支

仍需事前确认：
- `git push --force` / `git reset --hard` 已发布的 commit
- gh repo archive / settings 修改
- 数据销毁（`~/.pinrule/` 清空）
- 跨仓库改动

## 失败处理

pinrule 第一原则是**诚实**：

- hook 没生效 → 明说，不伪装
- check 漏了真违反 → 记下来，不掩盖
- 自用一周没感觉到价值 → 明说重新设计，不为了维护 sunk cost 强行调

## 跟 v1 的关系

v1 在 [jhaizhou-ops/karma-v1](https://github.com/jhaizhou-ops/karma-v1) 归档。v1 可复用的资产（SEED 20 条、qwen3.5 helper 等）可以引用，但不强求复用。

v2 是认知重启，不是 v1 重构。如果某个组件设计变了，砍掉 v1 方案没关系。
