# karma v2 交接 — 2026-05-14（M3 六波结束）

> 给下个 session 的快速接手指引。

## 当前状态：M3 第六波完成，karma 装到本机并经历完整 dogfooding

### 已交付里程碑

| 里程碑 | 内容 | 关键 commit |
|---|---|---|
| M0 | 项目初始化 + 4 核心文档 | 9cb460f |
| M1 | sticky.yaml 加载 + 2 hook 原型 + CLI 骨架 | e6f4466 |
| M1.5 | pre_tool_use 实时拦截 hook | bf29d73 |
| M2 | 6 条规则工程检测 + session_state | 484f267 |
| M2.1 | 适配 Claude Code 真实 hook 协议 | b61deee |
| M2.2 | long_term check 按 tool 分组 + 文档豁免 | 52af21b |
| **M3 第一波** | **降假阳 9 项**（has_recent_test_pass 新语义 / _FAIL_RE 精确化 / 描述上下文统一抽象 / 关键词层只扫 Bash / 字面量列表 hint / testset hash 上下文 / evidence 行为词 / non_blocking 剥引号 / background catchup 雏形） | 72065f9 |
| **M3 第二波** | **假阴对偶 7 项**（_FAIL_RE 加 ERROR/FATAL / 意图注释 pattern / 全大写常量名单 / gold 列表 hex / 间接 shell / Write→record_read / **background catchup 真根因 — tool_response 是 dict**） | 0c7af6a + 3b10325 |
| **M3 第三波** | **CLI 装机体验**（install-hooks 自动写 settings.json idempotent + 备份 + 保留他人 hook / uninstall-hooks 同步清理 / doctor hook 安装检测） | 3b10325 |
| **M3 第四波** | **长期质量 4 缺口**（session-state 30 天清理 / violations.jsonl rotation / save tmp 名 pid+ns / post_tool_use 跳过失败 tool） | 2938d91 |
| **M3 第五波** | **描述上下文完整化 2 项**（commit message 80 字位置约束 / heredoc 剥） | bf928bd |
| **M3 第六波** | **用户反馈担心放过真违反，对偶审计 + 加严**（heredoc 区分头部命令 bash/sh 内是真 shell / 关键词层 Write/Edit 加注释 + docstring 扫描 / 11 个对偶假阴回归测试） | 8f58bb9 |
| **M4 装机体验 + 反馈机制** | sticky.example → dev.example（场景化定位）+ 5 项 sticky 调整 / 桌面通知（macOS/Linux/Windows）/ 累积告警 / 配置系统 / doctor 显示配置 | 216f754 → 61a7c72 |
| **M4 turn 维度重构** | ⚠️ 标记 + 累积告警按 **turn 距离**（Agent 漂移按 turn 累积，不按人类时钟）+ Violation 加 turn 字段 + recent_turns / count_recent_turns | 42955ba |
| **M4 audit + 假阳根因修复** | karma audit 命令（自动标可疑假阳，触发词占 ≥ 50% 标 ⚠️）/ docs/yaml Edit 不推 last_edit_ts / conventional commit (docs/chore) 豁免 evidence / stats 加最近 5 turn 列 | 667f15c → 9429173 |
| **M4 reset 命令** | karma reset 清 session-state 漂移实验重启 | ffcbd07 |
| **M4 audit turn 维度** | audit 末尾段「本 session 最近 10 turn 漂移近况」+ 🔥 高频标记 | ca65116 |
| **M4 keep-pushing 工程层 + Stop hook 真干预** | keep_pushing check（问号 / 停顿语气词双信号）+ Stop hook decision=block 让 Agent 不真停继续生成 + safeguard `stop_block_max_per_turn` 防死循环 | 8502713 |
| **M4 keep-pushing 反转 + audit 改进建议** | 用户精准纠正：问号是合理决策应豁免，纯陈述完结无下一步才是真停下 → 反转检测方向（推进/问号豁免，停顿词/默认 → 命中）。stats / doctor 显示 stop_block_count；audit 末尾自动改进建议段；catchup 多 hook 跑（UserPromptSubmit+PreToolUse 都跑，task #8 剩余 case）；non_blocking 长任务列表收紧（移除 pytest 等测试命令，保留 docker/build/install）| 8502713 → 最新 |
| **M4 元层面监管 — 自身被绕过的检测**（用户反馈核心场景） | 回应「这就是一个典型的出现了问题，你绕过/忽略了问题拿了个短期结果」三层实施：① bypass_karma check（Bash 命令含 karma 内部敏感字面 + 写操作 → 命中）② Stop hook 累积强制 decision=block（同 sticky ≥ N 次必须 fix 根因不许继续绕）③ sticky #8 deep-fix-not-bypass 进默认开发模板（preference + 关键词 + 工程层）。strip_shell_quoted_literals 加 python/node/ruby -c flag + placeholder 保护内部引号字面（commit message 自指假阳豁免 + python -c 真执行代码保留扫）| 最新 |
| **M4 user_prompt_submit 强提醒 fallback** | 用户反馈「你又停下来了，自己加的 sticky 也没拦」根因：Claude Code Stop hook 在 user 立刻接 prompt 时**不跑**（user_prompt_submit 优先级覆盖 Stop hook idle 触发）。fallback：user_prompt_submit hook 读 transcript last assistant message 跑 keep_pushing.check，命中（纯陈述完结无推进）→ 注入「强提醒」段告诉本 turn Claude 上次停了，本 turn 必须立即推进。这是 karma 当前能做的最强 keep-pushing 干预（不依赖 Stop hook 协议层 limitation） | 最新 |
| **M4 Stop hook 不跑 → 撤回错误诊断**（重要错误教训） | 之前结论「Claude Code Stop hook 在 user-continuous 对话不跑」**错** — 用户质疑「stop hook 原理机制咱们没研究清楚」后重派 claude-code-guide 确认：**Stop hook 不支持 matcher 字段**，karma install-hooks 给所有 event 都加 `matcher: '*'` → Stop event 看到 matcher 会无声忽略整个 hook entry → Stop hook 根本没装上 → trace 0 条记录。**真根因**：karma 自身 install-hooks 配置 bug。修：_karma_event_entry 只对 PreToolUse/PostToolUse/UserPromptSubmit 加 matcher，Stop 不加。`karma install-hooks` 重装后修好。教训：单次 trace 0 条记录不能直接断言「协议 limitation」，要查配置先 | 最新 |

