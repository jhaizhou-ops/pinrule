"""karma CLI — sticky 管理 + 违反观察 + hook 安装。

Usage:
    karma init [--minimal|--no-minimal]
                                   创建 ~/.claude/karma/ + 复制 sticky/config 模板
                                   默认按系统语言偏好自动选：中文 → 7 条完整；
                                   非中文/检测不到 → 5 条精简（砍 chinese_plain）
                                   --minimal / --no-minimal 强制覆盖
    karma install-hooks [--backend claude-code|codex|gemini-cli|all]
                                   自动配置 hooks（默认 claude-code 向后兼容）
                                   codex 会同时启用 features.hooks；
                                   gemini-cli 写 ~/.gemini/settings.json；
                                   all 装本机检测到的所有 AI 编程客户端
    karma uninstall-hooks [--backend ...]   移除 hook 配置
    karma doctor                   检查环境 + hook 装机 + 当前生效 config

    karma sticky list              列出所有 sticky 规则
    karma sticky edit              用 $EDITOR 编辑 sticky.yaml
    karma sticky remove <id>       移除某条

    karma stats                    每条规则违反计数（含本 session 最近 5 turn）
    karma violations recent [N]    最近 N 条违反详情（默认 20）
    karma violations clear         清空违反历史（需确认）
    karma audit                    审计 — 每条 sticky top 触发词 + 假阳嫌疑标记
    karma reset                    清 session-state（漂移实验重启）
"""

from __future__ import annotations

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

from karma.paths import karma_home

KARMA_DIR = karma_home()
EXAMPLE_STICKY = Path(__file__).parent.parent / "data" / "sticky.dev.example.yaml"
EXAMPLE_STICKY_MINIMAL = Path(__file__).parent.parent / "data" / "sticky.dev.minimal.example.yaml"
EXAMPLE_CONFIG = Path(__file__).parent.parent / "data" / "config.example.yaml"

def cmd_init(minimal: bool | None = None) -> int:
    """创建 ~/.claude/karma/ + 复制 sticky 模板 + config 模板。

    minimal=None（默认）→ 自动按系统语言偏好选：中文用户 7 条完整含
    chinese_plain check；非中文 / 检测不到 → 5 条精简（砍 chinese_plain）。
    minimal=True 强制装 5 条；minimal=False 强制装 7 条。

    跨平台检测见 `karma/locale_detect.py`（macOS 用 defaults read AppleLanguages,
    Linux 用 $LANG / $LC_ALL）。跟 VS Code / Slack 等 app 安装时自动选语言做法一致。
    """
    KARMA_DIR.mkdir(parents=True, exist_ok=True)

    auto_chose = ""
    if minimal is None:
        # 自动按系统语言偏好选（跨平台：macOS defaults / Linux $LANG /
        # Windows GetUserDefaultUILanguage / fallback POSIX 环境变量）
        from karma.locale_detect import detect_user_language, is_chinese_user
        lang = detect_user_language()
        if is_chinese_user():
            minimal = False
            auto_chose = f"（检测到系统语言 {lang!r} → 装完整 7 条含 chinese_plain）"
        else:
            minimal = True
            lang_label = lang or "无法检测"
            auto_chose = f"（检测到系统语言 {lang_label!r} → 装精简 5 条砍 chinese_plain）"

    template = EXAMPLE_STICKY_MINIMAL if minimal else EXAMPLE_STICKY
    label = "5 条真中性核心" if minimal else "7 条完整开发场景"
    # sticky 模板
    if STICKY_PATH.exists():
        print(f"sticky.yaml 已存在: {STICKY_PATH}")
    elif not template.exists():
        print(f"模板文件不存在: {template}", file=sys.stderr)
        return 1
    else:
        shutil.copyfile(template, STICKY_PATH)
        print(f"创建 sticky.yaml: {STICKY_PATH} ({label}) {auto_chose}".rstrip())
    # config 模板
    config_path = KARMA_DIR / "config.yaml"
    if config_path.exists():
        print(f"config.yaml 已存在: {config_path}")
    elif EXAMPLE_CONFIG.exists():
        shutil.copyfile(EXAMPLE_CONFIG, config_path)
        print(f"创建 config.yaml: {config_path}")
    print("编辑用: karma sticky edit  /  vim ~/.claude/karma/config.yaml")
    if auto_chose:
        override_flag = "--no-minimal" if minimal else "--minimal"
        print(f"自动选不对？强制覆盖：karma init {override_flag}")
    return 0


