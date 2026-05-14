"""Hook entrypoints — input/output 集成测试。"""

from __future__ import annotations

import io
import json
from pathlib import Path

import yaml

from karma.hooks import post_tool_use, stop, user_prompt_submit
from karma import session_state


def _patch_paths(monkeypatch, tmp_path: Path, sticky_items: list[dict] | None = None):
    """让 hook 用 tmp 目录的 sticky/violations 文件。"""
    sticky_path = tmp_path / "sticky.yaml"
    violations_path = tmp_path / "violations.jsonl"
    if sticky_items is not None:
        sticky_path.write_text(yaml.safe_dump(sticky_items, allow_unicode=True), encoding="utf-8")
    monkeypatch.setattr("karma.sticky.DEFAULT_PATH", sticky_path)
    monkeypatch.setattr("karma.violations.DEFAULT_PATH", violations_path)
    return sticky_path, violations_path


def test_user_prompt_submit_no_sticky_passthrough(monkeypatch, tmp_path, capsys):
    """sticky.yaml 不存在 → 输出空 JSON（无 additionalContext）。"""
    _patch_paths(monkeypatch, tmp_path, sticky_items=None)
    payload = json.dumps({"prompt": "你好", "session_id": "s"})
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    rc = user_prompt_submit.main()
    captured = capsys.readouterr()
    assert rc == 0
    out = json.loads(captured.out)
    assert out == {}


def test_user_prompt_submit_injects_sticky_as_context(monkeypatch, tmp_path, capsys):
    _patch_paths(monkeypatch, tmp_path, sticky_items=[
        {"id": "test-rule", "preference": "用长期方案", "violation_keywords": ["补丁"]},
    ])
    payload = json.dumps({"prompt": "开始吧", "session_id": "s"})
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    rc = user_prompt_submit.main()
    captured = capsys.readouterr()
    assert rc == 0
    out = json.loads(captured.out)
    hso = out["hookSpecificOutput"]
    assert hso["hookEventName"] == "UserPromptSubmit"
    ctx = hso["additionalContext"]
    assert "[karma sticky" in ctx
    assert "用长期方案" in ctx


def test_user_prompt_submit_handles_bad_yaml(monkeypatch, tmp_path, capsys):
    """sticky.yaml 配置错 → stderr 报错，输出 passthrough（空 JSON）。"""
    sticky_path = tmp_path / "sticky.yaml"
    sticky_path.write_text("- {{ this is not valid yaml", encoding="utf-8")
    monkeypatch.setattr("karma.sticky.DEFAULT_PATH", sticky_path)
    monkeypatch.setattr("karma.violations.DEFAULT_PATH", tmp_path / "violations.jsonl")
    payload = json.dumps({"prompt": "你好", "session_id": "s"})
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    rc = user_prompt_submit.main()
    captured = capsys.readouterr()
    assert rc == 0
    out = json.loads(captured.out)
    assert out == {}
    assert "karma:" in captured.err


def test_stop_reads_transcript_and_detects(monkeypatch, tmp_path, capsys):
    """Stop hook 读 transcript 文件，扫最后 assistant message 中违反。"""
    _, violations_path = _patch_paths(monkeypatch, tmp_path, sticky_items=[
        {"id": "no-patch", "preference": "no patches", "violation_keywords": ["先打个补丁"]},
    ])
    # 准备假 transcript
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text("\n".join([
        json.dumps({"type": "user", "message": {"content": "你来修一下"}}),
        json.dumps({
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "text", "text": "让我先打个补丁快速搞定"}
                ]
            }
        }),
    ]), encoding="utf-8")
    payload = json.dumps({
        "session_id": "test-session",
        "transcript_path": str(transcript),
    })
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    rc = stop.main()
    captured = capsys.readouterr()
    assert rc == 0
    assert violations_path.exists()
    lines = violations_path.read_text(encoding="utf-8").splitlines()
    assert any(json.loads(ln)["sticky_id"] == "no-patch" for ln in lines)
    assert "⚠️ karma" in captured.err


