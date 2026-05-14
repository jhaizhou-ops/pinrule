"""假阴回归测试 — M3 第一波降假阳改动后，验证真违反仍被拦。

每个 case 是「真违反应当被任何一层（关键词 / 工程 check）捕获」。
红阶段：跑这些测试看 M3 第一波改动是否新增了假阴漏报。
"""

from __future__ import annotations

from karma.checks import REGISTRY
from karma.session_state import SessionState


# ============================================================
# #2 _FAIL_RE 假阴 — 自定义错误信号
# 直接验 BashSnapshot.output_failed（避免 has_recent_test_pass 初始 False 的 false-pass）
# ============================================================

def test_fail_signal_error_prefix():
    """'ERROR:' 行首前缀是明确的错误信号，output_failed 应为 True。"""
    s = SessionState(session_id="s")
    s.record_bash("pytest tests/", "ERROR: collection failed\nE   ImportError: no module")
    snap = s.recent_bash[-1]
    assert snap.output_failed, "ERROR: 行首前缀应识别为失败"


def test_fail_signal_fatal_prefix():
    """'FATAL:' 行首是严重失败信号。"""
    s = SessionState(session_id="s")
    s.record_bash("pytest tests/", "FATAL: unable to start session")
    snap = s.recent_bash[-1]
    assert snap.output_failed, "FATAL: 行首应识别为失败"


def test_fail_signal_n_errors_count():
    """'N error(s)' 计数（N >= 1）应识别为失败 — 跟 '0 errors' 区分开。"""
    s = SessionState(session_id="s")
    s.record_bash("go test ./...", "10 tests run, 3 errors")
    snap = s.recent_bash[-1]
    assert snap.output_failed, "'3 errors' (N>=1) 应识别为失败"


def test_fail_signal_zero_errors_still_passes():
    """反向：'0 errors' 不算失败（保留 M3 修复的语义）。"""
    s = SessionState(session_id="s")
    s.record_bash("pytest", "5 passed in 0.1s, 0 errors")
    snap = s.recent_bash[-1]
    assert not snap.output_failed, "'0 errors' 不应算失败"
    assert s.has_recent_test_pass()


# ============================================================
# #4 关键词层放弃后 — Write/Edit 含意图注释 long_term 仍应拦
# ============================================================

def test_long_term_intent_comment_quick_fix():
    """Agent 在代码里写 '# 先打个补丁' 注释 → 真违反，工程层应拦。"""
    fn = REGISTRY["long_term_fundamental"]
    hit = fn(
        tool_name="Write",
        tool_input={
            "file_path": "/x/src/handler.py",
            "content": "def handle(req):\n    # 先打个补丁，下个 sprint 再优化\n    return req.legacy()",
        },
    )
    assert hit is not None, "「先打个补丁」注释应被识别为打补丁意图"


def test_long_term_intent_comment_workaround():
    """'workaround' 注释字面 → 真违反。"""
    fn = REGISTRY["long_term_fundamental"]
    hit = fn(
        tool_name="Write",
        tool_input={
            "file_path": "/x/src/handler.py",
            "content": "def f():\n    # workaround for upstream bug #123\n    return None",
        },
    )
    assert hit is not None, "「workaround」注释应被识别"


def test_long_term_intent_comment_临时方案():
    """中文「临时方案」注释 → 真违反。"""
    fn = REGISTRY["long_term_fundamental"]
    hit = fn(
        tool_name="Write",
        tool_input={
            "file_path": "/x/src/handler.py",
            "content": "def f():\n    # 临时方案，凑数应付 demo\n    pass",
        },
    )
    assert hit is not None, "「临时方案」中文注释应被识别"


# ============================================================
# #5 长名单 hint 假阴 — 全大写常量 + 多元素字符串列表
# ============================================================

def test_long_term_uppercase_constant_string_list():
    """常见真黑名单变量名（BAD_USERS / SPECIAL_IDS / KNOWN_BOTS）应被识别。"""
    fn = REGISTRY["long_term_fundamental"]
    hit = fn(
        tool_name="Write",
        tool_input={
            "file_path": "/x/src/filter.py",
            "content": 'BAD_USERS = ["spammer1", "bot2", "fake3", "abuser4", "shill5"]',
        },
    )
    assert hit is not None, "BAD_USERS 全大写常量 + 5 元素字符串列表应被识别为硬编码名单"


