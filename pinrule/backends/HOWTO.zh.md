# 如何加一个新 AI 编程客户端 backend

**[🇬🇧 English](./HOWTO.md) · [🇨🇳 中文（当前）](./HOWTO.zh.md)**

pinrule 当前装机支持 4 家（Claude / Codex / Cursor / Hermes）。本文档讲怎么加第 5 家
— 理论上**任何提供 hook 接口（能注册外部命令在事件触发时执行 + 通过
stdin 传递 payload）的 AI 编程客户端**都可以加 backend 支持。

## 5 步加一个新 backend

### 第 1 步：调研客户端 hook 协议

按 pinrule 的 `long-term-fundamental` 规则 — **真跑不凭假设**，调研以下：

1. **hook 配置文件路径** — 通常 `~/.<client>/settings.json` 或 `~/.<client>/hooks.json`
2. **hook event 名** — 写进配置文件的 event 名（如 `UserPromptSubmit` vs Cursor 的 camelCase
   `BeforeAgent`）
3. **stdin payload 字段** — case style（snake_case 还是 camelCase？）+ 哪些字段
   pinrule 关心（`prompt` / `tool_name` / `tool_input` / `tool_response` /
   等同 stop 字段如 `last_assistant_message` / `prompt_response` / `transcript_path`）
4. **stdout JSON 字段** — 跟 Claude 一致就直接用，不一致要适配 hook 入口模块
5. **是否需要启用步骤** — 像 Codex 要 `[features] hooks = true`
6. **每条 hook entry 是否需要 matcher / timeout 字段** — 各家不一样

调研来源优先级：① 官方文档 ② 跑客户端 + trace hook 看 stdin 字段
③ GitHub issues / 社区

### 第 2 步：在 `pinrule/backends/` 新建一个 backend 文件

**第 1 步调研项 → 第 2 步类属性对照表**（让填表闭环）：

| 调研项 | 类属性 | 例子（Codex） |
|---|---|---|
| hook 配置文件路径 | `_CONFIG_DIR_NAME` + `_SETTINGS_FILENAME` | `".codex"` + `"hooks.json"`（自动拼成 `~/.codex/hooks.json`） |
| 客户端命令名（PATH 检测） | `_CLIENT_CMD` | `"codex"`（检测 `command -v codex`） |
| backend 注册名 | `name` | `"codex"` |
| 用户可见名 | `display_name` | `"Codex"` |
| hook event 名映射 | `_HOOK_EVENTS` | `{"UserPromptSubmit": "user_prompt_submit", ...}` |
| 是否要 matcher / timeout 字段 | override `build_event_entry`（可选） | Codex 加 `timeout: 30` |
| 是否要启用步骤 | override `pre_install_setup`（可选） | Codex 跑 `codex features enable hooks` |
| stdin payload 字段差异 | 改 `pinrule/hooks/stop.py` fallback 链（可选） | Codex 用 `last_assistant_message` 而非 `transcript_path` |

参考 `pinrule/backends/claude_code.py` 最简洁的样板（继承 `JsonHooksBackend`
只填类属性）：

```python
from pinrule.backends._json_hooks import JsonHooksBackend

class CursorBackend(JsonHooksBackend):
    name = "cursor"                          # backend 注册名
    display_name = "Cursor"                  # 给用户看的名字
    _CONFIG_DIR_NAME = ".cursor"             # ~/ 下配置目录名
    _SETTINGS_FILENAME = "hooks.json"        # 配置文件名
    _CLIENT_CMD = "cursor"                   # PATH 命令名（用于检测装机）

    # backend native event 名 → pinrule 内部 wrapper basename
    # pinrule 内部 4 个 wrapper：user_prompt_submit / pre_tool_use /
    # post_tool_use / stop（跨 backend 复用，不动）
    _HOOK_EVENTS = {
        "UserPromptSubmit": "user_prompt_submit",
        "PreToolUse": "pre_tool_use",
        "PostToolUse": "post_tool_use",
        "Stop": "stop",
    }

    # ✓ 最小 stub 写到这里就停 — 默认不需要 override
    # build_event_entry / pre_install_setup。基类 _json_hooks.py 提供合理默认。
```

### Claude 特有可选扩展 (v0.4.28+)

pinrule v0.4.28+ 加了 2 个 Claude 协议特有 hook event 给「中段
注入 + compact 失忆两端夹击」用：

```python
# Claude backend 额外 2 个（其他 backend 协议没对应不强求）
"SessionStart": "session_start",  # v0.4.28 — session 起手注入 sticky baseline
                                   # source 字段区分 startup/resume/clear/compact
"PreCompact": "pre_compact",       # v0.4.29 — compact 前落盘 sticky 完整状态
                                   # 跟 SessionStart(source=compact) 两端夹击
```

新 backend 实现者评估：

- 如果 backend 协议**有**类似 session lifecycle / context compact 事件 →
  在 `_HOOK_EVENTS` 加映射 + 写对应 wrapper 升级到 pinrule 中段注入 + compact 落盘双端夹击能力
- 如果**没**对应事件（如 Codex / Cursor 当前情况）→ 跳过即可，4 个通用
  wrapper 已经够 pinrule 核心功能（违反检测 + sticky 注入到 user prompt）

如果 backend 需要 matcher / timeout 字段在 hook entry 里：override
`build_event_entry`：

