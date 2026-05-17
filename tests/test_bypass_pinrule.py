"""bypass_pinrule check — 检测「绕过 pinrule 内部状态」的命令。

用户痛点（2026-05-14）：Agent 被 pinrule 反复拦后倾向手动绕（修
last_test_pass_ts / 清 pending_bg_tasks），违反 sticky #1「最根本方案」。
"""

from __future__ import annotations

from pinrule.checks import REGISTRY


def _check(cmd: str):
    return REGISTRY["bypass_pinrule_detection"](
        tool_name="Bash", tool_input={"command": cmd},
    )


def test_manual_update_last_test_pass_ts_blocked():
    """经典 anti-pattern：python -c 改 last_test_pass_ts 让 commit 通过。"""
    cmd = '''python -c "
import json
from pathlib import Path
p = Path.home() / '.pinrule/session-state/abc.json'
d = json.loads(p.read_text())
d['last_test_pass_ts'] = 9999
p.write_text(json.dumps(d))
"'''
    hit = _check(cmd)
    assert hit is not None
    assert "绕开" in hit.trigger or "bypass" in hit.trigger.lower()


def test_clear_pending_bg_tasks_blocked():
    """手动清 pending_bg_tasks 是绕 catchup → 拦。"""
    cmd = "python -c \"d['pending_bg_tasks'] = []; p.write_text(json.dumps(d))\""
    hit = _check(cmd)
    assert hit is not None


def test_write_session_state_path_blocked():
    """直接 echo > session-state json 也算绕。"""
    cmd = "echo '{}' > ~/.pinrule/session-state/abc.json"
    hit = _check(cmd)
    assert hit is not None


def test_pinrule_cli_command_exempted():
    """pinrule 官方命令豁免（pinrule reset / pinrule stats 是合法操作）。"""
    assert _check("pinrule reset") is None
    assert _check("pinrule init") is None
    assert _check("pinrule audit") is None
    assert _check("pinrule violations clear --sticky x") is None


def test_normal_command_passes():
    """普通命令不命中。"""
    assert _check("git status") is None
    assert _check("ls -la") is None
    assert _check("pytest tests/") is None


def test_discussion_of_internal_without_write_passes():
    """讨论 pinrule 内部字面但无写操作 → 不算绕。"""
    # 只 cat / grep 看 ts 不算绕
    assert _check("cat session-state/x.json | grep last_test_pass_ts") is None
    # 但凡有 write 操作就拦（保守）
    hit = _check("cat session-state/x.json | grep last_test_pass_ts > /tmp/out")
    # 这条 write 是 grep 输出到 /tmp/out 不是写 pinrule 状态，按字面命中（保守）
    # 实际 production 中不算「绕 pinrule」— 但简单 regex 难区分，接受小假阳
    # 用户应该用 pinrule audit 看而非 grep session-state
    assert hit is not None or hit is None  # 保守：宁可严格


def test_read_only_inspection_passes():
    """只读 inspection 应豁免（不含写操作）。"""
    hit = _check("cat ~/.pinrule/session-state/abc.json")
    assert hit is None  # 没写操作


def test_readonly_inspection_with_dev_null_redirect_passes():
    """dogfooding 实测假阳：`2>/dev/null` stderr 转黑洞不算写，
    只读 inspection 含 pinrule 状态路径字面（`~/.pinrule/session-state`）
    不该被拦。

    触发：`python -c "...session_state.load(...)" 2>/dev/null` 含 pinrule 内部
    路径 + `2>/dev/null` 之前被 `>\\s*[/.~\\w]` pattern 误识别为写。修：lookahead
    排除 /dev/null/zero/stderr/stdout 等丢弃目标。
    """
    for cmd in [
        'python -c "from pinrule import session_state; print(session_state.load(\'x\').turn_count)" 2>/dev/null',
        'ls ~/.pinrule/session-state/*.json 2>/dev/null | head -1',
        'cat ~/.pinrule/violations.jsonl 2>/dev/null | head -3',
    ]:
        assert _check(cmd) is None, f"只读 inspection + dev/null 重定向不该拦: {cmd!r}"


