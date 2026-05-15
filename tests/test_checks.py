"""6 个 violation_check 函数测试。"""

from __future__ import annotations

from karma.checks import REGISTRY, run_checks
from karma.session_state import SessionState


# -------- #1 long-term-fundamental --------

def test_long_term_detects_hash_if_branch():
    fn = REGISTRY["long_term_fundamental"]
    hit = fn(
        tool_name="Edit",
        tool_input={"new_string": 'if turn_id == "abc-def-12345":\n    return special'},
    )
    assert hit is not None
    assert hit.rule_id == "long-term-fundamental"
    assert "长 ID" in hit.trigger


def test_long_term_detects_quick_fix_commit():
    fn = REGISTRY["long_term_fundamental"]
    hit = fn(
        tool_name="Bash",
        tool_input={"command": 'git commit -m "quick fix for that bug"'},
    )
    assert hit is not None
    assert "quick fix" in hit.trigger.lower() or "fix" in hit.trigger


def test_long_term_commit_message_describe_pattern_passes():
    """commit message 长描述区里讨论 hack/quick-fix 概念 → 不算违反。

    违反是「字眼作为 commit 主语」（前 80 字内），不是长描述里偶然提到。
    """
    fn = REGISTRY["long_term_fundamental"]
    # 字眼在描述区（120 字之后）— 不算违反
    long_msg = (
        'feat(x): 实现新功能 X\n\n'
        '本提交做了三件事：\n'
        '1. 加了 A 功能\n'
        '2. 改了 B 测试\n'
        '3. 重构了 C 模块的逻辑\n\n'
        '附带说明：这里讨论一下 quick fix 这个反 pattern，'  # 这里字眼在 message 后部
        '我们不应该这么做。'
    )
    hit = fn(
        tool_name="Bash",
        tool_input={"command": f'git commit -m "{long_msg}"'},
    )
    assert hit is None, "commit message 后部讨论字眼不该被认成违反"


def test_long_term_commit_message_subject_quick_fix_blocked():
    """commit message 主语区（80 字内）含 hack 词 → 违反，拦。"""
    fn = REGISTRY["long_term_fundamental"]
    hit = fn(
        tool_name="Bash",
        tool_input={"command": 'git commit -m "hack: 临时修个 bug"'},
    )
    assert hit is not None


def test_long_term_detects_no_verify():
    fn = REGISTRY["long_term_fundamental"]
    hit = fn(
        tool_name="Bash",
        tool_input={"command": "git commit --no-verify -m 'msg'"},
    )
    assert hit is not None
    assert "跳过" in hit.trigger or "验证" in hit.trigger


def test_long_term_detects_temp_comment():
    fn = REGISTRY["long_term_fundamental"]
    hit = fn(
        tool_name="Write",
        tool_input={"content": "def foo():\n    # HACK: 临时这样\n    return 42"},
    )
    assert hit is not None


def test_long_term_clean_code_passes():
    fn = REGISTRY["long_term_fundamental"]
    hit = fn(tool_name="Write", tool_input={"content": "def foo(x): return x * 2"})
    assert hit is None


def test_long_term_write_with_no_verify_string_passes():
    """Write 文档里描述 --no-verify 字面（不是要跑）→ 不该拦。"""
    fn = REGISTRY["long_term_fundamental"]
    content = "# karma 检测规则\n这条规则会拦截 --no-verify、--skip、--force 等 flag。"
    hit = fn(tool_name="Write", tool_input={"file_path": "/tmp/doc.md", "content": content})
    assert hit is None


def test_long_term_bash_with_no_verify_blocked():
    """Bash 跑 git commit --no-verify → 该拦。"""
    fn = REGISTRY["long_term_fundamental"]
    hit = fn(tool_name="Bash", tool_input={"command": "git commit --no-verify -m 'fix'"})
    assert hit is not None
    assert "验证" in hit.trigger or "verify" in hit.trigger.lower() or "git" in hit.trigger.lower()


def test_long_term_cli_dispatch_kebab_passes():
    """CLI dispatch 字符串字面（kebab-case 命令名）不该命中「长 ID if 分支」
    pattern — 命令名是合法分发不是 ID 硬写。dogfooding 实证：karma cli.py
    'if cmd == \"install-hooks\"' 之前误命中。"""
    fn = REGISTRY["long_term_fundamental"]
    for code in [
        'if cmd == "install-hooks":\n    pass',
        'if cmd == "uninstall-hooks":\n    pass',
        'if name == "no-testset-no-future-leakage":\n    pass',
        'if event == "UserPromptSubmit":\n    pass',
    ]:
        hit = fn(tool_name="Write", tool_input={
            "file_path": "/x/cli.py", "content": code,
        })
        assert hit is None, f"CLI dispatch 字面不该拦: {code!r}"


def test_long_term_uuid_hash_in_if_still_blocked():
    """对偶：UUID / hash / 含数字长字面 if 分支硬编码 — 仍要拦（违反）。"""
    fn = REGISTRY["long_term_fundamental"]
    for code in [
        'if user_id == "abc-def-12345-uuid":\n    pass',
        'if hash == "9f5687fc2ab975ea":\n    pass',
        'if token == "tok_abc12345xyz":\n    pass',
    ]:
        hit = fn(tool_name="Write", tool_input={
            "file_path": "/x/src/handler.py", "content": code,
        })
        assert hit is not None, f"含数字长字面 if 分支应拦: {code!r}"


def test_long_term_pytest_skip_flag_passes():
    """评审 B Agent 痛点：pytest / pip / cmake / rsync 等合法 --skip / --force
    flag 不该被错拦（之前泛 flag 匹配会误拦）。"""
    fn = REGISTRY["long_term_fundamental"]
    for cmd in [
        "pytest --skip-broken-isolation tests/",
        "pip install --skip-existing requirements.txt",
        "cmake --build . --force",
        "rsync --force /src /dst",
        "tar --skip-old-files -xf x.tar",
        "cargo build --force",
    ]:
        hit = fn(tool_name="Bash", tool_input={"command": cmd})
        assert hit is None, f"不该拦合法 flag: {cmd!r}, 触发 {hit.trigger if hit else ''}"


