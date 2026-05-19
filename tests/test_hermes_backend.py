"""Hermes Agent backend unit tests — v0.19.0 candidate.

按 [[feedback-no-guessing-other-platforms.md]]: 这些测试基于 Hermes 官方
hooks docs (https://hermes-agent.nousresearch.com/docs/user-guide/features/hooks)
模拟 payload + 验证 backend output shape, 但**不假装真本机捕获过 payload**.
真本机集成验证在 user 装 Hermes Agent 跑过后做 (v0.19.0 ship 前).

测试覆盖:
1. Registry 含 hermes
2. paths (config.yaml not json, agent-hooks/ 不是 hooks/)
3. event 名 snake_case (pre_tool_call / pre_llm_call 等)
4. event entry shape (command + timeout, no matcher)
5. is_pinrule_entry 识别
6. normalize_tool_name (terminal → Bash 等)
7. emit_deny / allow / context_injection shape
8. YAML subset emitter (mapping / sequence / scalar)
9. YAML subset parser (roundtrip + reject advanced features)
10. load + save roundtrip 真生效
"""

from __future__ import annotations

import json

import pytest

from pinrule.backends import REGISTRY, HermesBackend
from pinrule.backends._base import SettingsParseError
from pinrule.backends.hermes import (
    _emit_yaml_subset,
    _parse_yaml_subset,
    _YamlSubsetError,
)


