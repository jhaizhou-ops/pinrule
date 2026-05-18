"""pinrule 状态目录路径单一来源 — 支持 `PINRULE_HOME` 环境变量。

跨用户场景 / dry-run / CI / 多 profile 用 `PINRULE_HOME` 隔离不污染默认 home：

```bash
PINRULE_HOME=/tmp/pinrule-test pinrule init        # 不动 ~/.pinrule/
PINRULE_HOME=~/pinrule-profile-A pinrule rule list  # 多 profile
```

默认值：`~/.pinrule/` — 与 Claude / Codex / Cursor 客户端无关的共享规则库。

注：path 在 module-level 常量 import 时 freeze，所以 `PINRULE_HOME` 必须在
启动 pinrule 进程前 set，进程跑中改 env 不会生效。

v0.16.0 (rename karma → pinrule): fresh brand, 不保留 v0.15- karma 自动
迁移逻辑. 老 karma 用户手工 `mv ~/.karma ~/.pinrule && pinrule install-hooks`
即可 — 详见 CHANGELOG v0.16.0 迁移指南.
"""

from __future__ import annotations

import os
from pathlib import Path

# v0.16.0+ 共享状态根（所有 backend hooks 应读同一目录）
SHARED_PINRULE_HOME = Path.home() / ".pinrule"


def pinrule_home() -> Path:
    """pinrule 状态根目录 (data: rules.json / violations / session-state).

    `PINRULE_HOME` env 可 override; 否则 `~/.pinrule/`.
    """
    env = os.environ.get("PINRULE_HOME")
    if env:
        return Path(env).expanduser()
    return SHARED_PINRULE_HOME


def pinrule_install_root() -> Path:
    """install root: hook wrapper / skill / backend settings.json 装哪.

    v0.16.11: 实现真 sandbox — 设 `PINRULE_HOME` 时, hook 装机也归到 sandbox 内,
    不再偷偷动用户主目录 (round-3 audit 视角 12 #1+#4 真根因 fix).

    - 设了 `PINRULE_HOME=/tmp/foo` → install root = `/tmp/foo/`,
      backend hooks 装 `/tmp/foo/.claude/hooks/...`, skill 装 `/tmp/foo/.claude/skills/...`
    - 没设 → install root = `Path.home()`, 老 production 行为 100% 不变

    跟 `pinrule_home()` 区别: `pinrule_home()` 是数据 dir (default ~/.pinrule/),
    `pinrule_install_root()` 是装机 root (default ~/). 没设 PINRULE_HOME 时
    两个返不同路径, 设了 PINRULE_HOME 时**两个返同一个根** (整 sandbox).
    """
    env = os.environ.get("PINRULE_HOME")
    if env:
        return Path(env).expanduser()
    return Path.home()