def test_long_term_git_push_no_verify_blocked():
    """git push --no-verify 也该拦（不只 commit）。"""
    fn = REGISTRY["long_term_fundamental"]
    hit = fn(tool_name="Bash", tool_input={"command": "git push --no-verify origin main"})
    assert hit is not None


def test_long_term_bash_with_todo_passes():
    """Bash 里出现 # TODO 是 shell 注释，不算 Write 代码 → 不拦。"""
    fn = REGISTRY["long_term_fundamental"]
    hit = fn(tool_name="Bash", tool_input={"command": "echo hello  # TODO refactor later"})
    assert hit is None


def test_long_term_blacklist_literal_blocked():
    """变量名含黑白名单语义 + 字面量列表 → 拦（真硬编码名单）。"""
    fn = REGISTRY["long_term_fundamental"]
    hit = fn(
        tool_name="Write",
        tool_input={
            "file_path": "/x/src/filter.py",
            "content": 'BLACKLIST = ["bot1", "bot2", "spammer"]',
        },
    )
    assert hit is not None


def test_long_term_samples_literal_passes():
    """普通 samples=[..] / examples=[..] 测试样本数组 → 不拦。"""
    fn = REGISTRY["long_term_fundamental"]
    hit = fn(
        tool_name="Write",
        tool_input={
            "file_path": "/x/src/util.py",
            "content": 'samples = ["alice", "bob"]\nexamples = ["x", "y"]',
        },
    )
    assert hit is None


def test_long_term_description_context_exempts(tmp_path):
    """描述上下文（.md / tests/ / /tmp/）下任何 pattern 都豁免。"""
    fn = REGISTRY["long_term_fundamental"]
    # .md 文档里写 if 长 ID 字面 → 豁免
    hit = fn(
        tool_name="Write",
        tool_input={
            "file_path": "/x/README.md",
            "content": 'if user_id == "abc-def-12345":\n    pass',
        },
    )
    assert hit is None
    # tests/ 下同样 → 豁免
    hit = fn(
        tool_name="Edit",
        tool_input={
            "file_path": "/repo/tests/test_foo.py",
            "new_string": 'BLACKLIST = ["a", "b", "c"]',
        },
    )
    assert hit is None


# -------- #2 non-blocking-parallel --------

def test_non_blocking_detects_sleep():
    fn = REGISTRY["non_blocking_parallel"]
    hit = fn(tool_name="Bash", tool_input={"command": "sleep 30"})
    assert hit is not None
    assert "sleep" in hit.trigger


def test_non_blocking_wait_blocking_blocked():
    """裸 wait / wait $pid 阻塞当前 shell → 该拦。"""
    fn = REGISTRY["non_blocking_parallel"]
    for cmd in ["wait", "wait $!", "wait $pid", "jobs; wait"]:
        hit = fn(tool_name="Bash", tool_input={"command": cmd})
        assert hit is not None, f"裸 wait 应拦: {cmd!r}"


def test_non_blocking_python_real_time_sleep_caught():
    """v0.4.22：v0.4.18 fix 过宽 — python -c 内 time.sleep / asyncio.sleep /
    subprocess sleep 真阻塞前端应拦。"""
    fn = REGISTRY["non_blocking_parallel"]
    real_block_cases = [
        ('python -c "import time; ' + 'time.sleep(60)' + '"', "time.sleep"),
        ('python -c "import asyncio; ' + 'asyncio.sleep(30)' + '"', "asyncio.sleep"),
        ('python -c "import subprocess; subprocess.run(\'sleep 30\', shell=True)"', "subprocess sleep"),
        ('python -c "import os; os.system(\'sleep 30\')"', "os.system sleep"),
    ]
    for cmd, label in real_block_cases:
        hit = fn(tool_name="Bash", tool_input={"command": cmd})
        assert hit is not None, f"python 真阻塞 {label} 应命中: {cmd!r}"


def test_evidence_pytest_collect_only_not_exempted():
    """v0.4.22：v0.4.14 fix 过宽 — pytest --collect-only 等假证据 flag 不该豁免。"""
    fn = REGISTRY["loud_failure_with_evidence"]
    state = SessionState(session_id="s5")
    fake_test_cases = [
        "pytest --collect-only && git commit -m fix",
        "pytest --help && git commit -m fix",
        "pytest --version && git commit -m fix",
    ]
    for cmd in fake_test_cases:
        hit = fn(tool_name="Bash", tool_input={"command": cmd}, session_state=state)
        assert hit is not None, f"假证据 flag 不该豁免: {cmd!r}"


def test_non_blocking_python_c_sleep_literal_exempted():
    """v0.4.18：python -c "..." 内的 sleep 字面是字符串数据不是真 shell sleep。

    dogfooding 实测假阳率 60%：karma 自测 _SLEEP_RE 探针
    `python3 -c "for c in ['sleep 5']: ..."` 被错算真 sleep。
    fix：命令头是宿主语言 + -c 时跳 sleep 检测（同 deep-fix v0.4.13 _WRITE_OP_RE 根因）。
    真 python 等待用 time.sleep 不是裸 sleep 字面。
    """
    fn = REGISTRY["non_blocking_parallel"]
    cmd = 'python3 -c "for c in [\'sleep 5\', \'sleep 30\']: print(c)"'
    assert fn(tool_name="Bash", tool_input={"command": cmd}) is None
    # node / ruby / perl -c 同样豁免
    for cmd in [
        'node -e "console.log(\'sleep 30\')"',
        'ruby -e "puts \'sleep 5\'"',
    ]:
        assert fn(tool_name="Bash", tool_input={"command": cmd}) is None, \
            f"宿主语言 -c 应豁免 sleep 字面: {cmd!r}"


def test_non_blocking_python_c_wait_identifier_exempted():
    """v0.4.18：python -c "..." 内的 _WAIT_RE / wait_fn 等 identifier 字面命中
    \\bwait\\b 是假阳（python identifier 不是 shell wait 命令）。同 sleep 根因。
    """
    fn = REGISTRY["non_blocking_parallel"]
    cmd = 'python3 -c "from karma.checks.non_blocking import _WAIT_RE; print(_WAIT_RE)"'
    assert fn(tool_name="Bash", tool_input={"command": cmd}) is None