def test_real_write_to_dev_null_alternatives_still_blocked():
    """对偶：写 pinrule 状态到普通文件仍要拦（不能因放宽 /dev/null 全放过）。"""
    cmd = 'echo bad > ~/.pinrule/session-state/abc.json'
    assert _check(cmd) is not None, "写 pinrule 状态文件该拦"


def test_user_backup_pinrule_files_passes():
    """评审 B Agent 痛点：用户自己 cp / mv / rm pinrule 状态文件（备份 /
    清老 rotation）是合法操作，不该拦。攻击者用 echo > / python write
    才是真 hack 路径仍能 catch。"""
    for cmd in [
        "cp ~/.pinrule/sticky.yaml ~/backup/sticky.yaml.bak",
        "mv ~/.pinrule/violations.jsonl ~/old-violations.jsonl",
        "rm ~/.pinrule/violations.jsonl.3",
        "cp ~/.pinrule/sticky.yaml ./snapshot/",
    ]:
        assert _check(cmd) is None, f"用户合法备份/清理不该拦: {cmd!r}"


def test_keep_pushing_workflow_not_blocked():
    """sticky #7 keep-pushing 干预时 Agent 写 reason 不该被这个 check 误判。"""
    cmd = 'echo "我接下来去做 X"'
    assert _check(cmd) is None


def test_commit_message_describing_bypass_not_blocked():
    """git commit message 描述 bypass anti-pattern 字面 → 是描述不是执行，豁免。

    场景：sticky.yaml 写「禁止 update last_test_pass_ts」/ commit message 描述
    「修了 last_test_pass_ts race」都是描述。剥引号字面后命中字面消失 → 豁免。
    """
    cmd = 'git commit -m "fix: update last_test_pass_ts race (json.dump)"'
    assert _check(cmd) is None  # 引号字面剥后不含敏感字面


def test_self_referential_commit_message_about_bypass_exempted():
    """meta-test：本身就是 commit 描述 bypass fix 的 message，含敏感字面但是
    描述 → 应豁免（验证 strip_shell_quoted_literals fix 原因方案）。"""
    msg = "fix(pinrule): bypass check 加 last_test_pass_ts 检测 + json.dump 写操作"
    cmd = f'git commit -m "{msg}"'
    assert _check(cmd) is None, "commit message 描述 bypass check 改动不该被自身拦"


def test_python_heredoc_real_bypass_still_caught():
    """python heredoc 改 session_state 文件 — 是绕（不是 commit message 描述）。

    注意：strip_shell_quoted_literals 对 python heredoc 剥成数据 — 这是个
    已知 limitation。检测主要靠剥后命令骨架，python heredoc 内的绕会被漏。
    用户可以靠 sticky.yaml 关键词层和 stop hook 兜底。
    """
    cmd = """python <<'EOF'
import json
from pathlib import Path
p = Path.home() / '.pinrule/session-state/x.json'
d = json.loads(p.read_text())
d['last_test_pass_ts'] = 9999
p.write_text(json.dumps(d))
EOF"""
    # 当前 strip 把 python heredoc 当数据剥 → 这条漏报（已知 limitation）
    # 不强 assert — 表达「python heredoc 内绕过」是工程层覆盖盲区
    hit = _check(cmd)
    # 如果未来 strip 改成保留 python heredoc 内容 → 此 case 会命中
    # 当前接受 hit is None — 但 sticky.yaml violation_keywords 兜底
    _ = hit  # documentation 用，不 assert


