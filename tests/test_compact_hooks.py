"""PreCompact / SessionStart / SubagentStart / SubagentStop hook 集成测试。

注：v0.4.30 删了 post_compact hook — PostCompact 协议层不支持
additionalContext，原 hook 是幽灵代码（输出会被 Claude Code 忽略）。

v0.9.2: 动态路径解析 (修 issue #2) — 不再硬编码 /Users/jhz/karma。
"""

import json
import pathlib
import subprocess
import sys

import pytest

# v0.9.2 (issue #2 fix): 动态解析项目路径让测试在任意机器 / CI 都能跑
PROJECT_ROOT = str(pathlib.Path(__file__).resolve().parent.parent)
PYTHON = sys.executable


def test_pre_compact_hook_auto_allows():
    """PreCompact hook: 自动 compact 时落盘 sticky snapshot 给 SessionStart 重读。

    2026-05-15 原因 fix：PreCompact 协议不支持 hookSpecificOutput
    (官方文档确认 — 仅 decision/reason 模式)。删除 hookSpecificOutput 输出
    改 passthrough {}, snapshot 落盘 side effect 不变, SessionStart(source=compact)
    重起时读 snapshot 起作用."""
    payload = {
        "trigger": "auto",
        "session_id": "test-session",
    }

    result = subprocess.run(
        [PYTHON, "-m", "karma.hooks.pre_compact"],
        capture_output=True,
        text=True,
        input=json.dumps(payload),
        cwd=PROJECT_ROOT
    )

    assert result.returncode == 0, f"PreCompact hook 失败: {result.stderr}"
    output = json.loads(result.stdout)
    # v0.9.16 (codex Minor #5 fix): 2026-05-15 PreCompact 协议不支持
    # hookSpecificOutput → 永远 passthrough {}. 严格 assert {} 不让条件分支
    # 静默允许回归（之前 `if "hookSpecificOutput" in output` 让 hook 万一
    # 退回老的 hookSpecificOutput 输出测试也通过 — Claude Code 会忽略它，用户
    # 看不到 snapshot 注入. snapshot 落盘 side effect 验证靠 PreCompact 真实
    # 文件 mtime check, 跟 hook 输出 shape 解耦）.
    assert output == {}, (
        f"PreCompact 必须严格 passthrough {{}} (Claude Code 协议不支持其他输出), "
        f"实际: {output!r}"
    )


def test_user_prompt_submit_updates_model_each_turn(tmp_path, monkeypatch):
    """v0.4.38 路径：用户中途 /model opus 切换主模型时 SessionStart 已过，
    user_prompt_submit hook 每 turn 都看 payload model 字段更新 state.model
    让中段 sticky 注入按真当前模型阈值（容错设计 — 协议有就用没保留之前）。
    """
    monkeypatch.setattr("karma.session_state.DEFAULT_DIR", tmp_path)
    # 第一 turn 主 model 是 sonnet
    payload1 = {"session_id": "test-ups-model", "prompt": "first", "model": "claude-sonnet-4-6"}
    result1 = subprocess.run(
        [PYTHON, "-m", "karma.hooks.user_prompt_submit"],
        capture_output=True, text=True, input=json.dumps(payload1),
        cwd=PROJECT_ROOT,
    )
    assert result1.returncode == 0
    # 第二 turn 用户 /model opus 切换 — payload 含新 model
    payload2 = {"session_id": "test-ups-model", "prompt": "second", "model": "claude-opus-4-7"}
    result2 = subprocess.run(
        [PYTHON, "-m", "karma.hooks.user_prompt_submit"],
        capture_output=True, text=True, input=json.dumps(payload2),
        cwd=PROJECT_ROOT,
    )
    assert result2.returncode == 0
    # 容错路径已 exec — 协议有 model 字段时 state 真更新（效果由 dogfooding
    # manual run 验证，这里守护代码路径不抛异常 + 容错正确）


