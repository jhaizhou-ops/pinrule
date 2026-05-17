---
name: Bug 报告
about: 报告 pinrule 的 bug / 假阳 / 装机问题 / hook 失效
title: '[Bug] '
labels: bug
assignees: ''
---

## 你遇到什么

简短描述问题。如果是**假阳**（pinrule 误拦合法操作）请贴 `pinrule audit` 输出含 `⚠️ 可能假阳` 标记的 trigger。

## 复现步骤

1. 装机 `pinrule install-hooks ...`
2. ...
3. 看到的错误 / 不预期行为

## 状态（用 `pinrule doctor` 输出）

```
（贴 `pinrule doctor` 完整输出）
```

## 环境

- pinrule 版本: （`pinrule --version`）
- AI 客户端: Claude Code / Codex CLI / Gemini CLI（含版本）
- OS: macOS / Linux / WSL
- Python: （`python --version`）
- Shell: zsh / bash / fish

## 关键日志（如有）

如果 hook 输出 schema 错或装机失败，贴 stderr / Claude Code UI 报错段。