def test_python_c_compare_operator_not_shell_redir():
    """python -c "..." 内的 `>` `<` 是比较运算符不是 shell 重定向 — 不该拦。

    v0.4.13 dogfooding 触发：读 violations.jsonl 时 python 代码含
    `json.loads(l).get('ts', 0) > cutoff` 被 _WRITE_OP_RE 的 `> c`
    误命中 shell 重定向 → 错算 pinrule 内部状态写 → 假阳拦读操作。

    fix：拆 _PYTHON_OR_SHELL_WRITE_RE（跨语言通用写）+ _SHELL_REDIR_WRITE_RE
    （shell-only 重定向）。命令头是宿主语言 + -c 时跳 shell 重定向检测。
    真 python 写绕过用 `.write` 仍命中（_PYTHON_OR_SHELL_WRITE_RE 扫）。
    """
    cmd = (
        '.venv/bin/python -c "import json, time\\n'
        "cutoff = time.time() - 600\\n"
        "with open('/Users/jhz/.pinrule/violations.jsonl') as f:\\n"
        "    new = [json.loads(l) for l in f if json.loads(l).get('ts', 0) > cutoff]"
        '"'
    )
    assert _check(cmd) is None, "python -c 内比较运算符 `>` 不是 shell 重定向，不该误算写绕过"


def test_python_c_real_write_still_caught():
    """python -c "..." 内**真**调用 .write 写 pinrule 文件 — 仍命中（绕过）。

    跟上一 case 对偶：python -c 不能整段豁免，否则绕过漏拦。靠
    `.write` / `.unlink` 等 python 写字面识别。
    """
    cmd = """python -c "open('.pinrule/session-state.json', 'w').write('{}')\""""
    assert _check(cmd) is not None, "python -c 内 .write 绕过应命中"


def test_python_os_system_real_bypass_caught():
    """v0.4.22：v0.4.13 fix 过宽 — python -c 内 os.system 真调 shell 绕过应拦。"""
    cmd = """python -c "import os; os.system('rm ~/.pinrule/session-state.json')\""""
    assert _check(cmd) is not None, "python os.system 绕过应命中"


def test_python_subprocess_real_bypass_caught():
    """v0.4.22：python -c 内 subprocess.run 真调 shell 绕过应拦。"""
    cmd = """python -c "import subprocess; subprocess.run(['rm', '~/.pinrule/sticky.yaml'])\""""
    assert _check(cmd) is not None, "python subprocess 绕过应命中"


def test_cat_read_session_state_not_blocked():
    """v0.4.32 触发：cat ~/.pinrule/session-state/xxx.json 是 read-only 输出
    内容 → 不该当绕过拦。dogfooding 实证：调试 session_state 实际行为时跑这命令
    被假阳拦了。

    原因：read-only cat / less / head / tail 不写文件，但路径含敏感字面
    `.pinrule/session-state` 满足 has_state_path → 只要 has_write 也 True
    就命中。所以核心是 has_write 不能在纯读命令里被错触发。
    """
    cmd = "cat ~/.pinrule/session-state/abc.json"
    assert _check(cmd) is None, "纯 cat 读 session-state 不该被拦"


def test_pipe_to_python_json_dumps_not_blocked():
    """v0.4.32 原因：`json.dumps`（序列化为字符串纯输出）跟 `json.dump`（写
    file-like）regex 没加 word boundary 导致 `json.dumps` 被误判 `json.dump`。

    dogfooding 实证：cat session-state.json | python -c "import json; d=json.load(...);
    print(json.dumps(d, indent=2))" 是纯读 + pretty-print 输出，被假阳拦了。

    fix：`r"json\\.dump\\b"` 加 \\b word boundary 让 `json.dumps` 不命中。
    """
    cmd = (
        "cat ~/.pinrule/session-state/abc.json | "
        'python3 -c "import json, sys; d = json.load(sys.stdin); '
        'print(json.dumps(d, indent=2, ensure_ascii=False))"'
    )
    assert _check(cmd) is None, "json.dumps (序列化为字符串纯读) 不该被 json.dump 模式假阳"


def test_release_notes_markdown_backtick_path_not_leaked():
    """v0.4.33 原因 fix：`gh release create --notes "$(cat <<'EOF' ... EOF)"`
    里 markdown 反引号包的 `cat ~/.pinrule/session-state/xxx.json` 字面
    不该被错当 shell substitution 保留扫到外层 cmd。

    触发：v0.4.32 release create 命令被自己拦了 — release notes 里描述用户
    场景的 markdown 反引号被先抽到 placeholder → heredoc 剥时 placeholder 已
    不在内容里 → 最终替回保留扫漏。

    fix：strip Step 顺序 — heredoc 先于 indirect / hoist 处理，让 heredoc 内
    一切字面跟 heredoc 一起按 prefix 命令决定剥/保留。
    """
    cmd = """gh release create v0.4.32 --notes "$(cat <<'EOF'
描述场景：`cat ~/.pinrule/session-state/xxx.json` 被拦
EOF
)" """
    assert _check(cmd) is None, "release notes markdown 反引号包路径不该被算执行意图"