def test_stop_no_transcript_no_op(monkeypatch, tmp_path, capsys):
    _patch_paths(monkeypatch, tmp_path, sticky_items=[
        {"id": "no-patch", "preference": "x", "violation_keywords": ["补丁"]},
    ])
    payload = json.dumps({"session_id": "s", "transcript_path": "/nonexistent"})
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    rc = stop.main()
    captured = capsys.readouterr()
    assert rc == 0
    assert json.loads(captured.out) == {}


def test_post_tool_use_write_records_read(monkeypatch, tmp_path, capsys):
    """Write 文件后 post_tool_use 既 record_edit 也 record_read —
    Agent 写过的内容自己知道，后续 Edit 同文件不该被 read_first 多余拦。
    """
    monkeypatch.setattr("karma.session_state.DEFAULT_DIR", tmp_path)
    payload = json.dumps({
        "session_id": "write_then_edit",
        "tool_name": "Write",
        "tool_input": {"file_path": "/x/new.py", "content": "x = 1"},
        "tool_response": "File created successfully",
    })
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    rc = post_tool_use.main()
    assert rc == 0
    # 验证 state 文件里 read_files 含 /x/new.py
    state = session_state.load("write_then_edit", base_dir=tmp_path)
    assert "/x/new.py" in state.read_files, "Write 应该同时 record_read"
    assert "/x/new.py" in state.edit_files


def test_post_tool_use_edit_does_not_imply_read(monkeypatch, tmp_path, capsys):
    """Edit 只改部分内容 → 不该 record_read（read_first 仍要拦未读 Edit）。"""
    monkeypatch.setattr("karma.session_state.DEFAULT_DIR", tmp_path)
    payload = json.dumps({
        "session_id": "edit_only",
        "tool_name": "Edit",
        "tool_input": {"file_path": "/x/existing.py", "old_string": "a", "new_string": "b"},
        "tool_response": "ok",
    })
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    rc = post_tool_use.main()
    assert rc == 0
    state = session_state.load("edit_only", base_dir=tmp_path)
    assert "/x/existing.py" not in state.read_files, "Edit 不应自动 record_read"
    assert "/x/existing.py" in state.edit_files


# ---- 缺口 #6 — tool 失败时不 record（防 read_first 被绕过） ----

def test_post_tool_use_failed_read_does_not_record(monkeypatch, tmp_path):
    """Read 失败（dict 含 isError=True）→ 不 record_read。否则 Agent 用 Read 失败
    后立刻 Edit 同文件会绕过 read_first 检测。"""
    monkeypatch.setattr("karma.session_state.DEFAULT_DIR", tmp_path)
    payload = json.dumps({
        "session_id": "read_fail",
        "tool_name": "Read",
        "tool_input": {"file_path": "/x/notexist.py"},
        "tool_response": {"content": "", "isError": True},
    })
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    rc = post_tool_use.main()
    assert rc == 0
    state = session_state.load("read_fail", base_dir=tmp_path)
    assert "/x/notexist.py" not in state.read_files, "Read 失败不该 record_read"


def test_post_tool_use_failed_read_string_error_does_not_record(monkeypatch, tmp_path):
    """Read 返回 'Error: ...' 字符串前缀也算失败 → 不 record。"""
    monkeypatch.setattr("karma.session_state.DEFAULT_DIR", tmp_path)
    payload = json.dumps({
        "session_id": "read_str_fail",
        "tool_name": "Read",
        "tool_input": {"file_path": "/x/notexist.py"},
        "tool_response": "Error: File does not exist: /x/notexist.py",
    })
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    post_tool_use.main()
    state = session_state.load("read_str_fail", base_dir=tmp_path)
    assert "/x/notexist.py" not in state.read_files


