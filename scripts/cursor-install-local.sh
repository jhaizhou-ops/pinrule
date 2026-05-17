#!/usr/bin/env bash
# Run in Terminal (not Agent sandbox): full Cursor hook install + rules sync.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export ROOT
# 规则库默认 ~/.pinrule（与各端 hook 共享）；仅测试可 override PINRULE_HOME
export PINRULE_HOME="${PINRULE_HOME:-$HOME/.pinrule}"
PY="${PY:-$ROOT/.venv/bin/python}"
export PY
PINRULE="${PINRULE:-$ROOT/.venv/bin/pinrule}"
"$PY" -m pip install -e "$ROOT" -q
# install-hooks may fail overwriting dogfood probe wrappers — always merge hooks.json
if ! "$PINRULE" install-hooks --backend cursor; then
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
    ("pinrule_pre_compact.py", "pre_compact"),
    ("pinrule_subagent_start.py", "subagent_start"),
    ("pinrule_subagent_stop.py", "subagent_stop"),
    ("pinrule_user_prompt_submit.py", "user_prompt_submit"),
    ("pinrule_after_agent_response.py", "after_agent_response"),
]:
    p = hooks_dir / name
    if p.exists():
        continue
    body = (
        f"#!{py}\n"
        "import os\n"
        "import sys\n"
        f'sys.exit(__import__("pinrule.hooks.{mod}", fromlist=["main"]).main())\n'
    )
    p.write_text(body, encoding="utf-8")
    p.chmod(p.stat().st_mode | stat.S_IXUSR)
print(f"  已合并 hooks.json → {target}")
PY
"$PINRULE" sync-cursor-visibility
# Project rules: only apply when workspace root is opened (not empty-window)
"$PY" -c "
from pathlib import Path
from pinrule.cursor_rules_sync import sync_cursor_rules
_, logs = sync_cursor_rules(user=True, project_root=Path('$ROOT'))
for line in logs:
    print(line)
"
"$PINRULE" doctor | sed -n '/\[cursor\]/,$p'
echo ""
echo "Reload Cursor window, then open a new Composer."
echo "若在「空窗口」测可见性：请打开 pinrule 仓库文件夹，或 Settings → Rules 确认 User Rules。"
