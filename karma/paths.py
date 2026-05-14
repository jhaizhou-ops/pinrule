"""karma 状态目录路径单一来源 — 支持 `KARMA_HOME` 环境变量。

跨用户场景 / dry-run / CI / 多 profile 用 `KARMA_HOME` 隔离不污染默认 home：

```bash
KARMA_HOME=/tmp/karma-test karma init        # 不动 ~/.claude/karma/
KARMA_HOME=~/karma-profile-A karma sticky list  # 多 profile
```

默认值：`~/.claude/karma/`（保留历史路径向后兼容）。

注：path 在 module-level 常量 import 时 freeze，所以 `KARMA_HOME` 必须在
启动 karma 进程前 set，进程跑中改 env 不会生效。
"""

from __future__ import annotations

import os
from pathlib import Path


def karma_home() -> Path:
    """karma 状态根目录。`KARMA_HOME` env 可 override 默认 `~/.claude/karma/`。"""
    env = os.environ.get("KARMA_HOME")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".claude" / "karma"
