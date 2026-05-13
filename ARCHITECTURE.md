# karma 技术架构

## 总览

```
┌──────────────────────────────────────────────────────────┐
│  ~/.claude/karma/                                        │
│  ├── sticky.yaml           ← 用户手工维护核心方向          │
│  ├── violations.jsonl      ← 违反历史 (append-only)        │
│  └── stats.json            ← 聚合统计 (CLI 用)             │
└──────────────────────────────────────────────────────────┘
                       │
                       │ 读
                       ▼
┌──────────────────────────────────────────────────────────┐
│  Claude Code hooks (~/.claude/hooks/)                    │
│  ├── user_prompt_submit.py  ← 前置注入 sticky            │
│  └── post_response.py        ← 扫违反 + 记录              │
└──────────────────────────────────────────────────────────┘
                       │
                       │ inject / detect
                       ▼
              ┌─────────────────────┐
              │   Claude Code       │
              │   (Agent loop)      │
              └─────────────────────┘
```

## 数据模型

### sticky.yaml

```yaml
# 用户手工维护，5-10 条上限
- id: long-term-thinking            # 短 slug，CLI 用
  preference: |
    用普适长期正确优雅方案，不打补丁不作弊不短视。
    遇到复杂问题深挖根因，不绕过；评估方案时优先长期可维护性。
  violation_keywords:                # 简单触发词列表
    - 先打个补丁
    - 快速绕过
    - 硬编码
    - 先这样
    - 短期目标
  # 可选高级检测（v1+ 实施）
  # violation_check: english_density_above_0.3
```

字段说明：
- `id`: kebab-case 短 slug，CLI 用 `karma sticky remove long-term-thinking`
- `preference`: 多行允许，建议 30-80 字描述
- `violation_keywords`: 数组，**任一匹配**算违反（不区分大小写）
- `violation_check` (v1+): 命名内置检测函数（如 `english_density_above_X`）

### violations.jsonl

```jsonl
{"ts": 1715617200, "session_id": "abc123", "sticky_id": "long-term-thinking", "trigger": "硬编码", "snippet": "...让我先 硬编码 这个值快速验证..."}
{"ts": 1715617250, "session_id": "abc123", "sticky_id": "no-blocking-frontend", "trigger": "等测试完", "snippet": "...先 等测试完 再继续下一步..."}
```

append-only，CLI 用 `tail` 看最近违反。

### stats.json (cache)

```json
{
  "long-term-thinking": {"count_total": 23, "count_7d": 5, "last_ts": 1715617200, "recent_triggers": ["硬编码", "先这样", "硬编码"]},
  "no-blocking-frontend": {"count_total": 12, "count_7d": 3, "last_ts": 1715617250}
}
```

由 CLI / hook 异步聚合，**hook 不读不写**（避免 IO 拖延 user prompt submit）。

## Hook 集成

karma 通过 Claude Code 标准 hooks 接入，不需要 fork / patch Claude Code。

### user_prompt_submit hook

时机：每次用户发消息 Claude Code 把消息送给模型**之前**调用。

实现：`~/.claude/hooks/karma_user_prompt_submit.py`

```python
#!/usr/bin/env python3
"""karma user_prompt_submit hook — 前置注入 sticky 提示。

输入：从 stdin 读 hook payload (含 user_text)
输出：修改后的 user_text 到 stdout

性能预算：< 50ms（影响每个 user prompt 响应）
"""
import json, sys, time, yaml
from pathlib import Path

STICKY_PATH = Path.home() / ".claude" / "karma" / "sticky.yaml"
VIOLATIONS_PATH = Path.home() / ".claude" / "karma" / "violations.jsonl"
RECENT_VIOLATION_WINDOW_SEC = 24 * 3600  # 24h 内的违反算 recent

def load_sticky():
    if not STICKY_PATH.exists():
        return []
    return yaml.safe_load(STICKY_PATH.read_text()) or []

def recent_violations():
    """返回 sticky_id → 最近违反时间戳的 dict（24h 内）。"""
    if not VIOLATIONS_PATH.exists():
        return {}
    cutoff = time.time() - RECENT_VIOLATION_WINDOW_SEC
    recent = {}
    # 反向读最近 200 行就够（违反不会太频繁）
    lines = VIOLATIONS_PATH.read_text().splitlines()[-200:]
    for line in lines:
        try:
            v = json.loads(line)
            if v["ts"] >= cutoff:
                sid = v["sticky_id"]
                recent[sid] = max(recent.get(sid, 0), v["ts"])
        except (json.JSONDecodeError, KeyError):
            continue
    return recent

def main():
    payload = json.load(sys.stdin)
    user_text = payload.get("user_text", "")

    sticky = load_sticky()
    if not sticky:
        sys.stdout.write(user_text)  # 没配 sticky，原样返回
        return

    recent = recent_violations()
    lines = ["[karma sticky — 用户最高优先级方向，请始终遵守]"]
    for i, s in enumerate(sticky, 1):
        marker = " ⚠️ 上次违反！" if s["id"] in recent else ""
        lines.append(f"{i}. {s['preference'].strip()}{marker}")
    lines.append("")
    lines.append("[用户当前消息]")
    lines.append(user_text)

    sys.stdout.write("\n".join(lines))

if __name__ == "__main__":
    main()
```