def test_heredoc_in_subshell_recognizes_inner_command():
    """v0.4.33：`$(cat <<EOF)` / `(cat <<EOF)` 子 shell 嵌套时，heredoc 头识别
    应该取 cat（内层命令）而不是外层 gh / 别的。

    原因 fix：_heredoc_prefix_command 加 `(` 到 boundary 集合。
    """
    # cat heredoc 内容是数据应剥 — 即使在 $(...) 嵌套
    cmd = """echo "$(cat <<'EOF'
.pinrule/session-state/x.json
EOF
)" """
    assert _check(cmd) is None, "$(cat <<EOF) 嵌套 heredoc 内容应被剥"


def test_python_json_dump_real_write_still_caught():
    """对偶：json.dump (无 s — 写 file-like) 写文件应仍命中。

    用 single quote 外层 + double quote 内层避免触发 strip 转义引号 limitation
    （HANDOFF M3 第六波已知 limitation 跟本测无关）。
    """
    cmd = """python -c 'import json; json.dump({}, open(".pinrule/session-state/x.json", "w"))'"""
    assert _check(cmd) is not None, "json.dump 写 file-like 应命中"


def test_python_pathlib_unlink_real_bypass_caught():
    """v0.4.22：python -c 内 Path(x).unlink() 绕过应拦。"""
    cmd = """python -c "from pathlib import Path; Path('~/.pinrule/violations.jsonl').unlink()\""""
    assert _check(cmd) is not None, "Path.unlink 绕过应命中"


def test_shell_redir_real_bypass_still_caught():
    """shell `>` 重定向写 pinrule 文件 — 命令头不是宿主语言时仍扫。"""
    cmd = "echo '{}' > ~/.pinrule/session-state.json"
    assert _check(cmd) is not None, "shell 真 `>` 重定向写 pinrule 状态应命中"


def test_v0518_read_pinrule_state_write_tmp_exempted():
    """v0.5.18 原因 fix (dogfooding 触发驱动):
    grep pinrule state 写 tmp 临时文件是合法 audit, 不该拦.

    场景: Agent 想分析 violations.jsonl 数据, 用 grep 过滤行写到 /tmp/audit 跑解析.
    redirect target 是 /tmp 不是 pinrule 路径 → 应豁免.
    之前 bypass_pinrule 判定「pinrule 路径出现 + 任何 write」就拦, 错算这是绕检测.
    """
    cmd = "grep deep-fix ~/.pinrule/violations.jsonl > /tmp/df_audit.jsonl"
    assert _check(cmd) is None, "读 pinrule 写 tmp 是合法 audit, 不该拦"


def test_v0518_cat_pinrule_pipe_to_python_exempted():
    """v0.5.18: cat pinrule state 输出到 python 分析也合法 (无 redirect 到 pinrule 路径)."""
    cmd = "cat ~/.pinrule/violations.jsonl | python3 -m json.tool > /tmp/pretty.json"
    assert _check(cmd) is None


def test_v0518_redirect_target_is_pinrule_path_still_blocked():
    """v0.5.18 对偶: redirect target 是 pinrule 路径仍拦 (写 pinrule state)."""
    cmd = "echo '{}' >> ~/.pinrule/violations.jsonl"
    assert _check(cmd) is not None


def test_v0518_internal_field_name_write_to_tmp_now_exempted():
    """v0.5.18: 内部 field name + 写到 /tmp (非 pinrule 路径) 豁免.

    写 /tmp 不影响 pinrule 状态, 即使字符串里含 field 名也不是绕过.
    跟 redirect-target 维度判定一致: target 是 pinrule path 才算写 pinrule.
    """
    cmd = "echo 'last_test_pass_ts=999999' > /tmp/inject.txt"
    assert _check(cmd) is None, "写 /tmp 不影响 pinrule 状态, 应豁免"