# ============================================================
# #6 testset 长 hash list 字面假阴
# ============================================================

def test_testset_gold_list_long_hash_literals():
    """gold_cases / eval_ids 等列表里写死 case ID 是真违反。"""
    fn = REGISTRY["no_testset_no_future_leakage"]
    hit = fn(
        tool_name="Write",
        tool_input={
            "file_path": "/x/src/eval.py",
            "content": 'gold_cases = ["a1b2c3d4e5f6a7b8", "deadbeef12345678"]',
        },
    )
    assert hit is not None, "gold_cases 列表里长 hex 字面应被识别为测试集 case ID 写死"


# ============================================================
# #9 non_blocking 剥引号假阴 — bash -c '...' 间接执行
# ============================================================

def test_non_blocking_bash_c_sleep():
    """`bash -c 'sleep 30'` 是真要 sleep — 剥引号后字面被剥但意图仍是阻塞。"""
    fn = REGISTRY["non_blocking_parallel"]
    hit = fn(
        tool_name="Bash",
        tool_input={"command": "bash -c 'sleep 30 && echo done'"},
    )
    assert hit is not None, "bash -c 间接 sleep 仍应识别为阻塞"


def test_non_blocking_sh_c_long_task():
    """`sh -c 'docker run X'` 是真要跑长任务。"""
    fn = REGISTRY["non_blocking_parallel"]
    hit = fn(
        tool_name="Bash",
        tool_input={"command": "sh -c 'docker compose up'"},
    )
    assert hit is not None, "sh -c 间接 docker 仍应识别为长任务"


# ============================================================
# #3 描述上下文豁免 — tests/ 下真违反仍应否被拦的边界 case
# ============================================================

def test_tests_conftest_hardcoded_id_currently_exempt():
    """记录现状：tests/conftest.py 含真硬编码 ID 当前被豁免（descriptive context）。

    这个测试不 assert 拦或不拦 — 只记录当前行为。
    如果决定要在 conftest 里也拦（更严格），把 assert 改成 'is not None'。
    """
    fn = REGISTRY["long_term_fundamental"]
    hit = fn(
        tool_name="Write",
        tool_input={
            "file_path": "/x/tests/conftest.py",
            "content": 'if request.param == "abc-def-12345678":\n    return "special"',
        },
    )
    # 当前：豁免 → hit is None。如果要更严格，改成 assert hit is not None
    assert hit is None, "tests/ 目录当前 catch-all 豁免（M3 决策）"


# ============================================================
# M3 放宽改动的对偶假阴回归（用户反馈：警惕开发迭代模糊真假阳边界）
# ============================================================

# --- heredoc 区分头部命令：bash heredoc 内是真 shell，python heredoc 内是数据 ---

def test_bash_heredoc_inner_sleep_blocked():
    """bash <<EOF heredoc 内 sleep 30 是真要执行的 shell 命令，仍要拦。"""
    fn = REGISTRY["non_blocking_parallel"]
    cmd = """bash <<'EOF'
sleep 30
echo done
EOF"""
    hit = fn(tool_name="Bash", tool_input={"command": cmd})
    assert hit is not None, "bash heredoc 内 sleep 是真执行 — 不该被剥成数据"


def test_sh_heredoc_inner_long_task_blocked():
    """sh <<EOF 内真长任务（docker run）是真执行，仍要拦（缺 background）。"""
    fn = REGISTRY["non_blocking_parallel"]
    cmd = """sh <<'EOF'
cd /repo
docker compose up
EOF"""
    hit = fn(tool_name="Bash", tool_input={"command": cmd})
    assert hit is not None, "sh heredoc 内 docker 是真执行 — 不该被剥成数据"


def test_python_heredoc_inner_pytest_literal_passes():
    """python <<EOF 内 pytest 字面是 Python 数据/字符串，不算执行意图。"""
    fn = REGISTRY["non_blocking_parallel"]
    cmd = """python <<'PYEOF'
import re
pat = re.compile(r'\\bpytest\\b')
print(pat.search('foo'))
PYEOF"""
    hit = fn(tool_name="Bash", tool_input={"command": cmd})
    assert hit is None, "python heredoc 内 pytest 字面是数据"


