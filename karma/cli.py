"""karma CLI — rule 管理 + 违反观察 + hook 安装。

Usage:
    karma init [--minimal|--no-minimal]
                                   创建 ~/.claude/karma/ + 复制 rules/config 模板
                                   默认按系统语言偏好自动选：中文 → 7 条完整；
                                   非中文/检测不到 → 5 条精简（砍 chinese_plain）
                                   --minimal / --no-minimal 强制覆盖
    karma install-hooks [--backend claude-code|codex|gemini-cli|all]
                                   自动配置 hooks（默认 claude-code 向后兼容）
                                   codex 会同时启用 features.hooks；
                                   gemini-cli 写 ~/.gemini/settings.json；
                                   all 装本机检测到的所有 AI 编程客户端
    karma install-skill [--force]  装 karma-rule Claude Code skill 到 ~/.claude/skills/
                                   (karma init 已自动跑一次, 老用户 / skill 升级时用)
                                   已存在且不同 → 写 .md.new 文件让用户对比, 不覆盖；
                                   --force 强制覆盖（会丢用户对 skill 的本地改动）
    karma uninstall-hooks [--backend ...]   移除 hook 配置
    karma uninstall                一键卸所有 backend（= uninstall-hooks --backend all）
    karma doctor                   检查环境 + hook 装机 + 当前生效 config

    karma rule list                列出所有 rule 规则
    karma rule edit                用 $EDITOR 编辑 rules.yaml
    karma rule remove <id>         移除某条
    karma rule add --from-yaml <file>       从 yaml 文件追加一条新 rule
    karma rule add --from-stdin             从 stdin 读 yaml 追加 (Claude Code skill 用)
    karma rule preview --from-yaml <file>   预览注入头部样子 (不写入)
    karma rule preview --from-stdin         预览 stdin yaml (不写入)

    karma stats                    每条规则违反计数（含本 session 最近 5 turn）
    karma violations recent [N]    最近 N 条违反详情（默认 20）
    karma violations clear         清空违反历史（需确认）
    karma audit                    审计 — 每条 rule top 触发词 + 假阳嫌疑标记
    karma reset                    清 session-state（漂移实验重启）

提示: Claude Code 用户可发 `/karma rule <自然语言描述>` 让 Agent 自动用
karma skill 优化结构后调 `karma rule add --from-stdin` 写入。
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
from karma.rule import DEFAULT_PATH as RULES_PATH
from karma.rule import HARD_MAX, MAX_RULES, RuleConfigError, format_for_injection
from karma.rule import load as load_rules
from karma.violations import DEFAULT_PATH as VIOLATIONS_PATH
from karma.violations import load_all

from karma.paths import karma_home

KARMA_DIR = karma_home()
_DATA_DIR = Path(__file__).parent.parent / "data"
EXAMPLE_RULES_EN = _DATA_DIR / "rules.dev.example.yaml"        # English default
EXAMPLE_RULES_ZH = _DATA_DIR / "rules.dev.example.zh.yaml"     # 中文
EXAMPLE_RULES_MINIMAL_EN = _DATA_DIR / "rules.dev.minimal.example.yaml"
EXAMPLE_RULES_MINIMAL_ZH = _DATA_DIR / "rules.dev.minimal.example.zh.yaml"
EXAMPLE_CONFIG = _DATA_DIR / "config.example.yaml"
# v0.5.16: karma skill source — Markdown source of truth; auto-installed to
# all detected backends with format conversion (Markdown → TOML for Gemini commands path).
_SKILLS_DIR = Path(__file__).parent.parent / "skills"
KARMA_SKILL_SRC = _SKILLS_DIR / "karma" / "SKILL.md"


def _select_rule_template(minimal: bool) -> Path:
    """按系统语言 detect 选模板（中文用户 .zh.yaml / 其他英文 default）。"""
    from karma.locale_detect import is_chinese_user
    if is_chinese_user():
        return EXAMPLE_RULES_MINIMAL_ZH if minimal else EXAMPLE_RULES_ZH
    return EXAMPLE_RULES_MINIMAL_EN if minimal else EXAMPLE_RULES_EN


def _write_skill_target(
    src_text: str,
    dest: Path,
    content_format: str,
    force: bool = False,
) -> tuple[bool, str]:
    """装一份 skill 到单个目标路径, 按 format 决定 Markdown 直写还是 TOML 转换.

    冲突处理 (sticky #1 不覆盖用户改动):
    - 不存在 → 写, 返回 (True, "installed")
    - 已存在 + 内容一致 → skip, 返回 (False, "up-to-date")
    - 已存在 + 内容不同 + force=False → 写 .new 兄弟文件, 返回 (False, "exists-diff")
    - 已存在 + 内容不同 + force=True → 覆盖, 返回 (True, "force-overwritten")
    """
    if content_format == "toml":
        from karma.skill_packaging import markdown_to_toml
        body = markdown_to_toml(src_text)
    else:
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


def _install_karma_skill_multi_backend(
    force: bool = False,
    backend_filter: str | None = None,
) -> list[tuple[str, Path, bool, str]]:
    """装 karma skill 到所有 (或指定) detected backend.

    backend_filter: None / "all" → 所有 detected backend
                    "claude-code" / "codex" / "gemini-cli" → 单独装该 backend
                    (不要求 backend 在本机已装 — 用户可能想预装等以后用客户端时生效)

    返回 [(backend_name, dest_path, changed, reason), ...] 让 caller 汇报.
    """
    if not KARMA_SKILL_SRC.exists():
        return [("source", KARMA_SKILL_SRC, False, "source-missing")]

    src_text = KARMA_SKILL_SRC.read_text(encoding="utf-8")
    from karma.backends import REGISTRY as _BACKENDS

    if backend_filter in (None, "all"):
        backends_to_install = list(_BACKENDS.items())
    elif backend_filter in _BACKENDS:
        backends_to_install = [(backend_filter, _BACKENDS[backend_filter])]
    else:
        return [("error", Path(), False, f"unknown-backend ({backend_filter})")]

    out: list[tuple[str, Path, bool, str]] = []
    for name, backend in backends_to_install:
        for dest, fmt in backend.skill_install_targets("karma"):
            changed, reason = _write_skill_target(src_text, dest, fmt, force=force)
            out.append((name, dest, changed, reason))
    return out



def cmd_install_skill(force: bool = False, backend: str | None = None) -> int:
    """装 karma skill 到所有 / 指定 backend (多 backend 一波装).

    flow:
    - karma init 已自动调一次, 已 init 老用户跑 karma install-skill 补装
    - skill 升级 (clarity audit 等) 用 --force 覆盖
    - --backend <name> 单独装某家 (claude-code / codex / gemini-cli)
    """
    results = _install_karma_skill_multi_backend(force=force, backend_filter=backend)

    if not results:
        print("❌ 没找到任何 backend", file=sys.stderr)
        return 1
    first_name = results[0][0]
    if first_name == "source":
        print(f"❌ source-missing: {KARMA_SKILL_SRC}", file=sys.stderr)
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
                print(f"✓ [{backend_name}] 装 karma skill: {dest}")
            elif reason == "up-to-date":
                print(f"✓ [{backend_name}] karma skill 已是最新: {dest}")
            elif reason == "force-overwritten":
                print(f"✓ [{backend_name}] 强制覆盖: {dest}")
            elif reason == "exists-diff":
                new_path = dest.with_suffix(dest.suffix + ".new")
                print(f"⚠ [{backend_name}] {dest} 已存在跟当前 karma 版本不一致")
                print(f"  → 新版写到 {new_path}")
                print("  → diff 对比或 karma install-skill --force 覆盖 (会丢用户改动)")
            else:
                print(f"? [{backend_name}] {dest}: {reason}")
    print()
    print("用法: 各 backend 输 `/karma <自然语言描述>` 触发 (Codex 用 `/skills` menu 或 `$karma <NL>`)")
    return 0


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
        # Auto-select by system locale (cross-platform: macOS defaults /
        # Linux $LANG / Windows GetUserDefaultUILanguage / POSIX fallback)
        from karma.locale_detect import detect_user_language, is_chinese_user
        lang = detect_user_language()
        if is_chinese_user():
            minimal = False
            auto_chose = f"(detected locale {lang!r} → installing full 7 rules with chinese_plain)"
        else:
            minimal = True
            lang_label = lang or "unknown"
            auto_chose = f"(detected locale {lang_label!r} → installing minimal 5 rules)"

    # v0.5.0 i18n: select template by system locale (zh / en)
    template = _select_rule_template(minimal)
    label = "minimal 5 cross-user-neutral" if minimal else "full 7 dev-scenario"

    # v0.5.0 migration: 检测旧 sticky.yaml 自动迁移到 rules.yaml
    # RULES_PATH 来自 karma.rule.DEFAULT_PATH (fallback 优先 rules.yaml)
    # 测试 monkeypatch RULES_PATH 仍生效
    rules_path = RULES_PATH
    legacy_sticky_path = rules_path.parent / "sticky.yaml"
    if legacy_sticky_path.exists() and not rules_path.exists() and rules_path.name == "rules.yaml":
        # 旧用户 — migrate sticky.yaml → rules.yaml + backup 老文件
        rules_path.parent.mkdir(parents=True, exist_ok=True)
        backup_path = legacy_sticky_path.with_suffix(".yaml.bak")
        shutil.copyfile(legacy_sticky_path, rules_path)
        legacy_sticky_path.rename(backup_path)
        print(f"⚠ 检测到旧 sticky.yaml — 自动迁移到 {rules_path}")
        print(f"  老文件备份到: {backup_path}")
    elif rules_path.exists():
        print(f"{rules_path.name} 已存在: {rules_path}")
    elif not template.exists():
        print(f"模板文件不存在: {template}", file=sys.stderr)
        return 1
    else:
        rules_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(template, rules_path)
        print(f"创建 {rules_path.name}: {rules_path} ({label}) {auto_chose}".rstrip())
    # config 模板
    config_path = KARMA_DIR / "config.yaml"
    if config_path.exists():
        print(f"config.yaml 已存在: {config_path}")
    elif EXAMPLE_CONFIG.exists():
        shutil.copyfile(EXAMPLE_CONFIG, config_path)
        print(f"创建 config.yaml: {config_path}")
    print(f"编辑用: karma rule edit  /  vim {config_path}")
    if auto_chose:
        override_flag = "--no-minimal" if minimal else "--minimal"
        print(f"自动选不对？强制覆盖：karma init {override_flag}")

    # v0.5.16: 自动装 karma skill 到所有 backend (Claude Code / Codex / Gemini)
    # 让 /karma <NL> 流程在装机的客户端开箱即用
    skill_results = _install_karma_skill_multi_backend(force=False, backend_filter="all")
    if skill_results and skill_results[0][0] == "source":
        print(f"⚠ karma skill source 未找到 ({KARMA_SKILL_SRC}) — 跳过自动装")
    else:
        for backend_name, dest, _changed, reason in skill_results:
            if reason == "installed":
                print(f"创建 [{backend_name}] karma skill: {dest}")
            elif reason == "up-to-date":
                pass  # init 时不刷屏报「已是最新」(可能跑过多次)
            elif reason == "exists-diff":
                new_path = dest.with_suffix(dest.suffix + ".new")
                print(f"⚠ [{backend_name}] karma skill 已存在跟当前版本不一致 — 新版写到 {new_path}")
        print("  → 在客户端里输 `/karma <自然语言描述>` 触发录入流程")

    # v0.9.9: 装完展示默认启用规则简要列表 — 让用户（自己跑 / 让 Agent 代装）
    # 一眼看到默认开了什么，知道下一步该改 / 删 / 加什么
    _print_default_rules_summary()
    return 0


def _cmd_audit_by_check(violations: list) -> int:
    """`karma audit --by-check` — 按 engine check 命中分布聚合 (v0.9.11)。

    设计：dogfood 数据驱动迭代，需要看「8 个 engine check 各自的真阳 / 假阳
    率」。当前 `karma audit` 视图按 rule_id 聚合（一条规则 多个 check 命中
    被混在一起）；by-check 视图按 trigger_key 聚合到 check 函数级别甚至
    sub-variant（如 evidence.commit / evidence.completion 分开）。

    数据源：复用现有 Violation.trigger_key 字段（v0.5.7 加的 i18n key，格式
    `check.<name>[.<sub>].trigger`）。**不需要 schema 变更** — 历史 jsonl 中
    没有 trigger_key 的行（keyword-only 命中）归到「keyword-only」桶。

    也是 `/karma` no-arg skill 默认输出 — 用户输 `/karma` 不带描述时 Agent
    跑 `karma audit --by-check` 把结果转述给用户，让用户看到 dogfood 数据
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
    print(f"karma engine check 命中分布 (总 {total} 条违反):\n")

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
    """`karma init` 末尾展示默认启用规则的简要列表 — Agent 代装的场景下，
    这段输出会被 Agent 转述给用户，让用户一眼看到默认开了什么规则。

    格式：每条 1 个 id + preference **首段**（split by 空行，到第一个空行为止）。
    比单纯首行（`split("\\n")[0]`）展示更完整 — 因为原作者把一句话写两行 visual
    wrap 时，首行会被砍成半句。首段保留一个完整意思单元（一句或一小段）。

    规则文本跟随用户安装时的 locale（中文用户装 zh 模板，preference 是中文；
    英文用户装 en 模板，preference 是英文）。i18n locale key 只覆盖 helper 的
    header 脚手架文字，不翻译规则内容本身。

    刻意不输出「下一步：跑 karma rule edit ...」这类指令 tip — 那会变成
    「让用户手动输指令」的 friction，跟 onboarding「Agent 代用户操作」目标相反。
    用户看到规则列表后想改，自然会跟 Agent 说「帮我改 X」，Agent 知道用
    `/karma` skill 或 `karma rule edit`。

    异常不阻塞 — init 末尾装到这里之前都已经成功，summary 失败不该让 init 退非 0。
    """
    from karma.i18n import tr
    try:
        rules = load_rules()
    except Exception:
        return
    if not rules:
        return
    print()
    print(tr("init.summary.header", count=len(rules), soft_max=MAX_RULES))
    for r in rules:
        # 首段 = split 第一个空行（"\n\n"）。yaml `|` block 段间用空行分隔
        # 一个完整意思单元；段内 visual wrap 多行属于同一段。
        first_paragraph = r.preference.strip().split("\n\n")[0]
        print(f"  ▸ [{r.id}]")
        for line in first_paragraph.split("\n"):
            print(f"    {line.strip()}")
    # footer：告知用户 token 成本上限 + 想增改规则的 in-chat 入口
    # `/karma <自然语言>` 是 slash command 在客户端对话框输入触发 skill 自然语言
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
        print("没配置规则。运行 'karma init' 复制模板。")
        return 0
    print(f"karma 规则 ({len(rules)}/{MAX_RULES} 软上限, {HARD_MAX} 硬上限):\n")
    for i, r in enumerate(rules, 1):
        print(f"{i}. [{r.id}]")
        for line in r.preference.split("\n"):
            print(f"   {line}")
        print(f"   触发词: {', '.join(r.violation_keywords) if r.violation_keywords else '(无)'}")
        print()
    return 0


def cmd_rule_edit() -> int:
    if not RULES_PATH.exists():
        print("rules.yaml 不存在，先 'karma init'", file=sys.stderr)
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


def cmd_rule_add(yaml_path: str | None = None, stdin_yaml: bool = False) -> int:
    """添加新 rule 到 rules.yaml — 测试通过才写入.

    用法:
    - karma rule add --from-yaml <file>  # 从 yaml 文件读
    - karma rule add --from-stdin        # 从 stdin 读 yaml (Claude Code skill 用)

    流程:
    1. 读 yaml 输入 (一条新 rule 的 dict, 跟 rules.yaml 内单条格式一致)
    2. Schema validate (用 karma.rule.load 一致的校验逻辑)
    3. 检测 id 是否跟现有 rule 重复
    4. 检测软上限 (10 条) / 硬上限 (12 条) 不超
    5. 如果含 violation_checks, 验证 check 函数在 REGISTRY 注册
    6. 追加到 rules.yaml + 写回
    7. 反馈: 优化成什么 / 通过测试 / 当前规则库总数 / 是否有冲突建议删改
    """
    import yaml
    from karma.checks import REGISTRY as CHECK_REGISTRY

    # Step 1: 读 input
    if stdin_yaml:
        raw = sys.stdin.read()
    elif yaml_path:
        p = Path(yaml_path)
        if not p.exists():
            print(f"❌ yaml 文件不存在: {yaml_path}", file=sys.stderr)
            return 1
        raw = p.read_text(encoding="utf-8")
    else:
        print(
            "用法: karma rule add --from-yaml <file>  或  --from-stdin\n"
            "建议: 在 Claude Code 里发 '/karma rule <自然语言描述>' 让 Agent 用 karma "
            "skill 优化结构后调本命令",
            file=sys.stderr,
        )
        return 1

    try:
        new_rule = yaml.safe_load(raw)
    except yaml.YAMLError as e:
        print(f"❌ YAML 解析失败: {e}", file=sys.stderr)
        return 1

    # 支持 dict (单条) 或 list (多条, 取第一条)
    if isinstance(new_rule, list):
        if not new_rule:
            print("❌ yaml 是空 list", file=sys.stderr)
            return 1
        new_rule = new_rule[0]

    if not isinstance(new_rule, dict):
        print(f"❌ 期望 yaml 是 dict (一条 rule), 实际 {type(new_rule).__name__}", file=sys.stderr)
        return 1

    # Step 2: Schema validate (拼一个临时 list 复用 karma.rule.load 校验逻辑)
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8") as tmp:
        yaml.safe_dump([new_rule], tmp, allow_unicode=True, sort_keys=False)
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
        print(f"❌ 现有 rules.yaml 配置错误: {e}", file=sys.stderr)
        return 1

    existing_ids = {r.id for r in existing}
    if validated_rule.id in existing_ids:
        print(f"❌ 规则 id={validated_rule.id!r} 已存在 — 用 karma rule edit 修改或 karma rule remove 后再 add", file=sys.stderr)
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

    # Step 6: 追加写回 rules.yaml
    try:
        raw_existing = yaml.safe_load(RULES_PATH.read_text(encoding="utf-8")) if RULES_PATH.exists() else []
    except yaml.YAMLError as e:
        print(f"❌ 读 rules.yaml 失败: {e}", file=sys.stderr)
        return 1
    if not isinstance(raw_existing, list):
        raw_existing = []
    raw_existing.append(new_rule)
    RULES_PATH.parent.mkdir(parents=True, exist_ok=True)
    RULES_PATH.write_text(
        yaml.safe_dump(raw_existing, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    # Step 7: 反馈 (按用户要求: 优化后内容 / 已通过测试 / 当前总数 / 是否需删改)
    print(f"✓ 新规则已通过 karma schema 测试 + 写入 {RULES_PATH}")
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
    print("💡 建议: 看现有规则是否有重复 / 可合并 / 应该删除的, 用 karma rule remove <id> 调整")
    return 0


def cmd_rule_preview(yaml_path: str | None = None, stdin_yaml: bool = False) -> int:
    """预览新 rule 注入到头部的样子 — schema 校验 + 不写入.

    用 Claude Code skill 在让用户确认前调这个看效果.
    """
    import yaml

    if stdin_yaml:
        raw = sys.stdin.read()
    elif yaml_path:
        p = Path(yaml_path)
        if not p.exists():
            print(f"❌ yaml 文件不存在: {yaml_path}", file=sys.stderr)
            return 1
        raw = p.read_text(encoding="utf-8")
    else:
        print("用法: karma rule preview --from-yaml <file>  或  --from-stdin", file=sys.stderr)
        return 1

    try:
        new_rule = yaml.safe_load(raw)
    except yaml.YAMLError as e:
        print(f"❌ YAML 解析失败: {e}", file=sys.stderr)
        return 1

    if isinstance(new_rule, list):
        if not new_rule:
            print("❌ yaml 是空 list", file=sys.stderr)
            return 1
        new_rule = new_rule[0]

    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8") as tmp:
        yaml.safe_dump([new_rule], tmp, allow_unicode=True, sort_keys=False)
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
    print("用 `karma rule add --from-yaml <file>` 写入 rules.yaml")
    return 0


def cmd_rule_remove(rule_id: str) -> int:
    """简单删除 — 读 yaml，过滤，写回。"""
    import yaml
    if not RULES_PATH.exists():
        print("rules.yaml 不存在", file=sys.stderr)
        return 1
    raw = yaml.safe_load(RULES_PATH.read_text(encoding="utf-8")) or []
    filtered = [item for item in raw if item.get("id") != rule_id]
    if len(filtered) == len(raw):
        print(f"没找到 id={rule_id!r}", file=sys.stderr)
        return 1
    RULES_PATH.write_text(
        yaml.safe_dump(filtered, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    print(f"已删除规则 {rule_id!r} ({len(filtered)} 条剩余)")
    return 0


def cmd_reset_session() -> int:
    """清所有 session-state JSON — Agent 注意力漂移实验重启。

    用法场景：观察「干净 session 起步」vs「累积 N turn 后」Agent 行为差异。
    不动 violations.jsonl（历史保留）+ 不动 rules.yaml / config.yaml。
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


def _check_file_last_commit_ts(sticky_id: str, sticky_list) -> int | None:
    """查 sticky 对应 check 文件最新 git commit 时间戳（dogfooding fix 时间线用）。

    用 sticky.yaml 的 violation_checks 字段反查 REGISTRY[func_name].__module__
    → check 文件路径 → `git log -1 --format=%ct -- <path>`。

    返回 None 的情况：不在 karma 仓库 cwd / git 不可用 / sticky 没工程 check
    （只关键词层）。这是 dev 工具按 sticky #1「失败要响亮」fail open。
    """
    import subprocess
    from pathlib import Path
    target_sticky = next((s for s in sticky_list if s.id == sticky_id), None)
    if not target_sticky or not target_sticky.violation_checks:
        return None
    try:
        from karma.checks import REGISTRY
        check_fn = REGISTRY.get(target_sticky.violation_checks[0])
        if not check_fn:
            return None
        # __module__ 形如 'karma.checks.chinese_plain'
        module_path = check_fn.__module__.replace(".", "/") + ".py"
        # 找 karma 仓库根 — cwd 或父目录含 pyproject.toml + karma/ 子目录
        cwd = Path.cwd()
        for candidate in [cwd, *cwd.parents]:
            if (candidate / "pyproject.toml").exists() and (candidate / "karma").is_dir():
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
    violation.ts 标记每条 violation 在 fix 前 / 后。dev 工具，仅 karma 仓库 cwd
    + git 可用时启用。

    output_format='md' 时输出 markdown 表格，方便粘贴到 PR / issue 分享
    dogfooding 数据。

    by_check=True 时切换到「engine check 命中分布」视图（v0.9.11+）：
    按 trigger_key 中的 check 名 + sub-variant 聚合命中次数，dogfood 数据驱动
    判断 8 个 engine check 各自的真阳 / 假阳率。这个视图也是 `/karma` no-arg
    skill 的默认输出 —— 用户输 `/karma` 不带描述时 Agent 跑这个给用户看。

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
        print("没有违反记录。先用 karma 一阵子再来 audit。")
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
        print(f"# karma 违反审计 (总 {len(violations)} 条)\n")
    else:
        print(f"karma 违反审计 (总 {len(violations)} 条):\n")
    # fix 时间线 — 仅 with_fix_timeline=True 时算
    fix_ts_by_sticky: dict[str, int | None] = {}
    if with_fix_timeline:
        from karma.rule import load as load_sticky
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
    from karma.session_state import get_current_session_id
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
    from karma.session_state import get_current_session_id
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

    print(f"karma 违反统计 (总 {len(violations)} 条):")
    if current_session:
        # 顺便显示本 session stop_block_count（Stop hook 干预次数）
        from karma import session_state as ss
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
                from karma.violations import extract_rule_id
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


def cmd_doctor() -> int:
    print(f"karma v{__version__} doctor")
    print(f"  KARMA_DIR: {KARMA_DIR} ({'存在' if KARMA_DIR.exists() else '不存在'})")
    print(f"  rules.yaml: {RULES_PATH} ({'存在' if RULES_PATH.exists() else '不存在'})")
    print(f"  violations.jsonl: {VIOLATIONS_PATH} ({'存在' if VIOLATIONS_PATH.exists() else '不存在'})")
    config_path = KARMA_DIR / "config.yaml"
    print(f"  config.yaml: {config_path} ({'存在' if config_path.exists() else '不存在 (用默认值)'})")
    # v0.5.16: skill 装机状态 — multi-backend, /karma <NL> 流程依赖
    print("  karma skill 装机 (多 backend):")
    from karma.backends import REGISTRY as _BACKENDS_FOR_SKILL
    src_text = KARMA_SKILL_SRC.read_text(encoding="utf-8") if KARMA_SKILL_SRC.exists() else None
    if src_text is None:
        print(f"    ⚠ source 未找到: {KARMA_SKILL_SRC} (dev install 异常)")
    else:
        from karma.skill_packaging import markdown_to_toml
        for backend_name, backend in _BACKENDS_FOR_SKILL.items():
            for dest, fmt in backend.skill_install_targets("karma"):
                expected = markdown_to_toml(src_text) if fmt == "toml" else src_text
                if not dest.exists():
                    print(f"    [{backend_name}] {dest}: 未装")
                    continue
                try:
                    same = dest.read_text(encoding="utf-8") == expected
                except OSError:
                    print(f"    [{backend_name}] {dest}: 存在 (无法读)")
                    continue
                label = "✓ 最新" if same else "⚠ 跟当前版本不一致 (跑 `karma install-skill --force` 升级)"
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
    from karma.config import load as _load_config
    cfg = _load_config()
    print("  当前生效配置:")
    for k, v in cfg.items():
        print(f"    {k}: {v}")

    # 显示活跃 session 简况（turn / stop_block 状态）
    # 权威 source = session-state 目录最新 mtime 文件，不依赖 violations[-1]
    # （当前 session 可能没产生违反但仍是活跃 session）
    from karma import session_state as _ss
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

    # v0.9.17 L2: codex 审批状态 reminder. codex 0.130+ 不公开 approval 存储
    # 位置 (sqlite / 文件 / keychain 都没查到), karma 没法程序化验证 4 个
    # wrapper 是否真 approved. 诚实路径: 检测到 codex 装了 + hooks.json 写了
    # karma entry → 响亮提醒用户去 TUI /hooks 确认审批 + 给完整 wrapper
    # 路径让用户对照. 不假装能自动检测（rule #4: 假装查过比说没查过更失信任）.
    if "codex" in _BACKENDS:
        codex = _BACKENDS["codex"]
        if codex.client_installed():
            try:
                codex_settings = codex.load_settings()
                codex_has_karma_entry = any(
                    any(codex.is_karma_entry(e) for e in codex_settings.get("hooks", {}).get(ev, []))
                    for ev in codex.hook_events()
                )
            except Exception:
                codex_has_karma_entry = False
            if codex_has_karma_entry:
                hooks_dir = codex.hooks_dir()
                print("")
                print("  ⚠️  Codex 审批状态自检（karma 无法自动验证，请人工确认）:")
                print("     codex 0.130+ 安全设计要求每个 hook 在 TUI 内 `/hooks`")
                print("     命令里手动 approve 才生效. karma hooks.json 写了不等于真生效.")
                print("     **没 approve = 所有 karma 规则在 codex 下静默失效**.")
                print("")
                print("     ▶ 确认步骤:")
                print("        1. 启动 `codex`")
                print("        2. TUI 内输 `/hooks`")
                print("        3. 检查这 4 个 wrapper 状态:")
                for basename in codex.hook_events().values():
                    wrapper = hooks_dir / f"karma_{basename}.py"
                    print(f"           {wrapper}")
                print("        4. 没 approved 的逐个 approve, 已 approved 跳过.")
                print("")
                print("     ▶ 验证: codex 改一个没先 Read 的文件 → 应被 karma 🛑 拦.")
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

    # v0.9.17 L1: backend 装完后的响亮警示（如 Codex TUI /hooks 审批步骤）.
    # 默认 backend 返回空 list 不打印额外内容; Codex override 返回完整审批框.
    # 用 getattr 兜底避免老 Backend 实现没这方法时抛 AttributeError.
    post_msg: list[str] = getattr(backend, "post_install_message", lambda: [])()
    for line in post_msg:
        print(line)
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
        backend = REGISTRY[backend_name]
        # 显式 backend 也必须查客户端是否实际装 — sub-agent 排查发现的 P1 bug：
        # 同事没装 Claude Code 跑 `karma install-hooks` 默认装 claude-code 静默
        # 写 ~/.claude/settings.json 完全无反馈，他不知道 hook 不会触发。
        # 修：检测不到客户端时报错 + 提示，要绕过装可用 --force（暂未加）。
        if not backend.client_installed():
            print(
                f"没检测到 {backend.display_name} 客户端在本机（PATH 上没对应"
                f"命令也没 {backend.settings_path().parent} 目录）。\n"
                f"karma 不装 hook 配置避免静默写。要么先装 {backend.display_name}，"
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
        # `karma uninstall` 一键卸所有 backend 的 alias — 陌生用户不用记
        # `uninstall-hooks --backend all` 长串
        return cmd_uninstall_hooks(backend_name="all")
    if cmd == "sticky":
        # v0.6.0 起删除 `karma sticky` alias — v0.5.0 起一直在打 DeprecationWarning,
        # 兑现废弃契约. 给一行「你是不是想用 karma rule」hint 救肌肉记忆.
        print(
            "❌ unknown command: 'sticky' (removed in v0.6.0).\n"
            "💡 你是不是想用 `karma rule`？ (sticky → rule 改名见 v0.5.0 CHANGELOG)",
            file=sys.stderr,
        )
        return 1
    if cmd == "rule":
        if not args:
            print(f"Usage: karma {cmd} <list|edit|remove|add|preview>", file=sys.stderr)
            return 1
        if args[0] == "list":
            return cmd_rule_list()
        if args[0] == "edit":
            return cmd_rule_edit()
        if args[0] == "remove":
            if len(args) < 2:
                print(f"Usage: karma {cmd} remove <id>", file=sys.stderr)
                return 1
            return cmd_rule_remove(args[1])
        if args[0] == "add":
            # karma rule add --from-yaml <file>  或  --from-stdin
            yaml_path = None
            stdin_yaml = False
            sub = args[1:]
            if "--from-stdin" in sub:
                stdin_yaml = True
            elif "--from-yaml" in sub:
                idx = sub.index("--from-yaml")
                if idx + 1 < len(sub):
                    yaml_path = sub[idx + 1]
            return cmd_rule_add(yaml_path=yaml_path, stdin_yaml=stdin_yaml)
        if args[0] == "preview":
            yaml_path = None
            stdin_yaml = False
            sub = args[1:]
            if "--from-stdin" in sub:
                stdin_yaml = True
            elif "--from-yaml" in sub:
                idx = sub.index("--from-yaml")
                if idx + 1 < len(sub):
                    yaml_path = sub[idx + 1]
            return cmd_rule_preview(yaml_path=yaml_path, stdin_yaml=stdin_yaml)
        print(f"未知 {cmd} 子命令: {args[0]}", file=sys.stderr)
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
