"""pre_tool_use hook — tool 拦截集成测试。"""

from __future__ import annotations

import io
import json
from pathlib import Path

import yaml

from pinrule.hooks import pre_tool_use


def _patch(monkeypatch, tmp_path: Path, sticky_items: list[dict]) -> tuple[Path, Path]:
    sticky_path = tmp_path / "sticky.yaml"
    sticky_path.write_text(yaml.safe_dump(sticky_items, allow_unicode=True), encoding="utf-8")
    violations_path = tmp_path / "violations.jsonl"
    monkeypatch.setattr("pinrule.rule.DEFAULT_PATH", sticky_path)
    monkeypatch.setattr("pinrule.violations.DEFAULT_PATH", violations_path)
    return sticky_path, violations_path


def _run_hook(monkeypatch, payload: dict) -> dict:
    """跑 hook，返回 hookSpecificOutput dict (含 permissionDecision)。"""
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    captured = io.StringIO()
    monkeypatch.setattr("sys.stdout", captured)
    pre_tool_use.main()
    out = json.loads(captured.getvalue())
    return out.get("hookSpecificOutput", {})


def test_allow_when_no_sticky(monkeypatch, tmp_path):
    monkeypatch.setattr("pinrule.rule.DEFAULT_PATH", tmp_path / "sticky.yaml")
    monkeypatch.setattr("pinrule.violations.DEFAULT_PATH", tmp_path / "v.jsonl")
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


def test_write_keyword_layer_scans_comments_only(monkeypatch, tmp_path):
    """Write/Edit 关键词层只扫注释 + docstring，不扫代码主体。

    用户反馈：关键词层全放 Write/Edit 会漏违反（注释里写意图字面是违反）。
    新语义：关键词层 Write/Edit 扫注释行 + docstring，代码主体不扫
    （主体里字面赋值几乎全是数据/描述假阳）。
    """
    _patch(monkeypatch, tmp_path, [
        {
            "id": "long-term",
            "preference": "用长期方案",
            "violation_keywords": ["硬编码", "先打个补丁"],
        },
    ])
    # Write 注释里写违反字眼 → deny（实际意图）
    out = _run_hook(monkeypatch, {
        "tool_name": "Write",
        "tool_input": {
            "file_path": "/x/src/foo.py",
            "content": "# 先打个补丁\nMAGIC = 42",
        },
    })
    assert out["permissionDecision"] == "deny", "注释里字面是实际意图，要拦"

    # Write 代码主体字面赋值（字符串数据）→ allow（不扫代码主体）
    out = _run_hook(monkeypatch, {
        "tool_name": "Write",
        "tool_input": {
            "file_path": "/x/src/foo.py",
            "content": 'MAGIC = "先打个补丁"\n# 这是个变量名常量',
        },
    })
    assert out["permissionDecision"] == "allow", "代码主体字面赋值不扫"

    # Edit 注释行被加 → deny
    out = _run_hook(monkeypatch, {
        "tool_name": "Edit",
        "tool_input": {
            "file_path": "/x/src/foo.py",
            "old_string": "# OLD",
            "new_string": "# 先打个补丁 fix",
        },
    })
    assert out["permissionDecision"] == "deny"

    # 描述上下文（.md 等）仍整段豁免（包括注释层）
    out = _run_hook(monkeypatch, {
        "tool_name": "Write",
        "tool_input": {
            "file_path": "/x/README.md",
            "content": "# 这条规则拦截「硬编码」「先打个补丁」字眼",
        },
    })
    assert out["permissionDecision"] == "allow", ".md 描述上下文仍豁免"


def test_bash_keyword_layer_still_scans(monkeypatch, tmp_path):
    """Bash command 关键词层仍扫 — 这是明确执行意图，关键词出现就是违反。"""
    _patch(monkeypatch, tmp_path, [
        {
            "id": "no-sleep",
            "preference": "不要 sleep",
            "violation_keywords": ["sleep 30"],
        },
    ])
    out = _run_hook(monkeypatch, {
        "tool_name": "Bash",
        "tool_input": {"command": "sleep 30 && echo done"},
    })
    assert out["permissionDecision"] == "deny"


def test_description_context_exempts_engine_checks(monkeypatch, tmp_path):
    """描述上下文（.md / tests/ / /tmp/）→ 工程 check 整段豁免。

    根因：HANDOFF.md / README.md 描述触发模式时 long_term/testset 会误判；
    探针/测试代码里写触发模式样本也被误判。统一抽象一次解决。
    """
    _patch(monkeypatch, tmp_path, [
        {
            "id": "long-term",
            "preference": "x",
            "violation_keywords": [],
            "violation_checks": ["long_term_fundamental"],
        },
    ])
    # .md 文档里写 if id 长 hash 字面 → 豁免
    out = _run_hook(monkeypatch, {
        "tool_name": "Write",
        "tool_input": {
            "file_path": "/x/README.md",
            "content": 'if u == "abc123def456789":\n    pass',
        },
    })
    assert out["permissionDecision"] == "allow"

    # tests/ 下写同样代码 → 豁免（测试样本）
    out = _run_hook(monkeypatch, {
        "tool_name": "Write",
        "tool_input": {
            "file_path": "/x/tests/test_foo.py",
            "content": 'if u == "abc123def456789":\n    pass',
        },
    })
    assert out["permissionDecision"] == "allow"

    # 正常源码下写同样代码 → 拦（违反）
    out = _run_hook(monkeypatch, {
        "tool_name": "Write",
        "tool_input": {
            "file_path": "/x/src/handler.py",
            "content": 'if u == "abc123def456789":\n    pass',
        },
    })
    assert out["permissionDecision"] == "deny"


def test_fail_open_on_bad_yaml(monkeypatch, tmp_path):
    """sticky.yaml 配置错 → 不阻塞 tool（fail open）。"""
    sticky_path = tmp_path / "sticky.yaml"
    sticky_path.write_text("- {{ bad yaml")
    monkeypatch.setattr("pinrule.rule.DEFAULT_PATH", sticky_path)
    monkeypatch.setattr("pinrule.violations.DEFAULT_PATH", tmp_path / "v.jsonl")
    out = _run_hook(monkeypatch, {
        "tool_name": "Bash",
        "tool_input": {"command": "sleep 5"},
    })
    # 配置坏掉了，但不该完全阻断 tool
    assert out["permissionDecision"] == "allow"


def test_fail_open_on_bad_payload(monkeypatch, tmp_path):
    """payload JSON 解析失败 → fail open。"""
    monkeypatch.setattr("pinrule.rule.DEFAULT_PATH", tmp_path / "sticky.yaml")
    monkeypatch.setattr("pinrule.violations.DEFAULT_PATH", tmp_path / "v.jsonl")
    import io
    monkeypatch.setattr("sys.stdin", io.StringIO("not json"))
    captured = io.StringIO()
    monkeypatch.setattr("sys.stdout", captured)
    pre_tool_use.main()
    out = json.loads(captured.getvalue())
    # bad payload 走顶层 _allow() → hookSpecificOutput.permissionDecision
    assert out["hookSpecificOutput"]["permissionDecision"] == "allow"
