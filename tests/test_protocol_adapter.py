"""v0.9.15: cross-backend protocol adapter — tool_name 归一化 + output shape.

Background: codex GPT-5.5 cross-model audit + WebFetch 官方文档 (Gemini hooks
ref / Codex hooks docs) 双验证发现 karma 之前假设三家 backend「字段同名兼容」
有 2 个 critical bug：

1. Codex emit_allow 必须返 `{}` 不是 Claude `{hookSpecificOutput: {permissionDecision: allow}}` — karma v0.9.16 真测发现 codex 不接受 Claude shape
   拦截全失效（写 violation 但 tool 真执行）
2. Codex 编辑用
   `apply_patch` — karma checks 用 Claude `Bash`/`Read`/`Edit`/`Write` 比较，
   完全不识别 → 全部 checks 跳过

protocol_adapter.py 修这个：input normalize + output shape 分流。本测试锁
不变量：未来 PR 加新 backend / 改 output shape 必须经过 adapter。
"""

from __future__ import annotations

import json
import sys

from karma.backends.protocol_adapter import (
    detect_backend,
    emit_allow,
    emit_deny,
    normalize_tool_input,
    normalize_tool_name,
)
# v0.10.5: parse_apply_patch_envelope 从 codex.py 直接 import (codex 私货归位)
# 不再从 protocol_adapter re-export (v0.9.16 back-compat 已不需要)
from karma.backends.codex import parse_apply_patch_envelope


# v0.9.16 Codex apply_patch envelope — 真捕获自本机 codex 0.130.0 + GPT-5.5
# session rollout (2026-05-16T13:51:47, custom_tool_call.input 字段). 锁这条字面
# 确保 parser 不退化.
REAL_CODEX_SINGLE_FILE_ENVELOPE = (
    "*** Begin Patch\n"
    "*** Update File: /tmp/karma-codex-toy.py\n"
    "@@\n"
    "+# v0.9.16 test\n"
    "*** End Patch\n"
)

# 多文件 + Add + Delete 综合 envelope — 文档化 codex apply_patch 完整语法
# (https://developers.openai.com/codex/hooks docs apply_patch grammar). 单文件
# 真捕获已锁，多文件靠文档+grammar 推理保证 parser 对所有 op 都识别.
SYNTHETIC_MULTI_FILE_ENVELOPE = (
    "*** Begin Patch\n"
    "*** Update File: /tmp/a.py\n"
    "@@\n"
    "-old line\n"
    "+new line\n"
    "*** Update File: /tmp/b.py\n"
    "@@\n"
    "+added\n"
    "*** Add File: /tmp/c.py\n"
    "+brand new content\n"
    "*** Delete File: /tmp/d.py\n"
    "*** End Patch\n"
)

# 真源码路径的多文件 envelope — 用于 post_tool_use 集成测试，因为 /tmp/ 路径会被
# is_description_context 当 probe context 跳过 record_edit. 这里用 src/ 路径
# 验证 last_edit_ts 真推进.
SYNTHETIC_MULTI_FILE_CODE_ENVELOPE = (
    "*** Begin Patch\n"
    "*** Update File: /workspace/src/a.py\n"
    "@@\n"
    "-old\n"
    "+new\n"
    "*** Update File: /workspace/src/b.py\n"
    "@@\n"
    "+added\n"
    "*** Add File: /workspace/src/c.py\n"
    "+new content\n"
    "*** Delete File: /workspace/src/d.py\n"
    "*** End Patch\n"
)


def test_detect_backend_claude_codex_by_event_name():
    """Claude / Codex stdin payload 含 hook_event_name in PreToolUse/Stop/...

    v0.10.0: claude-code 是 REGISTRY canonical key (取代之前的简写 'claude').
    """
    assert detect_backend({"hook_event_name": "PreToolUse"}) == "claude-code"
    assert detect_backend({"hook_event_name": "PostToolUse"}) == "claude-code"
    assert detect_backend({"hook_event_name": "Stop"}) == "claude-code"
    assert detect_backend({"hook_event_name": "UserPromptSubmit"}) == "claude-code"
    # 缺字段 default claude-code（detect 走 fallback）
    assert detect_backend({}) == "claude-code"


