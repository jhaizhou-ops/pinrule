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


def test_long_term_detects_no_verify():
    fn = REGISTRY["long_term_fundamental"]
    hit = fn(
        tool_name="Bash",
        tool_input={"command": "git commit --no-verify -m 'msg'"},
    )
    assert hit is not None
    assert "verify" in hit.trigger.lower() or "skip" in hit.trigger.lower() or "force" in hit.trigger.lower()


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


# -------- #2 non-blocking-parallel --------

def test_non_blocking_detects_sleep():
    fn = REGISTRY["non_blocking_parallel"]
    hit = fn(tool_name="Bash", tool_input={"command": "sleep 30"})
    assert hit is not None
    assert "sleep" in hit.trigger


def test_non_blocking_detects_long_task_no_background():
    fn = REGISTRY["non_blocking_parallel"]
    hit = fn(tool_name="Bash", tool_input={"command": "pytest tests/", "run_in_background": False})
    assert hit is not None
    assert "background" in hit.trigger or "pytest" in hit.trigger


def test_non_blocking_long_task_with_background_passes():
    fn = REGISTRY["non_blocking_parallel"]
    hit = fn(tool_name="Bash", tool_input={"command": "pytest tests/", "run_in_background": True})
    assert hit is None


def test_non_blocking_ignores_non_bash():
    fn = REGISTRY["non_blocking_parallel"]
    hit = fn(tool_name="Write", tool_input={"content": "sleep is a function"})
    assert hit is None


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


def test_evidence_weak_claim_without_test_fails():
    fn = REGISTRY["loud_failure_with_evidence"]
    state = SessionState(session_id="s1")
    hit = fn(response="应该可以了，应该没问题", session_state=state)
    assert hit is not None


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
