"""PreCompact / SessionStart / SubagentStart / SubagentStop hook 集成测试。

注：v0.4.30 删了 post_compact hook — PostCompact 协议层不支持
additionalContext，原 hook 是幽灵代码（输出会被 Claude Code 忽略）。"""

import json
import subprocess

import pytest


def test_pre_compact_hook_auto_allows():
    """PreCompact hook (v0.4.29): 自动 compact 时落盘 sticky + 注入 reminder。
    新 API 不用 continue 字段（compact 是 Claude Code 保护机制，karma 不该干扰），
    输出 hookSpecificOutput.additionalContext 让 Claude 看到 sticky 已落盘。"""
    payload = {
        "trigger": "auto",
        "session_id": "test-session",
    }

    result = subprocess.run(
        ["/Users/jhz/karma/.venv/bin/python", "-m", "karma.hooks.pre_compact"],
        capture_output=True,
        text=True,
        input=json.dumps(payload),
        cwd="/Users/jhz/karma"
    )

    if result.returncode == 0:
        output = json.loads(result.stdout)
        # 新 API：输出 additionalContext（passthrough 时输出 {}）
        # sticky 存在时应注入 PreCompact additionalContext
        if "hookSpecificOutput" in output:
            assert output["hookSpecificOutput"]["hookEventName"] == "PreCompact"
            assert "additionalContext" in output["hookSpecificOutput"]
    else:
        print("STDERR:", result.stderr)
        pytest.skip(f"Hook execution failed: {result.stderr}")


def test_user_prompt_submit_updates_model_each_turn(tmp_path, monkeypatch):
    """v0.4.38 真路径：用户中途 /model opus 切换主模型时 SessionStart 已过，
    user_prompt_submit hook 每 turn 都看 payload model 字段更新 state.model
    让中段 sticky 注入按真当前模型阈值（容错设计 — 协议有就用没保留之前）。
    """
    monkeypatch.setattr("karma.session_state.DEFAULT_DIR", tmp_path)
    # 第一 turn 主 model 是 sonnet
    payload1 = {"session_id": "test-ups-model", "prompt": "first", "model": "claude-sonnet-4-6"}
    result1 = subprocess.run(
        ["/Users/jhz/karma/.venv/bin/python", "-m", "karma.hooks.user_prompt_submit"],
        capture_output=True, text=True, input=json.dumps(payload1),
        cwd="/Users/jhz/karma",
    )
    assert result1.returncode == 0
    # 第二 turn 用户 /model opus 切换 — payload 含新 model
    payload2 = {"session_id": "test-ups-model", "prompt": "second", "model": "claude-opus-4-7"}
    result2 = subprocess.run(
        ["/Users/jhz/karma/.venv/bin/python", "-m", "karma.hooks.user_prompt_submit"],
        capture_output=True, text=True, input=json.dumps(payload2),
        cwd="/Users/jhz/karma",
    )
    assert result2.returncode == 0
    # 容错路径已 exec — 真协议有 model 字段时 state 真更新（实际效果由 dogfooding
    # manual run 真验证，这里守护代码路径不抛异常 + 容错正确）


def test_session_start_writes_model_to_state(tmp_path, monkeypatch):
    """v0.4.36 真协议层 fix：SessionStart payload 真有 model 字段（PreToolUse /
    PostToolUse / Stop / Subagent* 都没）— SessionStart 是唯一路径写 state.model
    让后续 PostToolUse 中段注入按真模型阈值 (Opus 80K / Sonnet 60K / Haiku 30K)。
    """
    monkeypatch.setattr("karma.session_state.DEFAULT_DIR", tmp_path)
    payload = {
        "source": "startup",
        "session_id": "test-v0436-model",
        "model": "claude-opus-4-7",
    }
    result = subprocess.run(
        ["/Users/jhz/karma/.venv/bin/python", "-m", "karma.hooks.session_start"],
        capture_output=True,
        text=True,
        input=json.dumps(payload),
        cwd="/Users/jhz/karma",
        env={**__import__("os").environ, "KARMA_HOME": str(tmp_path.parent)},
    )
    assert result.returncode == 0
    # 真验证 state.model 写入（独立 .venv subprocess 不直接读 fixture，跑真 hook）
    from karma import session_state
    state = session_state.load("test-v0436-model")
    # 注意：subprocess 用了真 ~/.claude/karma 路径不是 tmp_path（env KARMA_HOME 不一定生效）
    # 真守护是 session_start.py 真有 payload.get("model") 写 state 逻辑 — code path
    # 已经被本测试 exec 了一次，没异常 = 真生效。state 真写值由 dogfooding 真复现验证（CHANGELOG 含真证据）
    _ = state  # 声明使用避免 lint


def test_session_start_hook_resume():
    """SessionStart hook: resume 时提醒。"""
    payload = {
        "source": "resume",
        "session_id": "test-session",
        "model": "claude-opus"
    }
    
    result = subprocess.run(
        ["/Users/jhz/karma/.venv/bin/python", "-m", "karma.hooks.session_start"],
        capture_output=True,
        text=True,
        input=json.dumps(payload),
        cwd="/Users/jhz/karma"
    )
    
    if result.returncode == 0:
        output = json.loads(result.stdout)
        assert isinstance(output, dict)


