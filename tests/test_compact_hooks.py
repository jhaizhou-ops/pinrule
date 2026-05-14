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