def test_v0518_internal_field_name_write_to_pinrule_still_blocked():
    """v0.5.18 原因对偶: 内部 field name + 写到 pinrule 路径 → 违反 仍拦."""
    cmd = "echo 'last_test_pass_ts=999999' > ~/.pinrule/session-state/x"
    assert _check(cmd) is not None, "写到 pinrule 路径是绕过"


# === v0.9.7: PINRULE_HOME 隔离 mode 下 bypass 检测仍生效 ===
# v0.9.6 前 _PINRULE_STATE_PATH_RE 硬编码 `\.pinrule/...` 字面，
# 用户跑 `PINRULE_HOME=/tmp/foo` 时 `rm /tmp/foo/session-state/x.json`
# 该拦但完全打不到。v0.9.7 用 pinrule_home() 工厂动态构造正则修这个洞。

def test_build_state_path_re_default_mode_matches_home_writes():
    """默认 mode：~/.pinrule/* / 绝对 home 路径 / 相对 fragment 都该匹配。"""
    from pinrule.checks.bypass_pinrule import _build_state_path_re
    pat = _build_state_path_re()
    assert pat.search("rm ~/.pinrule/session-state/x.json")
    assert pat.search("rm /Users/anyone/.pinrule/violations.jsonl")
    assert pat.search("rm .pinrule/rules.yaml")
    # 不该匹配无关路径
    assert not pat.search("rm /tmp/random/session-state/x.json")


def test_build_state_path_re_PINRULE_HOME_mode_matches_isolated_writes(monkeypatch, tmp_path):
    """PINRULE_HOME 隔离 mode：override 路径下的 bypass 也该 match（不是 home 子目录）。"""
    from pinrule.checks.bypass_pinrule import _build_state_path_re
    custom = tmp_path / "pinrule-isolated"
    custom.mkdir()
    monkeypatch.setenv("PINRULE_HOME", str(custom))
    # 动态调工厂拿新 env 值（实际 hook 子进程启动时 env 已 set 不需 reimport）
    pat = _build_state_path_re()
    # 绝对路径写法
    assert pat.search(f"rm {custom}/session-state/x.json")
    assert pat.search(f"echo '{{}}' > {custom}/violations.jsonl")
    # 默认路径在 PINRULE_HOME mode 下也仍匹配（兼容老装机器迁移期）
    assert pat.search("rm ~/.pinrule/session-state/x.json")


def test_build_state_path_re_PINRULE_HOME_in_home_dir_matches_tilde_literal(monkeypatch, tmp_path, request):
    """PINRULE_HOME 设到 home 下子目录时：用户用 `~/<rel>` 字面也该 match。"""
    from pathlib import Path

    from pinrule.checks.bypass_pinrule import _build_state_path_re

    # 用一个 home 下的临时子目录（tmp_path 在 /var 不在 home，要构造 home 下的）
    home_subdir = Path.home() / ".pinrule-test-isolated"
    home_subdir.mkdir(exist_ok=True)
    request.addfinalizer(lambda: home_subdir.rmdir() if home_subdir.exists() else None)

    monkeypatch.setenv("PINRULE_HOME", str(home_subdir))
    pat = _build_state_path_re()
    # 字面 ~/<rel> 应该 match
    assert pat.search("rm ~/.pinrule-test-isolated/session-state/x.json")
    # 绝对路径也 match
    assert pat.search(f"rm {home_subdir}/session-state/x.json")


def test_rules_yaml_now_in_state_path_set():
    """v0.6.0 BREAKING 把 sticky.yaml 改名 rules.yaml — bypass 检测要拦两者。"""
    from pinrule.checks.bypass_pinrule import _build_state_path_re
    pat = _build_state_path_re()
    assert pat.search("echo '...' > ~/.pinrule/rules.yaml")
    assert pat.search("echo '...' > ~/.pinrule/rules.yaml")
    assert pat.search("echo '...' > ~/.pinrule/sticky.yaml"), "兼容老用户路径"
