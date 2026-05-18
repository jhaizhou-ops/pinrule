"""SKILL.md 内容 lockdown — 防 Path A / Path B workflow 后续被改坏丢字段.

SKILL.md 是给 Agent 看的指导文档. 不是 pinrule 自己读, 但是 Agent 客户端
(Claude / Codex / Cursor) 装完 pinrule 后会读这个文件决定怎么处理 /pinrule 调用.

如果 SKILL.md 丢了关键 workflow 段, 用户 /pinrule 体验会沉默地降级.
这组测试锁住 SKILL.md 必须含的关键结构.
"""

from __future__ import annotations

from pathlib import Path

import pytest

SKILL_MD = Path(__file__).resolve().parents[1] / "skills" / "pinrule" / "SKILL.md"


@pytest.fixture(scope="module")
def skill_text() -> str:
    """读 SKILL.md 一次, 所有 lockdown 测试共享."""
    return SKILL_MD.read_text(encoding="utf-8")


def test_skill_md_exists(skill_text: str) -> None:
    """SKILL.md 必须存在 + 非空."""
    assert len(skill_text) > 1000, f"SKILL.md 太短可能被砍坏 ({len(skill_text)} chars)"


def test_skill_dispatch_section_present(skill_text: str) -> None:
    """SKILL.md 必须有 Path A vs Path B dispatcher — 告诉 Agent 先决策走哪条 workflow."""
    # dispatcher 段头
    assert "Your job (Agent) — dispatch first" in skill_text, \
        "SKILL.md 丢了 dispatcher 段头, Agent 不会做 Path A/B 决策"
    # 两条 path 标签必须存在
    assert "Single rule" in skill_text, "SKILL.md 丢了 Path A 描述"
    assert "Scenario rule pack" in skill_text, "SKILL.md 丢了 Path B 描述"


def test_skill_path_a_workflow_intact(skill_text: str) -> None:
    """Path A 主 workflow 7 步必须齐."""
    assert "Path A: Single-rule workflow" in skill_text, "丢了 Path A workflow 段头"
    # 7 步骤标题
    for step in ("Understand intent", "Check existing rules", "Refine into JSON",
                 "Preview test", "Confirm with user", "Write to rules.json",
                 "Report results"):
        assert step in skill_text, f"Path A 丢了关键步骤: {step!r}"


def test_skill_path_b_workflow_intact(skill_text: str) -> None:
    """Path B 场景规则集 workflow 必须齐 — Step 0.5 Preflight + 2 phase 共 11 步 + 4 信号源."""
    assert "Path B: Scenario rule pack generation" in skill_text, \
        "丢了 Path B workflow 段头"
    # Phase 1 / Phase 2 分段
    assert "Phase 1 — Content draft" in skill_text, \
        "Path B 丢了 Phase 1 (Content) 段头"
    assert "Phase 2 — Mechanism design" in skill_text, \
        "Path B 丢了 Phase 2 (Mechanism) 段头"
    # 12 步骤都有标识 (Step 0.5 Preflight + Step 1-11)
    for step_marker in ("Step 0.5 (Path B)", "Step 1 (Path B)", "Step 2 (Path B)",
                        "Step 3 (Path B, Phase 1)", "Step 4 (Path B, Phase 1)",
                        "Step 5 (Path B, Phase 1)",
                        "Step 6 (Path B, Phase 2)", "Step 7 (Path B, Phase 2)",
                        "Step 8 (Path B, Phase 2)", "Step 9 (Path B, Phase 2)",
                        "Step 10 (Path B)", "Step 11 (Path B)"):
        assert step_marker in skill_text, f"Path B 丢了步骤: {step_marker}"