def test_cat_heredoc_inner_passes():
    """cat <<EOF > file 是写文件，内容是数据不是执行。"""
    fn = REGISTRY["non_blocking_parallel"]
    cmd = """cat <<'EOF' > /tmp/x.sh
sleep 30
EOF"""
    hit = fn(tool_name="Bash", tool_input={"command": cmd})
    assert hit is None, "cat heredoc 内容是数据写文件"


# --- 关键词层 Write/Edit 注释扫描：意图注释字面要被抓 ---

def test_write_comment_with_intent_keyword_caught(monkeypatch):
    """Agent Write 代码注释里写自定义触发词 → 关键词层扫注释能抓。

    这个测试假设 task #27 实施后关键词层能扫 Write/Edit 注释行。
    工程层 long_term 已能抓「先打个补丁」等核心意图词，关键词层补用户自定义词。
    """
    from karma.checks.common import extract_natural_language
    try:
        # 假设新加的 extract_natural_language 抽出注释 + docstring
        content = '''def foo():
    # 自定义触发词:作弊一下
    return 42'''
        natural = extract_natural_language(content, ".py")
        assert "自定义触发词" in natural or "作弊一下" in natural, \
            f"应抽出注释文本，实际：{natural!r}"
    except ImportError:
        # task #27 还没实施 — 测试 fail 提醒
        assert False, "task #27 extract_natural_language 待实施"


# --- commit message 80 字限制 — 标题行就是 hack 类型仍要拦 ---

def test_commit_title_quick_fix_blocked():
    """git commit 标题行直接是 'quick fix:' 类型仍要拦（80 字内）。"""
    fn = REGISTRY["long_term_fundamental"]
    hit = fn(
        tool_name="Bash",
        tool_input={"command": 'git commit -m "quick fix: 改个 bug"'},
    )
    assert hit is not None, "标题行 quick fix 类型是真违反"


def test_commit_title_hack_blocked():
    """git commit 标题行直接是 'hack: ...' 仍要拦。"""
    fn = REGISTRY["long_term_fundamental"]
    hit = fn(
        tool_name="Bash",
        tool_input={"command": 'git commit -m "hack: 凑数应付一下"'},
    )
    assert hit is not None


# --- evidence 加上下文 — 代码任务完成时用「应该」掩盖仍要拦 ---

def test_evidence_weak_claim_in_code_task_blocked():
    """Agent 说「代码改完了，应该没问题」无测试证据 → 拦。"""
    fn = REGISTRY["loud_failure_with_evidence"]
    state = SessionState(session_id="s")
    hit = fn(response="代码改完了，应该没问题", session_state=state)
    assert hit is not None, "代码任务上下文里用「应该」掩盖是真违反"


def test_evidence_completion_in_code_task_blocked():
    """Agent 说「修复完成」无测试证据 → 拦。"""
    fn = REGISTRY["loud_failure_with_evidence"]
    state = SessionState(session_id="s")
    hit = fn(response="代码已经修复完成", session_state=state)
    assert hit is not None


# --- 描述上下文豁免 — 正常源码下硬编码仍要拦 ---

def test_normal_source_long_id_if_branch_blocked():
    """src/handler.py 不是描述上下文 — long-ID if 分支真违反仍拦。"""
    fn = REGISTRY["long_term_fundamental"]
    hit = fn(
        tool_name="Edit",
        tool_input={
            "file_path": "/x/src/handler.py",
            "new_string": 'if turn_id == "abc-def-12345":\n    return special',
        },
    )
    assert hit is not None


def test_normal_source_intent_comment_blocked():
    """src/foo.py 含意图注释 → 拦（工程层意图注释 pattern）。"""
    fn = REGISTRY["long_term_fundamental"]
    hit = fn(
        tool_name="Write",
        tool_input={
            "file_path": "/x/src/foo.py",
            "content": "def f():\n    # 先打个补丁应付一下\n    return None",
        },
    )
    assert hit is not None