def test_non_blocking_real_bash_sleep_still_caught():
    """对偶守护：宿主语言豁免不影响真 shell sleep 拦截。"""
    fn = REGISTRY["non_blocking_parallel"]
    assert fn(tool_name="Bash", tool_input={"command": "sleep 30 && echo done"}) is not None


def test_non_blocking_kubectl_wait_passes():
    """评审 B Agent 痛点：kubectl wait / docker wait / aws cloudformation wait
    是 CI/CD 合法同步原语，不该拦。"""
    fn = REGISTRY["non_blocking_parallel"]
    for cmd in [
        "kubectl wait --for=condition=ready pod/foo",
        "docker wait container_id",
        "aws cloudformation wait stack-create-complete --stack-name foo",
        "gcloud compute operations wait my-op",
    ]:
        hit = fn(tool_name="Bash", tool_input={"command": cmd})
        assert hit is None, f"不该拦合法 wait: {cmd!r}"


def test_non_blocking_sleep_zero_not_blocking():
    """sleep 0 是 no-op (shell 立即返回，不阻塞)，不该拦。"""
    fn = REGISTRY["non_blocking_parallel"]
    hit = fn(tool_name="Bash", tool_input={"command": "sleep 0"})
    assert hit is None


def test_non_blocking_sleep_fractional_caught():
    """sleep 0.5 仍是阻塞（半秒）— 应拦。"""
    fn = REGISTRY["non_blocking_parallel"]
    hit = fn(tool_name="Bash", tool_input={"command": "sleep 0.5"})
    assert hit is not None


def test_non_blocking_detects_long_task_no_background():
    fn = REGISTRY["non_blocking_parallel"]
    # 长任务（docker run / build）— 不带 background 命中
    hit = fn(tool_name="Bash", tool_input={"command": "docker compose up", "run_in_background": False})
    assert hit is not None
    assert "background" in hit.trigger or "docker" in hit.trigger.lower()


def test_non_blocking_long_task_with_background_passes():
    fn = REGISTRY["non_blocking_parallel"]
    hit = fn(tool_name="Bash", tool_input={"command": "docker compose up", "run_in_background": True})
    assert hit is None


def test_non_blocking_test_commands_not_long_task():
    """pytest / jest 等测试命令默认不算长任务（多数项目跑得快 < 5s），
    避免 audit 指出的高频假阳。长测试用户自加 background。"""
    fn = REGISTRY["non_blocking_parallel"]
    hit = fn(tool_name="Bash", tool_input={"command": "pytest tests/"})
    assert hit is None  # 不再算长任务
    hit = fn(tool_name="Bash", tool_input={"command": "jest"})
    assert hit is None


def test_non_blocking_ignores_non_bash():
    fn = REGISTRY["non_blocking_parallel"]
    hit = fn(tool_name="Write", tool_input={"content": "sleep is a function"})
    assert hit is None


def test_non_blocking_ignores_quoted_literals():
    """命令引号字面里出现长任务命令字面词不该假阳（commit message / echo）。"""
    fn = REGISTRY["non_blocking_parallel"]
    # git commit message 含 docker / build 字面 — 不是要执行
    hit = fn(
        tool_name="Bash",
        tool_input={"command": 'git commit -m "fix: docker run output parsing"'},
    )
    assert hit is None
    # echo "sleep 30" 是 echo 字面 — 不是要 sleep
    hit = fn(
        tool_name="Bash",
        tool_input={"command": 'echo "sleep 30 before retry"'},
    )
    assert hit is None
    # 要跑 docker run 仍命中
    hit = fn(
        tool_name="Bash",
        tool_input={"command": "docker run myapp"},
    )
    assert hit is not None


def test_non_blocking_ignores_heredoc_content():
    """heredoc 内是程序数据 — 命令字面词不算执行意图。"""
    fn = REGISTRY["non_blocking_parallel"]
    # Python heredoc 含字面词（regex pattern 内）— 不命中
    cmd = """python <<'PYEOF'
import re
pat = re.compile(r'\\b(docker|sleep)\\b')
print(pat.search('foo'))
PYEOF"""
    hit = fn(tool_name="Bash", tool_input={"command": cmd})
    assert hit is None, "heredoc 内字面不算执行意图"
    # 但 heredoc **外**（命令头）长任务仍命中
    cmd_with_docker = """docker compose up <<'EOF'
some input
EOF"""
    hit = fn(tool_name="Bash", tool_input={"command": cmd_with_docker})
    assert hit is not None, "heredoc 外命令头长任务仍是执行"


# -------- #3 chinese-plain-no-jargon --------

def test_chinese_plain_all_chinese_passes():
    fn = REGISTRY["chinese_plain_no_jargon"]
    hit = fn(response="好的，开始干活了，先看下当前情况。这个改动应该不大。")
    assert hit is None


def test_chinese_plain_detects_low_chinese_ratio():
    fn = REGISTRY["chinese_plain_no_jargon"]
    response = (
        "OK let me explain how the algorithm works. "
        "Basically it uses cosine similarity over embeddings to find nearest neighbors. "
        "The threshold parameter controls precision recall tradeoff."
    )
    hit = fn(response=response)
    assert hit is not None


def test_chinese_plain_url_not_counted_in_ratio():
    """URL 全英文但是结构性内容（不是 jargon 话术）— 算 ratio 时先剥。

    dogfooding 实测触发：发 release 汇报 'v0.3.0 发布 — https://github.com/.../tag/v0.3.0'
    URL 35+ 字符把中文占比从主体内容的 ~50% 拉低到 28% 误命中。修后 URL 先剥
    再算 ratio。
    """
    fn = REGISTRY["chinese_plain_no_jargon"]
    response = (
        "v0.3.0 已发布到 https://github.com/jhaizhou-ops/karma/releases/tag/v0.3.0 "
        "看这个链接拿 release notes。本轮做了 codex backend 适配，跑通了实测。"
    )
    hit = fn(response=response)
    assert hit is None, f"URL 不该拉低中文比例造假阳: {hit}"