def test_skill_path_b_engine_check_mapping_table(skill_text: str) -> None:
    """Path B Step 7 必须含 8 个 engine check 的语义模式映射表 — Agent 跨场景复用的核心."""
    # 8 个内建 check 函数名都必须列出
    for check_name in ("read_before_write", "loud_failure_with_evidence",
                       "non_blocking_parallel", "keep_pushing_no_stop",
                       "long_term_fundamental", "no_testset_no_future_leakage",
                       "deep_fix_not_bypass", "chinese_plain_no_jargon"):
        assert check_name in skill_text, \
            f"Path B engine check 映射表丢了 {check_name}"
    # 必须含跨场景复用的具体 example (UX / Legal / Writing / Research / Marketing)
    assert "Cross-scenario reuse examples" in skill_text, \
        "Path B 丢了「跨场景复用 example」段头"
    # 至少 3 个不同非 dev 场景的复用 example
    cross_scenario_keywords = ["UX scenario", "Legal scenario", "Writing scenario",
                                "Research scenario", "Marketing scenario"]
    found = sum(1 for kw in cross_scenario_keywords if kw in skill_text)
    assert found >= 3, \
        f"Path B 跨场景复用 example 不足 (找到 {found}, 至少要 3 个不同场景)"


def test_skill_path_b_phase_1_content_only(skill_text: str) -> None:
    """Path B Phase 1 必须强调「只生成 content 不填 keyword/check」— 分阶段核心."""
    # Phase 1 必须明确「不填 keyword / check」
    assert "Do NOT fill `violation_keywords` or `violation_checks` yet" in skill_text, \
        "Phase 1 没明确「暂不填 keyword/check」"
    # Phase 2 配机制时必须强调「不再 debate 内容」
    assert "content was locked in Step 5" in skill_text, \
        "Phase 2 没明确「content 已锁定不再 debate」"


def test_skill_path_b_four_signal_sources(skill_text: str) -> None:
    """Path B 必须含 4 个信号源 — A 本机文件 / B 联网 / H Karpathy / S session 上下文."""
    # Source A: 本机规则文件
    assert "Source A — User's existing local rule files" in skill_text, \
        "丢了 Source A (本机已有规则文件)"
    # Source B: 联网
    assert "Source B — Online best practices" in skill_text, \
        "丢了 Source B (联网 best practice)"
    assert "WebSearch" in skill_text and "WebFetch" in skill_text, \
        "Source B 丢了 WebSearch / WebFetch 工具引用"
    # Source H: Karpathy baseline
    assert "Source H — Karpathy CLAUDE.md baseline" in skill_text, \
        "丢了 Source H (Karpathy baseline)"
    # Source S: session context
    assert "Source S — Your session context" in skill_text, \
        "丢了 Source S (session 上下文 — 这是 Agent 独有的信号)"


def test_skill_path_b_skip_self_generated_files(skill_text: str) -> None:
    """Path B 必须明确跳过 pinrule 自己生成的文件 (防自指 / 噪声)."""
    assert "pinrule-*.mdc" in skill_text, \
        "Path B 没明确跳 pinrule 自己生成的 .cursor/rules/pinrule-*.mdc"
    # 也跳 karma legacy 命名
    assert "karma-*.mdc" in skill_text, \
        "Path B 没跳 karma legacy 命名的自生成文件"


def test_skill_path_b_source_attribution_required(skill_text: str) -> None:
    """Path B 每条规则必须带 source attribution — 用户审查可追溯性."""
    assert "Source attribution" in skill_text or "source attribution" in skill_text, \
        "Path B 丢了 source attribution 要求"
    # 例子里也要展示出来
    assert "Source: 源自" in skill_text or "Source: " in skill_text, \
        "Path B 没展示 source attribution 格式例子"


def test_skill_path_b_replace_default_not_append(skill_text: str) -> None:
    """Path B 默认 replace 不是 append (跟 Path A 默认 append 相反)."""
    assert "default is replace" in skill_text or "默认 replace" in skill_text or \
           "default REPLACE" in skill_text, \
        "Path B 没明确默认是 replace (跟 Path A append 区分)"


