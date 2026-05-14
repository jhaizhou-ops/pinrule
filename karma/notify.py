"""跨平台桌面通知 — stop hook 检测违反时如果用户离开 stderr 视野的补充提示。

设计：
- macOS: osascript display notification
- Linux: notify-send (gnome / KDE / etc)
- Windows: powershell New-BurntToastNotification (or fallback msg.exe)
- 失败静默不抛错（fail open 原则）
- 环境变量 KARMA_NO_NOTIFY=1 关闭
- subprocess timeout=2s 防卡 hook
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess


def _escape_for_osascript(s: str) -> str:
    """AppleScript 字符串字面转义。"""
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def _notify_macos(title: str, message: str) -> bool:
    script = (
        f'display notification "{_escape_for_osascript(message)}" '
        f'with title "{_escape_for_osascript(title)}"'
    )
    try:
        subprocess.run(
            ["osascript", "-e", script],
            timeout=2,
            check=False,
            capture_output=True,
        )
        return True
    except (OSError, subprocess.TimeoutExpired):
        return False


def _notify_linux(title: str, message: str) -> bool:
    if not shutil.which("notify-send"):
        return False
    try:
        subprocess.run(
            ["notify-send", title, message],
            timeout=2,
            check=False,
            capture_output=True,
        )
        return True
    except (OSError, subprocess.TimeoutExpired):
        return False


def _notify_windows(title: str, message: str) -> bool:
    # 简单 fallback — 用 msg 命令（Windows Pro/Server）
    # 更好的方案是 powershell BurntToast，但要装模块
    if not shutil.which("msg"):
        return False
    try:
        subprocess.run(
            ["msg", "*", f"{title}: {message}"],
            timeout=2,
            check=False,
            capture_output=True,
        )
        return True
    except (OSError, subprocess.TimeoutExpired):
        return False


def notify(title: str, message: str) -> bool:
    """跨平台桌面通知。失败静默返回 False。

    用 KARMA_NO_NOTIFY=1 环境变量关闭（CI / 静音场景）。
    title / message 长度建议 < 100 字（macOS 通知中心截断）。
    """
    if os.environ.get("KARMA_NO_NOTIFY"):
        return False
    if not title and not message:
        return False
    sys_name = platform.system()
    if sys_name == "Darwin":
        return _notify_macos(title, message)
    if sys_name == "Linux":
        return _notify_linux(title, message)
    if sys_name == "Windows":
        return _notify_windows(title, message)
    return False