def test_detect_backend_codex_by_wrapper_path(monkeypatch):
    """v0.10.0 真测试 2026-05-16 抓到 codex 不接受 permissionDecision:allow shape.

    detect_backend 必须真识别 codex 来路 (sys.argv[0] 含 /.codex/hooks/)，
    不能 fallback 到 claude-code, 否则 emit_allow 走错 shape 让 codex 报
    'unsupported permissionDecision:allow' 失败. 这是 v0.9.15 假设错的根因 lockdown.
    """
    monkeypatch.setattr(sys, "argv", ["/Users/jhz/.codex/hooks/karma_pre_tool_use.py"])
    assert detect_backend({}) == "codex"
    assert detect_backend({"hook_event_name": "PreToolUse"}) == "codex"


def test_codex_emit_allow_returns_empty_dict_not_claude_shape():
    """v0.10.0 Bug A lockdown — codex docs 原文:
    > "permissionDecision: 'allow' ... not supported yet"
    > "To permit a tool call, either return an empty JSON object ({})"

    真测试 2026-05-16 codex 0.130 cli 报: unsupported permissionDecision:allow.
    任何后续 PR 让 codex.emit_allow 退回 Claude hookSpecificOutput shape 必须挂.
    """
    from karma.backends import REGISTRY as _REG
    out = _REG["codex"].emit_allow({})
    assert out == "{}", (
        f"Codex emit_allow 必须返 '{{}}' 让 codex 通过 fail-open 路径, "
        f"不能用 Claude hookSpecificOutput.allow shape (codex 拒绝). 实际: {out!r}"
    )


def test_codex_permission_request_routes_to_codex_deny_shape(monkeypatch):
    """PermissionRequest is Codex-only; wrapper path must route to Codex output shape."""
    monkeypatch.setattr(sys, "argv", ["/Users/jhz/.codex/hooks/karma_pre_tool_use.py"])
    out = emit_deny(
        "blocked by karma",
        {"hook_event_name": "PermissionRequest"},
    )
    assert json.loads(out) == {
        "hookSpecificOutput": {
            "hookEventName": "PermissionRequest",
            "decision": {
                "behavior": "deny",
                "message": "blocked by karma",
            },
        }
    }


def test_normalize_tool_name_codex_apply_patch_to_edit(monkeypatch):
    """v0.9.15 critical fix: Codex apply_patch（编辑入口）归一化成 Edit 让
    long_term / testset / bypass_karma 扫 tool_input.command 时真触发。
    之前 apply_patch 漏所有编辑型 check → evidence check 被绕过。

    v0.10.5 (Agent 2 F1 fix): mock sys.argv 让 detect_backend 路由到 codex,
    不再依赖删掉的「apply_patch 字面兜底」.
    """
    monkeypatch.setattr(sys, "argv", ["/Users/jhz/.codex/hooks/karma_pre_tool_use.py"])
    codex_payload = {"hook_event_name": "PreToolUse"}
    assert normalize_tool_name("apply_patch", codex_payload) == "Edit"
    # Codex Bash 已是 canonical
    assert normalize_tool_name("Bash", codex_payload) == "Bash"


def test_normalize_tool_name_claude_passthrough():
    """Claude 原生 tool_name 已是 canonical，透传不变。"""
    claude_payload = {"hook_event_name": "PreToolUse"}
    for tn in ("Bash", "Read", "Edit", "Write", "NotebookEdit", "Agent"):
        assert normalize_tool_name(tn, claude_payload) == tn


def test_emit_deny_claude_codex_shape_hookSpecificOutput():
    """Claude + Codex 用 hookSpecificOutput 新格式（Codex 文档明确支持）."""
    claude_payload = {"hook_event_name": "PreToolUse"}
    out = emit_deny("test reason", claude_payload)
    parsed = json.loads(out)
    hso = parsed.get("hookSpecificOutput", {})
    assert hso.get("permissionDecision") == "deny"
    assert hso.get("permissionDecisionReason") == "test reason"
    assert hso.get("hookEventName") == "PreToolUse"
    # 不该有 top-level decision（避免 schema 模糊）
    assert "decision" not in parsed


def test_emit_allow_claude_explicit_allow():
    """Claude/Codex 用 hookSpecificOutput.permissionDecision: allow 显式表态."""
    claude_payload = {"hook_event_name": "PreToolUse"}
    out = emit_allow(claude_payload)
    hso = json.loads(out).get("hookSpecificOutput", {})
    assert hso.get("permissionDecision") == "allow"


def test_parse_apply_patch_real_codex_envelope_single_file():
    files = parse_apply_patch_envelope(REAL_CODEX_SINGLE_FILE_ENVELOPE)
    assert files == [{"op": "Update", "path": "/tmp/karma-codex-toy.py"}], (
        "真 codex envelope (本机捕获) parser 退化 → "
        "Codex apply_patch 单文件场景 read_first/record_edit 漏文件路径"
    )