@pytest.fixture
def fake_home(tmp_path, monkeypatch):
    """Sandbox HOME + PINRULE_HOME (兼容 Windows USERPROFILE 行为)."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("PINRULE_HOME", str(tmp_path))
    return tmp_path


@pytest.fixture
def hermes_test_config_dir(fake_home, monkeypatch):
    """Use non-.hermes dir to avoid clashing with real Hermes install."""
    dir_name = "hermes-pinrule-test"
    monkeypatch.setattr(HermesBackend, "_CONFIG_DIR_NAME", dir_name)
    return fake_home / dir_name


# ---------- Registry + 基础结构 ----------


def test_registry_has_hermes():
    assert "hermes" in REGISTRY
    assert isinstance(REGISTRY["hermes"], HermesBackend)


def test_hermes_paths(hermes_test_config_dir):
    b = HermesBackend()
    assert b.hooks_dir() == hermes_test_config_dir / "agent-hooks"
    assert b.settings_path() == hermes_test_config_dir / "config.yaml"
    assert b.settings_path().name == "config.yaml"  # 真 YAML 不是 JSON


def test_hermes_event_names_are_snake_case():
    """Hermes 真用 snake_case 跟 Cursor camelCase / Claude PascalCase 都不同."""
    b = HermesBackend()
    events = b.hook_events()
    assert "pre_tool_call" in events
    assert "pre_llm_call" in events
    assert "post_tool_call" in events
    assert "on_session_start" in events
    # 反例真不该有
    assert "PreToolUse" not in events  # Claude/Codex PascalCase
    assert "preToolUse" not in events  # Cursor camelCase


def test_hermes_event_mapping_covers_pinrule_canonical_wrappers():
    """Hermes events 真映射到 pinrule canonical wrapper basenames."""
    wrappers = set(HermesBackend().hook_events().values())
    minimum_commons = {"pre_tool_use", "post_tool_use", "stop"}
    assert minimum_commons.issubset(wrappers), f"缺 {minimum_commons - wrappers}"
    # pre_llm_call → user_prompt_submit (Claude UserPromptSubmit 真等价)
    events = HermesBackend().hook_events()
    assert events["pre_llm_call"] == "user_prompt_submit"
    assert events["on_session_start"] == "session_start"
    # on_session_end 是 Hermes CLI 模式真 Stop 等价 (agent:end 真不存在)
    assert events["on_session_end"] == "stop"


def test_hermes_does_not_use_gateway_only_events():
    """gateway:startup / agent:end / agent:start 等是 Gateway-only events,
    CLI 模式真不 fire. 源码 verify (agent/shell_hooks.py 真不在 whitelist).
    pinrule 真不映射这些避免装无效 hook."""
    events = HermesBackend().hook_events()
    assert "agent:end" not in events
    assert "agent:start" not in events
    assert "gateway:startup" not in events


# ---------- event entry + pinrule entry 识别 ----------


def test_hermes_event_entry_has_timeout_no_matcher():
    """pinrule 不用 matcher (要拦所有 tool call). timeout 30s 跟 Codex 一致."""
    b = HermesBackend()
    entry = b.build_event_entry("pre_tool_use", "pre_tool_call")
    assert "command" in entry
    assert entry["timeout"] == 30
    assert "matcher" not in entry  # 真不加


def test_hermes_event_entry_flat_command_shape():
    """Hermes hook entry 是 flat {command: ...} 不是 Claude nested {hooks: [...]}."""
    b = HermesBackend()
    entry = b.build_event_entry("pre_tool_use", "pre_tool_call")
    assert isinstance(entry["command"], str)
    assert "hooks" not in entry  # 不是 Claude nested 格式
    assert "pinrule_pre_tool_use.py" in entry["command"]


def test_hermes_is_pinrule_entry_recognizes_pinrule_prefix():
    b = HermesBackend()
    assert b.is_pinrule_entry({"command": "/path/to/pinrule_pre_tool_use.py"})
    assert not b.is_pinrule_entry({"command": "/other/script.sh"})
    assert not b.is_pinrule_entry({})


# ---------- protocol contract methods ----------


def test_hermes_normalize_tool_name_maps_shell_variants_to_bash():
    """Hermes 'terminal' / 'shell' / 'execute_shell' 真都映射到 pinrule canonical 'Bash'."""
    b = HermesBackend()
    assert b.normalize_tool_name("terminal", {}) == "Bash"
    assert b.normalize_tool_name("shell", {}) == "Bash"
    assert b.normalize_tool_name("execute_shell", {}) == "Bash"


def test_hermes_normalize_tool_name_maps_file_ops():
    b = HermesBackend()
    assert b.normalize_tool_name("read_file", {}) == "Read"
    assert b.normalize_tool_name("write_file", {}) == "Write"
    assert b.normalize_tool_name("patch_file", {}) == "Edit"
    assert b.normalize_tool_name("edit_file", {}) == "Edit"


def test_hermes_normalize_tool_name_passthrough_unknown():
    """Hermes 47+ tools 不在 map 里的 passthrough — pinrule check 见 unknown
    tool_name 真不命中 (跟现有 Claude PreToolUse 行为一致)."""
    b = HermesBackend()
    assert b.normalize_tool_name("web_search", {}) == "web_search"
    assert b.normalize_tool_name("schedule_task", {}) == "schedule_task"


def test_hermes_emit_deny_uses_claude_shape():
    """Hermes 接受 Claude 同款 {decision: block, reason: ...} (docs 明确)."""
    b = HermesBackend()
    out = b.emit_deny("blocked: sleep 30 detected", {})
    parsed = json.loads(out)
    assert parsed == {"decision": "block", "reason": "blocked: sleep 30 detected"}


def test_hermes_emit_allow_returns_empty_object():
    """Hermes pass-through 真用空 {} (docs 'no-op / pass-through')."""
    b = HermesBackend()
    parsed = json.loads(b.emit_allow({}))
    assert parsed == {}


def test_hermes_emit_context_injection_pre_llm_call_uses_top_level_context():
    """pre_llm_call: Hermes docs 明确接受 {"context": "..."} 顶层注入."""
    b = HermesBackend()
    out = b.emit_context_injection("pre_llm_call", "remember rule #4", {})
    parsed = json.loads(out)
    assert parsed == {"context": "remember rule #4"}


def test_hermes_emit_context_injection_other_events_safe_empty():
    """非 pre_llm_call event docs 没明确 context 支持, 安全 fallback 空 {}.
    等 user 真本机测试反馈再扩展 (avoid guessing protocol)."""
    b = HermesBackend()
    parsed = json.loads(b.emit_context_injection("on_session_start", "ctx", {}))
    assert parsed == {}
    parsed = json.loads(b.emit_context_injection("post_tool_call", "ctx", {}))
    assert parsed == {}


def test_hermes_emit_context_injection_empty_context_returns_empty_object():
    """空 context 不该 emit {context: ""} 占位 — 直接空 {}."""
    b = HermesBackend()
    parsed = json.loads(b.emit_context_injection("pre_llm_call", "", {}))
    assert parsed == {}
    parsed = json.loads(b.emit_context_injection("pre_llm_call", "   ", {}))
    assert parsed == {}


def test_hermes_emit_stop_block_returns_empty_object():
    """agent:end 真 stop 协议 docs 未详 — 安全 fallback 空 {}, stderr 已经能见
    pinrule notification. v0.19.0 ship 前 user 本机捕获 agent:end payload 真行为
    后再增强."""
    b = HermesBackend()
    parsed = json.loads(b.emit_stop_block("agent stopping early", {}))
    assert parsed == {}


# ---------- YAML subset emitter ----------


def test_yaml_emit_minimal_dict():
    out = _emit_yaml_subset({"key": "value", "n": 42, "ok": True})
    # 顺序 + 格式真稳
    assert "key: value" in out
    assert "n: 42" in out
    assert "ok: true" in out


def test_yaml_emit_nested_mapping():
    data = {"hooks": {"pre_tool_call": []}}
    out = _emit_yaml_subset(data)
    assert "hooks:" in out
    assert "pre_tool_call: []" in out


def test_yaml_emit_hermes_full_config_shape():
    """模拟真 Hermes config.yaml shape — pinrule 真要写出去这种格式."""
    data = {
        "hooks": {
            "pre_tool_call": [
                {"command": "~/.hermes/agent-hooks/pinrule_pre_tool_use.py", "timeout": 30},
            ],
            "pre_llm_call": [
                {"command": "~/.hermes/agent-hooks/pinrule_user_prompt_submit.py", "timeout": 30},
            ],
        },
        "hooks_auto_accept": False,
    }
    out = _emit_yaml_subset(data)
    # 真能反向 parse 回 same struct
    reparsed = _parse_yaml_subset(out)
    assert reparsed == data


def test_yaml_emit_quotes_special_strings():
    """含 : / # / leading space 等真 special str 必须 quote."""
    out = _emit_yaml_subset({"k": "value: with colon"})
    assert '"value: with colon"' in out

    out = _emit_yaml_subset({"k": "  leading space"})
    assert '"  leading space"' in out

    out = _emit_yaml_subset({"k": "true"})  # str "true" not bool
    assert '"true"' in out


