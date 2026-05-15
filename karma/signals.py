"""karma 检测信号字眼的 i18n 加载器。

karma 的 regex 检测对象是「用户跟 Agent 的对话文本」— 用户/Agent 用什么
语言对话，karma 就要在那个语言层面识别信号。所以信号字眼必须按语言分别
维护，加载时 union 所有可用语言的字眼。

两种存储格式：

1. `.txt`（v0.8.0）— 平面字眼，一行一个
   适合: user_stop_hints / agent_saturation / stop_hints / explicit_handoff /
   weak_claims 这类纯短语列表

2. `.yaml`（v0.8.1）— cartesian 模板 + 词集 + 平面短语混合
   适合: push_signals 这类「主语 + 动词」笛卡尔积大的信号
   yaml schema:
     templates: ["{subject}\\s+{verb}"]      # 模板列表，{key} 占位符
     subjects: [我, 我现在, ...]              # 占位符词集
     verbs: [做, 改, ...]
     phrases: [继续推进, 开始做, ...]         # 不需 cartesian 的平面字眼

设计：
- 加载时把目录下所有语言文件（.txt + .yaml 都扫）的字眼 union
- 不同语言字符集不重叠（中文 vs 拉丁 vs 假名）→ 天然无误命中
- 加新语言零代码：社区只需提交一个 `xx.txt` 或 `xx.yaml`

跟 `karma/i18n.py` 的关系（双向 i18n）：
- `i18n.py` — karma 说给 Agent 听的注入文本（hook header / suggested_fix）
- `signals.py` — karma 听 Agent / 用户说什么（regex 检测字眼）
"""

from __future__ import annotations

import re
from functools import lru_cache
from itertools import product
from pathlib import Path

import yaml

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


def _expand_yaml_signals(path: Path) -> list[str]:
    """读 .yaml 信号文件，展开 cartesian + 加平面 phrases。

    yaml schema:
      templates: list of pattern strings with {placeholder} tokens
      <plural_name>: list of values to fill (e.g. subjects / verbs)
      phrases: list of non-cartesian flat phrases

    模板占位符 `{subject}` 自动匹配复数 yaml 字段 `subjects`（DSL 约定：
    模板里用单数语义读起来自然，yaml list 字段用复数命名是惯例）。

    返回展开后的字眼列表（templates × cartesian + phrases），去重保序。
    """
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        return []

    templates = data.get("templates", []) or []
    phrases = data.get("phrases", []) or []

    # 占位符词集：除了 templates/phrases 之外的 list 字段
    # 支持两种 lookup: 字段原名 (subjects) + 单数 (subject → subjects)
    vocab: dict[str, list] = {
        k: v for k, v in data.items()
        if k not in ("templates", "phrases") and isinstance(v, list)
    }

    def resolve_key(placeholder_key: str) -> list | None:
        """查 vocab：先字段原名，再加 's' 复数。"""
        if placeholder_key in vocab:
            return vocab[placeholder_key]
        plural = placeholder_key + "s"
        if plural in vocab:
            return vocab[plural]
        return None

    out: list[str] = []
    seen: set[str] = set()

    # 展开 templates × cartesian
    for tmpl in templates:
        if not isinstance(tmpl, str):
            continue
        # 提取模板里所有 {key} 占位符（按出现顺序）
        keys_in_order = re.findall(r"\{(\w+)\}", tmpl)
        resolved = [(k, resolve_key(k)) for k in keys_in_order]
        # 漏掉任何占位符 → 跳过该模板（避免静默错误）
        if any(v is None for _, v in resolved):
            continue
        if not resolved:
            # 模板无占位符 → 直接当字面
            if tmpl not in seen:
                seen.add(tmpl)
                out.append(tmpl)
            continue
        # cartesian 展开
        word_lists = [v for _, v in resolved]
        for combo in product(*word_lists):
            phrase = tmpl
            for (k, _), v in zip(resolved, combo):
                phrase = phrase.replace("{" + k + "}", str(v))
            if phrase not in seen:
                seen.add(phrase)
                out.append(phrase)

    # 加平面 phrases
    for p in phrases:
        if isinstance(p, str) and p not in seen:
            seen.add(p)
            out.append(p)

    return out


@lru_cache(maxsize=None)
def load_phrases(signal_name: str) -> tuple[str, ...]:
    """加载某信号下「字面字眼」union（仅 `.txt` 文件，向后兼容 v0.8.0）。

    返回 tuple 是为了 lru_cache 安全。signal_name 对应 `data/signals/<name>/`
    目录名（如 `user_stop_hints` / `push_signals`）。

    注意：本函数只返回 `.txt` 文件的字面字眼，不含 `.yaml` cartesian 展开。
    `.yaml` 字眼通过 `load_patterns()` 拿（已含 regex 元字符）。
    `compile_alternation()` 把两者合并编译成单 regex。
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
def load_patterns(signal_name: str) -> tuple[str, ...]:
    """加载某信号下 `.yaml` 文件的「raw regex pattern」union (v0.8.1)。

    yaml templates 字段可含 regex 元字符（`\\s+` `\\s*` 等），cartesian
    展开后得到的字眼**保留**为 regex pattern（不被 escape）。
    """
    signal_dir = _SIGNALS_DIR / signal_name
    if not signal_dir.is_dir():
        return ()
    seen: set[str] = set()
    out: list[str] = []
    for lang_file in sorted(signal_dir.glob("*.yaml")):
        for phrase in _expand_yaml_signals(lang_file):
            if phrase in seen:
                continue
            seen.add(phrase)
            out.append(phrase)
    for lang_file in sorted(signal_dir.glob("*.yml")):
        for phrase in _expand_yaml_signals(lang_file):
            if phrase in seen:
                continue
            seen.add(phrase)
            out.append(phrase)
    return tuple(out)


@lru_cache(maxsize=None)
def compile_alternation(signal_name: str, *, flags: int = re.IGNORECASE) -> re.Pattern[str]:
    """把某信号的所有字眼 + yaml 模板编译成 `(?:a|b|c)` regex。

    - `.txt` 字面字眼 → `re.escape` 后加入 alternation（防特殊字符当 regex 元字符）
    - `.yaml` 模板展开的 pattern → **不 escape**，直接当 regex 字面（支持 `\\s+` 等）
    - 全部按长度倒序排（贪婪匹配长字眼优先，避免 `OK` 抢 `OK 了` 前面命中）
    - 空集合返回永远不匹配的 pattern
    """
    literal_phrases = load_phrases(signal_name)
    raw_patterns = load_patterns(signal_name)
    if not literal_phrases and not raw_patterns:
        return re.compile(r"(?!)")  # never matches
    # 字面字眼 escape；raw patterns 原样保留
    escaped_literals = [re.escape(p) for p in literal_phrases]
    all_parts = sorted(escaped_literals + list(raw_patterns), key=len, reverse=True)
    pattern = "(?:" + "|".join(all_parts) + ")"
    return re.compile(pattern, flags)


def reset_cache() -> None:
    """测试用：清缓存让 phrase 文件改动后重新读。"""
    load_phrases.cache_clear()
    load_patterns.cache_clear()
    compile_alternation.cache_clear()