def test_parse_apply_patch_multi_file_with_add_and_delete():
    files = parse_apply_patch_envelope(SYNTHETIC_MULTI_FILE_ENVELOPE)
    assert files == [
        {"op": "Update", "path": "/tmp/a.py"},
        {"op": "Update", "path": "/tmp/b.py"},
        {"op": "Add", "path": "/tmp/c.py"},
        {"op": "Delete", "path": "/tmp/d.py"},
    ], "多文件 envelope parser 漏 op 或 path — 多文件 patch 部分文件 read_first 漏拦"


def test_parse_apply_patch_empty_input_returns_empty_list():
    assert parse_apply_patch_envelope("") == []
    assert parse_apply_patch_envelope("not a patch") == []
    assert parse_apply_patch_envelope("*** Begin Patch\n*** End Patch") == [], (
        "无 file op 的空 envelope 应返回 []，不抛"
    )


def test_normalize_tool_input_codex_apply_patch_synthesizes_edit_shape(monkeypatch):
    """Codex apply_patch (string envelope) → karma canonical Edit dict.

    v0.10.5 (Agent 2 F1 fix): mock sys.argv 让 detect_backend 真路由 codex
    (sys.argv[0] 含 /.codex/ → backend = codex), 而不是依赖 protocol_adapter
    的 `apply_patch` 字面兜底 (那条已删让 protocol_adapter 真无 backend 字面).
    """
    monkeypatch.setattr(sys, "argv", ["/Users/jhz/.codex/hooks/karma_pre_tool_use.py"])
    codex_payload = {"hook_event_name": "PreToolUse", "tool_name": "apply_patch"}
    out = normalize_tool_input("apply_patch", REAL_CODEX_SINGLE_FILE_ENVELOPE, codex_payload)
    assert isinstance(out, dict)
    assert out["file_path"] == "/tmp/karma-codex-toy.py", (
        "primary file_path 没提到第一条 Update — read_first 会用错路径"
    )
    assert out["new_string"] == REAL_CODEX_SINGLE_FILE_ENVELOPE, (
        "new_string 应该是整个 envelope 让 keyword scan 看到全部内容"
    )
    assert out["multi_file_targets"] == [{"op": "Update", "path": "/tmp/karma-codex-toy.py"}]


def test_normalize_tool_input_codex_apply_patch_dict_form_input_field(monkeypatch):
    """Codex hook payload 可能 wrap tool_input 成 dict 含 input 字段 — 兜底."""
    monkeypatch.setattr(sys, "argv", ["/Users/jhz/.codex/hooks/karma_pre_tool_use.py"])
    codex_payload = {"hook_event_name": "PreToolUse", "tool_name": "apply_patch"}
    wrapped = {"input": REAL_CODEX_SINGLE_FILE_ENVELOPE}
    out = normalize_tool_input("apply_patch", wrapped, codex_payload)
    assert isinstance(out, dict)
    assert out["file_path"] == "/tmp/karma-codex-toy.py"
    assert out["multi_file_targets"] == [{"op": "Update", "path": "/tmp/karma-codex-toy.py"}]


def test_normalize_tool_input_non_apply_patch_passthrough():
    """非 apply_patch tool_call 原样返回 — 不破坏 Claude 现有路径."""
    claude_payload = {"hook_event_name": "PreToolUse", "tool_name": "Edit"}
    claude_input = {"file_path": "/tmp/x.py", "old_string": "a", "new_string": "b"}
    assert normalize_tool_input("Edit", claude_input, claude_payload) is claude_input


def test_normalize_tool_input_multi_file_primary_is_first_update(monkeypatch):
    """多文件 envelope: primary file_path = 第一条 Update path（不是 Add/Delete）."""
    monkeypatch.setattr(sys, "argv", ["/Users/jhz/.codex/hooks/karma_pre_tool_use.py"])
    payload = {"hook_event_name": "PreToolUse", "tool_name": "apply_patch"}
    out = normalize_tool_input("apply_patch", SYNTHETIC_MULTI_FILE_ENVELOPE, payload)
    assert out["file_path"] == "/tmp/a.py"
    assert len(out["multi_file_targets"]) == 4


