"""pytest conftest — 全局测试 fixture。

v0.9.5 (CI fix): force PINRULE_LOCALE=zh — 测试 fixture 假设 zh locale
(写死中文字面 assert 「默契 / 偏离 / 纯陈述」)。但 CI runner 默认
English locale, `pinrule.locale_detect.is_chinese_user()` 返回 False
→ i18n 选 en → fixture 断言 fail。

`pytest_configure` 在任何 pinrule import 之前跑, setenv 让 i18n.tr()
解析到 zh locale。本机用户跑测试也能借这个 force 确保跟 CI 一致。
"""
from __future__ import annotations

import os


def pytest_configure(config):
    """Force zh locale before any pinrule module is imported."""
    os.environ.setdefault("PINRULE_LOCALE", "zh")


def np(path_literal: str) -> str:
    """跨平台 normalize path: 跟 pinrule session_state._normalize_path 一致.

    v0.16.17 Windows 支持加这个 helper. 测试 assert path-in-set 时用 — Unix
    上 "/x/y" → "/x/y", Windows 上 "/x/y" → "D:\\x\\y" (跟 os.path.abspath
    Windows 语义一致). 让 test expected 跟 production normalize 跨平台对齐.
    """
    from pinrule.session_state import _normalize_path
    return _normalize_path(path_literal)