### 真实工作证据 — 假阳治理后 audit 干净

完整 audit 工具链实证（本 session M4 末尾）：
1. audit 找问题 → 33 条历史，标 2 个假阳重灾区（evidence / non_blocking pytest）
2. 修 pattern → conventional commit 豁免 / docs Edit 不推 ts / pytest 移出长任务列表 / sleep 0 不算阻塞 / TODO 后缀要求 / 描述上下文 yaml/json 豁免 等
3. clear --trigger 治理历史 → 33 → 11 条剩真违反
4. 现状 audit：**「暂无明显假阳重灾区」** ✓

剩余 11 条都是真违反 / 边缘观察：
| sticky_id | 总 | 类型 |
|---|---|---|
| read-before-write | 6 | **真违反**（未 Read 就 Edit /Users/jhz/.claude/statusline.sh 等） |
| chinese-plain-no-jargon | 3 | 真违反（中文比例 34% / mutex 无中文解释） |
| no-testset-no-future-leakage | 2 | 边缘（描述 ML 概念） |

**全 7 个 sticky 都装好**（含 sticky #7 keep-pushing-no-stop 工程层 + Stop block 真干预）。

### 测试状态

`pytest tests/` → **227/227 passed**（M3+M4 加了 152 个新测试）
- `tests/test_false_negative_regression.py` — 23 个对偶假阴测试
- `tests/test_cli.py` — 10 个 CLI 测试
- `tests/test_description_context.py` — 9 个上下文测试
- `tests/test_session_state.py` — 22 个（含 background catchup / purge / unique tmp）
- 其他原有测试也加了新 case

