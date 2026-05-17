"""pinrule i18n — Simple yaml-dict translation lookup.

v0.5.2 i18n infrastructure. User-visible text (hook injection headers,
suggested_fix, CLI output) goes through ``tr(key)`` lookup. Locale resolved:

  config.yaml ``locale`` field:
    - "en" → English (default for new users)
    - "zh" → Chinese
    - "auto" → ``pinrule.locale_detect.is_chinese_user()`` decides

Translations live in ``data/locales/<lang>.yaml`` as flat key → value dict.
Missing key → return the key itself (fail-open, never crash hook).
Missing locale file → fall back to English.

Designed for early-stage simplicity: no gettext, no .po files. Translators
edit yaml directly. Once translation coverage stabilizes, can migrate to
gettext for tooling support — but not now.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

# data/locales/ relative to package root
_LOCALES_DIR = Path(__file__).parent.parent / "data" / "locales"

# Fallback language when locale file missing
_FALLBACK_LANG = "en"


def _resolve_locale() -> str:
    """Resolve effective locale from config + PINRULE_LOCALE override + auto-detect."""
    # Env var has highest priority (for testing / one-off override)
    env_override = os.environ.get("PINRULE_LOCALE", "").strip().lower()
    if env_override in ("en", "zh"):
        return env_override

    # Read config
    try:
        from pinrule.config import load as _load_cfg
        cfg = _load_cfg()
        cfg_locale = str(cfg.get("locale", "auto")).strip().lower()
    except Exception:
        cfg_locale = "auto"

    if cfg_locale in ("en", "zh"):
        return cfg_locale

    # "auto" → ask locale_detect
    try:
        from pinrule.locale_detect import is_chinese_user
        return "zh" if is_chinese_user() else "en"
    except Exception:
        return _FALLBACK_LANG


@lru_cache(maxsize=4)
def _load_locale_dict(lang: str) -> dict[str, Any]:
    """Load translations for given lang. Returns empty dict if missing."""
    path = _LOCALES_DIR / f"{lang}.yaml"
    if not path.exists():
        return {}
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (yaml.YAMLError, OSError):
        return {}
    if not isinstance(raw, dict):
        return {}
    return raw


def tr(key: str, lang: str | None = None, **fmt: Any) -> str:
    """Translate ``key`` for the given language (or auto-resolved locale).

    Returns the key itself if translation missing (fail-open).
    ``fmt`` kwargs interpolate via .format() into the translation.
    """
    effective_lang = lang or _resolve_locale()
    translations = _load_locale_dict(effective_lang)
    val = translations.get(key)
    if val is None and effective_lang != _FALLBACK_LANG:
        # Fall back to English if specific lang lacks key
        val = _load_locale_dict(_FALLBACK_LANG).get(key)
    if val is None:
        val = key  # last-resort fallback — don't crash hook
    if fmt:
        try:
            return str(val).format(**fmt)
        except (KeyError, IndexError) as e:
            # v0.16.9: 之前 silent 吞 — 违反 loud-failure. 现 stderr 输出
            # warning, hook 进程 stderr Claude 看不见但 pytest / CLI debug 能看到.
            import sys as _sys
            _sys.stderr.write(
                f"pinrule i18n: tr({key!r}) .format(**{list(fmt.keys())}) 失败 "
                f"({type(e).__name__}: {e}), 返回原文未插值\n"
            )
            return str(val)
    return str(val)


