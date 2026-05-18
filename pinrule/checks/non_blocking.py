"""#2 non-blocking-parallel — 不阻塞前端，长任务并行。

检测的行为模式（pre_tool_use Bash）：
1. Bash `sleep N` 显式等待
2. Bash `wait` 阻塞
3. 长任务（pytest / npm test / docker run 等）不带 run_in_background=True
4. 轮询 sleep (while true; do sleep N; done)
"""

from __future__ import annotations

import re

from pinrule.checks._types import CheckHit
from pinrule.checks.common import is_python_c_command, strip_shell_quoted_literals
from pinrule.i18n import tr

_STICKY_ID = "non-blocking-parallel"

# sleep 0 是 no-op 不阻塞（也常用于 yield 调度），只拦 sleep N (N >= 1)
_SLEEP_RE = re.compile(r"\bsleep\s+([1-9]\d*|0?\.\d+|[1-9]\d*\.\d+)", re.IGNORECASE)
# v0.5.13: _LANG_C_HEAD_RE 下沉到 pinrule.checks.common.is_python_c_command() —
# 历史动机：v0.4.18 加 python/node/ruby/perl -c 命令头识别豁免（python -c 内的
# `sleep` 字面是字符串不是真 shell sleep 调用）.
# v0.5.13 之前 testset / bypass_pinrule / non_blocking 各自定义同款 pattern.
# v0.4.22：python -c 内真阻塞接口 — `time.sleep(N)` / `subprocess.run('sleep', shell=True)`
# / `asyncio.sleep(N)` 等。v0.4.18 修过宽漏拦真 python 阻塞。
_PYTHON_REAL_BLOCK_RE = re.compile(
    r"\btime\.sleep\s*\(\s*[1-9]\d*"          # time.sleep(N) N >= 1
    r"|\basyncio\.sleep\s*\(\s*[1-9]\d*"        # asyncio.sleep
    r"|\bsubprocess\.(?:run|call|Popen)\s*\([^)]*[\"']sleep\s+[1-9]"  # subprocess 调 sleep
    r"|\bos\.system\s*\([^)]*[\"']sleep\s+[1-9]",  # os.system 调 sleep
    re.IGNORECASE,
)
# wait 命令检测 — 见 _is_blocking_wait 函数
# 拦 shell 内置 wait（裸 / 接 PID / 接 $!）。豁免有合法 wait 子命令的工具
# （kubectl wait / docker wait / aws cloudformation wait / gcloud / az）。

# 含 wait 词的子命令的命令头白名单（这些工具 wait 是同步原语不是阻塞）
_WAIT_EXEMPT_HEADS = {"kubectl", "docker", "podman", "aws", "gcloud", "az", "helm"}


def _is_blocking_wait(cmd: str) -> bool:
    """判断命令是否含真阻塞 wait（shell 内置 wait $pid / 裸 wait）。

    拆 `;` `&&` `||` 子命令独立看，每个子命令第一个 token 在豁免列表里
    → 该子命令里 wait 是合法子命令名，不算阻塞。
    """
    import re as _re
    # 拆子命令（保留分隔符位置不重要 — 只需独立分析每段）
    subs = _re.split(r"(?:&&|\|\||;|\n)", cmd)
    for sub in subs:
        sub = sub.strip()
        if not sub:
            continue
        # 子命令内是否含 wait 词
        if not _re.search(r"\bwait\b", sub, _re.IGNORECASE):
            continue
        # 看第一个非 flag token（可能前缀有 sudo / time 等）
        tokens = sub.split()
        first = tokens[0].lower() if tokens else ""
        # 简单跳一层 sudo/time/env 类前缀
        if first in {"sudo", "time", "env", "nohup"} and len(tokens) > 1:
            first = tokens[1].lower()
        if first in _WAIT_EXEMPT_HEADS:
            continue  # 豁免（合法 wait 子命令）
        # 命令头不在豁免列表 + 含 wait 词 → 真阻塞 wait（裸 wait / wait $pid /
        # wait $! / wait 1234 等）
        return True
    return False
# 「长任务」— 通常运行时间 ≥ 30s 的命令。短测试命令（pytest / jest 等多数项目
# 跑得快 < 5s）从默认列表移除，避免 audit 指出的高频假阳（pinrule 自身测试 0.1s
# 但触发拦截 5×，占 sticky 触发 83%）。
# 保留：构建（docker build / cargo build）/ 容器（docker run）/ 包管理（npm install）/
# 基建（make 大目标 / docker compose up）
_LONG_TASK_RE = re.compile(
    r"""\b(
        docker\s+run|docker\s+compose\s+(?:up|run|build)|docker\s+build|
        cargo\s+build|cargo\s+install|
        npm\s+(?:install|ci)|yarn\s+install|pnpm\s+install|
        pip\s+install|
        make\s+(?:install|build|all|release|deploy)|
        gradlew?\s+build|mvn\s+(?:install|package|deploy)
    )\b""",
    re.IGNORECASE | re.VERBOSE,
)
# v0.9.14: 加 pip install — audit 视角 1 抓到的真 FN（pip install 总是慢 ≥ 30s
# 解析依赖图 + 下载，不带 background 会卡用户）。`npm run` / `yarn build` 等
# user-defined script 仍不加（跑时长不可预测，design 留给用户自由）。

