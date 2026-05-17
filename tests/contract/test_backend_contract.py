"""跨 backend 契约自动验证 (v0.10.1) — 让加新 Agent 平台 backend 注册即自动覆盖.

pinrule v0.10.0 形式化了 6-method backend 契约 (`pinrule/backends/_base.py:Backend`).
本测试对 REGISTRY 里**每个**已注册 backend 跑同一套抽象契约测试. 任何 backend
（包括未来 Cursor / Copilot / Cline 等加入的）注册到 REGISTRY 后这里自动覆盖,
不需要为每个 backend 写一遍同样的契约测试.

**只测契约不测具体协议字面**: 这是分工边界 — backend 具体协议私货（codex
apply_patch envelope / Cursor permission shape 等）归各自 backend.py
单独测试，本文件只验「6 method 都 callable + 返回类型合理 + 不抛异常」.

参考: [[pinrule-backend-ownership-split]] memory, docs/CODEX_BACKEND.md
"""

from __future__ import annotations

import json

import pytest

from pinrule.backends import REGISTRY


# pytest parametrize fixture — 跑所有已注册 backend
ALL_BACKENDS = list(REGISTRY.items())


@pytest.fixture(params=ALL_BACKENDS, ids=[name for name, _ in ALL_BACKENDS])
def backend(request):
    """parametrize fixture: 每个 REGISTRY backend 跑一遍下面所有测试."""
    _, backend = request.param
    return backend


# --- 元契约：所有 6 method 都 callable 不崩 ---

def test_pre_install_setup_returns_list(backend):
    """pre_install_setup 返回 list[str] (即便没装客户端也不该崩)."""
    result = backend.pre_install_setup()
    assert isinstance(result, list)
    assert all(isinstance(line, str) for line in result)


def test_post_install_message_returns_list(backend):
    """post_install_message 返回 list[str] (v0.9.17 加的契约)."""
    result = backend.post_install_message()
    assert isinstance(result, list)
    assert all(isinstance(line, str) for line in result)


def test_normalize_tool_name_returns_string_and_passthrough_unknowns(backend):
    """normalize_tool_name 必须返 str 且未知 tool_name 透传 (不抛不返 None)."""
    out = backend.normalize_tool_name("UnknownToolXYZ", {})
    assert isinstance(out, str)
    assert out == "UnknownToolXYZ", (
        f"backend {backend.name!r} normalize_tool_name 把未知名 'UnknownToolXYZ' "
        f"映射成 {out!r} — 应该透传不知道的 tool_name 不该擅自改"
    )


def test_normalize_tool_name_canonical_idempotent(backend):
    """已是 canonical 的 tool_name (Bash/Read/Edit/Write) 再 normalize 还是自己."""
    for canonical in ("Bash", "Read", "Edit", "Write", "NotebookEdit"):
        out = backend.normalize_tool_name(canonical, {})
        assert out == canonical, (
            f"backend {backend.name!r} normalize_tool_name({canonical!r}) → {out!r} "
            f"应该幂等 — 已 canonical 的名再 normalize 仍是自己"
        )


def test_normalize_tool_input_passthrough_unknown_tool(backend):
    """normalize_tool_input 未知 tool_name 应 passthrough (不抛不破坏原 input)."""
    input_dict = {"file_path": "/tmp/x.py", "new_string": "abc"}
    out = backend.normalize_tool_input("UnknownToolXYZ", input_dict, {})
    # 允许是同对象（identity passthrough）或值相等（copy passthrough）
    assert out == input_dict or out is input_dict


def test_emit_deny_returns_valid_json_string(backend):
    """emit_deny 返回必须是合法 JSON string (不抛, 能 json.loads 解析)."""
    out = backend.emit_deny("test reason", {})
    assert isinstance(out, str)
    parsed = json.loads(out)  # 必须能解析不抛
    assert isinstance(parsed, dict)


def test_emit_allow_returns_valid_json_string(backend):
    """emit_allow 返回必须是合法 JSON string."""
    out = backend.emit_allow({})
    assert isinstance(out, str)
    parsed = json.loads(out)
    assert isinstance(parsed, dict)


def test_emit_context_injection_returns_valid_json_string(backend):
    """v0.10.6: emit_context_injection 必须返合法 JSON string (任何 event_name)."""
    out = backend.emit_context_injection("SessionStart", "test context", {})
    assert isinstance(out, str)
    parsed = json.loads(out)
    assert isinstance(parsed, dict)