def test_post_tool_use_failed_edit_does_not_record(monkeypatch, tmp_path):
    """Edit 失败（old_string 不匹配等）→ 不 record_edit（代码没真改成）。"""
    monkeypatch.setattr("karma.session_state.DEFAULT_DIR", tmp_path)
    payload = json.dumps({
        "session_id": "edit_fail",
        "tool_name": "Edit",
        "tool_input": {"file_path": "/x/foo.py", "old_string": "a", "new_string": "b"},
        "tool_response": {"content": "", "isError": True},
    })
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    post_tool_use.main()
    state = session_state.load("edit_fail", base_dir=tmp_path)
    assert "/x/foo.py" not in state.edit_files, "Edit 失败不该 record_edit"


def test_post_tool_use_failed_bash_still_records(monkeypatch, tmp_path):
    """Bash 即便 interrupted=True 也要 record — has_recent_test_pass 由内部
    PASS/FAIL 信号判，不依赖 tool 整体成败。"""
    monkeypatch.setattr("karma.session_state.DEFAULT_DIR", tmp_path)
    payload = json.dumps({
        "session_id": "bash_fail",
        "tool_name": "Bash",
        "tool_input": {"command": "pytest tests/"},
        "tool_response": {"stdout": "1 failed, 5 passed", "stderr": "", "interrupted": False},
    })
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    post_tool_use.main()
    state = session_state.load("bash_fail", base_dir=tmp_path)
    assert len(state.recent_bash) == 1, "Bash 仍应 record snapshot 即使输出有 fail 信号"
    snap = state.recent_bash[-1]
    assert snap.output_failed
    assert not state.has_recent_test_pass()


def test_post_tool_use_successful_read_records(monkeypatch, tmp_path):
    """Read 成功（无 isError）→ 正常 record_read。"""
    monkeypatch.setattr("karma.session_state.DEFAULT_DIR", tmp_path)
    payload = json.dumps({
        "session_id": "read_ok",
        "tool_name": "Read",
        "tool_input": {"file_path": "/x/exists.py"},
        "tool_response": {"content": "x = 1\n", "isError": False},
    })
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    post_tool_use.main()
    state = session_state.load("read_ok", base_dir=tmp_path)
    assert "/x/exists.py" in state.read_files


def test_post_tool_use_docs_edit_does_not_push_last_edit_ts(monkeypatch, tmp_path):
    """改 docs (.md) / 配置 (.yaml) 不算「代码改动」 — last_edit_ts 不动。

    用户洞察：sticky #4 说「完成代码任务必须附测试证据」，docs 改不是代码任务。
    post_tool_use 应区分文件类型，描述上下文文件 Edit 不推 last_edit_ts。
    """
    monkeypatch.setattr("karma.session_state.DEFAULT_DIR", tmp_path)
    # 改 README.md
    payload = json.dumps({
        "session_id": "docs_edit",
        "tool_name": "Edit",
        "tool_input": {"file_path": "/x/README.md", "old_string": "a", "new_string": "b"},
        "tool_response": "ok",
    })
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    post_tool_use.main()
    state = session_state.load("docs_edit", base_dir=tmp_path)
    assert state.last_edit_ts == 0.0, "docs Edit 不该推 last_edit_ts"
    # 但 edit_files 历史可以保留（record_edit 没被调）
    assert state.edit_files == []


def test_post_tool_use_code_edit_pushes_last_edit_ts(monkeypatch, tmp_path):
    """改普通源码（.py）推 last_edit_ts（real 代码改动）。"""
    monkeypatch.setattr("karma.session_state.DEFAULT_DIR", tmp_path)
    payload = json.dumps({
        "session_id": "code_edit",
        "tool_name": "Edit",
        "tool_input": {"file_path": "/x/src/foo.py", "old_string": "a", "new_string": "b"},
        "tool_response": "ok",
    })
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    post_tool_use.main()
    state = session_state.load("code_edit", base_dir=tmp_path)
    assert state.last_edit_ts > 0, "代码 Edit 应推 last_edit_ts"
    assert "/x/src/foo.py" in state.edit_files


