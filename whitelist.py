"""vulture whitelist — names used by tests but not visible to vulture
(因为 CI vulture 只扫 pinrule/, 不扫 tests/, 看不到 test 引用).

跑 vulture 时把这个文件一起喂进去:
    vulture pinrule/ whitelist.py --min-confidence 60
"""
import shlex as _shlex

from pinrule import signals as _signals
from pinrule.backends import native_capabilities as _native_caps

# tests/test_signals.py 用 reset_cache 隔离测试间的 lru_cache 状态 (vulture
# 只扫 pinrule/, 看不到 test 引用).
_signals.reset_cache

# pinrule/backends/codex.py:_shell_tokens 用 shlex.shlex.whitespace_split 切 tokens
# (v0.10.1 codex shell-as-Read parser). vulture min-confidence 60 看不到 stdlib
# attr 真实用法, 误报 unused.
_shlex.shlex.whitespace_split

# pinrule/backends/codex.py:53 真 import 这个 dict 喂 _HOOK_EVENTS, 但 vulture
# 60% 把跨 module 的 module-level dict 引用判 unused — 加 whitelist 显式声明.
_native_caps.CODEX_HOOK_EVENTS