# 复用 common.strip_shell_quoted_literals — 跟关键词层统一剥引号逻辑


def check(*, tool_name: str = "", tool_input: dict | None = None, rule_id: str = "", **_):
    if tool_name != "Bash":
        return None
    cmd_raw = (tool_input or {}).get("command", "") or ""
    if not cmd_raw:
        return None
    tool_input = tool_input or {}
    is_bg = bool(tool_input.get("run_in_background"))
    # Cursor Shell: sync `timeout` ms (no run_in_background field) — treat as blocking wait.
    if not is_bg:
        timeout_ms = tool_input.get("timeout")
        if isinstance(timeout_ms, (int, float)) and timeout_ms >= 30_000:
            return CheckHit(
                rule_id=rule_id or _STICKY_ID,
                trigger=tr(
                    "check.non_blocking.cursor_timeout.trigger",
                    ms=int(timeout_ms),
                ),
                trigger_key="check.non_blocking.cursor_timeout.trigger",
                snippet=cmd_raw[:200],
                suggested_fix=tr("check.non_blocking.cursor_timeout.fix"),
            )
        block_ms = tool_input.get("block_until_ms")
        if isinstance(block_ms, (int, float)) and block_ms >= 30_000:
            return CheckHit(
                rule_id=rule_id or _STICKY_ID,
                trigger=tr(
                    "check.non_blocking.cursor_timeout.trigger",
                    ms=int(block_ms),
                ),
                trigger_key="check.non_blocking.cursor_timeout.trigger",
                snippet=cmd_raw[:200],
                suggested_fix=tr("check.non_blocking.cursor_timeout.fix"),
            )
    # 扫命令骨架，跳过引号字面（commit message / echo 引号内容不是执行意图）
    cmd = strip_shell_quoted_literals(cmd_raw)

    # v0.4.18：命令头是宿主语言 + -c/-e 时跳 sleep 检测 — python/node 等代码
    # 里的 sleep 字面是字符串数据不是真 shell 调用。真 python 等待用 time.
    # sleep(N) / subprocess.run("sleep") 这种 — `sleep` 裸字面在 python 代码
    # 里只是 identifier 不会执行。同 v0.4.13 deep-fix 拆 _WRITE_OP_RE 根因。
    is_lang_c = is_python_c_command(cmd_raw)

    # v0.4.22：python -c 内**真**阻塞接口（time.sleep / subprocess.run("sleep") /
    # os.system("sleep") / asyncio.sleep）— v0.4.18 漏拦真 python 阻塞。
    # 注意用 cmd_raw 不是 cmd（strip 后）— 因为 strip_shell_quoted_literals 把
    # python -c "..." 内容保留扫，所以这里 cmd_raw 跟 cmd 都含 python 代码。但
    # commit message 里字面引用「time.sleep(60)」必须剥掉，所以扫 cmd（已剥引号
    # 字面 + python -c 内容保留 = 既能扫真 python 阻塞也能豁免 commit message 描述）。
    if is_lang_c:
        m_block = _PYTHON_REAL_BLOCK_RE.search(cmd)
        if m_block:
            return CheckHit(
                rule_id=rule_id or _STICKY_ID,
                trigger=tr("check.non_blocking.python_block.trigger", call=m_block.group()),
                trigger_key="check.non_blocking.python_block.trigger",
                snippet=cmd_raw[:200],
                suggested_fix=tr("check.non_blocking.python_block.fix"),
            )

    m = _SLEEP_RE.search(cmd)
    if m and not is_lang_c:
        return CheckHit(
            rule_id=rule_id or _STICKY_ID,
            trigger=tr("check.non_blocking.sleep.trigger", cmd=m.group()),
            trigger_key="check.non_blocking.sleep.trigger",
            snippet=cmd_raw[:200],
            suggested_fix=tr("check.non_blocking.sleep.fix"),
        )

    # v0.4.18：wait 检测也豁免宿主语言 -c — python 代码里 `_WAIT_RE` / `wait_fn`
    # 等 identifier 字面命中 \bwait\b 是假阳。同 sleep 根因。
    if _is_blocking_wait(cmd) and not is_lang_c:
        return CheckHit(
            rule_id=rule_id or _STICKY_ID,
            trigger=tr("check.non_blocking.wait.trigger"),
            trigger_key="check.non_blocking.wait.trigger",
            snippet=cmd_raw[:200],
            suggested_fix=tr("check.non_blocking.wait.fix"),
        )

    # 长任务且没标 background
    m = _LONG_TASK_RE.search(cmd)
    if m and not is_bg and "&" not in cmd:
        return CheckHit(
            rule_id=rule_id or _STICKY_ID,
            trigger=tr("check.non_blocking.long_task.trigger", cmd=m.group()),
            trigger_key="check.non_blocking.long_task.trigger",
            snippet=cmd_raw[:200],
            suggested_fix=tr("check.non_blocking.long_task.fix", cmd=m.group()),
        )

    return None