def test_post_tool_use_yaml_write_does_not_push_last_edit_ts(monkeypatch, tmp_path):
    """改 .yaml 配置不算代码改动。"""
    monkeypatch.setattr("karma.session_state.DEFAULT_DIR", tmp_path)
    payload = json.dumps({
        "session_id": "yaml_write",
        "tool_name": "Write",
        "tool_input": {"file_path": "/x/config.yaml", "content": "key: value\n"},
        "tool_response": "ok",
    })
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    post_tool_use.main()
    state = session_state.load("yaml_write", base_dir=tmp_path)
    assert state.last_edit_ts == 0.0, "yaml Write 不该推 last_edit_ts"


# ---- Stop hook decision: block 干预 keep-pushing ----

def test_stop_hook_force_blocks_on_accumulated_violations(monkeypatch, tmp_path, capsys):
    """机制 2：同一 sticky 累积 ≥ force_block_threshold 次 → Stop hook 强制 decision=block。

    Agent 反复违反同一规则却没 fix 真根因 → karma 强制要求修。
    """
    _, violations_path = _patch_paths(monkeypatch, tmp_path, sticky_items=[
        {
            "id": "long-term-fundamental",
            "preference": "x",
            "violation_keywords": ["先打个补丁"],
        },
    ])
    monkeypatch.setattr("karma.session_state.DEFAULT_DIR", tmp_path)
    # 预设 5 条同 sticky 违反 + 本 session turn=3
    from karma.violations import Violation, append as v_append
    items = [
        Violation(ts=i, session_id="force", sticky_id="long-term-fundamental",
                  trigger="先打个补丁", snippet=".", turn=t)
        for i, t in enumerate(range(1, 6))
    ]
    v_append(items, path=violations_path)
    # session_state turn=5（窗口内 5 条都算）
    state = session_state.SessionState(session_id="force")
    state.turn_count = 5
    session_state.save(state, base_dir=tmp_path)

    # transcript 含再次违反字眼
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(json.dumps({
        "type": "assistant",
        "message": {"content": [{"type": "text", "text": "我先打个补丁再说"}]},
    }) + "\n", encoding="utf-8")
    payload = json.dumps({
        "session_id": "force",
        "transcript_path": str(transcript),
    })
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    stop.main()
    out = json.loads(capsys.readouterr().out)
    assert out.get("decision") == "block", f"累积超阈值应强制 block，实际：{out}"
    assert "强制" in out.get("reason", "") or "累积" in out.get("reason", ""), \
        f"reason 应说明强制累积，实际：{out.get('reason', '')}"


