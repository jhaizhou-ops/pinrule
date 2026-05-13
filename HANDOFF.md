# karma v2 交接 — 2026-05-14

> 给明天新 session 的快速接手指引。

## 当前状态：M2.2 完成，karma 已装到本机并真实工作

### 已交付里程碑

| | 内容 | commit |
|---|---|---|
| M0 | 项目初始化 + 4 个核心文档（README / PRD / ARCHITECTURE / CLAUDE.md）| 9cb460f |
| M1 | sticky.yaml + 加载器 + 2 个 hook 原型 + CLI 骨架 + 27 测试 | e6f4466 |
| M1.5 | pre_tool_use hook + non-blocking 触发词扩到 24 条 | bf29d73 |
| M2 | 6 条规则工程检测 + session_state 跟踪（30 新测试） | 484f267 |
| M2.1 | 适配 Claude Code 真实 hook 协议（PascalCase + permissionDecision 等） | b61deee |
| M2.2 | long_term check 按 tool 分组 + 关键词层加 markdown 豁免 | (本提交) |

### 真实工作证据

karma 已经在我的开发流程里**真实拦截**违反，并暴露了 3 个真实假阳性场景（都已根因修复）：

| 触发情境 | 是真违反吗 | 修复 |
|---|---|---|
| git commit 没跑测试 → 拦 sticky #4 | ✅ 真违反 | 跑 pytest 再 commit |
| Write 写代码含 magic if 分支 → 拦 sticky #1 | ✅ 真违反 | 改通用逻辑 |
| Write 文档里描述触发词字面 → 误判 | ❌ 假阳性 | check 按 tool 分组，文档豁免 |
| Edit 没读过文件 → 拦 sticky #8 | ✅ 真违反 | 先 Read 再 Edit |

详细 `.venv/bin/karma stats` / `.venv/bin/karma violations recent` 可查。

### 测试状态

`pytest tests/` → **74/74 passed**（含 6 个 check 函数 30+ 个测试 + session_state 7 + sticky/violations/hooks 34）

## 装好的资产

### 仓库（jhaizhou-ops/karma）

```
/Users/jhz/karma/
├── README.md / PRD.md / ARCHITECTURE.md / CLAUDE.md
├── HANDOFF.md (本文件)
├── data/sticky.example.yaml      # 6 条 sticky 模板
├── karma/
│   ├── sticky.py                 # yaml 加载 + 校验
│   ├── session_state.py          # 跨 hook 共享状态
│   ├── violations.py             # 违反记录 IO + 关键词检测
│   ├── checks/                   # 6 个工程检测函数
│   │   ├── long_term.py
│   │   ├── non_blocking.py
│   │   ├── chinese_plain.py
│   │   ├── evidence.py
│   │   ├── testset.py
│   │   └── read_first.py
│   ├── hooks/                    # 4 个 Claude Code hook entrypoint
│   │   ├── user_prompt_submit.py
│   │   ├── pre_tool_use.py
│   │   ├── post_tool_use.py
│   │   └── stop.py
│   └── cli.py                    # karma init / install-hooks / stats / doctor
├── tests/                        # 74 个测试
└── pyproject.toml                # entrypoint: karma
```

### 用户 home（`~/.claude/karma/`）

```
~/.claude/karma/
├── sticky.yaml                   # 用户 6 条 sticky
├── violations.jsonl              # 违反记录（append-only）
└── session-state/                # 每个 session 一个 JSON
```

### Claude Code hook（`~/.claude/hooks/`）

4 个 wrapper 已生成，配置已写到 `~/.claude/settings.json`。
备份在 `~/.claude/settings.json.before-karma`。

## 重启 session 后预期

新 session 启动时：
- 每次你发消息，Claude 看到 user prompt 前会先看到 sticky 6 条提示
- Agent 想跑阻塞命令 → 实时 deny
- Agent Edit / Write 前没 Read 过该文件 → 实时 deny
- Agent commit 前最近 session 没跑过测试 → 实时 deny
- Agent 说「完成」但最近没测试通过 → stderr 通知

## 接下来可推进的方向

按优先级：

### M3 候选 1：自用观察 1 周（推荐先做）

PRD 里写的「验证 > 精度数字」原则。
- 不加新功能，单纯用 karma + 记录 5 个具体案例
- 一周后判断 karma 是否真有用
- 自用过程中可能发现：触发词漏检 / 假阳性 / sticky 内容不准

### M3 候选 2：macOS 系统通知

之前讨论过「你在忙别的没注意」场景需要主动推送。
- 加 `karma/notify.py`：osascript 弹通知
- 配置开关 `~/.claude/karma/config.yaml`
- 严重度分级（高严重弹通知，低只 stderr）

### M3 候选 3：违反阈值 / 累积警报

同一 session 累积违反 N 次后强提示用户。

### M3 候选 4：触发词假阳性持续优化

今天遇到的「文档里描述触发词被拦」假阳性，M2.2 修了 long_term check + 关键词层加 markdown 豁免。还有：
- `chinese-plain-no-jargon` 触发词层假阳性（代码字段名引用算 jargon）
- 改 violation_keywords 用精确短语（不单个词）

## Claude 自己要注意的

karma 实时观察 Claude 的违反，特别这些点：
1. commit 前必跑 pytest — 不然 sticky #4 拦
2. Edit/Write 前必 Read 同文件 — 不然 sticky #8 拦
3. 不要 bash 阻塞类命令 — 用 run_in_background=True
4. 用直白中文不堆 jargon — 术语必须括号给中文解释

## 临时关掉 karma

```
.venv/bin/karma uninstall-hooks
# 或恢复备份
cp ~/.claude/settings.json.before-karma ~/.claude/settings.json
```

## 仓库链接

- karma v2：https://github.com/jhaizhou-ops/karma
- karma v1（归档）：https://github.com/jhaizhou-ops/karma-v1
