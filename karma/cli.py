"""karma CLI — sticky 管理 + 违反观察 + hook 安装。

Usage:
    karma sticky list              列出所有 sticky 规则
    karma sticky edit              用 $EDITOR 编辑 sticky.yaml
    karma sticky remove <id>       移除某条
    karma stats                    显示每条规则的违反统计
    karma violations recent [N]    最近 N 条违反详情（默认 20）
    karma violations clear         清空违反历史（需确认）
    karma install-hooks            自动配置 Claude Code hooks
    karma uninstall-hooks          移除 hook 配置
    karma doctor                   检查环境（sticky 合法、hook 已装等）
    karma init                     创建 ~/.claude/karma/ 目录 + 复制 sticky 模板
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

from karma import __version__
from karma.sticky import DEFAULT_PATH as STICKY_PATH
from karma.sticky import HARD_MAX, MAX_STICKY, StickyConfigError, load
from karma.violations import DEFAULT_PATH as VIOLATIONS_PATH
from karma.violations import load_all

KARMA_DIR = Path.home() / ".claude" / "karma"
EXAMPLE_STICKY = Path(__file__).parent.parent / "data" / "sticky.dev.example.yaml"
EXAMPLE_CONFIG = Path(__file__).parent.parent / "data" / "config.example.yaml"

# karma hook 在 Claude Code settings.json 里的事件名 → wrapper 文件名 (snake_case)
_KARMA_HOOK_EVENTS = {
    "UserPromptSubmit": "user_prompt_submit",
    "PreToolUse": "pre_tool_use",
    "PostToolUse": "post_tool_use",
    "Stop": "stop",
}


def _hooks_dir() -> Path:
    return Path.home() / ".claude" / "hooks"


def _settings_path() -> Path:
    return Path.home() / ".claude" / "settings.json"


def _settings_backup_path() -> Path:
    return Path.home() / ".claude" / "settings.json.before-karma"


def _karma_wrapper_path(hook_name_lower: str) -> Path:
    return _hooks_dir() / f"karma_{hook_name_lower}.py"


def _karma_event_entry(hook_name_lower: str) -> dict:
    """构造一条 karma hook entry — Claude Code settings.json hooks 字段格式。"""
    return {
        "matcher": "*",
        "hooks": [{"type": "command", "command": str(_karma_wrapper_path(hook_name_lower))}],
    }


def _is_karma_entry(entry: dict) -> bool:
    """判断 hook entry 是不是 karma 装的（任一 command 路径含 karma_ 前缀）。"""
    for h in entry.get("hooks", []):
        if "karma_" in h.get("command", ""):
            return True
    return False


def _load_settings() -> dict:
    p = _settings_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _save_settings(data: dict) -> None:
    p = _settings_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _remove_karma_entries(settings: dict) -> dict:
    """从 settings.hooks 移除所有 karma entry，保留其他 hook。"""
    hooks = settings.get("hooks", {})
    for event in list(hooks.keys()):
        hooks[event] = [e for e in hooks[event] if not _is_karma_entry(e)]
        if not hooks[event]:
            del hooks[event]
    return settings


def _add_karma_entries(settings: dict) -> dict:
    """给 settings.hooks 4 个 event 各加一条 karma entry。调用方负责先清旧。"""
    settings.setdefault("hooks", {})
    for event, fname in _KARMA_HOOK_EVENTS.items():
        settings["hooks"].setdefault(event, [])
        settings["hooks"][event].append(_karma_event_entry(fname))
    return settings


def _check_hooks_installed() -> dict[str, dict]:
    """诊断每个 hook event 的安装状态 — wrapper 存在 + settings 含引用。"""
    settings = _load_settings()
    hooks = settings.get("hooks", {})
    result: dict[str, dict] = {}
    for event, fname in _KARMA_HOOK_EVENTS.items():
        wrapper = _karma_wrapper_path(fname)
        in_settings = any(
            _is_karma_entry(e) for e in hooks.get(event, [])
            if any(fname in h.get("command", "") for h in e.get("hooks", []))
        )
        result[event] = {
            "wrapper_exists": wrapper.exists(),
            "wrapper_executable": wrapper.exists() and os.access(wrapper, os.X_OK),
            "in_settings": in_settings,
        }
    return result


def cmd_init() -> int:
    """创建 ~/.claude/karma/ + 复制 sticky 模板 + config 模板。"""
    KARMA_DIR.mkdir(parents=True, exist_ok=True)
    # sticky 模板
    if STICKY_PATH.exists():
        print(f"sticky.yaml 已存在: {STICKY_PATH}")
    elif not EXAMPLE_STICKY.exists():
        print(f"模板文件不存在: {EXAMPLE_STICKY}", file=sys.stderr)
        return 1
    else:
        shutil.copyfile(EXAMPLE_STICKY, STICKY_PATH)
        print(f"创建 sticky.yaml: {STICKY_PATH}")
    # config 模板
    config_path = KARMA_DIR / "config.yaml"
    if config_path.exists():
        print(f"config.yaml 已存在: {config_path}")
    elif EXAMPLE_CONFIG.exists():
        shutil.copyfile(EXAMPLE_CONFIG, config_path)
        print(f"创建 config.yaml: {config_path}")
    print("编辑用: karma sticky edit  /  vim ~/.claude/karma/config.yaml")
    return 0


def cmd_sticky_list() -> int:
    try:
        sticky = load()
    except StickyConfigError as e:
        print(f"配置错误: {e}", file=sys.stderr)
        return 1
    if not sticky:
        print(f"没配置 sticky。运行 'karma init' 复制模板。")
        return 0
    print(f"karma sticky ({len(sticky)}/{MAX_STICKY} 软上限, {HARD_MAX} 硬上限):\n")
    for i, s in enumerate(sticky, 1):
        print(f"{i}. [{s.id}]")
        for line in s.preference.split("\n"):
            print(f"   {line}")
        print(f"   触发词: {', '.join(s.violation_keywords) if s.violation_keywords else '(无)'}")
        print()
    return 0


def cmd_sticky_edit() -> int:
    if not STICKY_PATH.exists():
        print(f"sticky.yaml 不存在，先 'karma init'", file=sys.stderr)
        return 1
    editor = os.environ.get("EDITOR", "vim")
    subprocess.run([editor, str(STICKY_PATH)])
    # 编辑后验证
    try:
        sticky = load()
        print(f"编辑成功，当前 {len(sticky)} 条 sticky。")
    except StickyConfigError as e:
        print(f"⚠️ 编辑后配置错误: {e}", file=sys.stderr)
        return 1
    return 0


def cmd_sticky_remove(rule_id: str) -> int:
    """简单删除 — 读 yaml，过滤，写回。"""
    import yaml
    if not STICKY_PATH.exists():
        print(f"sticky.yaml 不存在", file=sys.stderr)
        return 1
    raw = yaml.safe_load(STICKY_PATH.read_text(encoding="utf-8")) or []
    filtered = [item for item in raw if item.get("id") != rule_id]
    if len(filtered) == len(raw):
        print(f"没找到 id={rule_id!r}", file=sys.stderr)
        return 1
    STICKY_PATH.write_text(
        yaml.safe_dump(filtered, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    print(f"已删除 sticky {rule_id!r} ({len(filtered)} 条剩余)")
    return 0


def cmd_stats() -> int:
    """每条 sticky 的违反计数（总 / 7 天）。"""
    violations = load_all()
    if not violations:
        print("没有违反记录。")
        return 0
    now = int(time.time())
    week_ago = now - 7 * 24 * 3600
    total = Counter(v.sticky_id for v in violations)
    week = Counter(v.sticky_id for v in violations if v.ts >= week_ago)
    last_ts: dict[str, int] = {}
    for v in violations:
        if v.ts > last_ts.get(v.sticky_id, 0):
            last_ts[v.sticky_id] = v.ts
    print(f"karma 违反统计 (总 {len(violations)} 条):\n")
    print(f"{'sticky_id':<35} {'总':>6} {'7d':>6} {'最近违反':>20}")
    print("-" * 70)
    for sid, n in total.most_common():
        recent_str = datetime.fromtimestamp(last_ts.get(sid, 0)).strftime("%m-%d %H:%M")
        print(f"{sid:<35} {n:>6} {week.get(sid, 0):>6} {recent_str:>20}")
    return 0


def cmd_violations_recent(n: int = 20) -> int:
    violations = load_all()
    if not violations:
        print("没有违反记录。")
        return 0
    print(f"最近 {min(n, len(violations))} 条违反:\n")
    for v in violations[-n:]:
        ts_str = datetime.fromtimestamp(v.ts).strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{ts_str}] {v.sticky_id} (触发: {v.trigger!r})")
        print(f"  ...{v.snippet}...")
        print()
    return 0


def cmd_violations_clear() -> int:
    if not VIOLATIONS_PATH.exists():
        print("没有违反历史可清。")
        return 0
    n = sum(1 for _ in VIOLATIONS_PATH.open())
    confirm = input(f"确认清空 {n} 条违反历史? [y/N] ").strip().lower()
    if confirm != "y":
        print("已取消")
        return 0
    VIOLATIONS_PATH.unlink()
    print(f"已清空 {n} 条违反历史。")
    return 0


def cmd_doctor() -> int:
    print(f"karma v{__version__} doctor")
    print(f"  KARMA_DIR: {KARMA_DIR} ({'存在' if KARMA_DIR.exists() else '不存在'})")
    print(f"  sticky.yaml: {STICKY_PATH} ({'存在' if STICKY_PATH.exists() else '不存在'})")
    print(f"  violations.jsonl: {VIOLATIONS_PATH} ({'存在' if VIOLATIONS_PATH.exists() else '不存在'})")
    config_path = KARMA_DIR / "config.yaml"
    print(f"  config.yaml: {config_path} ({'存在' if config_path.exists() else '不存在 (用默认值)'})")
    try:
        sticky = load()
        print(f"  sticky 加载: ✓ {len(sticky)} 条")
        if len(sticky) > MAX_STICKY:
            print(f"    ⚠️ 超过软上限 {MAX_STICKY} (但未达硬上限 {HARD_MAX})")
    except StickyConfigError as e:
        print(f"  sticky 加载: ✗ {e}")
        return 1

    # 显示当前生效配置
    from karma.config import load as _load_config
    cfg = _load_config()
    print(f"  当前生效配置:")
    for k, v in cfg.items():
        print(f"    {k}: {v}")

    # hook 安装检测 — 每个 event 三项：wrapper 存在 / 可执行 / settings.json 含引用
    status = _check_hooks_installed()
    print(f"  hook 安装检测:")
    all_ok = True
    any_missing = False
    for event in ("UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop"):
        s = status[event]
        if s["wrapper_exists"] and s["wrapper_executable"] and s["in_settings"]:
            print(f"    {event}: ✓ wrapper + settings 都在")
        else:
            all_ok = False
            any_missing = True
            problems = []
            if not s["wrapper_exists"]:
                problems.append("wrapper 缺失")
            elif not s["wrapper_executable"]:
                problems.append("wrapper 不可执行")
            if not s["in_settings"]:
                problems.append("settings.json 未引用")
            print(f"    {event}: ✗ {', '.join(problems)}")
    if any_missing:
        print(f"  → 运行 `karma install-hooks` 修复")
    return 0 if all_ok else 1


def cmd_install_hooks() -> int:
    """生成 wrapper + 自动写 settings.json（idempotent + 备份 + 保留其他 hook）。"""
    hooks_dir = _hooks_dir()
    hooks_dir.mkdir(parents=True, exist_ok=True)
    karma_python = sys.executable  # 用当前 venv python（含 karma 包），避免 PATH 问题
    for hook_name in _KARMA_HOOK_EVENTS.values():
        wrapper = hooks_dir / f"karma_{hook_name}.py"
        wrapper.write_text(
            f"#!{karma_python}\n"
            f"# karma {hook_name} hook wrapper (auto-generated)\n"
            f"# python: {karma_python}\n"
            f"import sys\n"
            f"sys.exit(__import__('karma.hooks.{hook_name}', fromlist=['main']).main())\n"
        )
        wrapper.chmod(0o755)
        print(f"  生成: {wrapper}")
    # 清理旧版 post_response wrapper
    old_pr = hooks_dir / "karma_post_response.py"
    if old_pr.exists():
        old_pr.unlink()
        print(f"  删除旧版: {old_pr}")

    # 备份原 settings.json（仅首次，不覆盖已有备份）
    settings_path = _settings_path()
    backup_path = _settings_backup_path()
    if settings_path.exists() and not backup_path.exists():
        backup_path.write_text(settings_path.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"  备份原 settings: {backup_path}")

    # 改 settings.json — 先清旧 karma entry 再加新的（idempotent + 保留他人 hook）
    settings = _load_settings()
    _remove_karma_entries(settings)
    _add_karma_entries(settings)
    _save_settings(settings)
    print(f"  已配置 {settings_path}（4 个 hook event）")
    return 0


def cmd_uninstall_hooks() -> int:
    hooks_dir = _hooks_dir()
    n = 0
    for hook_name in ("user_prompt_submit", "pre_tool_use", "post_tool_use", "stop", "post_response"):
        wrapper = hooks_dir / f"karma_{hook_name}.py"
        if wrapper.exists():
            wrapper.unlink()
            n += 1
            print(f"  删除: {wrapper}")
    # 从 settings.json 也移除 karma entry
    settings_path = _settings_path()
    if settings_path.exists():
        settings = _load_settings()
        before = sum(len(e) for e in settings.get("hooks", {}).values())
        _remove_karma_entries(settings)
        after = sum(len(e) for e in settings.get("hooks", {}).values())
        if before > after:
            _save_settings(settings)
            print(f"  从 settings.json 移除 {before - after} 个 karma entry")
    print(f"已删除 {n} 个 hook wrapper。")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if argv[0] == "--version":
        print(f"karma v{__version__}")
        return 0

    cmd = argv[0]
    args = argv[1:]

    if cmd == "init":
        return cmd_init()
    if cmd == "doctor":
        return cmd_doctor()
    if cmd == "stats":
        return cmd_stats()
    if cmd == "install-hooks":
        return cmd_install_hooks()
    if cmd == "uninstall-hooks":
        return cmd_uninstall_hooks()
    if cmd == "sticky":
        if not args:
            print("Usage: karma sticky <list|edit|remove>", file=sys.stderr)
            return 1
        if args[0] == "list":
            return cmd_sticky_list()
        if args[0] == "edit":
            return cmd_sticky_edit()
        if args[0] == "remove":
            if len(args) < 2:
                print("Usage: karma sticky remove <id>", file=sys.stderr)
                return 1
            return cmd_sticky_remove(args[1])
        print(f"未知 sticky 子命令: {args[0]}", file=sys.stderr)
        return 1
    if cmd == "violations":
        if not args:
            print("Usage: karma violations <recent|clear>", file=sys.stderr)
            return 1
        if args[0] == "recent":
            n = int(args[1]) if len(args) > 1 else 20
            return cmd_violations_recent(n)
        if args[0] == "clear":
            return cmd_violations_clear()
        print(f"未知 violations 子命令: {args[0]}", file=sys.stderr)
        return 1
    print(f"未知命令: {cmd}\n{__doc__}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
