# pinrule 性能数据测量口径

**[🇬🇧 English](./EVALUATION.md) · [🇨🇳 中文（当前）](./EVALUATION.zh.md)**

README 性能段提到的两个数字（hook 延迟、token 占比）是怎么测的。

---

## hook 延迟：通常 50-70ms

### 测的是什么

从 AI 客户端起 hook 子进程开始，到 pinrule 输出 hook JSON 结果的端到端时间。包含：

- Python 解释器冷启动（最大头 — Python 3.11 / 3.12）
- `pinrule` 包 import + 从 `~/.pinrule/rules.yaml` 加载规则
- hook handler 分发
- 工程层检查 + 状态更新 + stdout 写出

### 本机怎么复现

```bash
python scripts/measure_perf.py
```

输出每个 hook 在 100 次跑里的中位数 + p95 延迟。

### 为啥是「~50-70ms」一个区间不是一个数

机器差异很大：

- Apple M 系列 Mac：中位数约 49ms
- 低端 Linux 机器（社区反馈）：约 67ms
- 老 Intel Mac：约 80-100ms

AI 客户端协议预算是 200ms，目前所有实测机器都安全在内。

---

## token 占比：真 dogfood 实测约 2%

### 测的是什么

pinrule 每轮注入的 token 数除以本轮对话总 token（输入 + 输出）。包含：

- `SessionStart` hook：session 起手注入完整规则 baseline（默认 7 条规则模板约 1.8K token，一次性成本）
- `UserPromptSubmit` hook：每轮注入精简锚点（平均约 490 token，**经常 0 token** — 见下方「0 锚点直通」）
- `PostToolUse` hook：长上下文衰减时重新注入完整规则，只在累积 context 达到当前模型的衰减拐点（Opus 60K / Sonnet 40K / Haiku 30K）时触发

2% 是 **(pinrule 注入 token) / (对话总 token)** 在 pinrule 开发期间 30 个真实工作 session 上的平均值。

### 30 个 session 锚点 token 分布

- **60% 的 session：0 锚点 token** — 没有规则被偏离过，每轮锚点是空的（只有 `[pinrule 提醒]` 头部一行）
- **中位数 session：锚点列 1 条规则**（约 60 token）
- **最坏 session：锚点列 4 条规则 + 偏离标记**（每轮约 280 token）

0 锚点直通是平均数低的关键 — 大部分工作 turn 不触发任何规则，所以每轮成本基本为零。只有 Agent 真漂移了，下一轮锚点才会列出漂移的规则。

### 本机怎么复现

每个 session 把锚点 token 数写进 `~/.pinrule/violations.jsonl`。算自己数据的 token 占比：

```bash
pinrule audit --token-ratio    # 计划中的 helper；暂时用 scripts/measure_token_overhead.py
```

或者直接从 log 算（one-liner）：

```bash
python scripts/measure_token_overhead.py --sessions ~/.pinrule/session-state/
```

脚本输出每 session 拆分（只有 baseline / 有锚点 / 有 reinject）+ 占总对话 token 的比例。

---

## 警示

- **测量是 dogfood 内部口径**，不是同行评审的 benchmark。数字来自作者本人开发期间 30 个 session 的样本，你的实测会受这些因素影响：
  - 规则数量（规则越多 → baseline 越大、锚点列偏离规则时也越大）
  - 漂移频率（Agent 漂移越频繁 → 每轮锚点越大）
  - session 长度（session 越长 → 越可能触达衰减拐点）
- **目前没测客户端侧开销** — AI 客户端本身（Claude / Codex / Cursor）起 hook 子进程 + 读 stdout 也有延迟，pinrule 的 `scripts/measure_perf.py` 只测 pinrule 自己那部分。
- **token 占比没算客户端侧压缩** — 如果你的客户端在发给模型之前压缩长对话历史，实际 prompt 大小比 pinrule 注入的小。

如果你测自己 pinrule session 数字跟本文档差很多，那挺值得分享 — 欢迎提 Issue 反馈。