def cmd_sticky_list() -> int:
    try:
        sticky = load()
    except StickyConfigError as e:
        print(f"配置错误: {e}", file=sys.stderr)
        return 1
    if not sticky:
        print("没配置 sticky。运行 'karma init' 复制模板。")
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
        print("sticky.yaml 不存在，先 'karma init'", file=sys.stderr)
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
        print("sticky.yaml 不存在", file=sys.stderr)
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


def cmd_reset_session() -> int:
    """清所有 session-state JSON — Agent 注意力漂移实验重启。

    用法场景：观察「干净 session 起步」vs「累积 N turn 后」Agent 行为差异。
    不动 violations.jsonl（历史保留）+ 不动 sticky.yaml / config.yaml。
    """
    from karma.session_state import DEFAULT_DIR as SS_DIR
    if not SS_DIR.exists():
        print(f"session-state 目录不存在: {SS_DIR}")
        return 0
    n = 0
    for p in SS_DIR.glob("*.json"):
        try:
            p.unlink()
            n += 1
        except OSError as e:
            print(f"删 {p} 失败: {e}", file=sys.stderr)
    print(f"已清空 {n} 个 session-state 文件 ({SS_DIR})")
    return 0


def cmd_audit() -> int:
    """审计违反历史：每条 sticky 的 top 触发词 + 假阳嫌疑标记 + 本 session 漂移近况。

    假阳嫌疑：同一触发词命中 ≥ 5 次且占该 sticky 触发 ≥ 50% → 可能 pattern 过宽
    """
    violations = load_all()
    if not violations:
        print("没有违反记录。先用 karma 一阵子再来 audit。")
        return 0
    from collections import Counter
    # 按 sticky_id 分组，每组数 trigger 出现频次
    by_sticky: dict[str, Counter] = {}
    for v in violations:
        by_sticky.setdefault(v.sticky_id, Counter())[v.trigger] += 1
    print(f"karma 违反审计 (总 {len(violations)} 条):\n")
    for sid in sorted(by_sticky, key=lambda s: -sum(by_sticky[s].values())):
        ctr = by_sticky[sid]
        total = sum(ctr.values())
        print(f"[{sid}] {total} 条触发")
        for trigger, cnt in ctr.most_common(5):
            ratio = cnt / total
            mark = " ⚠️ 可能假阳" if cnt >= 5 and ratio >= 0.5 else ""
            print(f"  {cnt:>3}× ({ratio*100:.0f}%) {trigger!r}{mark}")
        print()

    # 本 session 漂移近况（最近 N turn 内每条 sticky 累积次数）
    current_session = violations[-1].session_id
    current_turn = max((v.turn for v in violations if v.session_id == current_session), default=0)
    if current_turn > 0:
        turns_window = 10
        cutoff = current_turn - turns_window
        recent = Counter(
            v.sticky_id for v in violations
            if v.session_id == current_session and v.turn >= cutoff and v.turn > 0
        )
        if recent:
            print(f"=== 本 session 最近 {turns_window} turn 漂移近况（当前 turn={current_turn}）===")
            for sid, n in recent.most_common():
                hot = " 🔥 高频" if n >= 3 else ""
                print(f"  {n:>3}× {sid}{hot}")
        else:
            print(f"=== 本 session 最近 {turns_window} turn 无违反 ✓ (当前 turn={current_turn}) ===")
        print()

    # 自动改进建议（基于假阳分析）
    print("=== 改进建议 ===")
    suggestions: list[str] = []
    for sid, ctr in by_sticky.items():
        total = sum(ctr.values())
        if total < 5:
            continue
        for trigger, cnt in ctr.most_common(3):
            ratio = cnt / total
            if cnt >= 5 and ratio >= 0.5:
                suggestions.append(
                    f"- [{sid}] 触发词 {trigger!r} 占 {ratio*100:.0f}% ({cnt}×)，"
                    f"考虑收紧 pattern 或精确化关键词"
                )
    if suggestions:
        for s in suggestions:
            print(s)
    else:
        print("(暂无明显假阳重灾区)")
    return 0