def test_normalize_tool_input_malformed_envelope_passthrough():
    """envelope 不完整（没 *** Begin Patch）→ passthrough 原 input 不假装 normalize."""
    payload = {"hook_event_name": "PreToolUse", "tool_name": "apply_patch"}
    garbage = "not actually a patch"
    assert normalize_tool_input("apply_patch", garbage, payload) == garbage


def test_read_first_multi_file_blocks_when_any_update_unread(tmp_path, monkeypatch):
    """v0.9.16: codex apply_patch 多文件 patch 任一 Update 未 Read → read_first 拦.

    集成测试 lockdown: protocol_adapter.normalize_tool_input + read_first.check
    联动让多文件 codex 编辑真覆盖 read_first，不只看 primary file_path.
    """
    from karma import session_state
    from karma.checks.read_first import check as read_first_check

    state = session_state.SessionState(session_id="codex-multifile-test")
    # 只读了 /tmp/a.py，没读 /tmp/b.py
    state.record_read("/tmp/a.py")

    tool_input = {
        "file_path": "/tmp/a.py",  # primary
        "new_string": SYNTHETIC_MULTI_FILE_ENVELOPE,
        "multi_file_targets": [
            {"op": "Update", "path": "/tmp/a.py"},
            {"op": "Update", "path": "/tmp/b.py"},  # 这个没 Read
            {"op": "Add", "path": "/tmp/c.py"},     # 新建豁免
            {"op": "Delete", "path": "/tmp/d.py"},  # 删除不算
        ],
    }
    hit = read_first_check(tool_name="Edit", tool_input=tool_input, session_state=state)
    assert hit is not None, (
        "多文件 codex apply_patch 含未读 Update 文件 → read_first 必须拦. "
        "如果只检查 primary path (/tmp/a.py 已 Read) 会假阴。"
    )
    assert "/tmp/b.py" in hit.snippet


def test_read_first_multi_file_allows_when_all_updates_read(tmp_path):
    """v0.9.16: 所有 Update path 都 Read 过 → read_first 放过."""
    from karma import session_state
    from karma.checks.read_first import check as read_first_check

    state = session_state.SessionState(session_id="codex-multifile-pass")
    state.record_read("/tmp/a.py")
    state.record_read("/tmp/b.py")

    tool_input = {
        "file_path": "/tmp/a.py",
        "new_string": SYNTHETIC_MULTI_FILE_ENVELOPE,
        "multi_file_targets": [
            {"op": "Update", "path": "/tmp/a.py"},
            {"op": "Update", "path": "/tmp/b.py"},
            {"op": "Add", "path": "/tmp/c.py"},
            {"op": "Delete", "path": "/tmp/d.py"},
        ],
    }
    assert read_first_check(tool_name="Edit", tool_input=tool_input, session_state=state) is None


def test_post_tool_use_records_canonical_write_file_paths_advances_last_edit_ts(tmp_path, monkeypatch):
    """v0.10.5 Agent 2 F4 functional bug lockdown — canonical `write_file_paths` 字段消费.

    跟 `read_file_paths` (v0.10.1) 对称设计. 任何 backend 的 normalize_tool_input
    把 sed -i / shell redirect / 其他 in-place 写路径打到 write_file_paths, 通用
    post_tool_use 遍历调 record_edit 推 last_edit_ts.

    本测试用 synth payload (直接给 write_file_paths) 验证通用层 wiring; codex
    backend 是否真输出这字段是 codex 侧 TODO (docs/CODEX_BACKEND.md "剩余 TODO 7").
    """
    import io
    import json
    import sys
    from karma.hooks import post_tool_use
    from karma import session_state

    monkeypatch.setattr("karma.session_state.DEFAULT_DIR", tmp_path)
    state = session_state.SessionState(session_id="canonical-write-paths-test")
    session_state.save(state, base_dir=tmp_path)

    # synth payload — 任何 backend 都该能写出这种 canonical shape
    synth_payload = {
        "session_id": "canonical-write-paths-test",
        "tool_name": "exec_command",
        "tool_input": {
            "cmd": "sed -i 's/foo/bar/' /workspace/src/x.py",
            "command": "sed -i 's/foo/bar/' /workspace/src/x.py",
            "write_file_paths": ["/workspace/src/x.py"],  # canonical write 字段
        },
        "tool_response": "",
    }
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(synth_payload)))
    monkeypatch.setattr(sys, "stdout", io.StringIO())
    monkeypatch.setattr(sys, "argv", ["/Users/jhz/.codex/hooks/karma_post_tool_use.py"])
    rc = post_tool_use.main()
    assert rc == 0

    reloaded = session_state.load("canonical-write-paths-test", base_dir=tmp_path)
    # 关键: last_edit_ts 必须真推 (代码路径 .py, 不是 docs)
    assert reloaded.last_edit_ts > 0, (
        "canonical write_file_paths 字段没让通用层调 record_edit → last_edit_ts 没推 → "
        "evidence check 假阴. v0.10.5 F4 fix wiring 失败."
    )
    edits = [str(p) for p in reloaded.edit_files]
    assert "/workspace/src/x.py" in edits