def test_stop_hook_force_block_exempts_keep_pushing(monkeypatch, tmp_path, capsys):
    """keep-pushing-no-stop 自身豁免 force_block — 语义自相矛盾。

    累积「停下太多」违反 → 触发 force_block 让 Agent「停下让用户介入」恰好
    再违反 keep-pushing 本身。dogfooding 实战发现：本 session 触发 4 次
    keep-pushing，再 1 次就到 force_block 阈值会自我矛盾。
    """
    _, violations_path = _patch_paths(monkeypatch, tmp_path, sticky_items=[
        {
            "id": "keep-pushing-no-stop",
            "preference": "不停下",
            "violation_keywords": [],
            "violation_checks": ["keep_pushing_no_stop"],
            "force_block_exempt": True,  # 关键 — 这条字段控制豁免
        },
    ])
    monkeypatch.setattr("karma.session_state.DEFAULT_DIR", tmp_path)
    # 预设 5 条 keep-pushing 违反（force_threshold 默认 5）
    from karma.violations import Violation, append as v_append
    items = [
        Violation(ts=i, session_id="kp_force", sticky_id="keep-pushing-no-stop",
                  trigger="response 纯陈述完结", snippet=".", turn=t)
        for i, t in enumerate(range(1, 6))
    ]
    v_append(items, path=violations_path)
    state = session_state.SessionState(session_id="kp_force")
    state.turn_count = 5
    session_state.save(state, base_dir=tmp_path)

    # transcript 命中 keep-pushing（纯陈述完结）
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(json.dumps({
        "type": "assistant",
        "message": {"content": [{"type": "text", "text": "做完了，commit 推上。"}]},
    }) + "\n", encoding="utf-8")
    payload = json.dumps({
        "session_id": "kp_force",
        "transcript_path": str(transcript),
    })
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    stop.main()
    out = json.loads(capsys.readouterr().out)
    # 应该走 keep-pushing 轻干预路径（reason 含 'keep-pushing'）
    # 不该走 force_block 路径（reason 不含 '强制干预'）
    if out.get("decision") == "block":
        reason = out.get("reason", "")
        assert "强制干预" not in reason, (
            f"keep-pushing 不应触发 force_block 自我矛盾，应走轻干预。reason: {reason}"
        )


def test_stop_hook_blocks_when_keep_pushing_violated(monkeypatch, tmp_path, capsys):
    """Agent response 末尾停顿词 + 命中 keep-pushing → Stop hook 输出 decision=block
    让 Agent 不真停下，继续生成。"""
    _, violations_path = _patch_paths(monkeypatch, tmp_path, sticky_items=[
        {
            "id": "keep-pushing-no-stop",
            "preference": "不停下",
            "violation_keywords": [],
            "violation_checks": ["keep_pushing_no_stop"],
        },
    ])
    monkeypatch.setattr("karma.session_state.DEFAULT_DIR", tmp_path)
    # 准备 transcript 含「先到这」末尾停顿词
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(json.dumps({
        "type": "assistant",
        "message": {"content": [{"type": "text", "text": "做完了，测试全过。先到这。"}]},
    }) + "\n", encoding="utf-8")
    payload = json.dumps({
        "session_id": "block_test",
        "transcript_path": str(transcript),
    })
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    stop.main()
    out = json.loads(capsys.readouterr().out)
    assert out.get("decision") == "block", f"应输出 decision=block，实际：{out}"
    assert "keep-pushing" in out.get("reason", "")


def test_user_prompt_submit_injects_strong_reminder_when_last_response_stopped(
    monkeypatch, tmp_path, capsys,
):
    """user_prompt_submit hook 检测上一 response 末尾无推进信号 → 注入强提醒。

    这是 Stop hook 「user 立刻接 prompt 时不跑」协议 limitation 的 fallback fix。
    扩展版：跑所有 sticky 的 violation_checks，不只 keep-pushing。
    """
    _patch_paths(monkeypatch, tmp_path, sticky_items=[
        {"id": "keep-pushing-no-stop", "preference": "x",
         "violation_checks": ["keep_pushing_no_stop"]},
    ])
    monkeypatch.setattr("karma.session_state.DEFAULT_DIR", tmp_path)
    # transcript last assistant = 「完成了。」纯陈述无推进
    transcript = tmp_path / "trans.jsonl"
    transcript.write_text(json.dumps({
        "type": "assistant",
        "message": {"content": [{"type": "text", "text": "完成了，commit 推上。"}]},
    }) + "\n", encoding="utf-8")
    payload = json.dumps({
        "session_id": "stop_check",
        "transcript_path": str(transcript),
        "prompt": "hi",
    })
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    user_prompt_submit.main()
    out = json.loads(capsys.readouterr().out)
    ctx = out.get("hookSpecificOutput", {}).get("additionalContext", "")
    assert "强提醒" in ctx and "keep-pushing-no-stop" in ctx, \
        f"上一 response 无推进信号应注入强提醒含具体 sticky id：{ctx}"