def cmd_stats() -> int:
    """每条 sticky 的违反计数（总 / 7 天 / 本 session 最近 5 turn）。"""
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

    # 本 session 最近 N turn 维度（Agent 漂移视角）— 取最新 session_id 当前 turn
    # 简化：取 violations.jsonl 里最近一条的 session_id 当「当前 session」
    current_session = violations[-1].session_id if violations else ""
    current_turn = max((v.turn for v in violations if v.session_id == current_session), default=0)
    turns_window = 5
    cutoff_turn = current_turn - turns_window
    recent_turns_count = Counter(
        v.sticky_id for v in violations
        if v.session_id == current_session and v.turn >= cutoff_turn and v.turn > 0
    )

    print(f"karma 违反统计 (总 {len(violations)} 条):")
    if current_turn > 0:
        # 顺便显示本 session stop_block_count（Stop hook 干预次数）
        from karma import session_state as ss
        try:
            state = ss.load(current_session)
            if state.stop_block_count > 0:
                print(
                    f"本 session 当前 turn={current_turn}，Stop hook 已干预 {state.stop_block_count} 次"
                    f"（keep-pushing 不主动停）"
                )
            else:
                print(f"本 session 当前 turn={current_turn}")
        except Exception:
            print(f"本 session 当前 turn={current_turn}")
        print(f"「最近 {turns_window} turn」列代表 Agent 注意力漂移近况\n")
    else:
        print()
    print(f"{'sticky_id':<35} {'总':>6} {'7d':>6} {'最近 ' + str(turns_window) + ' turn':>14} {'最近违反':>20}")
    print("-" * 84)
    for sid, n in total.most_common():
        recent_str = datetime.fromtimestamp(last_ts.get(sid, 0)).strftime("%m-%d %H:%M")
        print(
            f"{sid:<35} {n:>6} {week.get(sid, 0):>6} "
            f"{recent_turns_count.get(sid, 0):>14} {recent_str:>20}"
        )
    # 未触发的 sticky 显示 ✓ 让作者看到正面证据（哪些规则没违反）
    try:
        from karma.sticky import load as _load_sticky
        all_sticky_ids = {s.id for s in _load_sticky()}
        untriggered = sorted(all_sticky_ids - set(total))
        if untriggered:
            print("\n=== 未触发的 sticky（✓ 没违反过）===")
            for sid in untriggered:
                print(f"  ✓ {sid}")
    except Exception:
        pass
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


