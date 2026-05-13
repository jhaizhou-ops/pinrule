"""pre_tool_use hook — tool 拦截集成测试。"""

from __future__ import annotations

import io
import json
from pathlib import Path

import yaml

from karma.hooks import pre_tool_use


def _patch(monkeypatch, tmp_path: Path, sticky_items: list[dict]) -> tuple[Path, Path]:
    sticky_path = tmp_path / "sticky.yaml"
    sticky_path.write_text(yaml.safe_dump(sticky_items, allow_unicode=True), encoding="utf-8")
    violations_path = tmp_path / "violations.jsonl"
    monkeypatch.setattr("karma.sticky.DEFAULT_PATH", sticky_path)
    monkeypatch.setattr("karma.violations.DEFAULT_PATH", violations_path)
    return sticky_path, violations_path


def _run_hook(monkeypatch, payload: dict) -> dict:
    """跑 hook，返回 hookSpecificOutput dict (含 permissionDecision)。"""
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    import sys
    captured = io.StringIO()
    monkeypatch.setattr("sys.stdout", captured)
    pre_tool_use.main()
    out = json.loads(captured.getvalue())
    return out.get("hookSpecificOutput", {})


def test_allow_when_no_sticky(monkeypatch, tmp_path):
    monkeypatch.setattr("karma.sticky.DEFAULT_PATH", tmp_path / "sticky.yaml")
    monkeypatch.setattr("karma.violations.DEFAULT_PATH", tmp_path / "v.jsonl")
    out = _run_hook(monkeypatch, {
        "tool_name": "Bash",
        "tool_input": {"command": "echo hi"},
    })
    assert out["permissionDecision"] == "allow"


def test_allow_clean_bash(monkeypatch, tmp_path):
    _patch(monkeypatch, tmp_path, [
        {"id": "no-sleep", "preference": "不要 sleep", "violation_keywords": ["sleep"]},
    ])
    out = _run_hook(monkeypatch, {
        "tool_name": "Bash",
        "tool_input": {"command": "ls -la"},
    })
    assert out["permissionDecision"] == "allow"


def test_deny_bash_sleep(monkeypatch, tmp_path):
    """Agent 想跑 sleep → pre_tool_use 拦截。"""
    _, violations_path = _patch(monkeypatch, tmp_path, [
        {
            "id": "non-blocking",
            "preference": "不阻塞",
            "violation_keywords": ["sleep"],
        },
    ])
    out = _run_hook(monkeypatch, {
        "tool_name": "Bash",
        "tool_input": {"command": "sleep 30 && echo done"},
        "session_id": "test",
    })
    assert out["permissionDecision"] == "deny"
    assert "non-blocking" in out["permissionDecisionReason"]
    assert "sleep" in out["permissionDecisionReason"]
    # 拦截也写入 violations.jsonl (供 stats 看到)
    assert violations_path.exists()


def test_deny_write_with_hardcoded(monkeypatch, tmp_path):
    """Agent 想 Write 含硬编码内容 → 拦截。"""
    _patch(monkeypatch, tmp_path, [
        {
            "id": "long-term",
            "preference": "用长期方案",
            "violation_keywords": ["硬编码", "先打个补丁"],
        },
    ])
    out = _run_hook(monkeypatch, {
        "tool_name": "Write",
        "tool_input": {
            "file_path": "/tmp/x.py",
            "content": "# 先打个补丁\nMAGIC = 42",
        },
    })
    assert out["permissionDecision"] == "deny"
    assert "long-term" in out["permissionDecisionReason"]


def test_deny_edit_only_scans_new_string(monkeypatch, tmp_path):
    """Edit 应该只扫 new_string (Agent 加的)，不扫 old_string (已有的代码)。"""
    _patch(monkeypatch, tmp_path, [
        {"id": "no-patch", "preference": "x", "violation_keywords": ["先打个补丁"]},
    ])
    # old_string 含违反词 (旧代码) → 不该 deny
    out = _run_hook(monkeypatch, {
        "tool_name": "Edit",
        "tool_input": {
            "file_path": "/tmp/x.py",
            "old_string": "# 先打个补丁",  # 旧代码原本就有 → 不该触发
            "new_string": "# 修复根因",     # 新加的内容干净
        },
    })
    assert out["permissionDecision"] == "allow"

    # new_string 含违反词 (Agent 想加) → 该 deny
    out = _run_hook(monkeypatch, {
        "tool_name": "Edit",
        "tool_input": {
            "file_path": "/tmp/x.py",
            "old_string": "# OLD",
            "new_string": "# 先打个补丁 fix",
        },
    })
    assert out["permissionDecision"] == "deny"


def test_doc_write_exempts_keyword_layer(monkeypatch, tmp_path):
    """Write .md / .rst 等文档时关键词层豁免 — 文档里描述触发词字面不是真违反。

    根因：HANDOFF.md / README.md 描述 sticky 触发词时关键词层会误判。
    """
    _patch(monkeypatch, tmp_path, [
        {"id": "long-term", "preference": "x", "violation_keywords": ["硬编码", "workaround"]},
    ])
    out = _run_hook(monkeypatch, {
        "tool_name": "Write",
        "tool_input": {
            "file_path": "/tmp/HANDOFF.md",
            "content": "# 触发词说明\n这条规则拦截「硬编码」「workaround」等字面",
        },
    })
    assert out["permissionDecision"] == "allow"  # 文档豁免

    # 同样内容但写 .py 文件 → 该拦（不是文档语境）
    out = _run_hook(monkeypatch, {
        "tool_name": "Write",
        "tool_input": {
            "file_path": "/tmp/foo.py",
            "content": "x = '硬编码'",
        },
    })
    assert out["permissionDecision"] == "deny"


def test_fail_open_on_bad_yaml(monkeypatch, tmp_path):
    """sticky.yaml 配置错 → 不阻塞 tool（fail open）。"""
    sticky_path = tmp_path / "sticky.yaml"
    sticky_path.write_text("- {{ bad yaml")
    monkeypatch.setattr("karma.sticky.DEFAULT_PATH", sticky_path)
    monkeypatch.setattr("karma.violations.DEFAULT_PATH", tmp_path / "v.jsonl")
    out = _run_hook(monkeypatch, {
        "tool_name": "Bash",
        "tool_input": {"command": "sleep 5"},
    })
    # 配置坏掉了，但不该完全阻断 tool
    assert out["permissionDecision"] == "allow"


def test_fail_open_on_bad_payload(monkeypatch, tmp_path):
    """payload JSON 解析失败 → fail open。"""
    monkeypatch.setattr("karma.sticky.DEFAULT_PATH", tmp_path / "sticky.yaml")
    monkeypatch.setattr("karma.violations.DEFAULT_PATH", tmp_path / "v.jsonl")
    import sys, io
    monkeypatch.setattr("sys.stdin", io.StringIO("not json"))
    captured = io.StringIO()
    monkeypatch.setattr("sys.stdout", captured)
    pre_tool_use.main()
    out = json.loads(captured.getvalue())
    # bad payload 走顶层 _allow() → hookSpecificOutput.permissionDecision
    assert out["hookSpecificOutput"]["permissionDecision"] == "allow"