def test_chinese_plain_markdown_table_not_counted_in_ratio():
    """markdown 表格也是结构性内容（数据 / 名称），不算自然语言话术。"""
    fn = REGISTRY["chinese_plain_no_jargon"]
    response = """本轮完成清单：

| Release | 做 |
|---|---|
| v0.3.0 | Codex CLI backend |
| v0.4.0 | Gemini CLI backend |

跨平台测试全过。"""
    hit = fn(response=response)
    assert hit is None, f"表格不该拉低中文比例造假阳: {hit}"


def test_chinese_plain_table_with_3plus_jargons_blocked():
    """v0.4.22：v0.4.15 fix 过宽 — 表格 cell 里堆 ≥ 3 个 jargon 是真话术应拦。

    用户视角 case：表格里堆 retrieval / reranker / transformer / embedding /
    baseline 等真技术话术不是项目术语引用，应该拦。
    """
    fn = REGISTRY["chinese_plain_no_jargon"]
    response = (
        "方案对比：\n\n"
        "| 方案 | 描述 |\n"
        "|---|---|\n"
        "| A | 用 retrieval 加 reranker 做精排，比 baseline 强 |\n"
        "| B | 用 transformer encoder 加 attention 做 embedding |\n"
    )
    hit = fn(response=response)
    assert hit is not None, "表格 cell 里堆 3+ 个 jargon 真话术应拦"


def test_chinese_plain_jargon_in_table_cell_exempted():
    """markdown 表格 cell 里的 jargon 是结构性引用不算 jargon 话术。

    v0.4.15 dogfooding 触发：上一 turn 末尾我写表格 `| 1 | 答 embedding 问
    | ... |` 里 embedding 被 jargon 扫错算违反。表格行已经在算 ratio 时被
    `_TABLE_ROW_RE` 剥，但 jargon 扫描没用 natural_for_ratio。fix：jargon
    扫描也用 natural_for_ratio 让表格 cell 里的 jargon 豁免。
    """
    fn = REGISTRY["chinese_plain_no_jargon"]
    response = (
        "最终交付清单：\n\n"
        "| # | 工作 | 证据 |\n"
        "|---|---|---|\n"
        "| 1 | 答 embedding 问 | karma v2 代码里只 3 处全是反例 |\n"
        "| 2 | retrieval 治理候选 | 跟 deep-fix 同根因 |\n"
    )
    hit = fn(response=response)
    assert hit is None, f"表格 cell 里的 jargon 引用是结构性数据不该命中: {hit}"


def test_chinese_plain_jargon_outside_table_still_caught():
    """对偶守护：表格外的真 jargon 仍命中。"""
    fn = REGISTRY["chinese_plain_no_jargon"]
    response = "我们用 retrieval 做检索效果不错。" * 3
    hit = fn(response=response)
    assert hit is not None, "表格外的真 jargon retrieval 应命中"
    assert "retrieval" in str(hit.trigger)


def test_chinese_plain_kebab_snake_idents_not_counted():
    """项目专有标识符 kebab-case / snake_case（chinese-plain / force_block / karma-v1）
    是 code identifier 不是自然语言 jargon — 算 ratio 时剥。

    dogfooding 实测第 6 次触发：karma 自己的发布报告里大量提自家 sticky_id
    / 规则名 / 仓库代号，被算成英文 token 拉低中文比例。
    """
    fn = REGISTRY["chinese_plain_no_jargon"]
    response = (
        "v0.4.10 发布 + karma-v1 永久归档完成。\n"
        "**v0.4.10**: chinese-plain 剥版本号 / markdown / emoji 后修掉累积 5 次 force_block 假阳。\n"
        "**karma-v1**: 已 `gh repo archive` 永久归档，readonly 状态。\n"
        "后续 sticky_id 报错时让同事贴 git remote -v 输出。"
    )
    hit = fn(response=response)
    assert hit is None, f"kebab/snake 标识符不该算英文 jargon: {hit}"


def test_chinese_plain_markdown_emphasis_not_counted():
    """markdown emphasis 标记（** * ~~）不算自然语言字符。

    v0.4.40 fixture 改：原 fixture 含 5 次「真」前缀堆叠会触发新 Check 3 同前缀
    重复检测（dogfooding 真抓住测试 fixture 自己），改成不堆前缀的等效场景。
    """
    fn = REGISTRY["chinese_plain_no_jargon"]
    response = (
        "**深挖找到关键问题**（不是瞎扯也不是猜想）：\n\n"
        "**这两类区分清楚**：\n"
        "- **codex Desktop App**：你这几天一直在用\n"
        "- **codex CLI**：装着但几乎没有跑过\n"
    )
    hit = fn(response=response)
    assert hit is None, f"markdown 加粗标记不该拉低中文比例: {hit}"


def test_chinese_plain_real_jargon_still_blocked():
    """对偶：URL/表格剥不能让真 jargon 漏报。"""
    fn = REGISTRY["chinese_plain_no_jargon"]
    response = (
        "使用 retrieval embedding tokenizer hyperparameter softmax "
        "orchestrator dispatcher 实现 baseline。"
    )
    hit = fn(response=response)
    assert hit is not None, "真 jargon 仍要拦"


def test_v0440_dotted_identifier_not_counted():
    """v0.4.40: 含点号的工程标识符（module.attr / file.py / state.model）不算
    自然语言中英比的英文部分 — 让 ratio 反映 Agent 自然表达不被工程文本污染。
    """
    fn = REGISTRY["chinese_plain_no_jargon"]
    response = (
        "我刚改了 pre_tool_use.py 的 state.model 字段，调用 extract_model_from_transcript() "
        "拿到了模型，karma.hooks.session_start 也写了 state，全跑通。"
    )
    hit = fn(response=response)
    # 含 5 个点号标识符 + 自然中文 — 算 ratio 时点号标识符剥后中文比应 ≥ 40%
    assert hit is None, f"含点号工程标识符不该拉低中文比: {hit}"


def test_v0440_path_literal_not_counted():
    """v0.4.40: 路径字面（/path / ~/.claude）不算自然语言英文。"""
    fn = REGISTRY["chinese_plain_no_jargon"]
    response = (
        "我看了 ~/.claude/karma/session-state/abc.json 里的字段，又查了 "
        "/Users/jhz/karma/karma/checks/chinese_plain.py 的实施，发现都对。"
    )
    hit = fn(response=response)
    assert hit is None, f"路径字面不该拉低中文比: {hit}"