def cmd_violations_clear(sticky_filter: str | None = None, trigger_filter: str | None = None) -> int:
    """清违反历史。
    无参数 → 清全部
    --sticky <id> → 只清该 sticky 的，保留其他
    --trigger <substring> → 只清触发词含该 substring 的（精细化 fix 后清假阳）
    两个 filter 都给 → 都匹配才清
    """
    if not VIOLATIONS_PATH.exists():
        print("没有违反历史可清。")
        return 0
    if sticky_filter or trigger_filter:
        # 选择性清
        lines = VIOLATIONS_PATH.read_text(encoding="utf-8").splitlines()
        keep_lines = []
        removed = 0
        import json as _json
        for line in lines:
            line_stripped = line.strip()
            if not line_stripped:
                continue
            try:
                d = _json.loads(line_stripped)
                match_sticky = sticky_filter is None or d.get("sticky_id") == sticky_filter
                match_trigger = trigger_filter is None or trigger_filter in d.get("trigger", "")
                if match_sticky and match_trigger:
                    removed += 1
                    continue
            except _json.JSONDecodeError:
                pass
            keep_lines.append(line)
        if removed == 0:
            filters = []
            if sticky_filter:
                filters.append(f"sticky={sticky_filter!r}")
            if trigger_filter:
                filters.append(f"trigger contains {trigger_filter!r}")
            print(f"没找到 {' AND '.join(filters)} 的违反记录。")
            return 0
        filter_desc = []
        if sticky_filter:
            filter_desc.append(f"sticky={sticky_filter!r}")
        if trigger_filter:
            filter_desc.append(f"trigger~{trigger_filter!r}")
        confirm = input(f"确认清 {removed} 条 {' AND '.join(filter_desc)} 的违反（保留 {len(keep_lines)} 条其他）? [y/N] ").strip().lower()
        if confirm != "y":
            print("已取消")
            return 0
        VIOLATIONS_PATH.write_text("\n".join(keep_lines) + ("\n" if keep_lines else ""), encoding="utf-8")
        print(f"已清 {removed} 条，保留 {len(keep_lines)} 条其他。")
        return 0
    # 全清
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
        exempt_ids = [s.id for s in sticky if s.force_block_exempt]
        if exempt_ids:
            print(f"    force_block 豁免: {', '.join(exempt_ids)} "
                  "（累积违反不触发 Stop 强制 block）")
    except StickyConfigError as e:
        print(f"  sticky 加载: ✗ {e}")
        return 1

    # 显示当前生效配置
    from karma.config import load as _load_config
    cfg = _load_config()
    print("  当前生效配置:")
    for k, v in cfg.items():
        print(f"    {k}: {v}")

    # 显示活跃 session 简况（turn / stop_block 状态）
    from karma import session_state as _ss
    from karma.violations import load_all as _load_v
    all_v = _load_v()
    if all_v:
        active_session = all_v[-1].session_id
        try:
            state = _ss.load(active_session)
            print(f"  最近活跃 session: {active_session}")
            print(f"    turn={state.turn_count}, stop_block={state.stop_block_count}, "
                  f"read={len(state.read_files)} files, edit={len(state.edit_files)} files")
        except Exception:
            pass

    # Stop hook trace 状态（仅当 KARMA_DEBUG_TRACE 指向可读文件时显示）
    _trace_env = os.environ.get("KARMA_DEBUG_TRACE")
    if _trace_env:
        from pathlib import Path as _Path
        trace = _Path(_trace_env)
        if trace.exists():
            try:
                n_lines = sum(1 for _ in trace.open(encoding="utf-8"))
                print(f"  Stop hook trace ({trace}): {n_lines} 条触发记录")
            except OSError:
                pass

    # hook 安装检测 — 跨所有 backend 显示（claude-code / codex / 未来）
    from karma.backends import REGISTRY as _BACKENDS
    print("  hook 安装检测（多 backend）:")
    all_ok = True
    any_install_missing = False
    for backend_name, backend in _BACKENDS.items():
        installed_client = backend.client_installed()
        marker = "✓" if installed_client else "✗"
        print(f"    [{backend_name}] {backend.display_name} 客户端: {marker}")
        if not installed_client:
            continue

        try:
            settings = backend.load_settings()
        except Exception as e:
            print(f"      ⚠️ 配置加载失败: {e}")
            all_ok = False
            continue
        hooks = settings.get("hooks", {})
        any_event_missing = False
        for event_name, hook_basename in backend.hook_events().items():
            wrapper = backend.hooks_dir() / f"karma_{hook_basename}.py"
            wrapper_ok = wrapper.exists() and os.access(wrapper, os.X_OK)
            in_settings = any(
                backend.is_karma_entry(e) for e in hooks.get(event_name, [])
                if any(hook_basename in h.get("command", "") for h in e.get("hooks", []))
            )
            if wrapper_ok and in_settings:
                print(f"      {event_name}: ✓")
            else:
                any_event_missing = True
                all_ok = False
                problems = []
                if not wrapper.exists():
                    problems.append("wrapper 缺失")
                elif not os.access(wrapper, os.X_OK):
                    problems.append("wrapper 不可执行")
                if not in_settings:
                    problems.append(f"{backend.settings_path().name} 未引用")
                print(f"      {event_name}: ✗ {', '.join(problems)}")
        if any_event_missing:
            any_install_missing = True
    if any_install_missing:
        print("  → 运行 `karma install-hooks --backend all` 修复")
    return 0 if all_ok else 1