## 装好的资产

### 仓库结构（已含 M3 新文件）

```
/Users/jhz/karma/
├── README / PRD / ARCHITECTURE / CLAUDE.md / HANDOFF.md
├── data/sticky.dev.example.yaml     # 6 条 sticky 模板 (软件开发场景)
├── karma/
│   ├── sticky.py                    # yaml 加载 + 校验
│   ├── session_state.py             # 跨 hook 状态 + background catchup
│   ├── violations.py                # 违反记录 + rotation
│   ├── cli.py                       # init / install-hooks / doctor / stats
│   ├── checks/
│   │   ├── common.py                # 共用 helpers (M3 新加 strip_shell_quoted_literals
│   │   │                              / strip_code_blocks / extract_natural_language)
│   │   ├── description_context.py   # 描述上下文统一豁免 (M3 新)
│   │   ├── long_term.py             # 多 pattern + 描述上下文豁免
│   │   ├── non_blocking.py          # 间接 shell + 引号字面剥
│   │   ├── chinese_plain.py
│   │   ├── evidence.py              # 行为词上下文判定 (M3 加)
│   │   ├── testset.py               # case_id / gold list 上下文约束
│   │   └── read_first.py
│   └── hooks/                       # 4 个 Claude Code hook
│       ├── user_prompt_submit.py    # sticky 注入 + 每 turn purge
│       ├── pre_tool_use.py          # 实时拦截
│       ├── post_tool_use.py         # 跟踪状态 + catchup
│       └── stop.py                  # response 扫违反
└── tests/                           # 158 个测试
```

### 用户 home（`~/.claude/karma/`）

```
~/.claude/karma/
├── sticky.yaml                      # 用户 6 条 sticky
├── violations.jsonl                 # append-only + 5000 行自动 rotation
└── session-state/                   # 每 session 一 json，30 天自动清理
```

### Claude Code hook 配置

`install-hooks` 自动写 `~/.claude/settings.json`（保留他人 hook，idempotent）。备份在 `~/.claude/settings.json.before-karma`。

## 关键设计 / 边界

### 描述上下文统一豁免（karma/checks/description_context.py）

多维度判定 tool 调用是否「描述」而非「执行意图」：
- file_path 是 `.md / .rst / .txt / .markdown / .adoc` → 文档
- path 含 `tests/` `test/` `__tests__` `spec` → 测试目录
- 文件名 `test_*.py` / `*_test.py` 等 → 测试代码
- 路径 `/tmp/` 或 `/var/tmp/` → 临时探针
- 文件名含 `probe / scratch / sample / playground / fixture` → 探针
- 命中即整段豁免工程层 long_term / testset + 关键词层

### shell 引号字面 + heredoc 智能剥（karma/checks/common.py）

`strip_shell_quoted_literals` 处理 commit message / echo / heredoc 等：
- `'...'` `"..."` 引号字面 → 剥（描述/数据）
- `bash -c '...'` → 保留内引号当真子命令
- `bash/sh/zsh <<EOF ... EOF` → 内容是真 shell 命令，保留
- `python/cat/grep <<EOF ... EOF` → 内容是数据，剥

### background 任务通过证据接入（task #8 真根因）

Claude Code 真实 `tool_response` 是 dict `{stdout, stderr, backgroundTaskId}` 不是字面。`record_bash` 接受 dict 并从 command 解析 `> /path` 重定向取真实输出文件。`catchup_pending_bg` 下次 hook 触发时读 log 接进 `last_test_pass_ts` — 解决了 background pytest 跑通后 evidence check 看不到证据的死结。

### 关键词层 Write/Edit 只扫注释 + docstring