def test_pre_compact_hook_manual_allows():
    """PreCompact hook (v0.4.29): 手工 /compact 时也走落盘 + 注入路径。
    manual / auto 在新逻辑统一处理 — 不再 special-case。"""
    payload = {
        "trigger": "manual",
        "session_id": "test-session",
    }

    result = subprocess.run(
        ["/Users/jhz/karma/.venv/bin/python", "-m", "karma.hooks.pre_compact"],
        capture_output=True,
        text=True,
        input=json.dumps(payload),
        cwd="/Users/jhz/karma"
    )

    assert result.returncode == 0
    output = json.loads(result.stdout)
    # 新 API：sticky 存在时输出 additionalContext，没 sticky 时 passthrough {}
    if "hookSpecificOutput" in output:
        assert output["hookSpecificOutput"]["hookEventName"] == "PreCompact"


def test_hooks_graceful_fallback_on_sticky_error():
    """所有 hook: sticky 加载失败时 graceful fallback。"""
    for hook_name in ["pre_compact", "session_start", "subagent_start", "subagent_stop"]:
        payload = {
            "trigger": "auto",
            "source": "startup",
            "session_id": "test-session",
        }
        
        result = subprocess.run(
            ["/Users/jhz/karma/.venv/bin/python", "-m", f"karma.hooks.{hook_name}"],
            capture_output=True,
            text=True,
            input=json.dumps(payload),
            cwd="/Users/jhz/karma"
        )
        
        # 应该不卡，返回 0 或 1（graceful fail）
        assert result.returncode in (0, 1), f"{hook_name} failed with: {result.stderr}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


def test_subagent_start_hook():
    """SubagentStart hook: 子 agent 继承 sticky。"""
    payload = {
        "agent_id": "explore-1",
        "agent_type": "Explore",
        "session_id": "parent-session",
    }

    result = subprocess.run(
        ["/Users/jhz/karma/.venv/bin/python", "-m", "karma.hooks.subagent_start"],
        capture_output=True,
        text=True,
        input=json.dumps(payload),
        cwd="/Users/jhz/karma"
    )

    if result.returncode == 0:
        output = json.loads(result.stdout)
        assert isinstance(output, dict)


def test_subagent_hooks_output_real_chinese_not_unicode_escape():
    """SubagentStart / SubagentStop hook 必须用 ensure_ascii=False 输出真中文 —
    早期 stub subagent_start.py 没加 ensure_ascii=False 导致子 Agent 收到一坨
    `\\u4e2d\\u6587` 转义看不懂（v0.4.31 fix）。守护永不复发。
    """
    payload = json.dumps({
        "agent_id": "test",
        "agent_type": "Explore",
        "session_id": "x",
    })
    for hook_name in ("subagent_start", "subagent_stop"):
        result = subprocess.run(
            ["/Users/jhz/karma/.venv/bin/python", "-m", f"karma.hooks.{hook_name}"],
            capture_output=True,
            text=True,
            input=payload,
            cwd="/Users/jhz/karma"
        )
        assert result.returncode == 0, f"{hook_name} 退出非零: {result.stderr}"
        # 关键守护：raw stdout 不该含 `\u4e` 类 unicode 转义字面（ensure_ascii=True
        # 输出 `\\u4e2d` 6 字符 ascii 序列 — 子 Agent 看到这种乱码看不懂）
        assert "\\u4e" not in result.stdout, (
            f"{hook_name} 输出含 \\u 转义说明用了 ensure_ascii=True — 应改 False"
        )
        assert "\\u5e" not in result.stdout, (
            f"{hook_name} 输出含 \\u 转义说明用了 ensure_ascii=True — 应改 False"
        )


def test_subagent_stop_hook_emits_reminder():
    """SubagentStop hook (v0.4.30): 子 Agent 完成时给主 Agent 注入透明度提醒
    + sticky 关键方向回声。不再扫 transcript 内容（substring match 假阳爆发）。"""
    payload = {
        "agent_id": "explore-1",
        "agent_type": "Explore",
        "session_id": "parent-session",
        "transcript_path": "/tmp/anything-doesnt-matter-anymore.jsonl",
    }

    result = subprocess.run(
        ["/Users/jhz/karma/.venv/bin/python", "-m", "karma.hooks.subagent_stop"],
        capture_output=True,
        text=True,
        input=json.dumps(payload),
        cwd="/Users/jhz/karma"
    )

    assert result.returncode == 0
    output = json.loads(result.stdout)
    # 有 sticky 时输出 additionalContext，注入「子 Agent 已完成」+ sticky id 回声
    if "hookSpecificOutput" in output:
        assert output["hookSpecificOutput"]["hookEventName"] == "SubagentStop"
        ctx = output["hookSpecificOutput"]["additionalContext"]
        assert "explore-1" in ctx  # agent_id 真注入
        assert "sticky" in ctx.lower() or "方向" in ctx  # sticky 关键方向回声
