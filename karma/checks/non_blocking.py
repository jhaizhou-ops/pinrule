"""#2 non-blocking-parallel — 不阻塞前端，长任务并行。

检测的行为模式（pre_tool_use Bash）：
1. Bash `sleep N` 显式等待
2. Bash `wait` 阻塞
3. 长任务（pytest / npm test / docker run 等）不带 run_in_background=True
4. 轮询 sleep (while true; do sleep N; done)
"""

from __future__ import annotations

import re

from karma.checks.common import strip_shell_quoted_literals

_STICKY_ID = "non-blocking-parallel"

# sleep 0 是 no-op 不阻塞（也常用于 yield 调度），只拦 sleep N (N >= 1)
_SLEEP_RE = re.compile(r"\bsleep\s+([1-9]\d*|0?\.\d+|[1-9]\d*\.\d+)", re.IGNORECASE)
_WAIT_RE = re.compile(r"(?:^|\s|\&)wait(?:\s|$|\&)", re.IGNORECASE)
# 「真长任务」— 通常运行时间 ≥ 30s 的命令。短测试命令（pytest / jest 等多数项目
# 跑得快 < 5s）从默认列表移除，避免 audit 指出的高频假阳（karma 自身测试 0.1s
# 但触发拦截 5×，占 sticky 触发 83%）。
# 保留：构建（docker build / cargo build）/ 容器（docker run）/ 包管理（npm install）/
# 基建（make 大目标 / docker compose up）
_LONG_TASK_RE = re.compile(
    r"""\b(
        docker\s+run|docker\s+compose\s+(?:up|run|build)|docker\s+build|
        cargo\s+build|cargo\s+install|
        npm\s+(?:install|ci)|yarn\s+install|pnpm\s+install|
        make\s+(?:install|build|all|release|deploy)|
        gradlew?\s+build|mvn\s+(?:install|package|deploy)
    )\b""",
    re.IGNORECASE | re.VERBOSE,
)

# 复用 common.strip_shell_quoted_literals — 跟关键词层统一剥引号逻辑


def check(*, tool_name: str = "", tool_input: dict | None = None, **_):
    if tool_name != "Bash":
        return None
    cmd_raw = (tool_input or {}).get("command", "") or ""
    if not cmd_raw:
        return None
    is_bg = bool((tool_input or {}).get("run_in_background"))
    # 扫命令骨架，跳过引号字面（commit message / echo 引号内容不是执行意图）
    cmd = strip_shell_quoted_literals(cmd_raw)

    from karma.checks import CheckHit

    m = _SLEEP_RE.search(cmd)
    if m:
        return CheckHit(
            sticky_id=_STICKY_ID,
            trigger=f"Bash sleep 命令: {m.group()!r}",
            snippet=cmd_raw[:200],
            suggested_fix="不要 sleep 阻塞前端。用 run_in_background=True 启动任务，并行做其他事。"
                          "需要等条件成立时用 Monitor + until 循环。",
        )

    m = _WAIT_RE.search(cmd)
    if m:
        return CheckHit(
            sticky_id=_STICKY_ID,
            trigger="Bash wait 命令阻塞",
            snippet=cmd_raw[:200],
            suggested_fix="不要 wait。用 run_in_background=True，让前端能继续推进其他事。",
        )

    # 长任务且没标 background
    m = _LONG_TASK_RE.search(cmd)
    if m and not is_bg and "&" not in cmd:
        return CheckHit(
            sticky_id=_STICKY_ID,
            trigger=f"长任务不带 run_in_background: {m.group()!r}",
            snippet=cmd_raw[:200],
            suggested_fix=f"{m.group()} 是长任务，加 run_in_background=True 让前端能继续做别的事。",
        )

    return None
