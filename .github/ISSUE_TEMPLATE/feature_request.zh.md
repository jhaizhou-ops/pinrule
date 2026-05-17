---
name: 功能 / 改进建议
about: 建议新功能 / 新规则场景 / 新 AI 客户端 backend
title: '[Feature] '
labels: enhancement
assignees: ''
---

## 你的痛点

具体描述场景。pinrule 设计原则是「用户痛点驱动」— 不接受「我觉得可能有用」类预防性建议。

## 提议方案

如有具体思路写出来。包括：
- 是规则层（用户自己写 `rules.yaml` 能解决吗）
- 还是 check 层（需要新工程层 `violation_check` 函数）
- 还是 hook 层（需要新 hook event 或改现有 hook 行为）

## 替代方案考虑过吗

pinrule 明确**不做**这些 — 看 README「试过但放弃的」段。如果你的需求落在这些边界外，说明为什么必须破例。

## 真实用户场景（不是猜测）

pinrule v1 的教训之一是「预防性设计」— 新功能必须有真实用户场景驱动，不接受「可能有用」类需求。
