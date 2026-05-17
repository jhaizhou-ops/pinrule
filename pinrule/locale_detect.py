"""跨平台用户系统语言偏好检测 — 给 pinrule init 自动选 sticky 模板用。

设计思路：
- macOS：`defaults read -g AppleLanguages`（用户系统语言列表，反映「系统设置 →
  语言与地区」里设的偏好）。`locale.getlocale()` 在 macOS 不准，因为
  shell 默认 `LANG=en_US.UTF-8` 不继承系统语言偏好。
- Linux：环境变量 `$LC_ALL` / `$LC_MESSAGES` / `$LANG`（按优先级），这是 POSIX
  标准做法，桌面环境会自动设置。
- Windows：`GetUserDefaultUILanguage` PowerShell（可选实现，当前 fallback 环境变量）。
- 检测不到（容器 / CI / 异常）→ 返回 None 让调用方走默认或显式 flag。

跟其他 app 安装时的「自动选语言」做法一致 — VS Code / Slack / Chrome 都用类
似方法。
"""

from __future__ import annotations

import os
import platform
import subprocess


def detect_user_language() -> str | None:
    """检测用户系统语言偏好。返回 ISO 语言代码前缀（'zh' / 'en' / 'ja' 等），
    检测不到返回 None。

    设计为简单 prefix 比较（不区分 zh-CN / zh-TW），pinrule 当前只关心「是不是
    中文用户」二分判定。需要更细可后续扩展。
    """
    sys_name = platform.system()

    if sys_name == "Darwin":
        try:
            result = subprocess.run(
                ["defaults", "read", "-g", "AppleLanguages"],
                timeout=2,
                capture_output=True,
                text=True,
                check=False,
            )
            # 返回类似:  '(\n    "zh-Hans-CN"\n)\n'  第一个引号字符串
            out = result.stdout
            # 取第一个 quoted 字符串
            import re
            m = re.search(r'"([a-zA-Z]{2,3})(?:[-_][a-zA-Z]+)*"', out)
            if m:
                return m.group(1).lower()
        except (OSError, subprocess.TimeoutExpired):
            pass

    if sys_name == "Windows":
        # Windows API GetUserDefaultUILanguage → LCID 数字 → 'zh_CN' 通过
        # Python 标准库 locale.windows_locale 查表。比 $LANG 准（Windows 默认
        # shell 通常不设 LANG）。跟「设置 → 时间和语言 → Windows 显示语言」一致。
        try:
            import ctypes  # type: ignore[import]
            lcid = ctypes.windll.kernel32.GetUserDefaultUILanguage()  # type: ignore[attr-defined]
            import locale as _locale
            lang_full = _locale.windows_locale.get(lcid, "")
            if lang_full:
                # 形态如 'zh_CN' / 'en_US' / 'ja_JP'
                prefix = lang_full.split("_")[0].lower()
                if len(prefix) >= 2 and prefix.isalpha():
                    return prefix
        except (OSError, AttributeError, ImportError):
            pass

    # POSIX 环境变量（Linux 桌面环境会自动设；macOS 失败回落；Windows fallback）
    # 优先级：LC_ALL > LC_MESSAGES > LANG
    for var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        val = os.environ.get(var, "")
        if not val or val.upper() == "C" or val.upper() == "POSIX":
            continue
        # 形态如 'zh_CN.UTF-8' / 'en_US.UTF-8' / 'zh-Hans-CN'
        prefix = val.split("_")[0].split("-")[0].split(".")[0].lower()
        if len(prefix) >= 2 and prefix.isalpha():
            return prefix

    return None


def is_chinese_user() -> bool:
    """便利包装 — pinrule 当前只关心是不是中文用户（决定要不要 chinese_plain check）。"""
    lang = detect_user_language()
    return lang == "zh"
