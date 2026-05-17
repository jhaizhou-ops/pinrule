#!/bin/bash
# 一键重生 README 嵌入的双语 demo SVG.
# 前置: pip install asciinema termtosvg (cross-platform Python pkg)
# 输出: assets/demo-zh.svg + assets/demo-en.svg
# 用法: bash scripts/regenerate-demo-svg.sh
set -euo pipefail

cd "$(dirname "$0")/.."

command -v asciinema >/dev/null || .venv/bin/python -m pip install --quiet asciinema termtosvg
command -v asciinema >/dev/null || alias asciinema=".venv/bin/python -m asciinema"
ASCII="${ASCIINEMA:-.venv/bin/python -m asciinema}"
TTSVG="${TERMTOSVG:-.venv/bin/termtosvg}"

mkdir -p assets

for lang in zh en; do
  echo "→ 录制 $lang demo cast..."
  LANG_MODE=$lang $ASCII rec /tmp/demo-$lang.cast \
    --command "LANG_MODE=$lang bash scripts/demo-script.sh" \
    --overwrite --idle-time-limit 4
  echo "→ 渲染 $lang SVG..."
  # termtosvg -m -M 单位是**毫秒** (不是秒). 历史教训:
  #   - v0.16.1 老 `-M 6 -m 1` = max 6ms/min 1ms 把 42s cast 压成 130ms 一闪而过
  #   - v0.16.2 改 `-M 4000 -m 100` 总长拉到 42s 又太长 (用户看不完)
  #   - v0.16.3 调 -M 1500 = max 1.5s/帧 + demo-script sleep 也缩, target 20-30s
  # 人类阅读速度: banner 1-1.5s 看清, hook output 2-3s 读完, 5 scene 约 25 秒.
  $TTSVG render /tmp/demo-$lang.cast assets/demo-$lang.svg -M 1500 -m 100
done

echo
echo "✓ 完成:"
ls -la assets/demo-*.svg
echo
echo "README.md 用 assets/demo-en.svg, README.zh.md 用 assets/demo-zh.svg"