def test_skill_path_b_backup_before_batch_write(skill_text: str) -> None:
    """Path B 批量写入前必须 backup — 防中途失败半残."""
    assert "before-scenario-" in skill_text, \
        "Path B 没要求 backup 到 ~/.pinrule/rules.json.before-scenario-* 路径"
    assert "Backup" in skill_text or "backup" in skill_text, \
        "Path B 没明确 backup 步骤"


def test_skill_path_b_two_phase_mistakes_listed(skill_text: str) -> None:
    """Path B 两阶段 specific mistakes 段必须存在 — 让 Agent 知道 Phase 1/2 边界."""
    assert "Path B two-phase mistakes" in skill_text, \
        "Path B 丢了两阶段 mistakes 段头"
    # 关键反模式必须被列
    assert "Don't put `violation_keywords` or `violation_checks` in Phase 1" in skill_text, \
        "Phase 1 反模式没列「不要在 Phase 1 填 keyword/check」"
    assert "re-debate rule **content** in Phase 2" in skill_text, \
        "Phase 2 反模式没列「不要在 Phase 2 重新 debate 内容」"


def test_skill_path_b_backend_detection_step(skill_text: str) -> None:
    """Path B Step 0.5 Preflight 必须含 backend detection (Path B 第一动作).

    v4 dogfood 真发现: Step 5.5 放 Phase 2 区域时 Agent 严格按 spec 跳过整个步骤.
    v5 dogfood 真发现: 改 Step 0.5 Phase 1 之前 + "mandatory first action" 警告 Agent 仍跳过.
    Root cause: Agent 单 turn 模式天然把 backend detection 当 Phase 2 prep 推迟.
    Real fix (v6+): Phase 1 preview 模板加 mandatory "Backends detected" 字段 — 工程约束
    替代 prompt 约束让 Agent 不可不跑 pinrule doctor (要填字段必须先跑).
    """
    assert "Step 0.5 (Path B): Preflight — detect user's active backends FIRST" in skill_text, \
        "Path B 丢了 Step 0.5 Preflight backend detection step"
    # Step 0.5 必须明确「mandatory first action」
    assert "Path B's mandatory first action" in skill_text, \
        "Step 0.5 没明确「Path B 第一动作不可跳」"
    # 必须明确「Run via Bash tool (NOT Read tool)」
    assert "Run via Bash tool (NOT Read tool" in skill_text, \
        "Step 0.5 没明确「用 Bash 跑 pinrule doctor 而不是 Read 文件」"


def test_skill_path_b_phase1_preview_requires_backend_line(skill_text: str) -> None:
    """Path B Phase 1 preview 必须强制含 "Backends detected" mandatory 字段.

    v5 dogfood 真验证: prompt 约束 (Step 0.5 标 "mandatory" 警告) 不够稳, Agent 仍跳过.
    工程约束 (Phase 1 preview 输出格式必须含 backend line) 才让 Agent 不可不跑 pinrule doctor.
    """
    assert "Required first line: backend detection summary" in skill_text, \
        "Phase 1 Step 4 没明确「必填字段: backend detection」"
    assert "**Backends detected**" in skill_text, \
        "Phase 1 preview 模板没含 mandatory `Backends detected` 字段"
    # 必须明确「Agent 没跑 doctor 现在就跑」
    assert "If you haven't run `pinrule doctor` yet, run it now" in skill_text, \
        "Step 4 没明确「Agent 没跑 doctor 必须立刻跑」"


def test_skill_no_argument_fast_path(skill_text: str) -> None:
    """SKILL.md 头部必须含无参数 /pinrule fast-path — 让 Agent 不在简单 path 加工.

    用户 design 拍板: 无参数 /pinrule 是纯工程实现 (pinrule audit --by-check), Agent
    不该转述 / 解读 / 加工. SKILL.md 头部强约束「STOP reading + Bash + raw output」.
    """
    assert "🚨 Fast-path: No-argument `/pinrule` — Bash direct, no synthesis" in skill_text, \
        "SKILL.md 丢了无参数 fast-path 段头"
    # 必须明确「STOP reading this skill」
    assert "STOP reading this skill right now" in skill_text, \
        "fast-path 没明确「立刻 STOP 不读 skill 后续」"
    # 必须明确「Dump output verbatim」+「no synthesis」
    assert "Dump the output verbatim to the user" in skill_text, \
        "fast-path 没明确「verbatim raw output」"
    assert "Do NOT synthesize / summarize / add commentary" in skill_text, \
        "fast-path 没明确「不要 synthesize / summarize / commentary」"