def test_user_prompt_submit_no_reminder_when_last_response_has_push(
    monkeypatch, tmp_path, capsys,
):
    """上一 response 含推进信号（我接下来 X）→ 不注入强提醒。"""
    _patch_paths(monkeypatch, tmp_path, sticky_items=[
        {"id": "keep-pushing-no-stop", "preference": "x",
         "violation_checks": ["keep_pushing_no_stop"]},
    ])
    monkeypatch.setattr("karma.session_state.DEFAULT_DIR", tmp_path)
    transcript = tmp_path / "trans.jsonl"
    transcript.write_text(json.dumps({
        "type": "assistant",
        "message": {"content": [{"type": "text",
                                  "text": "完成了，commit 推上。我接下来去做下一步推进。"}]},
    }) + "\n", encoding="utf-8")
    payload = json.dumps({
        "session_id": "stop_ok",
        "transcript_path": str(transcript),
        "prompt": "hi",
    })
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    user_prompt_submit.main()
    out = json.loads(capsys.readouterr().out)
    ctx = out.get("hookSpecificOutput", {}).get("additionalContext", "")
    assert "强提醒" not in ctx, "上一 response 有推进信号不该注入强提醒"


def test_user_prompt_submit_runs_catchup(monkeypatch, tmp_path, capsys):
    """UserPromptSubmit hook 也跑 catchup_pending_bg — task #8 task 完成后
    第一个 hook 触发时接证据，覆盖 PostToolUse 之外场景。"""
    _patch_paths(monkeypatch, tmp_path, sticky_items=[
        {"id": "test-rule", "preference": "x"},
    ])
    monkeypatch.setattr("karma.session_state.DEFAULT_DIR", tmp_path)
    # 准备 pending_bg_tasks + 文件
    log = tmp_path / "bg.log"
    log.write_text("===== 10 passed in 0.1s =====")
    state = session_state.SessionState(session_id="catchup_ups")
    state.pending_bg_tasks = [{
        "cmd": "pytest tests/",
        "output_file": str(log),
        "started_ts": 0,
    }]
    session_state.save(state, base_dir=tmp_path)

    payload = json.dumps({"prompt": "hi", "session_id": "catchup_ups"})
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    user_prompt_submit.main()

    state_after = session_state.load("catchup_ups", base_dir=tmp_path)
    assert state_after.pending_bg_tasks == [], "UserPromptSubmit 应跑 catchup 清 pending"
    assert state_after.has_recent_test_pass(), "catchup 后应有测试通过证据"


def test_stop_hook_respects_block_max(monkeypatch, tmp_path, capsys):
    """单 turn 内 block 累积超 max → 不再 block，让 Agent 真停（防死循环）。"""
    _patch_paths(monkeypatch, tmp_path, sticky_items=[
        {
            "id": "keep-pushing-no-stop",
            "preference": "x",
            "violation_keywords": [],
            "violation_checks": ["keep_pushing_no_stop"],
        },
    ])
    monkeypatch.setattr("karma.session_state.DEFAULT_DIR", tmp_path)
    # 预设 session state 已 block 3 次（达到 max）
    state = session_state.SessionState(session_id="max_block")
    state.stop_block_count = 3  # default max=3
    state.turn_count = 1
    session_state.save(state, base_dir=tmp_path)

    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(json.dumps({
        "type": "assistant",
        "message": {"content": [{"type": "text", "text": "测试通过。告一段落。"}]},
    }) + "\n", encoding="utf-8")
    payload = json.dumps({
        "session_id": "max_block",
        "transcript_path": str(transcript),
    })
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    stop.main()
    out = json.loads(capsys.readouterr().out)
    # 已达 max → 不再 block，走正常 additionalContext 输出
    assert out.get("decision") != "block", "已达 max 应放 Agent 停"
    assert "hookSpecificOutput" in out