def test_emit_stop_block_returns_valid_json_string(backend):
    """v0.10.6: emit_stop_block 必须返合法 JSON string. 各 backend 自决 fail-open shape
    也是合法的, 调用方 stop.py 主逻辑接受 (printed {} = passthrough 不阻塞)."""
    out = backend.emit_stop_block("test reason", {})
    assert isinstance(out, str)
    parsed = json.loads(out)
    assert isinstance(parsed, dict)


# --- 元契约：装机相关 method ---

def test_hook_events_returns_nonempty_dict(backend):
    """hook_events() 必须返回非空 dict event_name → wrapper_basename."""
    events = backend.hook_events()
    assert isinstance(events, dict)
    assert len(events) > 0, f"backend {backend.name!r} 不支持任何 hook event"
    for event_name, basename in events.items():
        assert isinstance(event_name, str)
        assert isinstance(basename, str)
        # wrapper basename 必须是合法 snake_case 文件名片段
        assert basename.replace("_", "").isalnum(), (
            f"backend {backend.name!r} wrapper basename {basename!r} 含非法字符 "
            f"(只允许 snake_case)"
        )


def test_settings_path_under_config_dir(backend):
    """settings_path() 必须在 backend 的配置目录下."""
    sp = backend.settings_path()
    # 至少应该含 backend 名特征（.claude / .codex / .cursor 等）
    assert any(part.startswith(".") for part in sp.parts), (
        f"backend {backend.name!r} settings_path {sp} 不在 dotted config 目录下"
    )


def test_build_event_entry_returns_valid_entry(backend):
    """build_event_entry 必须返回 dict, 内含 backend-specific 协议 shape.

    跨 backend shape 差异 (v0.12.3 Cursor dogfood 暴露):
    - Claude / Codex: nested `{"hooks": [{"type": "command", "command": "..."}]}`
    - Cursor (native, https://cursor.com/docs/hooks): flat `{"command": "..."}`

    Contract 只验 dict 且至少有 pinrule wrapper 路径痕迹 — 具体 shape 各 backend 自己测.
    """
    events = backend.hook_events()
    first_event, first_basename = next(iter(events.items()))
    entry = backend.build_event_entry(first_basename, first_event)
    assert isinstance(entry, dict)
    # 至少有一条路径里能找到 pinrule_ wrapper 前缀 (nested 或 flat shape 都 OK)
    entry_str = str(entry)
    assert "pinrule_" in entry_str, (
        f"backend {backend.name!r} build_event_entry 返回 {entry!r} — "
        f"没有 pinrule_ wrapper 路径痕迹 (uninstall 时 is_pinrule_entry 无法识别)"
    )


def test_is_pinrule_entry_recognizes_own_entry(backend):
    """build_event_entry 生成的 entry 必须被 is_pinrule_entry 识别（自循环契约）."""
    events = backend.hook_events()
    first_event, first_basename = next(iter(events.items()))
    entry = backend.build_event_entry(first_basename, first_event)
    assert backend.is_pinrule_entry(entry), (
        f"backend {backend.name!r} build_event_entry 生成的 entry 没被自己的 "
        f"is_pinrule_entry 识别 — uninstall 时无法清理自己装的 entry"
    )


def test_is_pinrule_entry_rejects_random_entry(backend):
    """is_pinrule_entry 必须拒认不含 pinrule_ 字面的 entry (避免误删用户其他 hook)."""
    foreign = {"hooks": [{"type": "command", "command": "/path/to/some-other-hook.py"}]}
    assert not backend.is_pinrule_entry(foreign), (
        f"backend {backend.name!r} is_pinrule_entry 误认陌生 entry — 卸载会误删用户其他 hook"
    )


# --- 元契约：name / display_name 必填 ---

def test_backend_has_name_and_display_name(backend):
    """每个 backend 必须有 name + display_name 类属性."""
    assert isinstance(backend.name, str) and backend.name
    assert isinstance(backend.display_name, str) and backend.display_name


# --- 元契约：skill_install_targets ---

def test_skill_install_targets_returns_list(backend):
    """skill_install_targets 返回 list[(Path, format_str)] tuple."""
    targets = backend.skill_install_targets("pinrule")
    assert isinstance(targets, list)
    for path, fmt in targets:
        assert hasattr(path, "parts"), f"{path} should be Path-like"
        assert fmt in ("markdown", "toml"), (
            f"backend {backend.name!r} skill format {fmt!r} 不在已知 (markdown/toml) 内"
        )