def test_skill_engineering_first_principle(skill_text: str) -> None:
    """SKILL.md 必须含「engineering-first, Agent 不该 reinvent」根本设计原则.

    Path B dogfood (v0.17.x) 真验证: 让 Agent 自己 Read 文件 reinvent backend detection,
    Agent 漏检测真装的 Cursor. fix: SKILL.md 头部 design principle 明确「有 pinrule
    subcommand 就直接调, Agent 创意空间留给 domain synthesis / 跨场景 semantic mapping
    类真需要判断的工作」.
    """
    assert "Design principle: engineering-first, Agent doesn't reinvent" in skill_text, \
        "SKILL.md 丢了根本 design principle 段头"
    # 必须列出 Agent 不该 reinvent 的工作 (有 pinrule 工程化 primitive)
    for primitive in ("pinrule doctor", "pinrule rule preview",
                      "pinrule rule add", "pinrule rule list", "pinrule audit"):
        assert primitive in skill_text, f"design principle 没列 pinrule 工程化 primitive: {primitive}"
    # 必须区分「Agent 自由发挥 belongs in」vs「Agent reinvention does NOT belong in」
    assert "Agent free-form judgment belongs in" in skill_text, \
        "design principle 没明确「Agent 该自由发挥的地方」"
    assert "Agent reinvention does NOT belong in" in skill_text, \
        "design principle 没明确「Agent 不该 reinvent 的地方」"


def test_skill_path_b_backend_coverage_table(skill_text: str) -> None:
    """Path B Step 7 必须含 backend coverage table 区分 Claude / Codex / Cursor 桌面 / Cursor CLI."""
    # 必须含 4 列 backend
    assert "Cursor 桌面 Agent" in skill_text, "backend coverage table 缺 Cursor 桌面 Agent 列"
    assert "Cursor CLI" in skill_text, "backend coverage table 缺 Cursor CLI 列"
    # 必须明确「桌面用户不需要 over-warning」
    assert "不要给桌面用户发任何 transcript advisory" in skill_text, \
        "没强调「桌面 Agent 用户不需要 over-warning」(否则 Agent 会无脑给桌面用户也发警告)"
    # 必须含 backend-aware reminder
    assert "Backend-aware reminder" in skill_text, \
        "Path B 丢了 Step 11 末尾 backend-aware reminder"


def test_skill_no_extra_subscenario_pingpong(skill_text: str) -> None:
    """Path B 不应该多问子场景 — Agent 从 session context 推断."""
    # 这条不是字面 grep, 是检查 Step 1 (Path B) 含「don't ping-pong」或类似精神
    assert "don't ping-pong" in skill_text or "Don't ping-pong" in skill_text or \
           "ping-pong" in skill_text, \
        "Path B 丢了「不要多轮 ping-pong 问子场景」的关键约束"


def test_skill_path_b_common_mistakes_listed(skill_text: str) -> None:
    """Path B 常见错误段必须列出 — 让 Agent 知道哪些反模式要避免."""
    assert "Path B specific mistakes" in skill_text, \
        "Path B 丢了 common mistakes section"


def test_skill_frontmatter_mentions_both_paths(skill_text: str) -> None:
    """SKILL.md frontmatter description 必须提到两条 path (Agent 客户端读这段决定 skill 适用范围)."""
    # frontmatter 头 200 字符
    head = skill_text[:600]
    assert "two paths" in head or "Single rule" in head, \
        "frontmatter description 没提 Path A (单条规则)"
    assert "Scenario rule pack" in head, \
        "frontmatter description 没提 Path B (场景规则集)"