def _install_to_backend(backend) -> int:
    """单 backend 装机流程：写 wrapper + 备份 + 改 settings + pre_install_setup。"""
    from karma.backends._base import SettingsParseError

    print(f"\n→ {backend.display_name}（{backend.name}）")

    # backend 特有的前置步骤（如 Codex 启用 features.hooks）
    for step in backend.pre_install_setup():
        print(f"  {step}")

    hooks_dir = backend.hooks_dir()
    hooks_dir.mkdir(parents=True, exist_ok=True)
    karma_python = sys.executable
    for hook_basename in backend.hook_events().values():
        wrapper = hooks_dir / f"karma_{hook_basename}.py"
        wrapper.write_text(
            f"#!{karma_python}\n"
            f"# karma {hook_basename} hook wrapper (auto-generated)\n"
            f"# python: {karma_python}\n"
            f"import sys\n"
            f"sys.exit(__import__('karma.hooks.{hook_basename}', fromlist=['main']).main())\n"
        )
        wrapper.chmod(0o755)
        print(f"  生成: {wrapper}")
    old_pr = hooks_dir / "karma_post_response.py"
    if old_pr.exists():
        old_pr.unlink()
        print(f"  删除旧版: {old_pr}")

    # 备份原 settings（保留初次 + 加 ts 的本次备份）
    settings_path = backend.settings_path()
    backup_path = backend.settings_backup_path()
    if settings_path.exists():
        if not backup_path.exists():
            backup_path.write_text(settings_path.read_text(encoding="utf-8"), encoding="utf-8")
            print(f"  备份原 settings: {backup_path}")
        ts_backup = settings_path.with_suffix(
            settings_path.suffix + f".before-karma.{int(time.time())}"
        )
        ts_backup.write_text(settings_path.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"  本次备份: {ts_backup}")

    try:
        settings = backend.load_settings()
    except SettingsParseError as e:
        print(f"\n{e}", file=sys.stderr)
        return 1

    # 移除旧 karma entry（idempotent + 保留他人 hook）
    hooks = settings.get("hooks", {})
    for event in list(hooks.keys()):
        hooks[event] = [e for e in hooks[event] if not backend.is_karma_entry(e)]
        if not hooks[event]:
            del hooks[event]

    # 加新 karma entry
    settings.setdefault("hooks", {})
    for event_name, hook_basename in backend.hook_events().items():
        settings["hooks"].setdefault(event_name, [])
        settings["hooks"][event_name].append(
            backend.build_event_entry(hook_basename, event_name)
        )

    backend.save_settings(settings)
    print(f"  已配置 {settings_path}（{len(backend.hook_events())} 个 hook event）")
    return 0


def cmd_install_hooks(backend_name: str = "claude-code") -> int:
    """生成 wrapper + 自动写客户端配置（idempotent + 备份 + 保留他人 hook）。

    backend_name:
      - "claude-code"（默认，向后兼容）：装 Claude Code
      - "codex": 装 Codex CLI
      - "all": 装本机所有检测到的客户端
    """
    from karma.backends import REGISTRY, detect_installed_backends

    if backend_name == "all":
        installed = detect_installed_backends()
        if not installed:
            print("没检测到任何支持的 AI 编程客户端（claude / codex）", file=sys.stderr)
            return 1
        print(f"检测到客户端：{', '.join(installed)}")
        backends_to_install = [REGISTRY[name] for name in installed]
    elif backend_name in REGISTRY:
        backends_to_install = [REGISTRY[backend_name]]
    else:
        print(f"未知 backend: {backend_name!r}（支持: {list(REGISTRY.keys()) + ['all']}）",
              file=sys.stderr)
        return 1

    rc = 0
    for backend in backends_to_install:
        if _install_to_backend(backend) != 0:
            rc = 1
    return rc


