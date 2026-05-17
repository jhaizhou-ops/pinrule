"""karma 状态目录路径单一来源 — 支持 `KARMA_HOME` 环境变量。

跨用户场景 / dry-run / CI / 多 profile 用 `KARMA_HOME` 隔离不污染默认 home：

```bash
KARMA_HOME=/tmp/karma-test karma init        # 不动 ~/.karma/
KARMA_HOME=~/karma-profile-A karma rule list  # 多 profile
```

默认值（v0.14.0+）：`~/.karma/` — 与 Claude / Cursor / Codex 客户端无关的共享规则库。
历史默认 `~/.claude/karma/` 在 `karma init` 时自动迁移（若存在且 `~/.karma` 为空）。

注：path 在 module-level 常量 import 时 freeze，所以 `KARMA_HOME` 必须在
启动 karma 进程前 set，进程跑中改 env 不会生效。
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

# v0.14.0: 共享状态根（所有 backend hooks 应读同一目录）
SHARED_KARMA_HOME = Path.home() / ".karma"
# v0.14.0 前默认；保留用于迁移与 bypass 检测 legacy 路径字面
LEGACY_KARMA_HOME = Path.home() / ".claude" / "karma"
# dogfood / 旧 Cursor 装机误用的第二份目录 — doctor 告警，不再写入
CURSOR_LEGACY_KARMA_HOME = Path.home() / ".cursor" / "karma"


def karma_home() -> Path:
    """karma 状态根目录。`KARMA_HOME` env 可 override；否则 `~/.karma/`。"""
    env = os.environ.get("KARMA_HOME")
    if env:
        return Path(env).expanduser()
    return SHARED_KARMA_HOME


def migrate_legacy_home_if_needed() -> Path | None:
    """若 `~/.karma` 不存在且 `~/.claude/karma` 有数据，复制迁移到共享目录。

    返回迁移后的路径；无迁移则 None。不删除 legacy 目录（用户可手工清理）。
    """
    target = SHARED_KARMA_HOME
    if target.exists() and any(target.iterdir()):
        return None
    legacy = LEGACY_KARMA_HOME
    if not legacy.exists():
        return None
    if not any(legacy.iterdir()):
        return None
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(legacy, target)
    return target
