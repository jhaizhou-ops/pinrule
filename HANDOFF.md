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

### 真实工作证据 — 本 session 累积 32 条违反

| sticky_id | 总 | 真违反典型 | 假阳性已修 |
|---|---|---|---|
| long-term-fundamental | 17 | hardcode / TODO 真注释 / git commit message hack 主语 | 描述类字面 / pattern 描述自身 |
| non-blocking-parallel | 6 | sleep / 长任务无 background | heredoc 数据字面 / commit message 字面 |
| read-before-write | 4 | 未 Read 就 Edit | (Write 后 record_read 修了) |
| loud-failure-with-evidence | 3 | git commit 无测试证据 | (闲聊用「应该」已加上下文豁免) |
| chinese-plain-no-jargon | 1 | jargon 多无中文 | — |
| no-testset-no-future-leakage | 1 | gold_cases 写 hash | — |

**全 6 个 sticky 都被触发过** — PRD 验证标准的实证。

### 测试状态

`pytest tests/` → **158/158 passed**（M3 加了 83 个新测试）
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
