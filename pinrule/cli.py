"""pinrule CLI — rule 管理 + 违反观察 + hook 安装。

Usage:
    pinrule init [--minimal|--no-minimal]
                                   创建 ~/.pinrule/ + 复制 rules/config 模板
                                   默认按系统语言偏好选 zh/en localized 模板 (都 7 条对称).
                                   --minimal 强制装 5 条 cross-scenario universal (砍
                                   chinese-plain / no-testset); --no-minimal 强制 7 条.
    pinrule install-hooks [--backend claude-code|codex|cursor|all]
                                   默认 'all' (v0.16.1+) — 装本机检测到的所有客户端
                                   --backend <name> 单独装某家
                                   codex 会同时启用 features.hooks
    pinrule sync-cursor-rules          刷新 ~/.cursor/rules/pinrule-sticky.mdc (Cursor 起手可见)
    pinrule sync-cursor-visibility   hook 之外: Claude skills 目录 + empty-window 项目 rules
    pinrule install-skill [--force] [--backend claude-code|codex|cursor|all]
                                   装 pinrule skill 到检测到的客户端
                                   - Claude: ~/.claude/skills/pinrule/SKILL.md
                                   - Codex:  ~/.agents/skills/pinrule/SKILL.md
                                   - Cursor: 协议级限 project-scoped, 跳过 (装机时
                                     post_install_message 告知怎么手工 cp 到目标项目)
                                   pinrule init 已自动跑一次, 老用户 / skill 升级用本命令.
                                   已存在且不同 → 写 .md.new 文件让用户对比, 不覆盖;
                                   --force 强制覆盖 (会丢用户对 skill 的本地改动)
    pinrule uninstall-hooks [--backend ...]   移除 hook 配置
    pinrule uninstall                一键卸所有 backend（= uninstall-hooks --backend all）
    pinrule doctor                   检查环境 + hook 装机 + 当前生效 config

    pinrule rule list                列出所有 rule 规则
    pinrule rule edit                用 $EDITOR 编辑 rules.json
    pinrule rule remove <id>         移除某条
    pinrule rule add --from-json <file>       从 JSON 文件追加一条新 rule
    pinrule rule add --from-stdin             从 stdin 读 JSON 追加 (Claude Code skill 用)
    pinrule rule preview --from-json <file>   预览注入头部样子 (不写入)
    pinrule rule preview --from-stdin         预览 stdin JSON (不写入)

    pinrule stats                    每条规则违反计数（含本 session 最近 5 turn）
    pinrule violations recent [N]    最近 N 条违反详情（默认 20）
    pinrule violations clear         清空违反历史（需确认）
    pinrule audit                    审计 — 每条 rule top 触发词 + 假阳嫌疑标记
    pinrule reset                    清 session-state（漂移实验重启）

提示: Claude / Codex / Cursor 用户都可发 `/pinrule <自然语言描述>` 让 Agent
自动用 pinrule skill 优化结构后调 `pinrule rule add --from-stdin` 写入.
(Cursor 协议级限 project-scoped, 需把 skill cp 到目标项目 .cursor/skills/pinrule/)
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

from pinrule import __version__
from pinrule.rule import DEFAULT_PATH as RULES_PATH
from pinrule.rule import HARD_MAX, MAX_RULES, RuleConfigError, format_for_injection
from pinrule.rule import load as load_rules
from pinrule.violations import DEFAULT_PATH as VIOLATIONS_PATH
from pinrule.violations import load_all

from pinrule.paths import pinrule_home

PINRULE_DIR = pinrule_home()
_DATA_DIR = Path(__file__).parent.parent / "data"
EXAMPLE_RULES_EN = _DATA_DIR / "rules.dev.example.json"        # English default
EXAMPLE_RULES_ZH = _DATA_DIR / "rules.dev.example.zh.json"     # 中文
EXAMPLE_RULES_MINIMAL_EN = _DATA_DIR / "rules.dev.minimal.example.json"
EXAMPLE_RULES_MINIMAL_ZH = _DATA_DIR / "rules.dev.minimal.example.zh.json"
EXAMPLE_CONFIG = _DATA_DIR / "config.example.json"
# v0.5.16: pinrule skill source — Markdown source of truth; auto-installed to
# all detected backends (Claude / Codex / Cursor). v0.13.2 dropped Gemini backend +
# the Markdown→TOML conversion path that used to feed it.
_SKILLS_DIR = Path(__file__).parent.parent / "skills"
PINRULE_SKILL_SRC = _SKILLS_DIR / "pinrule" / "SKILL.md"


def _select_rule_template(minimal: bool) -> Path:
    """按系统语言 detect 选模板（中文用户 .zh.json / 其他英文 default）。"""
    from pinrule.locale_detect import is_chinese_user
    if is_chinese_user():
        return EXAMPLE_RULES_MINIMAL_ZH if minimal else EXAMPLE_RULES_ZH
    return EXAMPLE_RULES_MINIMAL_EN if minimal else EXAMPLE_RULES_EN


def _write_skill_target(
    src_text: str,
    dest: Path,
    _content_format: str = "markdown",
    force: bool = False,
) -> tuple[bool, str]:
    """装一份 skill 到单个目标路径 (raw Markdown).

    v0.13.2 后: 砍 Gemini 后只剩 markdown 一种, 参数 _ 前缀标 intentionally-unused
    维持 caller 调用契约.

    冲突处理 (sticky #1 不覆盖用户改动):
    - 不存在 → 写, 返回 (True, "installed")
    - 已存在 + 内容一致 → skip, 返回 (False, "up-to-date")
    - 已存在 + 内容不同 + force=False → 写 .new 兄弟文件, 返回 (False, "exists-diff")
    - 已存在 + 内容不同 + force=True → 覆盖, 返回 (True, "force-overwritten")
    """
    body = src_text

    dest.parent.mkdir(parents=True, exist_ok=True)

    if not dest.exists():
        dest.write_text(body, encoding="utf-8")
        return True, "installed"

    if dest.read_text(encoding="utf-8") == body:
        return False, "up-to-date"

    if force:
        dest.write_text(body, encoding="utf-8")
        return True, "force-overwritten"

    new_path = dest.with_suffix(dest.suffix + ".new")
    new_path.write_text(body, encoding="utf-8")
    return False, "exists-diff"


def _install_pinrule_skill_multi_backend(
    force: bool = False,
    backend_filter: str | None = None,
) -> list[tuple[str, Path, bool, str]]:
    """装 pinrule skill 到所有 (或指定) detected backend.

    backend_filter: None / "all" → 所有 detected backend
                    "claude-code" / "codex" / "cursor" → 单独装该 backend
                    (不要求 backend 在本机已装 — 用户可能想预装等以后用客户端时生效)

    返回 [(backend_name, dest_path, changed, reason), ...] 让 caller 汇报.
    """
    if not PINRULE_SKILL_SRC.exists():
        return [("source", PINRULE_SKILL_SRC, False, "source-missing")]

    src_text = PINRULE_SKILL_SRC.read_text(encoding="utf-8")
    from pinrule.backends import REGISTRY as _BACKENDS

    if backend_filter in (None, "all"):
        backends_to_install = list(_BACKENDS.items())
    elif backend_filter in _BACKENDS:
        backends_to_install = [(backend_filter, _BACKENDS[backend_filter])]
    else:
        return [("error", Path(), False, f"unknown-backend ({backend_filter})")]

    out: list[tuple[str, Path, bool, str]] = []
    for name, backend in backends_to_install:
        for dest, fmt in backend.skill_install_targets("pinrule"):
            changed, reason = _write_skill_target(src_text, dest, fmt, force=force)
            out.append((name, dest, changed, reason))
    return out



def cmd_install_skill(force: bool = False, backend: str | None = None) -> int:
    """装 pinrule skill 到所有 / 指定 backend (多 backend 一波装).

    flow:
    - pinrule init 已自动调一次, 已 init 老用户跑 pinrule install-skill 补装
    - skill 升级 (clarity audit 等) 用 --force 覆盖
    - --backend <name> 单独装某家 (claude-code / codex / cursor)
    """
    results = _install_pinrule_skill_multi_backend(force=force, backend_filter=backend)

    if not results:
        print("❌ 没找到任何 backend", file=sys.stderr)
        return 1
    first_name = results[0][0]
    if first_name == "source":
        print(f"❌ source-missing: {PINRULE_SKILL_SRC}", file=sys.stderr)
        return 1
    if first_name == "error":
        print(f"❌ {results[0][3]}", file=sys.stderr)
        return 1

    by_backend: dict[str, list[tuple[Path, bool, str]]] = {}
    for backend_name, dest, changed, reason in results:
        by_backend.setdefault(backend_name, []).append((dest, changed, reason))

    for backend_name, entries in by_backend.items():
        for dest, _changed, reason in entries:
            if reason == "installed":
                print(f"✓ [{backend_name}] 装 pinrule skill: {dest}")
            elif reason == "up-to-date":
                print(f"✓ [{backend_name}] pinrule skill 已是最新: {dest}")
            elif reason == "force-overwritten":
                print(f"✓ [{backend_name}] 强制覆盖: {dest}")
            elif reason == "exists-diff":
                new_path = dest.with_suffix(dest.suffix + ".new")
                print(f"⚠ [{backend_name}] {dest} 已存在跟当前 pinrule 版本不一致")
                print(f"  → 新版写到 {new_path}")
                print("  → diff 对比或 pinrule install-skill --force 覆盖 (会丢用户改动)")
            else:
                print(f"? [{backend_name}] {dest}: {reason}")
    print()
    print("用法: 各 backend 输 `/pinrule <自然语言描述>` 触发 (Codex 用 `/skills` menu 或 `$pinrule <NL>`)")
    return 0


# v0.16.10: module-level 常量让 test fixture 真 monkeypatch sandbox.
# 之前 hardcoded `Path(__file__).resolve().parent.parent` 在函数体内,
# fixture 改不动 → pytest 跑时真 rmtree 老开发机 src/karma/ 子目录.
_CLEANUP_REPO_ROOT: Path = Path(__file__).resolve().parent.parent


def _cleanup_legacy_karma() -> None:
    """清掉 v0.15→v0.16 rename 残留 — 老 karma daemon / .pyc / 旧 CLI entry.

    Issue #12 真根因 (fyn1320068837-source 报): v0.16 rename karma→pinrule 时:
    1. 旧 `karma.daemon.server` 进程通过 .pyc 继续跑
    2. `.venv/bin/karma` 老 entry 还在但 import karma 已 broken
    3. `src/karma/__pycache__/*.pyc` 残留让 daemon 重启也能跑
    4. `~/.karma/daemon.{sock,err,log}` 持续被写, daemon.err 24MB

    这个函数 idempotent: 每次 init / install-hooks 起手自动跑, 检测到才提示 + 清.
    """
    import subprocess

    actions = []

    # 1) 检测 + kill 老 karma daemon 进程
    try:
        result = subprocess.run(
            ["pgrep", "-f", "karma.daemon.server"],
            capture_output=True, text=True, timeout=2,
        )
        pids = [p for p in result.stdout.strip().split() if p]
        for pid in pids:
            try:
                subprocess.run(["kill", "-9", pid], timeout=2, check=False)
                actions.append(f"  ✓ 杀掉老 karma daemon (PID {pid})")
            except Exception:
                actions.append(f"  ⚠ 老 karma daemon (PID {pid}) 杀不掉, 手动 `kill -9 {pid}`")
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass  # pgrep 缺 / 超时 — 跳过

    # 2) 删 .venv/bin/karma 老 entry (新 entry 是 pinrule)
    legacy_entry = Path(sys.prefix) / "bin" / "karma"
    if legacy_entry.exists():
        try:
            legacy_entry.unlink()
            actions.append(f"  ✓ 删老 CLI entry: {legacy_entry}")
        except OSError:
            actions.append(f"  ⚠ 老 entry {legacy_entry} 删不掉, 手动 `rm {legacy_entry}`")

    # 3) 删 src 树外的 karma 残留 __pycache__/*.pyc (现仓的 pinrule/__pycache__/bypass_karma.cpython-*.pyc 保留 — 它属 pinrule 不是老 karma)
    # v0.16.10: repo_root 走 module-level 常量让 test 真 mock (round-3 audit
    # 视角 9 #1: 之前 fixture docstring 说 mock 了 repo_root 但实际只 mock sys.prefix,
    # 贡献者建 src/karma/ 跑 pytest 真被 rmtree).
    src_karma = _CLEANUP_REPO_ROOT / "src" / "karma"
    if src_karma.exists():
        try:
            import shutil
            shutil.rmtree(src_karma)
            actions.append(f"  ✓ 删老源码残留: {src_karma}")
        except OSError as e:
            actions.append(f"  ⚠ {src_karma} 删不掉: {e}")

    # 4) 提示 ~/.karma daemon 产物 (不擅自删, 让 user 决定 — 可能含历史 violations)
    home_karma = Path.home() / ".karma"
    daemon_files = list(home_karma.glob("daemon.*")) if home_karma.exists() else []
    if daemon_files:
        actions.append(
            f"  ⚠ ~/.karma/ 还有 {len(daemon_files)} 个 daemon.* 文件 (老 daemon 残留产物);"
            f" 老 daemon 已 kill, 现在安全 rm: `rm ~/.karma/daemon.*`"
        )

    if actions:
        print("\n→ 检测到 karma → pinrule 升级残留, 清理:")
        for line in actions:
            print(line)


def cmd_init(minimal: bool | None = None) -> int:
    """创建 ~/.pinrule/ + 复制 sticky 模板 + config 模板。

    minimal=None（默认）→ 自动按系统语言偏好选：中文用户 7 条完整含
    chinese_plain check；非中文 / 检测不到 → 5 条精简（砍 chinese_plain）。
    minimal=True 强制装 5 条；minimal=False 强制装 7 条。

    跨平台检测见 `pinrule/locale_detect.py`（macOS 用 defaults read AppleLanguages,
    Linux 用 $LANG / $LC_ALL）。跟 VS Code / Slack 等 app 安装时自动选语言做法一致。
    """
    _cleanup_legacy_karma()  # v0.16.5+: kill 老 daemon + 删 src/karma + .venv/bin/karma
    PINRULE_DIR.mkdir(parents=True, exist_ok=True)

    auto_chose = ""
    if minimal is None:
        # v0.16.7: 双语对称 default — 中文跟英文用户都 default 装 full 7 条
        # (template 自己按 locale 选 zh/en, 但 rule count 对称). 老逻辑非中文
        # 用户只装 5 条 minimal, 英文用户拿到的功能比中文用户少, 不对等. 用户
        # 原话: "双语肯定是要自适配的" — 不只语言, rule set 也该对等.
        # `--minimal` flag 仍可显式装 5 条 cross-scenario universal.
        from pinrule.locale_detect import detect_user_language, is_chinese_user
        lang = detect_user_language()
        minimal = False  # 对称 default: 7 条
        if is_chinese_user():
            auto_chose = f"(detected locale {lang!r} → installing full 7 rules zh-localized with chinese-plain)"
        else:
            lang_label = lang or "unknown"
            auto_chose = f"(detected locale {lang_label!r} → installing full 7 rules en-localized; remove chinese-plain-no-jargon if not Chinese)"

    # v0.5.0 i18n: select template by system locale (zh / en)
    template = _select_rule_template(minimal)
    label = "minimal 5 cross-user-neutral" if minimal else "full 7 dev-scenario"

    rules_path = RULES_PATH
    if rules_path.exists():
        print(f"{rules_path.name} 已存在: {rules_path}")
    elif not template.exists():
        print(f"模板文件不存在: {template}", file=sys.stderr)
        return 1
    else:
        rules_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(template, rules_path)
        print(f"创建 {rules_path.name}: {rules_path} ({label}) {auto_chose}".rstrip())
    # config 模板
    config_path = PINRULE_DIR / "config.json"
    if config_path.exists():
        print(f"config.json 已存在: {config_path}")
    elif EXAMPLE_CONFIG.exists():
        shutil.copyfile(EXAMPLE_CONFIG, config_path)
        print(f"创建 config.json: {config_path}")
    print(f"编辑用: pinrule rule edit  /  vim {config_path}")
    if auto_chose:
        override_flag = "--no-minimal" if minimal else "--minimal"
        print(f"自动选不对？强制覆盖：pinrule init {override_flag}")

    # v0.5.16: 自动装 pinrule skill 到所有 backend (Claude Code / Codex / Cursor)
    # 让 /pinrule <NL> 流程在装机的客户端开箱即用 (v0.13.2 砍 Gemini 后剩这三家)
    skill_results = _install_pinrule_skill_multi_backend(force=False, backend_filter="all")
    if skill_results and skill_results[0][0] == "source":
        print(f"⚠ pinrule skill source 未找到 ({PINRULE_SKILL_SRC}) — 跳过自动装")
    else:
        for backend_name, dest, _changed, reason in skill_results:
            if reason == "installed":
                print(f"创建 [{backend_name}] pinrule skill: {dest}")
            elif reason == "up-to-date":
                pass  # init 时不刷屏报「已是最新」(可能跑过多次)
            elif reason == "exists-diff":
                new_path = dest.with_suffix(dest.suffix + ".new")
                print(f"⚠ [{backend_name}] pinrule skill 已存在跟当前版本不一致 — 新版写到 {new_path}")
        print("  → 在客户端里输 `/pinrule <自然语言描述>` 触发录入流程")

    # v0.9.9: 装完展示默认启用规则简要列表 — 让用户（自己跑 / 让 Agent 代装）
    # 一眼看到默认开了什么，知道下一步该改 / 删 / 加什么
    _print_default_rules_summary()
    _auto_install_hooks_for_detected_clients()
    _sync_cursor_rules_if_installed()
    return 0


def _cmd_audit_by_check(violations: list) -> int:
    """`pinrule audit --by-check` — 按 engine check 命中分布聚合 (v0.9.11)。

    设计：dogfood 数据驱动迭代，需要看「8 个 engine check 各自的真阳 / 假阳
    率」。当前 `pinrule audit` 视图按 rule_id 聚合（一条规则 多个 check 命中
    被混在一起）；by-check 视图按 trigger_key 聚合到 check 函数级别甚至
    sub-variant（如 evidence.commit / evidence.completion 分开）。

    数据源：复用现有 Violation.trigger_key 字段（v0.5.7 加的 i18n key，格式
    `check.<name>[.<sub>].trigger`）。**不需要 schema 变更** — 历史 jsonl 中
    没有 trigger_key 的行（keyword-only 命中）归到「keyword-only」桶。

    也是 `/pinrule` no-arg skill 默认输出 — 用户输 `/pinrule` 不带描述时 Agent
    跑 `pinrule audit --by-check` 把结果转述给用户，让用户看到 dogfood 数据
    分布。
    """
    from collections import Counter

    # 按 sub-variant 完整路径聚合（保留细粒度让作者看清 sub-check 分布）
    sub_counter: Counter[str] = Counter()
    # top-level check 名 → 总数（聚合所有 sub-variant）
    top_counter: Counter[str] = Counter()
    keyword_only = 0

    for v in violations:
        if not v.trigger_key:
            keyword_only += 1
            continue
        # trigger_key 格式: check.<name>[.<sub>...].trigger
        parts = v.trigger_key.split(".")
        if len(parts) < 3 or parts[0] != "check" or parts[-1] != "trigger":
            # 不识别格式 → 算 unknown engine
            sub_counter["unknown"] += 1
            top_counter["unknown"] += 1
            continue
        # check_name = parts[1]; sub-variant 在 parts[2..-1]
        top_name = parts[1]
        if len(parts) > 3:
            sub_name = ".".join(parts[1:-1])  # 含 top + sub
        else:
            sub_name = top_name
        sub_counter[sub_name] += 1
        top_counter[top_name] += 1

    total = len(violations)
    engine_total = total - keyword_only
    print(f"pinrule engine check 命中分布 (总 {total} 条违反):\n")

    if engine_total == 0:
        print("  (没有 engine check 命中 — 全部 violation 来自 keyword 兜底层)")
    else:
        # top-level 主表（让用户一眼看到 8 个 check 哪个多）
        print(f"按 check 函数聚合 ({engine_total} 条 engine 命中):")
        for name, n in top_counter.most_common():
            ratio = n / engine_total
            print(f"  {n:>4}× ({ratio*100:>3.0f}%) {name}")

        # sub-variant 细分（如 evidence.commit / evidence.completion 分开）
        # 仅当存在 sub-variant 时显示，避免跟主表重复
        has_subvariants = any("." in name for name in sub_counter)
        if has_subvariants:
            print(f"\n按 sub-variant 细分 ({engine_total} 条 engine 命中):")
            for name, n in sub_counter.most_common():
                ratio = n / engine_total
                print(f"  {n:>4}× ({ratio*100:>3.0f}%) {name}")

    if keyword_only:
        ratio = keyword_only / total
        print(f"\nkeyword-only 兜底命中 (无 engine check): {keyword_only}× ({ratio*100:.0f}%)")

    # v0.9.12 honesty caveat：v0.9.12 之前的 user_prompt_submit hook fallback 路径
    # 漏写 trigger_key 字段（v0.9.11 audit --by-check 暴露的真 bug），所以那段
    # 时期写入的 violation 即使是 engine check 真触发，也会被错归 keyword-only
    # 桶。v0.9.12 修了 hook 路径 + 加 regression test 锁住所有写 Violation 路径
    # 必须传 trigger_key。本视图统计混了老数据，**老 keyword-only 占比偏高是
    # 数据 bug 不是真行为**。要看准的 engine vs keyword-only 比例，只看 v0.9.12+
    # 写入的 violation。
    print(
        "\n注: v0.9.12 前历史 jsonl 可能漏 trigger_key 字段（hook 路径 bug），"
        "导致 engine check 真触发被错归 keyword-only。本视图未回填老数据"
        "（评测干净度），只对 v0.9.12+ 写入的 violation 分类准确。"
    )

    return 0


def _print_default_rules_summary() -> None:
    """`pinrule init` 末尾展示默认启用规则的简要列表 — Agent 代装的场景下，
    这段输出会被 Agent 转述给用户，让用户一眼看到默认开了什么规则。

    格式：每条 1 个 id + preference **首段**（split by 空行，到第一个空行为止）。
    比单纯首行（`split("\\n")[0]`）展示更完整 — 因为原作者把一句话写两行 visual
    wrap 时，首行会被砍成半句。首段保留一个完整意思单元（一句或一小段）。

    规则文本跟随用户安装时的 locale（中文用户装 zh 模板，preference 是中文；
    英文用户装 en 模板，preference 是英文）。i18n locale key 只覆盖 helper 的
    header 脚手架文字，不翻译规则内容本身。

    刻意不输出「下一步：跑 pinrule rule edit ...」这类指令 tip — 那会变成
    「让用户手动输指令」的 friction，跟 onboarding「Agent 代用户操作」目标相反。
    用户看到规则列表后想改，自然会跟 Agent 说「帮我改 X」，Agent 知道用
    `/pinrule` skill 或 `pinrule rule edit`。

    异常不阻塞 — init 末尾装到这里之前都已经成功，summary 失败不该让 init 退非 0。
    """
    from pinrule.i18n import tr
    try:
        rules = load_rules()
    except Exception:
        return
    if not rules:
        return
    print()
    print(tr("init.summary.header", count=len(rules), soft_max=MAX_RULES))
    for r in rules:
        # 首段 = split 第一个空行（"\n\n"）。preference 多段间用空行分隔
        # 一个完整意思单元；段内 visual wrap 多行属于同一段。
        first_paragraph = r.preference.strip().split("\n\n")[0]
        print(f"  ▸ [{r.id}]")
        for line in first_paragraph.split("\n"):
            print(f"    {line.strip()}")
    # footer：告知用户 token 成本上限 + 想增改规则的 in-chat 入口
    # `/pinrule <自然语言>` 是 slash command 在客户端对话框输入触发 skill 自然语言
    # 录入流程 — 不是 shell 命令，符合「不让用户手动开 terminal 输指令」原则
    print()
    print(tr("init.summary.footer"))


def cmd_rule_list() -> int:
    try:
        rules = load_rules()
    except RuleConfigError as e:
        print(f"配置错误: {e}", file=sys.stderr)
        return 1
    if not rules:
        print("没配置规则。运行 'pinrule init' 复制模板。")
        return 0
    print(f"pinrule 规则 ({len(rules)}/{MAX_RULES} 软上限, {HARD_MAX} 硬上限):\n")
    for i, r in enumerate(rules, 1):
        print(f"{i}. [{r.id}]")
        for line in r.preference.split("\n"):
            print(f"   {line}")
        print(f"   触发词: {', '.join(r.violation_keywords) if r.violation_keywords else '(无)'}")
        print()
    return 0


def cmd_rule_edit() -> int:
    if not RULES_PATH.exists():
        print("rules.json 不存在，先 'pinrule init'", file=sys.stderr)
        return 1
    editor = os.environ.get("EDITOR", "vim")
    subprocess.run([editor, str(RULES_PATH)])
    # 编辑后验证
    try:
        rules = load_rules()
        print(f"编辑成功，当前 {len(rules)} 条规则。")
    except RuleConfigError as e:
        print(f"⚠️ 编辑后配置错误: {e}", file=sys.stderr)
        return 1
    return 0


def cmd_rule_add(json_path: str | None = None, stdin_json: bool = False) -> int:
    """添加新 rule 到 rules.json — 测试通过才写入.

    用法:
    - pinrule rule add --from-json <file>  # 从 JSON 文件读
    - pinrule rule add --from-stdin        # 从 stdin 读 JSON (Claude Code skill 用)

    流程:
    1. 读 JSON 输入 (一条新 rule 的 dict, 跟 rules.json 内单条格式一致)
    2. Schema validate (用 pinrule.rule.load 一致的校验逻辑)
    3. 检测 id 是否跟现有 rule 重复
    4. 检测软上限 (10 条) / 硬上限 (12 条) 不超
    5. 如果含 violation_checks, 验证 check 函数在 REGISTRY 注册
    6. 追加到 rules.json + 写回
    7. 反馈: 优化成什么 / 通过测试 / 当前规则库总数 / 是否有冲突建议删改
    """
    import json
    from pinrule.checks import REGISTRY as CHECK_REGISTRY

    # Step 1: 读 input
    if stdin_json:
        raw = sys.stdin.read()
    elif json_path:
        p = Path(json_path)
        if not p.exists():
            print(f"❌ JSON 文件不存在: {json_path}", file=sys.stderr)
            return 1
        raw = p.read_text(encoding="utf-8")
    else:
        print(
            "用法: pinrule rule add --from-json <file>  或  --from-stdin\n"
            "建议: 在 Claude / Codex / Cursor 里发 '/pinrule <自然语言描述>' 让 Agent "
            "用 pinrule skill 优化结构后调本命令",
            file=sys.stderr,
        )
        return 1

    try:
        new_rule = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"❌ JSON 解析失败: {e}", file=sys.stderr)
        return 1

    # 支持 dict (单条) 或 list (多条, 取第一条)
    if isinstance(new_rule, list):
        if not new_rule:
            print("❌ JSON 是空 list", file=sys.stderr)
            return 1
        new_rule = new_rule[0]

    if not isinstance(new_rule, dict):
        print(f"❌ 期望 JSON 是 dict (一条 rule), 实际 {type(new_rule).__name__}", file=sys.stderr)
        return 1

    # Step 2: Schema validate (拼一个临时 list 复用 pinrule.rule.load 校验逻辑)
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as tmp:
        json.dump([new_rule], tmp, ensure_ascii=False, indent=2)
        tmp_path = Path(tmp.name)
    try:
        try:
            validated = load_rules(tmp_path)
        except RuleConfigError as e:
            print(f"❌ Schema 校验失败: {e}", file=sys.stderr)
            return 1
        if not validated:
            print("❌ Schema 校验后无 rule (空)", file=sys.stderr)
            return 1
        validated_rule = validated[0]
    finally:
        tmp_path.unlink(missing_ok=True)

    # Step 3: 加载现有 rules + 检测冲突
    try:
        existing = load_rules()
    except RuleConfigError as e:
        print(f"❌ 现有 rules.json 配置错误: {e}", file=sys.stderr)
        return 1

    existing_ids = {r.id for r in existing}
    if validated_rule.id in existing_ids:
        print(f"❌ 规则 id={validated_rule.id!r} 已存在 — 用 pinrule rule edit 修改或 pinrule rule remove 后再 add", file=sys.stderr)
        return 1

    # Step 4: 上限检查
    new_total = len(existing) + 1
    if new_total > HARD_MAX:
        print(f"❌ 超硬上限 {HARD_MAX} 条 (现有 {len(existing)} + 新 1 = {new_total})", file=sys.stderr)
        return 1
    over_soft = new_total > MAX_RULES

    # Step 5: 验证 violation_checks 函数存在 (如有)
    unknown_checks = [c for c in validated_rule.violation_checks if c not in CHECK_REGISTRY]
    if unknown_checks:
        print(
            f"❌ 未知 violation_checks 函数: {unknown_checks}\n"
            f"可用 check 函数: {sorted(CHECK_REGISTRY.keys())}",
            file=sys.stderr,
        )
        return 1

    # Step 6: 追加写回 rules.json
    try:
        raw_existing = json.loads(RULES_PATH.read_text(encoding="utf-8")) if RULES_PATH.exists() else []
    except json.JSONDecodeError as e:
        print(f"❌ 读 rules.json 失败: {e}", file=sys.stderr)
        return 1
    if not isinstance(raw_existing, list):
        raw_existing = []
    raw_existing.append(new_rule)
    RULES_PATH.parent.mkdir(parents=True, exist_ok=True)
    RULES_PATH.write_text(
        json.dumps(raw_existing, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    # Step 7: 反馈 (按用户要求: 优化后内容 / 已通过测试 / 当前总数 / 是否需删改)
    print(f"✓ 新规则已通过 pinrule schema 测试 + 写入 {RULES_PATH}")
    print()
    print(f"--- 新增规则 [{validated_rule.id}] ---")
    print(f"preference: {validated_rule.preference.strip()[:200]}")
    if validated_rule.violation_keywords:
        print(f"violation_keywords: {list(validated_rule.violation_keywords)}")
    if validated_rule.violation_checks:
        print(f"violation_checks: {list(validated_rule.violation_checks)} (engine-layer hook 判断已启用)")
    else:
        print("violation_checks: (无 — 仅头部注入提醒, 不开 engine-layer 实时拦截)")
    if validated_rule.force_block_exempt:
        print("force_block_exempt: true (豁免累积处罚)")
    print()
    print(f"📊 当前规则库: {new_total} 条 (软上限 {MAX_RULES} / 硬上限 {HARD_MAX})")
    if over_soft:
        print(f"⚠ 已超软上限 {MAX_RULES} 条 — Claude 注意力可能下降, 建议精简")
    print()
    print("📋 现有规则一览:")
    for r in existing + [validated_rule]:
        check_mark = "✓ engine" if r.violation_checks else "  preference-only"
        print(f"  - [{r.id}] {check_mark}")
    print()
    print("💡 建议: 看现有规则是否有重复 / 可合并 / 应该删除的, 用 pinrule rule remove <id> 调整")
    return 0


def cmd_rule_preview(json_path: str | None = None, stdin_json: bool = False) -> int:
    """预览新 rule 注入到头部的样子 — schema 校验 + 不写入.

    用 Claude Code skill 在让用户确认前调这个看效果.
    """
    import json

    if stdin_json:
        raw = sys.stdin.read()
    elif json_path:
        p = Path(json_path)
        if not p.exists():
            print(f"❌ JSON 文件不存在: {json_path}", file=sys.stderr)
            return 1
        raw = p.read_text(encoding="utf-8")
    else:
        print("用法: pinrule rule preview --from-json <file>  或  --from-stdin", file=sys.stderr)
        return 1

    try:
        new_rule = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"❌ JSON 解析失败: {e}", file=sys.stderr)
        return 1

    if isinstance(new_rule, list):
        if not new_rule:
            print("❌ JSON 是空 list", file=sys.stderr)
            return 1
        new_rule = new_rule[0]

    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as tmp:
        json.dump([new_rule], tmp, ensure_ascii=False, indent=2)
        tmp_path = Path(tmp.name)
    try:
        try:
            validated = load_rules(tmp_path)
        except RuleConfigError as e:
            print(f"❌ Schema 校验失败: {e}", file=sys.stderr)
            return 1
    finally:
        tmp_path.unlink(missing_ok=True)

    print("✓ Schema 校验通过")
    print()
    print("--- 注入到 prompt 头部的样子 ---")
    print(format_for_injection(validated))
    print("--- end ---")
    print()
    print("用 `pinrule rule add --from-json <file>` 写入 rules.json")
    return 0


def cmd_rule_remove(rule_id: str) -> int:
    """简单删除 — 读 JSON，过滤，写回。"""
    import json
    if not RULES_PATH.exists():
        print("rules.json 不存在", file=sys.stderr)
        return 1
    raw = json.loads(RULES_PATH.read_text(encoding="utf-8")) or []
    filtered = [item for item in raw if item.get("id") != rule_id]
    if len(filtered) == len(raw):
        print(f"没找到 id={rule_id!r}", file=sys.stderr)
        return 1
    RULES_PATH.write_text(
        json.dumps(filtered, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"已删除规则 {rule_id!r} ({len(filtered)} 条剩余)")
    return 0


def cmd_rule_import_pack(
    json_path: str,
    mode: str = "replace",
    backup: bool = False,
) -> int:
    """原子批量导入规则包 — Path B 场景切换主入口。

    用法:
      pinrule rule import-pack --from-json <file> [--mode replace|append] [--backup]

    流程 (engineering-first, 不让 Agent 串多条命令重新发明事务):
      1. 读现有 rules.json (or empty list)
      2. 读新 pack JSON (must be list of rule dicts)
      3. 全量 schema validate (走 pinrule.rule.load 一致逻辑)
      4. 检查 id 唯一性 / 软硬上限 / violation_checks 函数存在
      5. 写 backup (如果 --backup)
      6. 原子写: tmp 文件 + os.replace swap + fsync (任何一步挂 → rules.json 一字没动)

    --mode replace: 整库替换 (Path B 场景切换默认)
    --mode append: 追加到现有规则库 (会撞软上限 → 警告但仍写)
    """
    import json
    import os
    import tempfile
    from datetime import datetime
    from pinrule.checks import REGISTRY as CHECK_REGISTRY

    # Step 1: 读新 pack
    p = Path(json_path)
    if not p.exists():
        print(f"❌ JSON 文件不存在: {json_path}", file=sys.stderr)
        return 1
    try:
        new_pack = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"❌ JSON 解析失败: {e}", file=sys.stderr)
        return 1
    if not isinstance(new_pack, list):
        print(f"❌ pack 必须是 list of rules, 实际 {type(new_pack).__name__}", file=sys.stderr)
        return 1
    if not new_pack:
        print("❌ pack 是空 list — 拒绝写空规则库", file=sys.stderr)
        return 1

    # Step 2: 决定最终规则集 (replace 全量替换 / append 累加)
    if mode not in ("replace", "append"):
        print(f"❌ 未知 --mode {mode!r}, 必须是 'replace' or 'append'", file=sys.stderr)
        return 1
    if mode == "append":
        if RULES_PATH.exists():
            try:
                existing = json.loads(RULES_PATH.read_text(encoding="utf-8")) or []
            except json.JSONDecodeError as e:
                print(f"❌ 现有 rules.json 解析失败: {e}", file=sys.stderr)
                return 1
        else:
            existing = []
        final = existing + new_pack
    else:
        final = new_pack

    # Step 3: 全量 schema validate (写到 tmp 走 pinrule.rule.load)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as tmp:
        json.dump(final, tmp, ensure_ascii=False, indent=2)
        validate_path = Path(tmp.name)
    try:
        try:
            validated = load_rules(validate_path)
        except RuleConfigError as e:
            print(f"❌ Schema 校验失败: {e}", file=sys.stderr)
            print("   rules.json 一字没动 (atomic — 校验失败前不写)", file=sys.stderr)
            return 1
    finally:
        validate_path.unlink(missing_ok=True)

    # Step 4: id 唯一性 (load_rules 已经查) + violation_checks 函数存在
    for rule in validated:
        unknown = [c for c in rule.violation_checks if c not in CHECK_REGISTRY]
        if unknown:
            print(
                f"❌ 规则 {rule.id!r} 引用未注册 check 函数: {unknown}\n"
                f"   可用 check 函数: {sorted(CHECK_REGISTRY.keys())}\n"
                f"   rules.json 一字没动",
                file=sys.stderr,
            )
            return 1

    # Step 5: 写 backup (atomic 之前)
    # v0.18.1 fix (Codex A Round 1): 秒级 ts 可能同秒覆盖, 加 pid + random suffix
    # 真避免 backup file 同秒被另一个 pinrule import-pack 进程覆盖
    if backup and RULES_PATH.exists():
        import os as _os
        import secrets as _secrets
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        unique = f"{_os.getpid()}-{_secrets.token_hex(3)}"
        backup_path = RULES_PATH.parent / f"rules.json.before-scenario-{ts}-{unique}"
        backup_path.write_text(
            RULES_PATH.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        print(f"  备份: {backup_path}")

    # Step 6: 原子写 (NamedTemporaryFile 唯一 tmp + os.replace swap)
    # v0.18.1 fix (Codex A Round 1): 固定 tmp 文件名 `rules.json.tmp` 真有并发竞态 —
    # 两个 import-pack 同时跑会撞同一 tmp, 破坏 atomic 承诺. 改用 NamedTemporaryFile
    # 同目录唯一名 (跨 fs 不 atomic, 同目录才 atomic), delete=False 让 os.replace 真 rename.
    RULES_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(
        prefix=".rules.json.",
        suffix=".tmp",
        dir=str(RULES_PATH.parent),
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as tf:
            tf.write(json.dumps(final, ensure_ascii=False, indent=2) + "\n")
            tf.flush()
            os.fsync(tf.fileno())  # crash durability — 数据真落盘前不 replace
        os.replace(tmp_path, RULES_PATH)  # atomic 同目录 rename (POSIX + Windows)
    except OSError:
        # disk full / permission / 等 OS 错 → 清 tmp + 透传错误
        Path(tmp_path).unlink(missing_ok=True)
        raise

    # Step 7: 反馈
    n_final = len(validated)
    print(f"✓ Import pack 成功 ({mode} 模式) — 当前规则库 {n_final} 条")
    soft_max = MAX_RULES
    if n_final > soft_max:
        print(f"⚠ 已超软上限 {soft_max} 条 — Claude 注意力可能下降, 建议精简")
    return 0


def cmd_reset_session() -> int:
    """清所有 session-state JSON — Agent 注意力漂移实验重启。

    用法场景：观察「干净 session 起步」vs「累积 N turn 后」Agent 行为差异。
    不动 violations.jsonl（历史保留）+ 不动 rules.json / config.json。
    """
    from pinrule.session_state import DEFAULT_DIR as SS_DIR
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


def _check_file_last_commit_ts(sticky_id: str, sticky_list) -> int | None:
    """查 sticky 对应 check 文件最新 git commit 时间戳（dogfooding fix 时间线用）。

    用 rules.json 的 violation_checks 字段反查 REGISTRY[func_name].__module__
    → check 文件路径 → `git log -1 --format=%ct -- <path>`。

    返回 None 的情况：不在 pinrule 仓库 cwd / git 不可用 / sticky 没工程 check
    （只关键词层）。这是 dev 工具按 sticky #1「失败要响亮」fail open。
    """
    import subprocess
    from pathlib import Path
    target_sticky = next((s for s in sticky_list if s.id == sticky_id), None)
    if not target_sticky or not target_sticky.violation_checks:
        return None
    try:
        from pinrule.checks import REGISTRY
        check_fn = REGISTRY.get(target_sticky.violation_checks[0])
        if not check_fn:
            return None
        # __module__ 形如 'pinrule.checks.chinese_plain'
        module_path = check_fn.__module__.replace(".", "/") + ".py"
        # 找 pinrule 仓库根 — cwd 或父目录含 pyproject.toml + pinrule/ 子目录
        cwd = Path.cwd()
        for candidate in [cwd, *cwd.parents]:
            if (candidate / "pyproject.toml").exists() and (candidate / "pinrule").is_dir():
                check_file = candidate / module_path
                if not check_file.exists():
                    return None
                result = subprocess.run(
                    ["git", "log", "-1", "--format=%ct", "--", str(check_file)],
                    capture_output=True, text=True, cwd=str(candidate), timeout=2,
                )
                if result.returncode == 0 and result.stdout.strip():
                    return int(result.stdout.strip())
                return None
        return None
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def cmd_audit(
    with_fix_timeline: bool = False,
    output_format: str = "text",
    by_check: bool = False,
    days: int | None = None,
) -> int:
    """审计违反历史：每条 sticky 的 top 触发词 + 假阳嫌疑标记 + 本 session 漂移近况。

    假阳嫌疑：同一触发词命中 ≥ 5 次且占该 sticky 触发 ≥ 50% → 可能 pattern 过宽

    with_fix_timeline=True 时，调 git log 查每个 check 文件最新 commit ts，对比
    violation.ts 标记每条 violation 在 fix 前 / 后。dev 工具，仅 pinrule 仓库 cwd
    + git 可用时启用。

    output_format='md' 时输出 markdown 表格，方便粘贴到 PR / issue 分享
    dogfooding 数据。

    by_check=True 时切换到「engine check 命中分布」视图（v0.9.11+）：
    按 trigger_key 中的 check 名 + sub-variant 聚合命中次数，dogfood 数据驱动
    判断 8 个 engine check 各自的真阳 / 假阳率。这个视图也是 `/pinrule` no-arg
    skill 的默认输出 —— 用户输 `/pinrule` 不带描述时 Agent 跑这个给用户看。

    days=N 时仅统计最近 N 天 (v0.11.3+)：dogfood-driven 决策不被老数据稀释，
    特别是新 rule / engine 重设计 ship 后的 fresh 窗口效果评估。
    """
    violations = load_all()
    if days is not None:
        import time
        cutoff = time.time() - days * 86400
        violations = [v for v in violations if v.ts >= cutoff]
        if not violations:
            print(f"最近 {days} 天没违反记录。可以试更长窗口或不带 --days 看全量。")
            return 0
    if not violations:
        print("没有违反记录。先用 pinrule 一阵子再来 audit。")
        return 0
    if by_check:
        return _cmd_audit_by_check(violations)
    from collections import Counter
    # 按 sticky_id 分组，每组数 trigger 出现频次
    # v0.5.7: locale-agnostic 分组 — Violation.trigger_key 是 i18n key, 跨 zh/en
    # locale 稳定. trigger_key 缺 (老 jsonl 行) fallback 按 trigger 字面分组保兼容.
    # 显示用 trigger 字面（用户当前 locale 翻译过的），count 用 trigger_key 合并.
    by_sticky: dict[str, Counter] = {}
    # group_key 优先用 trigger_key, 没有 fallback trigger 字面
    # display_trigger: 同一 group_key 任取一个 trigger 字面做显示（同 key 字面已翻译，等价）
    display_trigger_by_key: dict[tuple[str, str], str] = {}
    for v in violations:
        group_key = v.trigger_key or v.trigger  # i18n key 或老格式字面
        by_sticky.setdefault(v.rule_id, Counter())[group_key] += 1
        display_trigger_by_key.setdefault((v.rule_id, group_key), v.trigger)
    is_md = output_format == "md"
    if is_md:
        print(f"# pinrule 违反审计 (总 {len(violations)} 条)\n")
    else:
        print(f"pinrule 违反审计 (总 {len(violations)} 条):\n")
    # fix 时间线 — 仅 with_fix_timeline=True 时算
    fix_ts_by_sticky: dict[str, int | None] = {}
    if with_fix_timeline:
        from pinrule.rule import load as load_sticky
        sticky_list = load_sticky()
        for sid in by_sticky:
            fix_ts_by_sticky[sid] = _check_file_last_commit_ts(sid, sticky_list)
    for sid in sorted(by_sticky, key=lambda s: -sum(by_sticky[s].values())):
        ctr = by_sticky[sid]
        total = sum(ctr.values())
        # fix 时间线：算这条 sticky 的 violations 多少在 check 最新 fix 前 / 后
        timeline_suffix = ""
        if with_fix_timeline:
            fix_ts = fix_ts_by_sticky.get(sid)
            if fix_ts:
                pre_fix = sum(1 for v in violations if v.rule_id == sid and v.ts < fix_ts)
                post_fix = total - pre_fix
                import time as _t
                fix_date = _t.strftime("%m-%d %H:%M", _t.localtime(fix_ts))
                timeline_suffix = (
                    f" [check 最新 fix {fix_date}: 修前 {pre_fix} / 修后 {post_fix}]"
                )
        # v0.4.25：字面多样性 — Agent 用多少种不同 snippet 末尾试探同一 sticky
        # 比例高 = 字面试探行为（学换字面不被检测拦不是改行为）
        diversity_suffix = ""
        if total >= 5:
            snippets_tail = {
                v.snippet[-40:] for v in violations if v.rule_id == sid
            }
            diversity = len(snippets_tail) / total
            if diversity >= 0.7:
                diversity_suffix = (
                    f" 🎭 字面试探 ({len(snippets_tail)}/{total}={diversity*100:.0f}%)"
                )
            elif diversity >= 0.4:
                diversity_suffix = f" ({len(snippets_tail)}/{total}={diversity*100:.0f}% 字面多样)"
        if is_md:
            print(f"### [{sid}] {total} 条触发{timeline_suffix}{diversity_suffix}\n")
            print("| 次数 | 占比 | 触发词 | 标记 |")
            print("|---|---|---|---|")
            for group_key, cnt in ctr.most_common(5):
                ratio = cnt / total
                mark = "⚠️ 可能假阳" if cnt >= 5 and ratio >= 0.5 else ""
                # v0.5.7: 显示用 trigger 字面（已 locale 翻译），count 按 trigger_key 合并
                display = display_trigger_by_key.get((sid, group_key), group_key)
                # markdown 表格 cell 转义 `|` 跟换行避免破表
                trigger_safe = display.replace("|", "\\|").replace("\n", " ")
                print(f"| {cnt} | {ratio*100:.0f}% | `{trigger_safe}` | {mark} |")
            print()
        else:
            print(f"[{sid}] {total} 条触发{timeline_suffix}{diversity_suffix}")
            for group_key, cnt in ctr.most_common(5):
                ratio = cnt / total
                mark = " ⚠️ 可能假阳" if cnt >= 5 and ratio >= 0.5 else ""
                display = display_trigger_by_key.get((sid, group_key), group_key)
                print(f"  {cnt:>3}× ({ratio*100:.0f}%) {display!r}{mark}")
            print()

    # 本 session 漂移近况（最近 N turn 内每条 sticky 累积次数）
    # 权威 source = session-state 目录最新 mtime 文件（不依赖 violations[-1] 推 — 当前
    # session 可能没产生违反，但仍是当前活跃 session）
    from pinrule.session_state import get_current_session_id
    current_session = get_current_session_id() or violations[-1].session_id
    current_turn = max((v.turn for v in violations if v.session_id == current_session), default=0)
    if current_turn > 0:
        turns_window = 10
        # v0.9.13 fix off-by-one: 跟 violations.recent_turns / count_recent_turns
        # 同步 — 「最近 N turn」字面意义匹配 N 个 turn 不是 N+1。原 `cur - window`
        # 让 audit 视图「漂移近况」段也多算 1 turn 跟 stop hook escalation 不一致。
        cutoff = current_turn - (turns_window - 1)
        recent = Counter(
            v.rule_id for v in violations
            if v.session_id == current_session and v.turn >= cutoff and v.turn > 0
        )
        sid_prefix = current_session[:8] if current_session else "?"
        if recent:
            print(
                f"=== 本 session={sid_prefix}... 最近 {turns_window} turn 漂移近况"
                f"（当前 turn={current_turn}）==="
            )
            for sid, n in recent.most_common():
                hot = " 🔥 高频" if n >= 3 else ""
                print(f"  {n:>3}× {sid}{hot}")
        else:
            print(
                f"=== 本 session={sid_prefix}... 最近 {turns_window} turn 无违反 ✓ "
                f"(当前 turn={current_turn}) ==="
            )
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
    total = Counter(v.rule_id for v in violations)
    week = Counter(v.rule_id for v in violations if v.ts >= week_ago)
    last_ts: dict[str, int] = {}
    for v in violations:
        if v.ts > last_ts.get(v.rule_id, 0):
            last_ts[v.rule_id] = v.ts

    # 本 session 维度 — 权威 source 是 session-state 目录最新 mtime 文件
    # （不再用 violations[-1].session_id 推，避免本 session 没产生违反时拉上 session 数据）
    from pinrule.session_state import get_current_session_id
    current_session = get_current_session_id() or (
        violations[-1].session_id if violations else ""
    )
    current_turn = max((v.turn for v in violations if v.session_id == current_session), default=0)
    turns_window = 5
    cutoff_turn = current_turn - turns_window
    current_session_count = Counter(
        v.rule_id for v in violations if v.session_id == current_session
    )
    recent_turns_count = Counter(
        v.rule_id for v in violations
        if v.session_id == current_session and v.turn >= cutoff_turn and v.turn > 0
    )
    historical_count = Counter(
        v.rule_id for v in violations if v.session_id != current_session
    )

    print(f"pinrule 违反统计 (总 {len(violations)} 条):")
    if current_session:
        # 顺便显示本 session stop_block_count（Stop hook 干预次数）
        from pinrule import session_state as ss
        try:
            # 只读快照，不需要 lock（atomic os.replace 保证不读到半更新 state）
            state = ss.read_state(current_session)
            if state.stop_block_count > 0:
                print(
                    f"本 session={current_session[:8]}... turn={current_turn}，"
                    f"Stop hook 已干预 {state.stop_block_count} 次（keep-pushing 不主动停）"
                )
            else:
                print(f"本 session={current_session[:8]}... turn={current_turn}")
        except Exception:
            print(f"本 session={current_session[:8]}... turn={current_turn}")
        print("「本 ses」=本 session 累积，「历史」=其他 session 累积，分开方便对照\n")
    else:
        print()
    print(
        f"{'rule_id':<35} {'本 ses':>7} {'历史':>6} "
        f"{'7d':>6} {'最近 ' + str(turns_window) + ' turn':>14} {'最近违反':>20}"
    )
    print("-" * 92)
    for sid, n in total.most_common():
        recent_str = datetime.fromtimestamp(last_ts.get(sid, 0)).strftime("%m-%d %H:%M")
        print(
            f"{sid:<35} {current_session_count.get(sid, 0):>7} {historical_count.get(sid, 0):>6} "
            f"{week.get(sid, 0):>6} {recent_turns_count.get(sid, 0):>14} {recent_str:>20}"
        )
    # 未触发的规则显示 ✓ 让作者看到正面证据（哪些规则没违反）
    try:
        all_rule_ids = {r.id for r in load_rules()}
        untriggered = sorted(all_rule_ids - set(total))
        if untriggered:
            print("\n=== 未触发的规则（✓ 没违反过）===")
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
        print(f"[{ts_str}] {v.rule_id} (触发: {v.trigger!r})")
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
                from pinrule.violations import extract_rule_id
                match_rule = sticky_filter is None or extract_rule_id(d) == sticky_filter
                match_trigger = trigger_filter is None or trigger_filter in d.get("trigger", "")
                if match_rule and match_trigger:
                    removed += 1
                    continue
            except _json.JSONDecodeError:
                pass
            keep_lines.append(line)
        if removed == 0:
            filters = []
            if sticky_filter:
                filters.append(f"rule={sticky_filter!r}")
            if trigger_filter:
                filters.append(f"trigger contains {trigger_filter!r}")
            print(f"没找到 {' AND '.join(filters)} 的违反记录。")
            return 0
        filter_desc = []
        if sticky_filter:
            filter_desc.append(f"rule={sticky_filter!r}")
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


def _pinrule_hook_entry_covers_event(
    backend, hooks: dict, event_name: str, hook_basename: str,
) -> bool:
    """True if hooks.json lists a pinrule wrapper for this event (Claude nested or Cursor flat)."""
    for entry in hooks.get(event_name, []):
        if not backend.is_pinrule_entry(entry):
            continue
        cmd = entry.get("command", "")
        if hook_basename in cmd:
            return True
        for nested in entry.get("hooks", []):
            if hook_basename in nested.get("command", ""):
                return True
    return False


def _unique_hook_basenames(backend) -> list[str]:
    """Wrapper files are materialized once even if native events share them."""
    return list(dict.fromkeys(backend.hook_events().values()))


def _backend_hooks_missing_reasons(backend) -> list[str]:
    """Return list of `<event>: <reason>` for any incomplete hook coverage.

    Empty list = backend fully installed. v0.16.12: also checks `os.access(X_OK)`
    so detection matches `cmd_doctor` (round-2 audit P1 #4 root cause — init
    silently re-installed hooks while doctor showed ✓ because doctor checked
    executable bit but the old `incomplete` flag didn't).
    """
    reasons: list[str] = []
    if not backend.client_installed():
        return reasons
    try:
        settings = backend.load_settings()
    except Exception as e:
        reasons.append(f"load_settings failed: {e}")
        return reasons
    hooks = settings.get("hooks", {})
    for event_name, hook_basename in backend.hook_events().items():
        wrapper = backend.hooks_dir() / f"pinrule_{hook_basename}.py"
        if not wrapper.exists():
            reasons.append(f"{event_name}: wrapper missing ({wrapper.name})")
            continue
        if not os.access(wrapper, os.X_OK):
            reasons.append(f"{event_name}: wrapper not executable ({wrapper.name})")
            continue
        if not _pinrule_hook_entry_covers_event(
            backend, hooks, event_name, hook_basename,
        ):
            reasons.append(f"{event_name}: {backend.settings_path().name} entry missing")
    return reasons


def _auto_install_hooks_for_detected_clients() -> None:
    """init 末尾：已装客户端 hook 不齐则 idempotent 跑 install-hooks all.

    v0.16.12: 打印**每 backend 真缺啥** 让 user 看到 reinstall 理由 (round-2
    audit P1 #4: 之前只 print "hook 未装全" 不说缺啥, user doctor 看 ✓ 不懂
    为啥 init 还要 reinstall).
    """
    from pinrule.backends import REGISTRY

    incomplete_by_backend = {
        b: _backend_hooks_missing_reasons(b)
        for b in REGISTRY.values()
        if b.client_installed()
    }
    incomplete_by_backend = {b: r for b, r in incomplete_by_backend.items() if r}
    if not incomplete_by_backend:
        return
    print("\n→ 检测到 hook 未装全, 真缺:")
    for backend, reasons in incomplete_by_backend.items():
        print(f"    [{backend.name}] {len(reasons)} 处不齐:")
        for reason in reasons[:5]:  # 限 5 条避免刷屏
            print(f"      - {reason}")
        if len(reasons) > 5:
            print(f"      ... +{len(reasons) - 5} more")
    print("→ 自动 install-hooks 给所有检测到的客户端补装…")
    cmd_install_hooks("all")


def _sync_cursor_rules_if_installed() -> None:
    from pinrule.backends import REGISTRY

    cursor = REGISTRY.get("cursor")
    if cursor is None or not cursor.client_installed():
        return
    from pinrule.cursor_rules_sync import sync_cursor_rules

    _written, logs = sync_cursor_rules(user=True)
    for line in logs:
        if line.strip():
            print(line)


def cmd_doctor() -> int:
    print(f"pinrule v{__version__} doctor")
    print(f"  PINRULE_DIR: {PINRULE_DIR} ({'存在' if PINRULE_DIR.exists() else '不存在'})")
    print(f"  rules.json: {RULES_PATH} ({'存在' if RULES_PATH.exists() else '不存在'})")
    print(f"  violations.jsonl: {VIOLATIONS_PATH} ({'存在' if VIOLATIONS_PATH.exists() else '不存在'})")
    config_path = PINRULE_DIR / "config.json"
    print(f"  config.json: {config_path} ({'存在' if config_path.exists() else '不存在 (用默认值)'})")
    # v0.5.16: skill 装机状态 — multi-backend, /pinrule <NL> 流程依赖
    print("  pinrule skill 装机 (多 backend):")
    from pinrule.backends import REGISTRY as _BACKENDS_FOR_SKILL
    src_text = PINRULE_SKILL_SRC.read_text(encoding="utf-8") if PINRULE_SKILL_SRC.exists() else None
    if src_text is None:
        print(f"    ⚠ source 未找到: {PINRULE_SKILL_SRC} (dev install 异常)")
    else:
        # v0.13.2: 砍 Gemini 后所有 backend 都 raw markdown (没 TOML 转换)
        for backend_name, backend in _BACKENDS_FOR_SKILL.items():
            for dest, _fmt in backend.skill_install_targets("pinrule"):
                expected = src_text
                if not dest.exists():
                    print(f"    [{backend_name}] {dest}: 未装")
                    continue
                try:
                    same = dest.read_text(encoding="utf-8") == expected
                except OSError:
                    print(f"    [{backend_name}] {dest}: 存在 (无法读)")
                    continue
                label = "✓ 最新" if same else "⚠ 跟当前版本不一致 (跑 `pinrule install-skill --force` 升级)"
                print(f"    [{backend_name}] {dest}: {label}")
    try:
        rules = load_rules()
        print(f"  规则加载: ✓ {len(rules)} 条")
        if len(rules) > MAX_RULES:
            print(f"    ⚠️ 超过软上限 {MAX_RULES} (但未达硬上限 {HARD_MAX})")
        exempt_ids = [r.id for r in rules if r.force_block_exempt]
        if exempt_ids:
            print(f"    force_block 豁免: {', '.join(exempt_ids)} "
                  "（累积违反不触发 Stop 强制 block）")
    except RuleConfigError as e:
        print(f"  规则加载: ✗ {e}")
        return 1

    # 显示当前生效配置
    from pinrule.config import load as _load_config
    cfg = _load_config()
    print("  当前生效配置:")
    for k, v in cfg.items():
        print(f"    {k}: {v}")

    # 显示活跃 session 简况（turn / stop_block 状态）
    # 权威 source = session-state 目录最新 mtime 文件，不依赖 violations[-1]
    # （当前 session 可能没产生违反但仍是活跃 session）
    from pinrule import session_state as _ss
    all_v = load_all()
    active_session = _ss.get_current_session_id() or (all_v[-1].session_id if all_v else None)
    if active_session:
        try:
            # 只读快照（doctor 信息展示，无并发风险）
            state = _ss.read_state(active_session)
            print(f"  当前活跃 session: {active_session}")
            print(f"    turn={state.turn_count}, stop_block={state.stop_block_count}, "
                  f"read={len(state.read_files)} files, edit={len(state.edit_files)} files")
        except Exception:
            pass

    # Stop hook trace 状态（仅当 PINRULE_DEBUG_TRACE 指向可读文件时显示）
    _trace_env = os.environ.get("PINRULE_DEBUG_TRACE")
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
    from pinrule.backends import REGISTRY as _BACKENDS
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
            wrapper = backend.hooks_dir() / f"pinrule_{hook_basename}.py"
            wrapper_ok = wrapper.exists() and os.access(wrapper, os.X_OK)
            in_settings = _pinrule_hook_entry_covers_event(
                backend, hooks, event_name, hook_basename,
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
        print("  → 运行 `pinrule install-hooks --backend all` 修复")

    # Codex hook trust 状态 reminder. v0.10.2+ pinrule 会按 Codex 0.130 源码算法
    # 给自己生成的 wrapper 写 trusted_hash；doctor 只能验证 pinrule 期望写入的 state
    # 是否存在且匹配，不能保证未来 Codex 没改算法。匹配时明确告诉用户无需逐个
    # approve；不匹配时再响亮提示去 TUI /hooks 复核。
    if "codex" in _BACKENDS:
        codex = _BACKENDS["codex"]
        if codex.client_installed():
            try:
                codex_settings = codex.load_settings()
                codex_has_pinrule_entry = any(
                    any(codex.is_pinrule_entry(e) for e in codex_settings.get("hooks", {}).get(ev, []))
                    for ev in codex.hook_events()
                )
            except Exception:
                codex_has_pinrule_entry = False
            if codex_has_pinrule_entry:
                hooks_dir = codex.hooks_dir()
                wrapper_basenames = list(dict.fromkeys(codex.hook_events().values()))
                trust_entries: dict[str, dict[str, str | bool]] = getattr(
                    codex, "codex_hook_state_entries", lambda _s: {},
                )(codex_settings)
                trusted_ok = False
                try:
                    import tomllib as _tomllib
                    from pinrule.paths import pinrule_install_root as _pir
                    config_path = _pir() / ".codex" / "config.toml"
                    config = _tomllib.loads(config_path.read_text(encoding="utf-8"))
                    state = config.get("hooks", {}).get("state", {})
                    trusted_ok = bool(trust_entries) and all(
                        state.get(key, {}) == value for key, value in trust_entries.items()
                    )
                except (OSError, ValueError):
                    trusted_ok = False
                print("")
                print("  Codex hook trust 状态:")
                print(f"     {len(codex.hook_events())} 个 event / "
                      f"{len(wrapper_basenames)} 个 wrapper 已配置.")
                if trusted_ok:
                    print("     trusted_hash 已写入并匹配 pinrule 当前 wrapper；正常不需要手动逐个 approve。")
                    print("     Codex 如升级 trust 算法，/hooks 可能显示 new/modified；届时再复核。")
                else:
                    all_ok = False
                    print("     ⚠️  trusted_hash 缺失或不匹配；Codex 可能不会运行 pinrule hooks。")
                    print("     请在 TUI `/hooks` 里复核并 approve pinrule wrapper。")
                print("")
                print("     ▶ 确认步骤:")
                print("        1. 启动 `codex`")
                print("        2. TUI 内输 `/hooks`")
                print("        3. 检查这些 wrapper 状态:")
                for basename in wrapper_basenames:
                    wrapper = hooks_dir / f"pinrule_{basename}.py"
                    print(f"           {wrapper}")
                print("")
                print("     ▶ 验证: codex 改一个没先 Read 的文件 → 应被 pinrule 🛑 拦.")

    if "cursor" in _BACKENDS and _BACKENDS["cursor"].client_installed():
        from pinrule.cursor_transcript_doctor import cursor_transcript_doctor_lines

        for line in cursor_transcript_doctor_lines():
            if line.strip():
                print(line)
    return 0 if all_ok else 1


def _install_to_backend(backend) -> int:
    """单 backend 装机流程：写 wrapper + 备份 + 改 settings + pre_install_setup。"""
    from pinrule.backends._base import SettingsParseError

    print(f"\n→ {backend.display_name}（{backend.name}）")

    # backend 特有的前置步骤（如 Codex 启用 features.hooks）
    for step in backend.pre_install_setup():
        print(f"  {step}")

    hooks_dir = backend.hooks_dir()
    hooks_dir.mkdir(parents=True, exist_ok=True)
    pinrule_python = sys.executable
    for hook_basename in _unique_hook_basenames(backend):
        wrapper = hooks_dir / f"pinrule_{hook_basename}.py"
        # v0.16.18: wrapper 起手 force UTF-8 stdio. Windows zh-CN console 默认
        # GBK strict 让 hook 输出的中文 reason + emoji 真乱码 (`\U...` 字面 +
        # `??`), 注入回 AI 客户端的 permissionDecisionReason 直接破坏.
        wrapper.write_text(
            f"#!{pinrule_python}\n"
            f"# pinrule {hook_basename} hook wrapper (auto-generated)\n"
            f"# python: {pinrule_python}\n"
            f"import sys\n"
            f"from pinrule._io_encoding import force_utf8_stdio\n"
            f"force_utf8_stdio()\n"
            f"sys.exit(__import__('pinrule.hooks.{hook_basename}', fromlist=['main']).main())\n"
        )
        wrapper.chmod(0o755)
        print(f"  生成: {wrapper}")
    old_pr = hooks_dir / "pinrule_post_response.py"
    if old_pr.exists():
        old_pr.unlink()
        print(f"  删除旧版: {old_pr}")

    # 备份原 settings — 真 pristine "装 pinrule 前" 内容只第一次写, 之后保留.
    # v0.16.18 真根因修: 之前 L1424 `if settings_path.exists()` 让 fresh install
    # 跳过整段 backup, 然后 init 自动 fire install-hooks 写出 pinrule 化 settings.
    # 用户后续手工 install-hooks 看到 settings.json 真存在 (但已 pinrule 化!),
    # backup_path 不存在条件成立 → 真把 pinrule 化版本当 pristine 备份了.
    # 卸载时 `cp settings.json.before-pinrule settings.json` 恢复的是 pinrule 化
    # 状态, 真 uninstall path 断. fresh install 必须写 empty marker 表示真 empty
    # pre-pinrule state.
    settings_path = backend.settings_path()
    backup_path = backend.settings_backup_path()
    if not backup_path.exists():
        if settings_path.exists():
            backup_path.write_text(settings_path.read_text(encoding="utf-8"), encoding="utf-8")
            print(f"  备份原 settings: {backup_path}")
        else:
            # fresh install — primary backup 写空标记真 pristine 状态 (no pre-pinrule settings)
            backup_path.write_text("", encoding="utf-8")
            print(f"  备份原 settings: {backup_path} (装 pinrule 前真无 settings 文件)")
    if settings_path.exists():
        ts_backup = settings_path.with_suffix(
            settings_path.suffix + f".before-pinrule.{int(time.time())}"
        )
        ts_backup.write_text(settings_path.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"  本次备份: {ts_backup}")

    try:
        settings = backend.load_settings()
    except SettingsParseError as e:
        print(f"\n{e}", file=sys.stderr)
        return 1

    # 移除旧 pinrule entry（idempotent + 保留他人 hook）
    hooks = settings.get("hooks", {})
    for event in list(hooks.keys()):
        hooks[event] = [e for e in hooks[event] if not backend.is_pinrule_entry(e)]
        if not hooks[event]:
            del hooks[event]

    # 加新 pinrule entry
    settings.setdefault("hooks", {})
    for event_name, hook_basename in backend.hook_events().items():
        settings["hooks"].setdefault(event_name, [])
        settings["hooks"][event_name].append(
            backend.build_event_entry(hook_basename, event_name)
        )

    backend.save_settings(settings)
    print(f"  已配置 {settings_path}（{len(backend.hook_events())} 个 hook event）")

    # v0.9.17 L1: backend 装完后的响亮警示（如 Codex TUI /hooks 审批步骤）.
    # 默认 backend 返回空 list 不打印额外内容; Codex override 返回完整审批框.
    # 用 getattr 兜底避免老 Backend 实现没这方法时抛 AttributeError.
    post_msg: list[str] = getattr(backend, "post_install_message", lambda: [])()
    for line in post_msg:
        print(line)
    return 0


def cmd_sync_cursor_visibility() -> int:
    """Sync pinrule rule ids into paths Cursor Composer actually loads (not hooks stdout)."""
    from pinrule.cursor_visibility import sync_all_visibility_layers

    for line in sync_all_visibility_layers():
        print(line)
    print("\n✓ 可见性同步完成 — Reload Cursor，新开 Composer，问「列出 pinrule 规则 id」")
    return 0


def cmd_sync_cursor_rules() -> int:
    """把当前 rules.json 同步到 Cursor native alwaysApply rule 文件."""
    from pinrule.cursor_rules_sync import sync_cursor_rules

    written, logs = sync_cursor_rules(user=True, project_root=Path.cwd())
    for line in logs:
        print(line)
    if not written:
        return 1
    print("✓ Cursor rules 已同步 — Reload Cursor 后新 Composer 起手应可见 pinrule 默契")
    return 0


def cmd_install_hooks(backend_name: str = "all") -> int:
    """生成 wrapper + 自动写客户端配置（idempotent + 备份 + 保留他人 hook）。

    backend_name:
      - "all"（默认 v0.16.1+）：装本机检测到的所有客户端 (Claude / Codex / Cursor)
      - "claude-code": 只装 Claude
      - "codex": 只装 Codex
      - "cursor": 只装 Cursor
    """
    _cleanup_legacy_karma()  # v0.16.5+: 双保险 (user 跳过 init 直接 install-hooks 时也 cleanup)
    from pinrule.backends import REGISTRY, detect_installed_backends

    if backend_name == "all":
        installed = detect_installed_backends()
        if not installed:
            print("没检测到任何支持的 AI 编程客户端（claude / codex）", file=sys.stderr)
            return 1
        print(f"检测到客户端：{', '.join(installed)}")
        backends_to_install = [REGISTRY[name] for name in installed]
    elif backend_name in REGISTRY:
        backend = REGISTRY[backend_name]
        # 显式 backend 也必须查客户端是否实际装 — sub-agent 排查发现的 P1 bug：
        # 同事没装 Claude Code 跑 `pinrule install-hooks` 默认装 claude-code 静默
        # 写 ~/.claude/settings.json 完全无反馈，他不知道 hook 不会触发。
        # 修：检测不到客户端时报错 + 提示，要绕过装可用 --force（暂未加）。
        if not backend.client_installed():
            print(
                f"没检测到 {backend.display_name} 客户端在本机（PATH 上没对应"
                f"命令也没 {backend.settings_path().parent} 目录）。\n"
                f"pinrule 不装 hook 配置避免静默写。要么先装 {backend.display_name}，"
                f"要么换 `--backend all` 装所有检测到的客户端。",
                file=sys.stderr,
            )
            return 1
        backends_to_install = [backend]
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
    """单 backend 卸装：删 wrapper + 从 settings 移除 pinrule entry。"""
    print(f"\n→ {backend.display_name}（{backend.name}）")
    hooks_dir = backend.hooks_dir()
    n = 0
    for hook_basename in _unique_hook_basenames(backend) + ["post_response"]:
        wrapper = hooks_dir / f"pinrule_{hook_basename}.py"
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
            hooks[event] = [e for e in hooks[event] if not backend.is_pinrule_entry(e)]
            if not hooks[event]:
                del hooks[event]
        after = sum(len(e) for e in settings.get("hooks", {}).values())
        if before > after:
            backend.save_settings(settings)
            print(f"  从 {settings_path.name} 移除 {before - after} 个 pinrule entry")
    print(f"  删除 {n} 个 wrapper")
    return 0


def cmd_uninstall_hooks(backend_name: str = "all") -> int:
    """卸 pinrule hook（默认 'all' v0.16.1+ — 跟 install 对称）。"""
    from pinrule.backends import REGISTRY, detect_installed_backends

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
    """从 CLI args 解析 --backend <name>，默认 'all' (v0.16.1+ — 三家全装).

    支持 '--backend codex' / '--backend claude-code' / '--backend cursor' / '--backend all'。
    不带 --backend 默认 'all' 装本机检测到的所有客户端 — 跟用户 mental model
    (装 pinrule 就是三家全 cover) 一致, 避免 silent gap (老 default 'claude-code'
    导致 Codex/Cursor 用户敲 `pinrule install-hooks` 以为装好实际 0 触发).
    """
    if "--backend" not in args:
        return "all"
    idx = args.index("--backend")
    if idx + 1 >= len(args):
        return "all"
    return args[idx + 1]


def main(argv: list[str] | None = None) -> int:
    # v0.16.18: force UTF-8 stdio. Windows zh-CN console default = GBK strict
    # encoding crashes on `▸` (U+25B8) / `🛑` 类字符. 真用户 dogfood issue
    # 报的 `pinrule init` UnicodeEncodeError 真根因. 重复 import 没副作用.
    from pinrule._io_encoding import force_utf8_stdio
    force_utf8_stdio()

    argv = argv if argv is not None else sys.argv[1:]
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if argv[0] == "--version":
        print(f"pinrule v{__version__}")
        return 0

    cmd = argv[0]
    args = argv[1:]

    # v0.16.6: 子命令 --help / -h 真打 top-level help, 不再被吃当真命令执行
    # (历史 footgun: `pinrule install-hooks --help` 会真装 hooks 不是打 help).
    if "--help" in args or "-h" in args:
        print(__doc__)
        return 0

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
        with_timeline = "--with-fix-timeline" in args
        by_check = "--by-check" in args
        output_format = "md" if "--format" in args and args[args.index("--format") + 1] == "md" else "text"
        # v0.11.3: --days N 过滤窗口 — dogfood 决策不被老数据稀释
        days = None
        if "--days" in args:
            try:
                days = int(args[args.index("--days") + 1])
                if days <= 0:
                    print(f"--days 必须 > 0, 收到 {days}", file=sys.stderr)
                    return 2
            except (IndexError, ValueError):
                print("--days 后必须跟正整数 (例: --days 7)", file=sys.stderr)
                return 2
        return cmd_audit(
            with_fix_timeline=with_timeline,
            output_format=output_format,
            by_check=by_check,
            days=days,
        )
    if cmd in ("reset", "reset-session"):
        return cmd_reset_session()
    if cmd == "sync-cursor-rules":
        return cmd_sync_cursor_rules()
    if cmd == "sync-cursor-visibility":
        return cmd_sync_cursor_visibility()
    if cmd == "install-hooks":
        return cmd_install_hooks(backend_name=_parse_backend_arg(args))
    if cmd == "install-skill":
        backend_arg = _parse_backend_arg(args) if "--backend" in args else None
        # _parse_backend_arg 默认返回 "claude-code" 我们要 None 走 "all" 路径
        if backend_arg == "claude-code" and "--backend" not in args:
            backend_arg = None
        return cmd_install_skill(force="--force" in args, backend=backend_arg)
    if cmd == "uninstall-hooks":
        return cmd_uninstall_hooks(backend_name=_parse_backend_arg(args))
    if cmd == "uninstall":
        # `pinrule uninstall` 一键卸所有 backend 的 alias — 陌生用户不用记
        # `uninstall-hooks --backend all` 长串
        return cmd_uninstall_hooks(backend_name="all")
    if cmd == "sticky":
        # v0.6.0 起删除 `pinrule sticky` alias — v0.5.0 起一直在打 DeprecationWarning,
        # 兑现废弃契约. 给一行「你是不是想用 pinrule rule」hint 救肌肉记忆.
        print(
            "❌ unknown command: 'sticky' (removed in v0.6.0).\n"
            "💡 你是不是想用 `pinrule rule`？ (sticky → rule 改名见 v0.5.0 CHANGELOG)",
            file=sys.stderr,
        )
        return 1
    if cmd == "rule":
        if not args:
            print(f"Usage: pinrule {cmd} <list|edit|remove|add|preview|import-pack>", file=sys.stderr)
            return 1
        if args[0] == "list":
            return cmd_rule_list()
        if args[0] == "edit":
            return cmd_rule_edit()
        if args[0] == "remove":
            if len(args) < 2:
                print(f"Usage: pinrule {cmd} remove <id>", file=sys.stderr)
                return 1
            return cmd_rule_remove(args[1])
        if args[0] == "add":
            # pinrule rule add --from-json <file>  或  --from-stdin
            json_path = None
            stdin_json = False
            sub = args[1:]
            if "--from-stdin" in sub:
                stdin_json = True
            elif "--from-json" in sub:
                idx = sub.index("--from-json")
                if idx + 1 < len(sub):
                    json_path = sub[idx + 1]
            return cmd_rule_add(json_path=json_path, stdin_json=stdin_json)
        if args[0] == "preview":
            json_path = None
            stdin_json = False
            sub = args[1:]
            if "--from-stdin" in sub:
                stdin_json = True
            elif "--from-json" in sub:
                idx = sub.index("--from-json")
                if idx + 1 < len(sub):
                    json_path = sub[idx + 1]
            return cmd_rule_preview(json_path=json_path, stdin_json=stdin_json)
        if args[0] == "import-pack":
            # pinrule rule import-pack --from-json <file> [--mode replace|append] [--backup]
            json_path = None
            mode = "replace"
            do_backup = False
            sub = args[1:]
            if "--from-json" in sub:
                idx = sub.index("--from-json")
                if idx + 1 < len(sub):
                    json_path = sub[idx + 1]
            if "--mode" in sub:
                idx = sub.index("--mode")
                if idx + 1 < len(sub):
                    mode = sub[idx + 1]
            if "--backup" in sub:
                do_backup = True
            if not json_path:
                print(
                    "Usage: pinrule rule import-pack --from-json <file> "
                    "[--mode replace|append] [--backup]",
                    file=sys.stderr,
                )
                return 1
            return cmd_rule_import_pack(json_path=json_path, mode=mode, backup=do_backup)
        print(f"未知 {cmd} 子命令: {args[0]}", file=sys.stderr)
        return 1
    if cmd == "violations":
        if not args:
            print("Usage: pinrule violations <recent|clear>", file=sys.stderr)
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
    # v0.16.10: 之前打整页 help 把错误信息淹没. 现单行错误 + 一行 hint, 让用户
    # 一眼看到 typo, 想看完整 usage 自己跑 `pinrule` (无参) — round-3 视角 6 #5.
    print(f"未知命令: {cmd!r}\n💡 跑 `pinrule` (无参) 看完整 usage", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
