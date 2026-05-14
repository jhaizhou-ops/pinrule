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
    assert hit.sticky_id == "long-term-fundamental"
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
    """commit message 长描述区里讨论 hack/quick-fix 概念 → 不算真违反。

    真违反是「字眼作为 commit 主语」（前 80 字内），不是长描述里偶然提到。
    """
    fn = REGISTRY["long_term_fundamental"]
    # 字眼在描述区（120 字之后）— 不算真违反
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
    assert hit is None, "commit message 后部讨论字眼不该被认成真违反"


def test_long_term_commit_message_subject_quick_fix_blocked():
    """commit message 主语区（80 字内）含 hack 词 → 真违反，拦。"""
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
    """Write 文档里描述 --no-verify 字面（不是真要跑）→ 不该拦。"""
    fn = REGISTRY["long_term_fundamental"]
    content = "# karma 检测规则\n这条规则会拦截 --no-verify、--skip、--force 等 flag。"
    hit = fn(tool_name="Write", tool_input={"file_path": "/tmp/doc.md", "content": content})
    assert hit is None


def test_long_term_bash_with_no_verify_blocked():
    """Bash 真跑 --no-verify → 该拦。"""
    fn = REGISTRY["long_term_fundamental"]
    hit = fn(tool_name="Bash", tool_input={"command": "git commit --no-verify -m 'fix'"})
    assert hit is not None
    assert "验证" in hit.trigger or "verify" in hit.trigger.lower() or "skip" in hit.trigger.lower()


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
    # 真长任务（docker run / build）— 不带 background 命中
    hit = fn(tool_name="Bash", tool_input={"command": "docker compose up", "run_in_background": False})
    assert hit is not None
    assert "background" in hit.trigger or "docker" in hit.trigger.lower()


def test_non_blocking_long_task_with_background_passes():
    fn = REGISTRY["non_blocking_parallel"]
    hit = fn(tool_name="Bash", tool_input={"command": "docker compose up", "run_in_background": True})
    assert hit is None


def test_non_blocking_test_commands_not_long_task():
    """pytest / jest 等测试命令默认不算长任务（多数项目跑得快 < 5s），
    避免 audit 指出的高频假阳。真长测试用户自加 background。"""
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
    # 真要跑 docker run 仍命中
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
    # 但 heredoc **外**（命令头）真长任务仍命中
    cmd_with_docker = """docker compose up <<'EOF'
some input
EOF"""
    hit = fn(tool_name="Bash", tool_input={"command": cmd_with_docker})
    assert hit is not None, "heredoc 外命令头真长任务仍是真执行"


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
    """长 hash 字面在 if 比较里 → 拦（真测试集 case ID 写死）。"""
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
    assert any(h.sticky_id == "long-term-fundamental" for h in hits)
