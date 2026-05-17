"""regression: user-facing 表面不再引入 v0.6.0 前的 `sticky` 旧名。

v0.6.0 BREAKING 把 `sticky.*` → `rules.*`。之前已做过多轮清扫（v0.8.2 / v0.9.7），
但每次都靠 grep + 人眼，漏点会被下次扫除时再次发现 —— 没有 regression 机制。

本测试锁住「用户可见表面」白名单：
- `data/locales/*.yaml` — 用户被拦时看到的 i18n message
- `data/config.example.yaml` — `pinrule init` 后用户配置文件
- `data/rules.dev.*.example*.yaml` — 用户安装时复制到 rules.yaml 的模板

下次有人改动这些文件不小心引入旧名 → CI fail。

允许的例外（讲历史 / migration / 教用户「不要绕 sticky.yaml」是合法保留）通过显式
白名单允许 —— 但白名单是「这一行字面」精确匹配，不是「整文件免检」。

dev-facing docstring / 注释 / tests 里的 sticky 残留是 cosmetic，留到 v0.10.x
单独大扫，不在本 regression 范围。
"""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"

# 锁住的 user-facing 文件
USER_FACING_FILES = [
    DATA_DIR / "locales" / "zh.yaml",
    DATA_DIR / "locales" / "en.yaml",
    DATA_DIR / "config.example.yaml",
    DATA_DIR / "rules.dev.example.yaml",
    DATA_DIR / "rules.dev.example.zh.yaml",
    DATA_DIR / "rules.dev.minimal.example.yaml",
    DATA_DIR / "rules.dev.minimal.example.zh.yaml",
]

# 允许的例外字面 —— 精确字符串匹配，不是子串
# 加新条目要给理由（讲历史 / migration / 真用户兼容路径）
ALLOWED_STICKY_LITERALS: set[str] = set()


def test_no_sticky_in_user_facing_files():
    """所有 user-facing 文件不能含 'sticky' 字面（除白名单例外）。"""
    offenders: list[tuple[str, int, str]] = []
    for f in USER_FACING_FILES:
        if not f.exists():
            continue
        for lineno, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if "sticky" not in line.lower():
                continue
            if line in ALLOWED_STICKY_LITERALS:
                continue
            offenders.append((str(f.relative_to(REPO_ROOT)), lineno, line.strip()))
    assert not offenders, (
        "user-facing 表面有 'sticky' 旧名残留（v0.6.0 已改名 rules）:\n"
        + "\n".join(f"  {f}:{ln}: {txt}" for f, ln, txt in offenders)
        + "\n\n如果确实是合法保留（讲历史 / migration），加到 ALLOWED_STICKY_LITERALS。"
    )


def test_allowed_list_entries_actually_exist():
    """白名单不能腐烂 —— 每条白名单字面必须真存在于某个 user-facing 文件里。"""
    if not ALLOWED_STICKY_LITERALS:
        return
    all_lines: set[str] = set()
    for f in USER_FACING_FILES:
        if f.exists():
            all_lines.update(f.read_text(encoding="utf-8").splitlines())
    stale = ALLOWED_STICKY_LITERALS - all_lines
    assert not stale, (
        f"ALLOWED_STICKY_LITERALS 有过时条目（已不在任何文件里）:\n  {stale}"
    )