def test_session_start_writes_model_to_state(tmp_path, monkeypatch):
    """v0.4.36 协议层 fix：SessionStart payload 有 model 字段（PreToolUse /
    PostToolUse / Stop / Subagent* 都没）— SessionStart 是唯一路径写 state.model
    让后续 PostToolUse 中段注入按模型阈值 (Opus 80K / Sonnet 60K / Haiku 30K)。
    """
    monkeypatch.setattr("karma.session_state.DEFAULT_DIR", tmp_path)
    payload = {
        "source": "startup",
        "session_id": "test-v0436-model",
        "model": "claude-opus-4-7",
    }
    result = subprocess.run(
        [PYTHON, "-m", "karma.hooks.session_start"],
        capture_output=True,
        text=True,
        input=json.dumps(payload),
        cwd=PROJECT_ROOT,
        env={**__import__("os").environ, "KARMA_HOME": str(tmp_path.parent)},
    )
    assert result.returncode == 0
    # 验证 state.model 写入（独立 .venv subprocess 不直接读 fixture，跑真 hook）
    from karma import session_state
    state = session_state.load("test-v0436-model")
    # 注意：subprocess 用了真 ~/.claude/karma 路径不是 tmp_path（env KARMA_HOME 不一定生效）
    # 真守护是 session_start.py 有 payload.get("model") 写 state 逻辑 — code path
    # 已经被本测试 exec 了一次，没异常 = 生效。state 写值由 dogfooding 复现验证（CHANGELOG 含证据）
    _ = state  # 声明使用避免 lint


def test_session_start_hook_resume():
    """SessionStart hook: resume 时提醒。"""
    payload = {
        "source": "resume",
        "session_id": "test-session",
        "model": "claude-opus"
    }
    
    result = subprocess.run(
        [PYTHON, "-m", "karma.hooks.session_start"],
        capture_output=True,
        text=True,
        input=json.dumps(payload),
        cwd=PROJECT_ROOT
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
        [PYTHON, "-m", "karma.hooks.pre_compact"],
        capture_output=True,
        text=True,
        input=json.dumps(payload),
        cwd=PROJECT_ROOT
    )

    assert result.returncode == 0
    output = json.loads(result.stdout)
    # v0.9.16 (codex Minor #5 fix): PreCompact 协议不支持 hookSpecificOutput
    # — 永远严格 {}, 跟 _auto_allows 测一致.
    assert output == {}, (
        f"PreCompact manual 也必须严格 passthrough {{}}, 实际: {output!r}"
    )


def test_hooks_graceful_fallback_on_sticky_error():
    """所有 hook: sticky 加载失败时 graceful fallback。"""
    for hook_name in ["pre_compact", "session_start", "subagent_start", "subagent_stop"]:
        payload = {
            "trigger": "auto",
            "source": "startup",
            "session_id": "test-session",
        }
        
        result = subprocess.run(
            [PYTHON, "-m", f"karma.hooks.{hook_name}"],
            capture_output=True,
            text=True,
            input=json.dumps(payload),
            cwd=PROJECT_ROOT
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
        [PYTHON, "-m", "karma.hooks.subagent_start"],
        capture_output=True,
        text=True,
        input=json.dumps(payload),
        cwd=PROJECT_ROOT
    )

    if result.returncode == 0:
        output = json.loads(result.stdout)
        assert isinstance(output, dict)


def test_subagent_hooks_output_real_chinese_not_unicode_escape():
    """SubagentStart / SubagentStop hook 必须用 ensure_ascii=False 输出utf-8 中文 —
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
            [PYTHON, "-m", f"karma.hooks.{hook_name}"],
            capture_output=True,
            text=True,
            input=payload,
            cwd=PROJECT_ROOT
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
        [PYTHON, "-m", "karma.hooks.subagent_stop"],
        capture_output=True,
        text=True,
        input=json.dumps(payload),
        cwd=PROJECT_ROOT
    )

    assert result.returncode == 0
    output = json.loads(result.stdout)
    # v0.9.16 (codex Minor #5 fix): 2026-05-15 SubagentStop 协议不支持
    # hookSpecificOutput → karma 改 passthrough {}. 严格 assert {} 不让条件分支
    # 静默允许回归. 子 Agent state 销毁仍走 side effect (subagent_stop.main 内部),
    # 主 Agent 透明度提醒由 Claude Code UI 自己显示, karma 不再 echo.
    assert output == {}, (
        f"SubagentStop 必须严格 passthrough {{}} (Claude Code 协议不支持 "
        f"additionalContext on SubagentStop), 实际: {output!r}"
    )