注册：在 Claude Code 配置里：

```json
{
  "hooks": {
    "user_prompt_submit": "~/.claude/hooks/karma_user_prompt_submit.py"
  }
}
```

### post_response hook

时机：每次 Agent 响应**完成后**调用。

实现：`~/.claude/hooks/karma_post_response.py`

```python
#!/usr/bin/env python3
"""karma post_response hook — 扫违反，记录到 violations.jsonl。

输入：从 stdin 读 hook payload (含 agent_response)
输出：可选 stderr 通知

性能预算：< 200ms（不阻塞用户感知）
"""
import json, sys, time, yaml
from pathlib import Path

STICKY_PATH = Path.home() / ".claude" / "karma" / "sticky.yaml"
VIOLATIONS_PATH = Path.home() / ".claude" / "karma" / "violations.jsonl"

def main():
    payload = json.load(sys.stdin)
    response = payload.get("agent_response", "")
    session_id = payload.get("session_id", "unknown")
    response_lower = response.lower()

    if not STICKY_PATH.exists():
        return
    sticky = yaml.safe_load(STICKY_PATH.read_text()) or []
    if not sticky:
        return

    violations = []
    for s in sticky:
        for kw in s.get("violation_keywords", []):
            if kw.lower() in response_lower:
                # 找 snippet (kw 前后 30 字)
                idx = response_lower.find(kw.lower())
                start = max(0, idx - 30)
                end = min(len(response), idx + len(kw) + 30)
                violations.append({
                    "ts": int(time.time()),
                    "session_id": session_id,
                    "sticky_id": s["id"],
                    "trigger": kw,
                    "snippet": response[start:end],
                })

    if violations:
        VIOLATIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with VIOLATIONS_PATH.open("a") as f:
            for v in violations:
                f.write(json.dumps(v, ensure_ascii=False) + "\n")
        # 通知用户
        for v in violations:
            print(f"⚠️ karma: Agent 违反 \"{v['sticky_id']}\" (触发: {v['trigger']})",
                  file=sys.stderr)

if __name__ == "__main__":
    main()
```

注册：

```json
{
  "hooks": {
    "post_response": "~/.claude/hooks/karma_post_response.py"
  }
}
```

## CLI 工具

`karma` CLI 提供 sticky 管理 + 观察工具。

实现：`bin/karma`（Python 脚本，pip install . 后可用）

### 命令

```bash
# sticky 管理
karma sticky list                       # 列出所有 sticky 规则
karma sticky add                        # 交互式添加新 sticky（编辑器打开）
karma sticky remove <id>                # 移除某条
karma sticky edit <id>                  # 编辑某条（编辑器打开）

# 观察
karma stats                             # 列出每条规则的违反统计（7 天 / 总）
karma violations recent                 # 最近 20 条违反详情
karma violations clear                  # 清违反历史（确认）

# 安装 / 卸载
karma install-hooks                     # 自动配置 Claude Code hooks
karma uninstall-hooks                   # 移除 hook 配置
karma doctor                            # 检查环境（hook 是否生效、sticky.yaml 是否合法等）
```

## 性能预算

| 路径 | 预算 |
|---|---|
| user_prompt_submit hook | < 50ms (sticky.yaml 通常 ≤ 1KB，violations 200 行就够) |
| post_response hook | < 200ms (sticky × response_len 简单 substring) |
| CLI stats | < 500ms |

不需要 SQLite / cache 等复杂数据层 — 纯文本 IO 在小数据量下足够。

## 安全 / 隐私

- karma 的所有数据都在 `~/.claude/karma/` 本地
- 不上传任何数据到任何 LLM 或服务
- 不调用 LLM（v0 完全无 LLM）
- 用户随时可以 `rm -rf ~/.claude/karma/` 清空所有 karma 状态

## v0 不做（明确边界）

- ❌ 数据库（SQLite 之类）— violations.jsonl 文件级够用
- ❌ LLM 调用 — v0 完全工程化
- ❌ 多平台支持（先 Claude Code only）
- ❌ Web UI / TUI — CLI + yaml 编辑器足够
- ❌ 自动学习 sticky — 用户掌控

## 实施 milestone

### M0: 骨架（这周内）

- [x] 项目初始化（仓库 / README / PRD / ARCHITECTURE）
- [ ] sticky.yaml schema 定稿
- [ ] user_prompt_submit hook 原型
- [ ] post_response hook 原型
- [ ] karma CLI 骨架（list / add / install-hooks）
- [ ] sticky 5-10 条种子规则（作者自用）

### M1: 自用验证（下周）

- [ ] 装好 hook 自用 1 周
- [ ] 观察 violations.jsonl 增长 + Agent 在长任务中行为变化
- [ ] 记录 5 个具体案例 → 评判 karma 是否真有用

### M2 (如果 M1 通过): 第一批种子分享

- [ ] README 加 quickstart
- [ ] 分享 sticky 模板（不强制使用，仅参考）
- [ ] 给 2-3 个朋友试用收反馈

如果 M1 验证失败 → karma 假设错，需要进一步重新设计。
