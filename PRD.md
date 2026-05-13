# karma 产品需求文档

## 用户痛点（实证）

karma v2 的设计起点是一个**真实长期痛点**，用户原话：

> 我不停强调但是 Agent 一再触犯到的规则就是：Agent 采取的方法总是短视、作弊、逐利和补丁性的，
> 而我一直追求根本、长期、普适和正确的，这需要我不断的重复和强调，但 Agent 仍然在硬编码、
> 作弊、追求短期目标的达成而忘掉长期目标。

> 还有比如我非常坚持不要前端阻塞开发和测试，但是过几个 turn 以后 Agent 就开始不顾后面
> 还有没有任务，全都是默认阻塞前端的无意义等待。

> 还有比如我非常追求效率，一再要求要并发多 Agent 开发和测试，以及不断探求更高效的工作方式，
> 但是 Agent 很快就会遗忘。

> 还有比如我只看中文和非技术背景，但 Agent 压缩后就会开始默认输出英文，并且内容越来越
> 技术化直到我完全看不懂。

## 痛点本质

这些例子有同一个模式：

| 特征 | 描述 |
|---|---|
| 类型 | 是「**长期方向偏好**」不是事实记忆（不是「我家狗叫 X」） |
| 用户行为 | 反复强调过（5+ 次），不是 Agent 没听到 |
| Agent 当下行为 | 听到时配合做对，记住几个 turn |
| Agent 中期行为 | 几个 turn 后注意力漂移，开始违反 |
| 跨 session/compact | 上下文压缩后完全丢失 |

**核心问题**：不是 Agent **不知道**用户偏好，是 **「在长上下文中注意力漂移 + compact 后压缩成模糊词」**。

## 为什么现有方案不够

| 方案 | 不够的地方 |
|---|---|
| **CLAUDE.md** | 写了但被任务细节淹没，Agent 注意力分散；compact 后压成模糊词；项目级不跨项目 |
| **Claude Code auto-memory** | 偏「事实记忆」(我用 Mac / 我喜欢 X)，不专门处理「行为方向偏好」；召回时机不对 |
| **karma v1** | 试图自动蒸馏 + retrieval — 但真实痛点是「永驻」而非「召回」，方向错位 |

## karma v2 设计哲学

### 1. 核心方向「钉死」而不是「检索」

用户的最高优先级方向（5-10 条上限）**always-on**，每个 user_prompt 前面都注入。

不需要 cosine / scene 选哪条 — 因为这些都是**用户公开声明的最高优先级**，每次都该看到。

### 2. 用户掌控（不自动蒸馏）

karma 不学新规则。用户手工列「核心方向」，karma 只负责让它们 **always 在 Agent 注意力最高的位置**。

这避免了：
- LLM 蒸馏的噪声 / 错位 / 过拟合特定用户
- 「关于用户的事实」跟「Agent 行为偏好」赛道混淆

### 3. 违反检测 → 反馈闭环

retrieve 的局限：把规则放进 context 让 Agent「看一眼」 — 但看见不等于优先级高。

karma 用 **「行为违反检测」** 做反馈：
- Agent 响应后，hook 扫触发词 / 正则 / 简单分类
- 检测到违反 → 通知用户 + 下次注入时该规则**显式标 RECENT_VIOLATION**
- Agent 看到 RECENT_VIOLATION 提示会比纯描述更注意（实证未验证，是核心假设）

### 4. 不抢任何已有赛道

- 事实记忆 / 偏好检索 → Claude Code auto-memory / mem0 等
- 项目级规则 → CLAUDE.md
- 工作流自动化 → Claude Code hooks 直接做

karma 只做**「核心方向永驻 + 违反检测」**这一件事。

## 功能需求（v0 MVP）

### F1. 核心方向配置

- 用户在 `~/.claude/karma/sticky.yaml` 定义 5-10 条
- 字段：`id` / `preference` (一句话规则) / `violation_keywords` (触发词数组) / 可选 `violation_check` (检查函数名)
- karma CLI: `karma sticky add / remove / list / edit`

### F2. user_prompt_submit hook

- 每次 user_prompt_submit，hook 读 sticky.yaml
- 在 user_text 前面注入 sticky 提示块
- 格式人类友好：
  ```
  [karma sticky — 用户最高优先级方向，请始终遵守]
  1. 用普适长期正确优雅方案
  2. 不要前端阻塞
  ...

  [用户当前消息]
  原 user_text
  ```
- RECENT_VIOLATION 规则在该规则前标 `⚠️` 或额外加一句「(上次违反)」

### F3. post_response hook

- Agent 响应后，hook 扫所有 sticky 的 `violation_keywords` / `violation_check`
- 匹配到 → 记录到 `~/.claude/karma/violations.jsonl`
- CLI 提醒（macOS 通知 / iTerm angle bracket / 简单 stderr 写）
- 下次 user_prompt_submit 该规则标 RECENT_VIOLATION

### F4. 自用观察工具

- `karma stats` 显示每条规则违反次数、最近违反时间
- 验证 karma 是否真减少了 Agent 的方向漂移

## 验证标准（v0）

karma v0 不追求精度数字 — 追求 **作者自用是否真感觉到「Agent 在长任务中少犯方向错」**。

观察指标（一周自用）：
1. **长任务中违反触发频次** — 装 karma 前 vs 后对比（粗略印象）
2. **用户重复强调同一规则次数** — 减少
3. **compact 后 Agent 是否还记得核心方向** — 通过几次 long-session 测试

如果一周自用没明显改善 → karma 假设错了，需要进一步重新设计。

## 非功能性要求

- **不能用 sonnet** — 严格继承 v1 LLM 授权规则
- **本地 ≤4 并发的小型任务可用 mlx Qwen3.6** — 但 karma v0 设计上不需要 LLM
- **Hook 性能** — user_prompt_submit hook 必须 < 50ms（不能拖 Agent 响应）

## v0 范围明确说不做

- ❌ 自动蒸馏新 sticky 规则
- ❌ retrieval / cosine / scene 路由
- ❌ 多用户协作 / 同步
- ❌ Web UI / 图形配置（CLI 编辑 yaml 够了）
- ❌ 跨 IDE / 跨 AI 平台支持（先 Claude Code only）
- ❌ 评测体系 / accuracy 指标（自用观察够了）

## 后续可能（v1+）

如果 v0 验证 karma 真的有用：

- **跨 IDE/平台**：Cursor / Windsurf / Codex 支持
- **团队级 sticky**：团队共享一份核心方向（如 SWE 团队的代码风格）
- **行为违反检测增强**：从「关键词」升级到「LLM-judged」（但本地小模型，零外发）
- **核心方向模板市场**：跨用户分享好用的 sticky 集（不强制 karma 自动用，仅参考）

但**v0 不做这些**。先验证最小假设。