def test_post_tool_use_records_codex_shell_read_paths(tmp_path, monkeypatch):
    """v0.10.1 集成 lockdown — codex exec_command + tail/sed 全链路:
    backend.normalize_tool_input → tool_input.read_file_paths → post_tool_use
    通用层 record_read → state.read_files 真增加.

    单元路径已锁在 tests/test_codex_backend.py (codex 私货). 这里锁通用层
    backend-neutral read_file_paths 字段消费, 任何后续 backend 也用同字段都生效.
    """
    import io
    import json
    import sys
    from karma.hooks import post_tool_use
    from karma import session_state

    monkeypatch.setattr("karma.session_state.DEFAULT_DIR", tmp_path)
    state = session_state.SessionState(session_id="codex-shell-read-test")
    session_state.save(state, base_dir=tmp_path)

    # 模拟 codex exec_command tail /tmp 文件 — Codex Desktop 实际用 cmd 字段
    codex_payload = {
        "session_id": "codex-shell-read-test",
        "tool_name": "exec_command",
        "tool_input": {"cmd": "tail -n 20 /workspace/src/x.py"},
        "tool_response": "file contents...",
    }
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(codex_payload)))
    monkeypatch.setattr(sys, "stdout", io.StringIO())
    monkeypatch.setattr(sys, "argv", ["/Users/jhz/.codex/hooks/karma_post_tool_use.py"])
    rc = post_tool_use.main()
    assert rc == 0

    reloaded = session_state.load("codex-shell-read-test", base_dir=tmp_path)
    assert reloaded.has_read("/workspace/src/x.py"), (
        "codex tail exec_command 没穿透到通用 record_read — read_first 在 codex "
        "下仍会假阳拦后续 Edit. v0.10.1 codex+karma 配套环节断了."
    )


def test_post_tool_use_records_all_update_paths_in_multi_file_patch(tmp_path, monkeypatch):
    """v0.9.16 lockdown: codex apply_patch 多文件 patch 在 PostToolUse 时遍历
    record_edit 所有 Update + Add 文件 — last_edit_ts 真推 + edit_files 累 N 条.

    之前 (v0.9.15) 只 normalize tool_name，post 还是按单 file_path record，
    多文件 patch 后 N-1 个文件 last_edit_ts 不推 → evidence check 假阴.
    """
    import io
    import json
    import sys
    from karma.hooks import post_tool_use
    from karma import session_state

    monkeypatch.setattr("karma.session_state.DEFAULT_DIR", tmp_path)
    state = session_state.SessionState(session_id="codex-multi-record")
    session_state.save(state, base_dir=tmp_path)

    codex_payload = {
        "session_id": "codex-multi-record",
        "tool_name": "apply_patch",  # Codex 真 tool_name
        "tool_input": SYNTHETIC_MULTI_FILE_CODE_ENVELOPE,  # 字符串 envelope, 真源码路径
        "tool_response": "Patch applied successfully.",
    }
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(codex_payload)))
    monkeypatch.setattr(sys, "stdout", io.StringIO())
    monkeypatch.setattr(sys, "argv", ["/Users/jhz/.codex/hooks/karma_post_tool_use.py"])
    rc = post_tool_use.main()
    assert rc == 0

    reloaded = session_state.load("codex-multi-record", base_dir=tmp_path)
    # 期望 Update /workspace/src/a.py + b.py + Add c.py 都 record_edit
    # (Delete d.py 跳过)
    edits = [str(p) for p in reloaded.edit_files]
    assert "/workspace/src/a.py" in edits
    assert "/workspace/src/b.py" in edits
    assert "/workspace/src/c.py" in edits
    assert "/workspace/src/d.py" not in edits, "Delete 不应 record_edit"
    # last_edit_ts 必须真推（代码路径 .py，不是 docs）
    assert reloaded.last_edit_ts > 0, (
        "多文件 patch 含代码改动 last_edit_ts 没推 → evidence check 在 codex 下假阴"
    )