def test_yaml_emit_scalar_types():
    """null / bool / int / str 各自真 emit format."""
    assert "null" in _emit_yaml_subset({"k": None})
    assert "true" in _emit_yaml_subset({"k": True})
    assert "false" in _emit_yaml_subset({"k": False})
    assert "42" in _emit_yaml_subset({"k": 42})


# ---------- YAML subset parser ----------


def test_yaml_parse_minimal_mapping():
    text = "key: value\nn: 42\nok: true\n"
    out = _parse_yaml_subset(text)
    assert out == {"key": "value", "n": 42, "ok": True}


def test_yaml_parse_nested_mapping():
    text = "hooks:\n  pre_tool_call: []\n"
    out = _parse_yaml_subset(text)
    assert out == {"hooks": {"pre_tool_call": []}}


def test_yaml_parse_sequence_of_dicts():
    """真 Hermes config.yaml shape — hook entries 是 list of dicts."""
    text = (
        "hooks:\n"
        "  pre_tool_call:\n"
        "    - command: /path/to/hook.sh\n"
        "      timeout: 30\n"
        "    - command: /another.sh\n"
        "      matcher: terminal\n"
    )
    out = _parse_yaml_subset(text)
    assert out == {
        "hooks": {
            "pre_tool_call": [
                {"command": "/path/to/hook.sh", "timeout": 30},
                {"command": "/another.sh", "matcher": "terminal"},
            ]
        }
    }


def test_yaml_parse_handles_comments_and_blank_lines():
    text = (
        "# top comment\n"
        "\n"
        "hooks:  # inline comment\n"
        "  # nested comment\n"
        "  pre_tool_call: []\n"
        "\n"
    )
    out = _parse_yaml_subset(text)
    assert out == {"hooks": {"pre_tool_call": []}}


def test_yaml_parse_quoted_strings():
    text = 'k: "value: with colon"\n'
    out = _parse_yaml_subset(text)
    assert out == {"k": "value: with colon"}


def test_yaml_parse_rejects_anchors():
    text = "k: &anchor value\n"
    with pytest.raises(_YamlSubsetError):
        _parse_yaml_subset(text)


def test_yaml_parse_rejects_flow_style():
    text = "k: {a: 1, b: 2}\n"
    with pytest.raises(_YamlSubsetError):
        _parse_yaml_subset(text)


def test_yaml_parse_rejects_multi_doc():
    text = "---\nk: v\n---\nk2: v2\n"
    with pytest.raises(_YamlSubsetError):
        _parse_yaml_subset(text)


def test_yaml_parse_rejects_tabs_in_indent():
    text = "hooks:\n\tpre_tool_call: []\n"
    with pytest.raises(_YamlSubsetError):
        _parse_yaml_subset(text)


# ---------- load + save 真集成 roundtrip ----------


def test_hermes_load_settings_empty_when_no_file(hermes_test_config_dir):
    b = HermesBackend()
    assert b.load_settings() == {}


def test_hermes_save_then_load_roundtrip(hermes_test_config_dir):
    """save_settings + load_settings 真 roundtrip 不丢字段."""
    b = HermesBackend()
    data = {
        "hooks": {
            "pre_tool_call": [
                {"command": "/x/pinrule_pre_tool_use.py", "timeout": 30},
            ],
        },
        "hooks_auto_accept": False,
    }
    b.save_settings(data)
    loaded = b.load_settings()
    assert loaded == data


def test_hermes_save_settings_atomic_no_tmp_leftover(hermes_test_config_dir):
    """save_settings 用 tmp + os.replace 真原子, 不留 .pinrule-tmp.* 残留."""
    b = HermesBackend()
    b.save_settings({"hooks": {}})
    assert b.settings_path().exists()
    tmp_files = list(b.settings_path().parent.glob("*pinrule-tmp*"))
    assert not tmp_files


def test_hermes_load_raises_on_unsupported_yaml(hermes_test_config_dir):
    """用户 config.yaml 含 advanced YAML 时 SettingsParseError loud-fail."""
    b = HermesBackend()
    p = b.settings_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    # Anchor — pinrule 真不支持
    p.write_text("k: &anchor value\n", encoding="utf-8")
    with pytest.raises(SettingsParseError) as exc:
        b.load_settings()
    assert "PyYAML" in str(exc.value) or "YAML 高级特性" in str(exc.value)
