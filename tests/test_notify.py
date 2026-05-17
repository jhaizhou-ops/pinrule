"""桌面通知跨平台 + 关闭开关测试。"""

from __future__ import annotations

from unittest.mock import patch, MagicMock

from pinrule.notify import notify, _escape_for_osascript


def test_notify_macos_calls_osascript(monkeypatch):
    monkeypatch.delenv("PINRULE_NO_NOTIFY", raising=False)
    monkeypatch.setattr("platform.system", lambda: "Darwin")
    mock_run = MagicMock(return_value=MagicMock(returncode=0))
    with patch("subprocess.run", mock_run):
        result = notify("test title", "test message")
    assert result is True
    args = mock_run.call_args[0][0]
    assert args[0] == "osascript"
    assert "-e" in args
    # AppleScript 字符串含 title + message
    script = args[args.index("-e") + 1]
    assert "test title" in script
    assert "test message" in script


def test_notify_linux_calls_notify_send(monkeypatch):
    monkeypatch.delenv("PINRULE_NO_NOTIFY", raising=False)
    monkeypatch.setattr("platform.system", lambda: "Linux")
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/notify-send" if name == "notify-send" else None)
    mock_run = MagicMock(return_value=MagicMock(returncode=0))
    with patch("subprocess.run", mock_run):
        result = notify("title", "msg")
    assert result is True
    assert mock_run.call_args[0][0][0] == "notify-send"


def test_notify_linux_missing_notify_send_returns_false(monkeypatch):
    monkeypatch.delenv("PINRULE_NO_NOTIFY", raising=False)
    monkeypatch.setattr("platform.system", lambda: "Linux")
    monkeypatch.setattr("shutil.which", lambda name: None)
    result = notify("t", "m")
    assert result is False


def test_notify_disabled_by_env(monkeypatch):
    monkeypatch.setenv("PINRULE_NO_NOTIFY", "1")
    mock_run = MagicMock()
    with patch("subprocess.run", mock_run):
        result = notify("t", "m")
    assert result is False
    mock_run.assert_not_called()


def test_notify_unsupported_platform_returns_false(monkeypatch):
    monkeypatch.delenv("PINRULE_NO_NOTIFY", raising=False)
    monkeypatch.setattr("platform.system", lambda: "Plan9")
    result = notify("t", "m")
    assert result is False


def test_notify_empty_input_returns_false(monkeypatch):
    monkeypatch.delenv("PINRULE_NO_NOTIFY", raising=False)
    monkeypatch.setattr("platform.system", lambda: "Darwin")
    mock_run = MagicMock()
    with patch("subprocess.run", mock_run):
        result = notify("", "")
    assert result is False
    mock_run.assert_not_called()


def test_notify_handles_subprocess_failure(monkeypatch):
    """subprocess 抛 OSError → 返回 False 不抛（fail open）。"""
    monkeypatch.delenv("PINRULE_NO_NOTIFY", raising=False)
    monkeypatch.setattr("platform.system", lambda: "Darwin")
    mock_run = MagicMock(side_effect=OSError("no osascript"))
    with patch("subprocess.run", mock_run):
        result = notify("t", "m")
    assert result is False


def test_notify_handles_timeout(monkeypatch):
    """subprocess timeout → 返回 False 不抛。"""
    import subprocess as sp
    monkeypatch.delenv("PINRULE_NO_NOTIFY", raising=False)
    monkeypatch.setattr("platform.system", lambda: "Darwin")
    mock_run = MagicMock(side_effect=sp.TimeoutExpired(cmd="osascript", timeout=2))
    with patch("subprocess.run", mock_run):
        result = notify("t", "m")
    assert result is False


def test_escape_osascript_quotes():
    """AppleScript 字符串字面 " 要转义，避免命令注入。"""
    assert _escape_for_osascript('he said "hi"') == 'he said \\"hi\\"'
    assert _escape_for_osascript("multi\nline") == "multi line"
    assert _escape_for_osascript("back\\slash") == "back\\\\slash"