def _uninstall_from_backend(backend) -> int:
    """单 backend 卸装：删 wrapper + 从 settings 移除 karma entry。"""
    print(f"\n→ {backend.display_name}（{backend.name}）")
    hooks_dir = backend.hooks_dir()
    n = 0
    for hook_basename in list(backend.hook_events().values()) + ["post_response"]:
        wrapper = hooks_dir / f"karma_{hook_basename}.py"
        if wrapper.exists():
            wrapper.unlink()
            n += 1
            print(f"  删除: {wrapper}")
    settings_path = backend.settings_path()
    if settings_path.exists():
        try:
            settings = backend.load_settings()
        except Exception:
            print(f"  ⚠️  {settings_path} 加载失败，跳过 entry 清理")
            return 0
        hooks = settings.get("hooks", {})
        before = sum(len(e) for e in hooks.values())
        for event in list(hooks.keys()):
            hooks[event] = [e for e in hooks[event] if not backend.is_karma_entry(e)]
            if not hooks[event]:
                del hooks[event]
        after = sum(len(e) for e in settings.get("hooks", {}).values())
        if before > after:
            backend.save_settings(settings)
            print(f"  从 {settings_path.name} 移除 {before - after} 个 karma entry")
    print(f"  删除 {n} 个 wrapper")
    return 0


def cmd_uninstall_hooks(backend_name: str = "claude-code") -> int:
    """卸 karma hook（默认 claude-code 向后兼容；--backend codex/all 同 install）。"""
    from karma.backends import REGISTRY, detect_installed_backends

    if backend_name == "all":
        installed = detect_installed_backends()
        backends_to_uninstall = [REGISTRY[name] for name in installed]
    elif backend_name in REGISTRY:
        backends_to_uninstall = [REGISTRY[backend_name]]
    else:
        print(f"未知 backend: {backend_name!r}", file=sys.stderr)
        return 1

    for backend in backends_to_uninstall:
        _uninstall_from_backend(backend)
    return 0


def _parse_backend_arg(args: list[str]) -> str:
    """从 CLI args 解析 --backend <name>，默认 'claude-code' 向后兼容。

    支持 '--backend codex' / '--backend claude-code' / '--backend all'。
    位置参数（不带 --backend）一律不识别为 backend 名。
    """
    if "--backend" not in args:
        return "claude-code"
    idx = args.index("--backend")
    if idx + 1 >= len(args):
        return "claude-code"
    return args[idx + 1]


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
        # --minimal 强制 5 条；--no-minimal 强制 7 条；都不带 → None 自动按
        # 系统语言偏好选
        if "--minimal" in args:
            minimal_arg: bool | None = True
        elif "--no-minimal" in args:
            minimal_arg = False
        else:
            minimal_arg = None
        return cmd_init(minimal=minimal_arg)
    if cmd == "doctor":
        return cmd_doctor()
    if cmd == "stats":
        return cmd_stats()
    if cmd == "audit":
        return cmd_audit()
    if cmd in ("reset", "reset-session"):
        return cmd_reset_session()
    if cmd == "install-hooks":
        return cmd_install_hooks(backend_name=_parse_backend_arg(args))
    if cmd == "uninstall-hooks":
        return cmd_uninstall_hooks(backend_name=_parse_backend_arg(args))
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
            # 支持 --sticky <id> / --trigger <substring> 选择性清
            sticky_filter = None
            trigger_filter = None
            i = 1
            while i < len(args):
                if args[i] == "--sticky" and i + 1 < len(args):
                    sticky_filter = args[i + 1]
                    i += 2
                elif args[i] == "--trigger" and i + 1 < len(args):
                    trigger_filter = args[i + 1]
                    i += 2
                else:
                    i += 1
            return cmd_violations_clear(sticky_filter, trigger_filter)
        print(f"未知 violations 子命令: {args[0]}", file=sys.stderr)
        return 1
    print(f"未知命令: {cmd}\n{__doc__}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