def test_v0440_repeated_prefix_check_catches_zhen_zi_kuangmo():
    """v0.4.40 Check 3: 同前缀「真X」≥ 5 次/response 触发自审（治理「真字
    狂魔」副作用 — sticky #4 + sticky #1 叠加效应根因）。"""
    fn = REGISTRY["chinese_plain_no_jargon"]
    response = (
        "经过真分析找到原因，复现脚本生效，闭环架构真完整，"
        "真效果对比真清晰，证据真齐。"
    )
    hit = fn(response=response)
    assert hit is not None, "5+ 次「真X」前缀堆叠违反"
    assert "真" in hit.trigger, f"trigger 应识别「真」前缀: {hit.trigger}"


def test_v0440_repeated_common_word_not_triggered():
    """v0.4.40 Check 3 对偶：高频汉字「不/我/你/在」等不算防御性堆叠。"""
    fn = REGISTRY["chinese_plain_no_jargon"]
    response = (
        "我去测试，我看代码，我跑命令，我改文件，我又验证一次，我再 commit 一下，全过了。"
    )
    hit = fn(response=response)
    # 「我」是合理高频前缀字（白名单豁免）— 不该当防御性堆叠
    assert hit is None, f"高频汉字不该当防御性堆叠: {hit}"


def test_chinese_plain_jargon_in_parenthesis_list_exempted():
    """jargon 在括号列表里（描述 jargon 不是用 jargon）→ 豁免。
    例：「扩通用编程词（mutex / orchestrator / dispatcher / observer）」
    用户在列举 jargon，不是堆 jargon 跟用户交流。"""
    fn = REGISTRY["chinese_plain_no_jargon"]
    response = "扩通用编程词（mutex / orchestrator / dispatcher / observer），加进 jargon 列表。"
    hit = fn(response=response)
    assert hit is None, "括号内列举的 jargon 是描述不是堆词，应豁免"


def test_chinese_plain_jargon_with_explanation_passes():
    """术语后跟中文解释 → 豁免。"""
    fn = REGISTRY["chinese_plain_no_jargon"]
    response = "这个用 precision (精度) 和 recall (召回率) 两个指标看，我会先优化精度。"
    hit = fn(response=response)
    # 后跟「精度」「召回率」中文，应该豁免
    assert hit is None or "ratio" in hit.trigger.lower()


def test_chinese_plain_jargon_no_explanation_fails():
    fn = REGISTRY["chinese_plain_no_jargon"]
    response = "这个 oracle 不行，咱们换 supervisor 试试，看 paradigm 是不是更好"
    hit = fn(response=response)
    assert hit is not None


def test_chinese_plain_ignores_code_block():
    fn = REGISTRY["chinese_plain_no_jargon"]
    response = "好的，跑这段代码就行：\n```python\ndef f(): return precision_recall(x)\n```\n看输出就知道了。"
    hit = fn(response=response)
    # code block 内的 English 不算
    assert hit is None


# -------- #4 loud-failure-with-evidence --------

def test_evidence_completion_without_test_fails():
    fn = REGISTRY["loud_failure_with_evidence"]
    state = SessionState(session_id="s1")  # 没 test pass 记录
    hit = fn(response="搞定了，已经修复完成", session_state=state)
    assert hit is not None
    assert "证据" in hit.trigger or "完成" in hit.trigger


def test_evidence_completion_with_test_passes():
    fn = REGISTRY["loud_failure_with_evidence"]
    state = SessionState(session_id="s1")
    state.record_bash("pytest tests/", "===== 10 passed in 0.3s =====")
    hit = fn(response="搞定了，已经修复完成", session_state=state)
    assert hit is None


def test_evidence_weak_claim_in_code_context_fails():
    """weak claim 出现在「代码任务行为词」附近 → 拦。"""
    fn = REGISTRY["loud_failure_with_evidence"]
    state = SessionState(session_id="s1")
    hit = fn(response="修复完了，代码应该可以了，应该没问题", session_state=state)
    assert hit is not None


def test_evidence_weak_claim_in_chitchat_passes():
    """weak claim 闲聊语境（无代码任务行为词）→ 不拦，避免日常对话假阳。"""
    fn = REGISTRY["loud_failure_with_evidence"]
    state = SessionState(session_id="s1")
    hit = fn(response="这个方向应该可以，慢慢来", session_state=state)
    assert hit is None


def test_evidence_completion_in_chitchat_passes():
    """完成词在非代码任务语境 → 不拦。

    例：「先告一段落」「这事告一个完成了」等不针对代码任务的完成话语。
    """
    fn = REGISTRY["loud_failure_with_evidence"]
    state = SessionState(session_id="s1")
    hit = fn(response="今天先告一段落，明天再聊", session_state=state)
    assert hit is None


def test_evidence_git_commit_without_test_fails():
    fn = REGISTRY["loud_failure_with_evidence"]
    state = SessionState(session_id="s1")
    hit = fn(
        tool_name="Bash",
        tool_input={"command": "git commit -m 'fix'"},
        session_state=state,
    )
    assert hit is not None
    assert "commit" in hit.trigger.lower() or "证据" in hit.trigger


def test_evidence_docs_commit_exempted():
    """conventional commit `docs:` / `chore:` 不需要测试证据（非代码 commit）。"""
    fn = REGISTRY["loud_failure_with_evidence"]
    state = SessionState(session_id="s1")  # 没 test pass
    # docs commit 豁免
    hit = fn(
        tool_name="Bash",
        tool_input={"command": 'git commit -m "docs: update README"'},
        session_state=state,
    )
    assert hit is None
    # chore commit 豁免
    hit = fn(
        tool_name="Bash",
        tool_input={"command": 'git commit -m "chore(deps): bump version"'},
        session_state=state,
    )
    assert hit is None
    # 但 feat: / fix: 仍需测试证据
    hit = fn(
        tool_name="Bash",
        tool_input={"command": 'git commit -m "feat: 加新功能"'},
        session_state=state,
    )
    assert hit is not None


