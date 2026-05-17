#!/usr/bin/env bash
# Run in Terminal (not Agent sandbox): full Cursor hook install + rules sync.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export ROOT
# 规则库默认 ~/.karma（与各端 hook 共享）；仅测试可 override KARMA_HOME
export KARMA_HOME="${KARMA_HOME:-$HOME/.karma}"
PY="${PY:-$ROOT/.venv/bin/python}"
export PY
KARMA="${KARMA:-$ROOT/.venv/bin/karma}"
"$PY" -m pip install -e "$ROOT" -q
# install-hooks may fail overwriting dogfood probe wrappers — always merge hooks.json
if ! "$KARMA" install-hooks --backend cursor; then
  echo "  (install-hooks 部分失败 — 仍合并 hooks.json 与补缺失 wrapper)"
fi
"$PY" <<'PY'
import json
import os
import stat
from pathlib import Path

root = Path(os.environ["ROOT"])
parity = json.loads((root / ".dogfood/hooks.cursor-parity.json").read_text())
target = Path.home() / ".cursor/hooks.json"
data = json.loads(target.read_text(encoding="utf-8")) if target.exists() else {"version": 1, "hooks": {}}
data["version"] = 1
data.setdefault("hooks", {})
data["hooks"].update(parity["hooks"])
target.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
hooks_dir = Path.home() / ".cursor/hooks"
hooks_dir.mkdir(parents=True, exist_ok=True)
py = Path(os.environ["PY"])
for name, mod in [
    ("karma_pre_compact.py", "pre_compact"),
    ("karma_subagent_start.py", "subagent_start"),
    ("karma_subagent_stop.py", "subagent_stop"),
    ("karma_user_prompt_submit.py", "user_prompt_submit"),
    ("karma_after_agent_response.py", "after_agent_response"),
]:
    p = hooks_dir / name
    if p.exists():
        continue
    body = (
        f"#!{py}\n"
        "import os\n"
        "import sys\n"
        f'sys.exit(__import__("karma.hooks.{mod}", fromlist=["main"]).main())\n'
    )
    p.write_text(body, encoding="utf-8")
    p.chmod(p.stat().st_mode | stat.S_IXUSR)
print(f"  已合并 hooks.json → {target}")
PY
"$KARMA" sync-cursor-visibility
# Project rules: only apply when workspace root is opened (not empty-window)
"$PY" -c "
from pathlib import Path
from karma.cursor_rules_sync import sync_cursor_rules
_, logs = sync_cursor_rules(user=True, project_root=Path('$ROOT'))
for line in logs:
    print(line)
"
"$KARMA" doctor | sed -n '/\[cursor\]/,$p'
echo ""
echo "Reload Cursor window, then open a new Composer."
echo "若在「空窗口」测可见性：请打开 karma 仓库文件夹，或 Settings → Rules 确认 User Rules。"
