"""karma 检测信号字眼的 i18n 加载器。

karma 的 regex 检测对象是「用户跟 Agent 的对话文本」— 用户/Agent 用什么
语言对话，karma 就要在那个语言层面识别信号。所以信号字眼必须按语言分别
维护，加载时 union 所有可用语言的字眼。

设计：
- 字眼数据在 `data/signals/<signal_name>/<lang>.txt`，一行一个字眼
- 加载时把目录下所有语言文件的字眼 union 成一个 regex
- 不同语言字符集不重叠（中文 vs 英文 vs 假名）→ 天然无误命中
- 加新语言零代码：社区只需提交一个 `xx.txt`

跟 `karma/i18n.py` 的关系（双向 i18n）：
- `i18n.py` — karma 说给 Agent 听的注入文本（hook header / suggested_fix）
- `signals.py` — karma 听 Agent / 用户说什么（regex 检测字眼）
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SIGNALS_DIR = _REPO_ROOT / "data" / "signals"


def _read_lines(path: Path) -> list[str]:
    """读一个字眼文件，跳过空行 + `#` 开头的注释行。"""
    if not path.exists():
        return []
    out: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        out.append(line)
    return out


@lru_cache(maxsize=None)
def load_phrases(signal_name: str) -> tuple[str, ...]:
    """加载某信号下所有语言文件的字眼 union（按字眼出现顺序，去重保序）。

    返回 tuple 是为了 lru_cache 安全。signal_name 对应 `data/signals/<name>/`
    目录名（如 `user_stop_hints` / `push_signals`）。
    """
    signal_dir = _SIGNALS_DIR / signal_name
    if not signal_dir.is_dir():
        return ()
    seen: set[str] = set()
    out: list[str] = []
    for lang_file in sorted(signal_dir.glob("*.txt")):
        for phrase in _read_lines(lang_file):
            if phrase in seen:
                continue
            seen.add(phrase)
            out.append(phrase)
    return tuple(out)


@lru_cache(maxsize=None)
def compile_alternation(signal_name: str, *, flags: int = re.IGNORECASE) -> re.Pattern[str]:
    """把某信号的所有字眼编译成 `(?:a|b|c)` regex。

    字眼按长度倒序排（贪婪匹配长字眼优先，避免 `OK` 抢在 `OK 了` 前面命中）。
    每个字眼 `re.escape` — 字眼文件里写字面文本不写 regex 特殊字符。
    空集合返回永远不匹配的 pattern。
    """
    phrases = load_phrases(signal_name)
    if not phrases:
        return re.compile(r"(?!)")  # never matches
    sorted_phrases = sorted(phrases, key=len, reverse=True)
    pattern = "(?:" + "|".join(re.escape(p) for p in sorted_phrases) + ")"
    return re.compile(pattern, flags)


def reset_cache() -> None:
    """测试用：清缓存让 phrase 文件改动后重新读。"""
    load_phrases.cache_clear()
    compile_alternation.cache_clear()