def test_evidence_git_commit_with_test_passes():
    fn = REGISTRY["loud_failure_with_evidence"]
    state = SessionState(session_id="s1")
    state.record_bash("pytest", "5 passed")
    hit = fn(
        tool_name="Bash",
        tool_input={"command": "git commit -m 'fix'"},
        session_state=state,
    )
    assert hit is None


def test_evidence_chained_pytest_commit_exempted():
    """`pytest && git commit` 链式调用 — pre_tool_use 时 pytest 还没跑，
    has_recent_test=False 会误拦。命令骨架含测试命令应视为「即时证据」豁免。

    v0.4.14 dogfooding 触发：commit v0.4.13 release 时 `pytest && git commit`
    链被错拦。
    """
    fn = REGISTRY["loud_failure_with_evidence"]
    state = SessionState(session_id="s2")  # 空 state, has_recent_test=False
    hit = fn(
        tool_name="Bash",
        tool_input={"command": ".venv/bin/python -m pytest tests/ -q && git add -A && git commit -m 'fix: stuff'"},
        session_state=state,
    )
    assert hit is None, "pytest 在同一 Bash 链路里先跑应豁免 evidence 拦截"


def test_evidence_heredoc_chore_commit_exempted():
    """heredoc / $(cat <<EOF) 包裹的 conventional commit prefix 也应豁免。

    v0.4.14 dogfooding 触发：`git commit -m "$(cat <<'EOF'\\nchore(release):
    ...\\nEOF\\n)"` 被错拦（_NON_CODE_COMMIT_PREFIX_RE 只识别紧邻引号形式）。
    """
    fn = REGISTRY["loud_failure_with_evidence"]
    state = SessionState(session_id="s3")
    cmd = (
        "git add scripts/x.sh && git commit -m \"$(cat <<'EOF'\n"
        "chore(release): scripts/verify-installed.sh 防发版后忘装本机\n"
        "EOF\n)\""
    )
    hit = fn(tool_name="Bash", tool_input={"command": cmd}, session_state=state)
    assert hit is None, "heredoc 包裹的 chore(release): 应被 conventional prefix 豁免"


def test_evidence_pytest_in_commit_msg_not_exempted():
    """commit message 字面提到 pytest 不算跑（防误豁免）。

    `_CHAINED_TEST_RE` 扫 strip 后的骨架，commit message 引号字面里的 pytest
    被剥掉，不会误豁免「假声称跑过测试」类。
    """
    fn = REGISTRY["loud_failure_with_evidence"]
    state = SessionState(session_id="s4")
    hit = fn(
        tool_name="Bash",
        tool_input={"command": "git commit -m \"fix: improve pytest fixture\""},
        session_state=state,
    )
    assert hit is not None, "commit message 字面提 pytest 不算跑，应命中"


# -------- #5 no-testset-no-future-leakage --------

def test_testset_detects_gold_cases_append():
    fn = REGISTRY["no_testset_no_future_leakage"]
    hit = fn(
        tool_name="Write",
        tool_input={"content": "gold_cases.append(new_case_from_eval)"},
    )
    assert hit is not None


def test_testset_detects_cross_split_cp():
    fn = REGISTRY["no_testset_no_future_leakage"]
    hit = fn(
        tool_name="Bash",
        tool_input={"command": "cp eval/cache/*.json train/cache/"},
    )
    assert hit is not None
    assert "split" in hit.trigger or "eval" in hit.trigger or "test" in hit.trigger.lower()


def test_testset_detects_split_boundary_hardcode():
    fn = REGISTRY["no_testset_no_future_leakage"]
    hit = fn(
        tool_name="Edit",
        tool_input={"new_string": "if turn_idx >= 400: skip"},
    )
    assert hit is not None


def test_testset_clean_code_passes():
    fn = REGISTRY["no_testset_no_future_leakage"]
    hit = fn(tool_name="Write", tool_input={"content": "def foo(): return train_data"})
    assert hit is None


def test_testset_long_hash_in_if_blocked():
    """长 hash 字面在 if 比较里 → 拦（测试集 case ID 写死）。"""
    fn = REGISTRY["no_testset_no_future_leakage"]
    hit = fn(
        tool_name="Edit",
        tool_input={
            "file_path": "/x/src/handler.py",
            "new_string": 'if turn_id == "a1b2c3d4e5f6a7b8":\n    return special',
        },
    )
    assert hit is not None
    assert "hash" in hit.trigger.lower() or "UUID" in hit.trigger or "case" in hit.trigger.lower()


def test_testset_long_hash_in_log_passes():
    """长 hex 字面在 log 调用 / 普通赋值里 → 不拦（合法日志字段 / commit hash 引用）。"""
    fn = REGISTRY["no_testset_no_future_leakage"]
    hit = fn(
        tool_name="Write",
        tool_input={
            "file_path": "/x/src/handler.py",
            "content": 'logger.info("commit: a1b2c3d4e5f6a7b8")\ncommit_hash = "a1b2c3d4e5f6a7b8"',
        },
    )
    assert hit is None


def test_testset_case_id_assignment_blocked():
    """case_id = "hash" 赋值 → 拦（测试 ID 写死）。"""
    fn = REGISTRY["no_testset_no_future_leakage"]
    hit = fn(
        tool_name="Edit",
        tool_input={
            "file_path": "/x/src/runner.py",
            "new_string": 'case_id = "a1b2c3d4e5f6a7b8"',
        },
    )
    assert hit is not None


def test_testset_python_c_string_literal_exempted():
    """v0.5.5：python -c "..." 内含 gold_cases.append 字面是字符串数据不是执行 — 豁免。

    v0.5.3 dogfooding 触发：probe 脚本里 `python -c "r = check(content='gold_cases.append(x)')"`
    被错算执行意图. 跟 non_blocking sleep / bypass_karma write 同根因 fix.
    """
    fn = REGISTRY["no_testset_no_future_leakage"]
    hit = fn(
        tool_name="Bash",
        tool_input={
            "command": 'python -c "r = check(content=\'gold_cases.append(x)\')"',
        },
    )
    assert hit is None, f"python -c 内字面应豁免, 拦: {hit}"


