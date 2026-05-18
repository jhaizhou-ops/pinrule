"""Force pinrule entry-point stdout/stderr to UTF-8.

Why: Windows Python's default stdout/stderr uses locale-preferred encoding
(zh-CN = cp936/GBK, en-US = cp1252). Strict encoding fails on characters
outside the locale codepage (e.g. `▸` U+25B8, `🛑` U+1F6D1, CJK punct).

Real user dogfood (2026-05-18 GitHub issue): `pinrule init` crashed on
zh-CN Windows with `UnicodeEncodeError: 'gbk' codec can't encode '▸'`.
Hook output also degraded to `\\U0001f6d1` literal + `??` for CJK chars,
silently breaking the rule-injection feature.

Fix scope: call this at every entry point (CLI `__main__`, `cli.main()`,
each generated hook wrapper). Library imports (`import pinrule`) should
NOT auto-force — caller may have legitimate non-UTF-8 stdout config.

Idempotent + safe: `reconfigure()` is no-op if stdout is already UTF-8
(Linux / macOS / Windows with PYTHONUTF8=1 or PYTHONIOENCODING=utf-8).
"""

from __future__ import annotations

import sys


def force_utf8_stdio() -> None:
    """Reconfigure sys.stdout / sys.stderr to UTF-8 in-place.

    Returns silently on any error — entry points shouldn't crash because
    encoding-forcing failed (sticky fail-open contract for hooks).
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            # ValueError: stream not text mode
            # OSError: stream closed / detached
            pass
