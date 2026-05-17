"""跨平台用户语言检测测试 — mock 各平台行为验证三路径都对。"""

from __future__ import annotations

import subprocess
from unittest.mock import patch

import pytest

from pinrule.locale_detect import detect_user_language, is_chinese_user


@pytest.fixture(autouse=True)
def _clean_locale_env(monkeypatch):
    """每个测试前清掉本机所有 LC_* / LANG 环境变量 — 否则作者本机
    LC_MESSAGES=en_US.UTF-8 会让 setenv("LC_ALL", "C") + setenv("LANG", "zh_CN")
    类测试拿到本机 LC_MESSAGES 假 hit 'en' 而不是预期的 'zh'。
    """
    for var in ("LC_ALL", "LC_MESSAGES", "LC_CTYPE", "LANG", "LANGUAGE"):
        monkeypatch.delenv(var, raising=False)


# ---- macOS: defaults read AppleLanguages 路径 ----


def test_macos_zh_user_detected():
    """macOS 系统语言中文 → defaults 返回 'zh-Hans-CN' → 检测 'zh'。"""
    fake_out = '(\n    "zh-Hans-CN"\n)\n'
    fake_result = subprocess.CompletedProcess(args=[], returncode=0, stdout=fake_out)
    with patch("platform.system", return_value="Darwin"):
        with patch("subprocess.run", return_value=fake_result):
            assert detect_user_language() == "zh"


def test_macos_en_user_detected():
    """macOS 系统语言英文 → 'en-US' → 检测 'en'。"""
    fake_out = '(\n    "en-US",\n    "zh-Hans-CN"\n)\n'
    fake_result = subprocess.CompletedProcess(args=[], returncode=0, stdout=fake_out)
    with patch("platform.system", return_value="Darwin"):
        with patch("subprocess.run", return_value=fake_result):
            # 取列表第一个（用户首选）
            assert detect_user_language() == "en"


def test_macos_ja_user_detected():
    """macOS 日文用户 — 验证不只是中英二分。"""
    fake_out = '(\n    "ja-JP"\n)\n'
    fake_result = subprocess.CompletedProcess(args=[], returncode=0, stdout=fake_out)
    with patch("platform.system", return_value="Darwin"):
        with patch("subprocess.run", return_value=fake_result):
            assert detect_user_language() == "ja"


def test_macos_defaults_command_fails_fallback_to_env(monkeypatch):
    """macOS defaults 命令失败 → 回落到 POSIX 环境变量。"""
    monkeypatch.setenv("LANG", "fr_FR.UTF-8")
    monkeypatch.delenv("LC_ALL", raising=False)
    monkeypatch.delenv("LC_MESSAGES", raising=False)
    with patch("platform.system", return_value="Darwin"):
        with patch("subprocess.run", side_effect=OSError("command not found")):
            assert detect_user_language() == "fr"


# ---- Windows: GetUserDefaultUILanguage 路径 ----


def test_windows_zh_user_detected():
    """Windows 系统 UI 语言中文 → GetUserDefaultUILanguage 返回中文 LCID
    （2052 = zh_CN）→ 检测 'zh'。"""
    import types
    fake_locale = types.SimpleNamespace(windows_locale={2052: "zh_CN", 1033: "en_US"})
    fake_ctypes = types.SimpleNamespace(
        windll=types.SimpleNamespace(
            kernel32=types.SimpleNamespace(GetUserDefaultUILanguage=lambda: 2052)
        )
    )
    with patch("platform.system", return_value="Windows"):
        with patch.dict("sys.modules", {"ctypes": fake_ctypes, "locale": fake_locale}):
            assert detect_user_language() == "zh"


def test_windows_en_user_detected():
    """Windows 英文 → LCID 1033 = en_US → 'en'。"""
    import types
    fake_locale = types.SimpleNamespace(windows_locale={1033: "en_US"})
    fake_ctypes = types.SimpleNamespace(
        windll=types.SimpleNamespace(
            kernel32=types.SimpleNamespace(GetUserDefaultUILanguage=lambda: 1033)
        )
    )
    with patch("platform.system", return_value="Windows"):
        with patch.dict("sys.modules", {"ctypes": fake_ctypes, "locale": fake_locale}):
            assert detect_user_language() == "en"


def test_windows_ctypes_unavailable_fallback_env(monkeypatch):
    """Windows ctypes / windll 不可用（非 NT 内核怪环境）→ 回落到 POSIX 环境变量。"""
    monkeypatch.setenv("LANG", "ja_JP.UTF-8")
    monkeypatch.delenv("LC_ALL", raising=False)
    monkeypatch.delenv("LC_MESSAGES", raising=False)
    with patch("platform.system", return_value="Windows"):
        # 让 ctypes 不可 import
        import sys
        original_ctypes = sys.modules.get("ctypes")
        sys.modules["ctypes"] = None  # type: ignore[assignment]
        try:
            assert detect_user_language() == "ja"
        finally:
            if original_ctypes is not None:
                sys.modules["ctypes"] = original_ctypes


# ---- Linux: 环境变量路径 ----


def test_linux_lang_env_detected(monkeypatch):
    """Linux 默认 $LANG=zh_CN.UTF-8 → 'zh'。"""
    monkeypatch.setenv("LANG", "zh_CN.UTF-8")
    monkeypatch.delenv("LC_ALL", raising=False)
    monkeypatch.delenv("LC_MESSAGES", raising=False)
    with patch("platform.system", return_value="Linux"):
        assert detect_user_language() == "zh"


def test_linux_lc_all_overrides_lang(monkeypatch):
    """LC_ALL 优先级最高（POSIX 标准）— 覆盖 LANG。"""
    monkeypatch.setenv("LC_ALL", "de_DE.UTF-8")
    monkeypatch.setenv("LANG", "en_US.UTF-8")
    with patch("platform.system", return_value="Linux"):
        assert detect_user_language() == "de"


def test_linux_c_locale_skipped(monkeypatch):
    """LANG=C / POSIX 是「无 locale」的标记，应跳过继续找下一变量。"""
    monkeypatch.setenv("LC_ALL", "C")
    monkeypatch.setenv("LANG", "zh_CN.UTF-8")
    with patch("platform.system", return_value="Linux"):
        assert detect_user_language() == "zh"


def test_linux_no_env_returns_none(monkeypatch):
    """所有相关环境变量都没设 → 返回 None。"""
    for var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        monkeypatch.delenv(var, raising=False)
    with patch("platform.system", return_value="Linux"):
        assert detect_user_language() is None


# ---- is_chinese_user 便利包装 ----


def test_is_chinese_user_true():
    fake_out = '(\n    "zh-Hans-CN"\n)\n'
    fake_result = subprocess.CompletedProcess(args=[], returncode=0, stdout=fake_out)
    with patch("platform.system", return_value="Darwin"):
        with patch("subprocess.run", return_value=fake_result):
            assert is_chinese_user() is True


def test_is_chinese_user_false_for_en(monkeypatch):
    monkeypatch.setenv("LANG", "en_US.UTF-8")
    monkeypatch.delenv("LC_ALL", raising=False)
    with patch("platform.system", return_value="Linux"):
        assert is_chinese_user() is False


def test_is_chinese_user_false_when_unknown(monkeypatch):
    """检测不到也算非中文用户 — fallback minimal 模板。"""
    for var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        monkeypatch.delenv(var, raising=False)
    with patch("platform.system", return_value="Linux"):
        assert is_chinese_user() is False