def test_testset_real_bash_reverse_feed_still_blocked():
    """v0.5.5：python -c 豁免不能漏拦真 bash 反喂（直接调用，非 -c 内）。"""
    fn = REGISTRY["no_testset_no_future_leakage"]
    hit = fn(
        tool_name="Bash",
        tool_input={"command": "cp eval/cache/x.json train/cache/"},
    )
    assert hit is not None


def test_testset_v058_heredoc_to_tests_path_exempted():
    """v0.5.8: cat heredoc 写到 tests/ 路径豁免 — heredoc 内容是测试代码字面.

    dogfooding v0.5.7 触发: tests/test_checks.py append 回归测试时 heredoc 内
    `case_id = "<hash>"` 字面被错拦. 跟 v0.5.5 python -c 同根因 — 字面是描述
    性测试代码不是执行.
    """
    fn = REGISTRY["no_testset_no_future_leakage"]
    cmd = (
        "cat >> /Users/x/proj/tests/test_checks.py <<'PY'\n"
        "def test_x():\n"
        "    " + "case" + "_id = \"a1b2c3d4e5f6a7b8\"\n"
        "PY"
    )
    hit = fn(tool_name="Bash", tool_input={"command": cmd})
    assert hit is None, f"heredoc 写 tests/ 应豁免, 拦: {hit}"


def test_testset_v058_heredoc_to_md_doc_exempted():
    """v0.5.8: heredoc 写到 .md 文档路径豁免."""
    fn = REGISTRY["no_testset_no_future_leakage"]
    cmd = (
        "cat >> docs/CHANGELOG.md <<'MD'\n"
        "示例 case " + "_id 写法: " + "case_id = \"a1b2c3d4e5f6a7b8\"\n"
        "MD"
    )
    hit = fn(tool_name="Bash", tool_input={"command": cmd})
    assert hit is None


def test_testset_v058_heredoc_to_src_still_blocked():
    """v0.5.8 对偶: heredoc 写到非 description context 路径 (src/ 类) 仍拦."""
    fn = REGISTRY["no_testset_no_future_leakage"]
    cmd = (
        "cat >> src/runner.py <<'PY'\n"
        "" + "case_id = \"a1b2c3d4e5f6a7b8\"\n"
        "PY"
    )
    hit = fn(tool_name="Bash", tool_input={"command": cmd})
    assert hit is not None, "src/ 路径不该被豁免"


# -------- #8 read-before-write --------

def test_read_first_denies_unread_edit():
    fn = REGISTRY["read_before_write"]
    state = SessionState(session_id="s1")  # 没读过任何文件
    hit = fn(
        tool_name="Edit",
        tool_input={"file_path": "/tmp/abc.py", "old_string": "x", "new_string": "y"},
        session_state=state,
    )
    assert hit is not None
    assert "Read" in hit.trigger or "/tmp/abc.py" in hit.trigger


def test_read_first_allows_after_read():
    fn = REGISTRY["read_before_write"]
    state = SessionState(session_id="s1")
    state.record_read("/tmp/abc.py")
    hit = fn(
        tool_name="Edit",
        tool_input={"file_path": "/tmp/abc.py", "old_string": "x", "new_string": "y"},
        session_state=state,
    )
    assert hit is None


def test_read_first_allows_write_new_file(tmp_path):
    """Write 全新（不存在）文件豁免。"""
    fn = REGISTRY["read_before_write"]
    state = SessionState(session_id="s1")
    new_file = tmp_path / "brand_new.py"  # 不存在
    hit = fn(
        tool_name="Write",
        tool_input={"file_path": str(new_file), "content": "x = 1"},
        session_state=state,
    )
    assert hit is None


def test_read_first_denies_write_existing_unread(tmp_path):
    """Write 已存在的文件但没读过 → deny。"""
    fn = REGISTRY["read_before_write"]
    state = SessionState(session_id="s1")
    existing = tmp_path / "existing.py"
    existing.write_text("# existing")
    hit = fn(
        tool_name="Write",
        tool_input={"file_path": str(existing), "content": "# overwrite"},
        session_state=state,
    )
    assert hit is not None


def test_read_first_ignores_non_edit_tool():
    fn = REGISTRY["read_before_write"]
    state = SessionState(session_id="s1")
    hit = fn(
        tool_name="Bash",
        tool_input={"command": "ls"},
        session_state=state,
    )
    assert hit is None


# -------- run_checks 注册表测试 --------

def test_run_checks_unknown_function_silently_skipped():
    """sticky.yaml 写错 check 名应该静默跳过，不要 crash hook。"""
    hits = run_checks(
        ["nonexistent_check_name"],
        tool_name="Bash",
        tool_input={"command": "sleep 30"},
    )
    assert hits == []


def test_run_checks_multiple_hits():
    """一次 tool 调用可能命中多个 sticky 的 check。"""
    hits = run_checks(
        ["long_term_fundamental", "non_blocking_parallel"],
        tool_name="Bash",
        tool_input={"command": 'git commit --no-verify -m "quick fix"'},
    )
    assert len(hits) >= 1
    assert any(h.rule_id == "long-term-fundamental" for h in hits)


def test_run_checks_check_exception_silently_swallowed_by_default(monkeypatch, capsys):
    """check 函数抛异常默认 fail open 静默吞错（不阻塞 hook）— 但 stderr 应该
    什么都不打（避免污染 hook 输出）。"""
    from karma.checks import REGISTRY

    def _bad_check(**_):
        raise RuntimeError("intentional test failure")

    monkeypatch.setitem(REGISTRY, "_bad_test_check", _bad_check)
    monkeypatch.delenv("KARMA_DEBUG", raising=False)
    hits = run_checks(["_bad_test_check"])
    assert hits == []
    captured = capsys.readouterr()
    assert "intentional test failure" not in captured.err, "默认不该打 traceback"