```python
def build_event_entry(self, hook_name_lower: str, event_name: str) -> dict:
    wrapper = self.hooks_dir() / f"pinrule_{hook_name_lower}.py"
    return {
        "hooks": [{"type": "command", "command": str(wrapper), "timeout": 30}]
    }
```

如果 backend 需要启用步骤（Codex 类）：override `pre_install_setup`：

```python
def pre_install_setup(self) -> list[str]:
    # 返回给用户看的步骤日志
    ...
```

### 第 3 步：注册到 `pinrule/backends/__init__.py`

```python
from pinrule.backends.cursor import CursorBackend

REGISTRY: dict[str, Backend] = {
    "claude-code": ClaudeCodeBackend(),
    "codex": CodexBackend(),
    "cursor": CursorBackend(),              # 加这行
}
```

### 第 4 步：检查 stdin payload 字段差异

pinrule hook 入口（`pinrule/hooks/*.py`）用以下字段，跨 backend 一般同名：

- `session_id` — 所有 backend 都用 `session_id`（snake_case）
- `prompt` — UserPromptSubmit / BeforeAgent 都用 `prompt`
- `tool_name` / `tool_input` / `tool_response` — Pre/PostToolUse 都用同名

Stop 字段三家不同（pinrule stop.py 已三选一适配）：
- Claude: `transcript_path`（反向读 transcript）
- Codex: `last_assistant_message`

如果新 backend 用第四种字段名，改 `pinrule/hooks/stop.py:_read_last_assistant_response`
前面那段 fallback 链加一条 `or payload.get("<new_field>", "")`。

### 第 5 步：加守护测试

参考 `tests/test_backends.py` 加：

- backend 路径正确
- event entry 构造对（含 timeout / matcher 字段如果有）
- load_settings / save_settings roundtrip
- `is_pinrule_entry` 识别 pinrule_ 前缀

如果改了 stop.py 适配字段：参考
`tests/test_hooks.py::test_stop_hook_uses_codex_last_assistant_message_field`
加一条字段 fallback 测试。

## 实测验证（跑不凭假设）

加完后**必须跑**验证：

```bash
pinrule install-hooks --backend <new-name>
cat ~/.<client>/settings.json | python -m json.tool  # 看 pinrule 4 个 entry 加进去 + 他人 hook 保留
pinrule uninstall-hooks --backend <new-name>
cat ~/.<client>/settings.json | python -m json.tool  # 看 pinrule 清掉 + 他人 hook 保留
```

模拟 stdin payload 跑 pinrule stop hook 看 catch 违反：

```bash
echo '{"session_id":"t","prompt_response":"我先打个补丁","<其他字段>":"..."}' | \
    ~/.<client>/hooks/pinrule_stop.py
# 期望：⚠️ pinrule: Agent 触发关键词 ... + JSON decision=block 输出
```

## 不能省的步骤（按 pinrule 项目原则）

- ❌ **不要凭文档结束，必须端到端跑过**（pinrule 的 `long-term-fundamental` + `loud-failure-with-evidence` 规则）
- ❌ **不要破坏他人 hook 共存**（rtk 等同 event 多 entry 必须保留）
- ❌ **配置文件原子写**（基类已实现 tmp + os.replace 不用动）
- ❌ **不要硬编码 backend id 名字到核心逻辑** — 加 backend 不该改 cli.py 等核心代码

## 已支持 backend

| 客户端 | 配置路径 | 状态 |
|---|---|---|
| Claude | `~/.claude/settings.json` | ✓ v0.1.0 起 |
| Codex | `~/.codex/hooks.json` | ✓ v0.3.0 起 |
| Cursor | `~/.cursor/hooks.json` | ✓ v0.12.0 起（需 Cursor 1.7+；`/pinrule` skill 仅 project-scoped — Cursor 没 home-level global skills 目录）。**回复级 check** 需用户开 Agent transcripts — 见 README「Cursor：开启 Agent Transcripts」 |
| Hermes | `~/.hermes/config.yaml` | ✓ v0.19.0 起（NousResearch Hermes Agent v0.14.0+ — 持久 server agent + plugin hooks；基于 `agent/shell_hooks.py` 源码 ground）。**v0.19.0 已知 limit**: pinrule 自带 YAML subset parser 不接受 Hermes 默认 `config.yaml`（`agent.personalities` 段含 multi-line string 续行）— workaround: `install-hooks` 生成 wrapper 后手工 append `hooks:` 段；line-based surgical operator v0.19.1 真补。 |

## 候选 backend — 没有现成清单

理论上**任何提供 hook 接口的 AI 编程客户端**都可以加 backend 支持。客户端协议需满足：

- 有 hook 配置文件（JSON / TOML / YAML 都行）
- 能在 user prompt / tool call / stop 这类事件触发时执行外部命令
- 通过 stdin 传 payload（含 `prompt` / `tool_input` / `transcript_path` 等字段）

**没有现成清单可以直接照抄** — 各家客户端协议在快速演化，二手情报往往过时（字段名变 / event 名变 / 启用 flag 变）。**实测协议字段比看清单更可靠**。

加新 backend 流程：装该客户端 → trace hook 协议看真字段 → 按上面 5 步走 → 加测试 → PR。

**加新 backend 跟踪本文件「已支持 backend」表格**，确保后人看到当前哪些已支持。