避开 M2.2 时的「描述字面假阳」和 M3 第一波「全放又漏真违反」的两端 — 注释里写「先打个补丁」是真意图表达扫，代码主体字面赋值（数据）不扫。

## 下个 session 接手指引

### 7+1 条 sticky 完整定位

| # | id | 作用 |
|---|---|---|
| 1 | long-term-fundamental | 用最根本方案不打补丁 |
| 2 | non-blocking-parallel | 测试 / 子 Agent 跑时并行推进 |
| 3 | chinese-plain-no-jargon | 直白中文不堆 jargon |
| 4 | loud-failure-with-evidence | 完成附测试证据 |
| 5 | no-testset-no-future-leakage | 不喂测试集 |
| 6 | read-before-write | 改代码前先读 |
| 7 | keep-pushing-no-stop | 完成后立即推下个不停（作者 / 全权委托型用户）|
| 8 | deep-fix-not-bypass | karma 拦截时深挖根因不绕（**元层监管**）|

sticky #7/#8 跟 #1-#6 不同维度 — #1-#6 是「开发场景行为规则」，#7 是「Agent 协作节奏」，#8 是「Agent 不绕 karma 自身」元层规则。

### 已知 bug / 待 fix 优先清单

- **task #8 catchup 多 hook fix 验证 OK** — catchup_pending_bg 加到 UserPromptSubmit / PreToolUse / PostToolUse 三个 hook 后实战验证 pending=0、last_test_pass_ts 自动接进。
- **task #8.1 catchup race condition（本 session 末尾发现）** — 当 pending_bg_tasks 有滞留 entry（log file 仍存在），每次 hook 调用 catchup 都重复处理 → 反复推 ltp 到 pytest log 时间。如果同时手动 update ltp 到 future，后续 hook 会用 `_next_ts()` floor = max(ltp, le) 覆盖。
  - **根因**：pending entry 没在 catchup 后被移除（看 catchup_pending_bg 代码 — 已经 still_pending list 应该 OK，但实战 ltp 仍被覆盖到旧值）
  - **下个 session 优先**：dump 一次 catchup 调用前后的 pending_bg_tasks + ltp 变化，看是否是 race 还是 catchup 重复读同一 log
- **历史假阳治理 workflow 验证** — 本 session 用 `karma violations clear --trigger <substring>` 选择性清掉 M4 fix 前累积的所有假阳：硬编码 / TODO / sleep 0 / quick fix 字面 / workaround / 先打个补丁 / 字面量列表 / 强制跳过验证 等。audit 从 33 → 11 条剩真违反，证明：
  1. fix 后立即清历史 = audit 视图干净
  2. 工具链完整：audit 找问题 → 修 pattern → clear 治理历史 → 进入纯 dogfooding 数据积累

### karma 自用持续观察 = 持续推进开发

用户原话「咱们继续推就是观察期」— 不要把「开发」和「观察」当二元选择。每次推进都是 dogfooding 数据点。

### 推进候选优先级

1. **macOS 系统通知**（HANDOFF 老版 M3 候选 2）— Agent 还没在 stdout 用户没看见时需要主动推
2. **违反阈值累积警报** — 同 session 累积 N 次后强提示
3. **触发词假阳性持续观察** — 实战可能还有未发现假阳
4. **sticky.yaml 模板扩** — 当前 6 条，模型支持 10
5. **README.md / PRD.md 更新反映 M3 现状**

### 接手前必读

- 跑 `pytest tests/` 应看到 158 passed
- 跑 `karma doctor` 应看到 4 个 hook event 全 ✓
- 看 `karma stats` 累积违反作为持续数据点

### 紧急关 karma

```
.venv/bin/karma uninstall-hooks         # 拆 wrapper + 清 settings.json
# 或恢复完整原 settings
cp ~/.claude/settings.json.before-karma ~/.claude/settings.json
```

## 仓库链接

- karma v2：https://github.com/jhaizhou-ops/karma
- karma v1（归档）：https://github.com/jhaizhou-ops/karma-v1