def test_run_checks_check_exception_prints_traceback_under_debug(monkeypatch, capsys):
    """KARMA_DEBUG=1 时 check 抛异常打 traceback 到 stderr — 评审 A Agent 建议
    的调试门控（让用户能 debug 自定义 check / karma 内部 bug 不黑盒）。"""
    from karma.checks import REGISTRY

    def _bad_check(**_):
        raise RuntimeError("intentional test failure")

    monkeypatch.setitem(REGISTRY, "_bad_test_check2", _bad_check)
    monkeypatch.setenv("KARMA_DEBUG", "1")
    hits = run_checks(["_bad_test_check2"])
    assert hits == []
    captured = capsys.readouterr()
    assert "intentional test failure" in captured.err
    assert "RuntimeError" in captured.err


def test_run_checks_unknown_name_prints_under_debug(monkeypatch, capsys):
    """KARMA_DEBUG=1 时未知 check 名也打提示 — sticky.yaml 写错时能立刻发现。"""
    monkeypatch.setenv("KARMA_DEBUG", "1")
    hits = run_checks(["nonexistent_xyz_check"])
    assert hits == []
    captured = capsys.readouterr()
    assert "nonexistent_xyz_check" in captured.err


# -------- v0.5.7 CheckHit / Violation trigger_key roundtrip --------

def test_v057_check_hits_carry_trigger_key():
    """所有 check 函数返回 CheckHit 时 trigger_key 字段非空 (locale-agnostic 分组用)."""
    state = SessionState(session_id="s1")
    probes = [
        ("loud_failure_with_evidence",
         {"tool_name": "Bash", "tool_input": {"command": "git commit -m 'feat: x'"}, "session_state": state}),
        ("non_blocking_parallel",
         {"tool_name": "Bash", "tool_input": {"command": "sleep 30"}}),
        ("read_before_write",
         {"tool_name": "Edit", "tool_input": {"file_path": "/x/y.py", "old_string": "a", "new_string": "b"},
          "session_state": state}),
        ("long_term_fundamental",
         {"tool_name": "Write", "tool_input": {"file_path": "/x/y.py",
                                                "content": "def f():\n    # T" + "ODO: fix\n    return 1\n"}}),
    ]
    for rule_id, kwargs in probes:
        fn = REGISTRY[rule_id]
        hit = fn(**kwargs)
        assert hit is not None, f"{rule_id} 探针应命中但 NONE"
        assert hit.trigger_key, f"{rule_id} CheckHit.trigger_key 不该空: {hit}"
        assert hit.trigger_key.startswith("check."), f"{rule_id} trigger_key 应是 i18n key 格式: {hit.trigger_key!r}"


def test_v057_violation_roundtrip_trigger_key():
    """Violation 写 jsonl + 读回 trigger_key 字段保留."""
    import json
    import tempfile
    from pathlib import Path
    from karma.violations import Violation, load_all

    v = Violation(
        ts=1700000000,
        session_id="s1",
        rule_id="loud-failure-with-evidence",
        trigger="No recent passing-test evidence",
        snippet="git commit -m foo",
        turn=5,
        trigger_key="check.evidence.commit.trigger",
    )
    payload = json.loads(v.to_json())
    assert payload["trigger_key"] == "check.evidence.commit.trigger"

    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "violations.jsonl"
        p.write_text(v.to_json() + "\n", encoding="utf-8")
        loaded = load_all(p)
        assert len(loaded) == 1
        assert loaded[0].trigger_key == "check.evidence.commit.trigger"


def test_v057_violation_backward_compat_no_trigger_key():
    """老 jsonl 行无 trigger_key 字段 → load_all 默认 ''，不该崩."""
    import json
    import tempfile
    from pathlib import Path
    from karma.violations import load_all

    legacy_line = json.dumps({
        "ts": 1600000000,
        "session_id": "s_old",
        "rule_id": "non-blocking-parallel",
        "trigger": "Bash sleep cmd",
        "snippet": "sleep 5",
        "turn": 1,
    }, ensure_ascii=False)

    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "violations.jsonl"
        p.write_text(legacy_line + "\n", encoding="utf-8")
        loaded = load_all(p)
        assert len(loaded) == 1
        assert loaded[0].trigger_key == ""
        assert loaded[0].trigger == "Bash sleep cmd"


def test_v057_audit_groups_by_trigger_key_across_locales():
    """audit 按 trigger_key 分组合并 — zh/en locale 同 key 的 trigger 字面被算成一组."""
    from collections import Counter
    from karma.violations import Violation

    violations = []
    for _ in range(5):
        violations.append(Violation(
            ts=1700000000, session_id="s1", rule_id="loud-failure-with-evidence",
            trigger="git commit 前最近 session 内无测试通过证据",
            snippet="git commit", turn=1,
            trigger_key="check.evidence.commit.trigger",
        ))
    for _ in range(5):
        violations.append(Violation(
            ts=1700000001, session_id="s1", rule_id="loud-failure-with-evidence",
            trigger="No recent passing-test evidence in session before git commit",
            snippet="git commit", turn=2,
            trigger_key="check.evidence.commit.trigger",
        ))

    by_sticky: dict[str, Counter] = {}
    for v in violations:
        group_key = v.trigger_key or v.trigger
        by_sticky.setdefault(v.rule_id, Counter())[group_key] += 1

    ctr = by_sticky["loud-failure-with-evidence"]
    assert len(ctr) == 1, f"同 trigger_key 应合并: {dict(ctr)}"
    assert ctr["check.evidence.commit.trigger"] == 10


def test_v057_audit_legacy_no_key_fallback_to_trigger():
    """audit 老数据无 trigger_key → fallback 按 trigger 字面分组保兼容."""
    from collections import Counter
    from karma.violations import Violation
    violations = [
        Violation(ts=1, session_id="s", rule_id="r", trigger="legacy A", snippet="x", turn=1),
        Violation(ts=2, session_id="s", rule_id="r", trigger="legacy A", snippet="x", turn=2),
        Violation(ts=3, session_id="s", rule_id="r", trigger="legacy B", snippet="x", turn=3),
    ]
    by_sticky: dict[str, Counter] = {}
    for v in violations:
        group_key = v.trigger_key or v.trigger
        by_sticky.setdefault(v.rule_id, Counter())[group_key] += 1
    ctr = by_sticky["r"]
    assert ctr["legacy A"] == 2
    assert ctr["legacy B"] == 1
