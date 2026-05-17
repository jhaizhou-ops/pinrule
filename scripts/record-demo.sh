#!/bin/bash
# pinrule demo 录制脚本 — 用 asciinema 录一段 30 秒 demo 加到 README
#
# 用法：
#   1. 装 asciinema: `brew install asciinema`（或 `pip install asciinema`）
#   2. 跑这个脚本: `bash scripts/record-demo.sh`
#   3. 脚本会引导你录三段：装机 / sticky 注入 / 实时拦截
#   4. 输出 .cast 文件，可上传 asciinema.org 拿 embed iframe / SVG
#   5. README 加 [![asciicast](URL.svg)](URL) 类链接

set -e

OUTPUT_DIR="${HOME}/pinrule-demo-recordings"
mkdir -p "$OUTPUT_DIR"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)

echo "=== pinrule demo 录制脚本 ==="
echo
echo "前置确认："
echo "  - asciinema 已装？$(command -v asciinema >/dev/null && echo '✓' || echo '✗')"
echo "  - pinrule 已装到 .venv？$(test -f .venv/bin/pinrule && echo '✓' || echo '✗')"
echo "  - 在 pinrule 仓库根目录跑？$(test -f README.md && grep -q '^# pinrule' README.md && echo '✓' || echo '✗')"
echo
read -p "继续？(y/N) " confirm
[ "$confirm" != "y" ] && exit 1

echo
echo "=== 第 1 段：装机 30 秒 demo ==="
echo "录制内容（脚本会自动跑这几条）："
echo "  $ pinrule --version"
echo "  $ pinrule init"
echo "  $ pinrule install-hooks"
echo "  $ pinrule doctor | head -10"
echo
read -p "起手录第 1 段？(y/N) " r1
if [ "$r1" = "y" ]; then
    OUT1="${OUTPUT_DIR}/pinrule-install-${TIMESTAMP}.cast"
    asciinema rec "$OUT1" -c "bash -c '
        echo \"# pinrule 30 秒装机 demo\";
        sleep 1;
        echo \"\$ pinrule --version\";
        .venv/bin/pinrule --version;
        sleep 1;
        echo;
        echo \"\$ pinrule init   # 初始化默认 sticky.yaml\";
        .venv/bin/pinrule init 2>&1 | head -5;
        sleep 1;
        echo;
        echo \"\$ pinrule install-hooks   # 装到 Claude Code\";
        .venv/bin/pinrule install-hooks 2>&1 | head -5;
        sleep 1;
        echo;
        echo \"\$ pinrule doctor   # 验证装机\";
        .venv/bin/pinrule doctor 2>&1 | head -8;
        sleep 2;
    '"
    echo "✓ 第 1 段录完: $OUT1"
fi

echo
echo "=== 第 2 段：sticky 注入展示 ==="
echo "录制内容：跑一个 manual user_prompt_submit hook 看注入头部"
echo
read -p "起手录第 2 段？(y/N) " r2
if [ "$r2" = "y" ]; then
    OUT2="${OUTPUT_DIR}/pinrule-sticky-inject-${TIMESTAMP}.cast"
    asciinema rec "$OUT2" -c "bash -c '
        echo \"# pinrule sticky 注入头部展示\";
        sleep 1;
        echo \"\$ echo '\\''{\\\"session_id\\\":\\\"demo\\\",\\\"prompt\\\":\\\"hi\\\",\\\"transcript_path\\\":\\\"/dev/null\\\"}'\\'' | pinrule_user_prompt_submit.py\";
        sleep 1;
        echo \\\"{\\\\\\\"session_id\\\\\\\":\\\\\\\"demo\\\\\\\",\\\\\\\"prompt\\\\\\\":\\\\\\\"hi\\\\\\\",\\\\\\\"transcript_path\\\\\\\":\\\\\\\"/dev/null\\\\\\\"}\\\" | ~/.claude/hooks/pinrule_user_prompt_submit.py | python3 -c \"import json,sys; d=json.load(sys.stdin); print(d.get('\\''hookSpecificOutput'\\'',{}).get('\\''additionalContext'\\'','\\'''\\'')[:600])\";
        sleep 3;
    '"
    echo "✓ 第 2 段录完: $OUT2"
fi

echo
echo "=== 第 3 段：实时拦截 ==="
echo "录制内容：sleep 命令触发 PreToolUse 拦截"
echo
read -p "起手录第 3 段？(y/N) " r3
if [ "$r3" = "y" ]; then
    OUT3="${OUTPUT_DIR}/pinrule-realtime-block-${TIMESTAMP}.cast"
    asciinema rec "$OUT3" -c "bash -c '
        echo \"# pinrule 实时拦截 demo\";
        sleep 1;
        echo \"\$ echo '\\''{\\\"tool_name\\\":\\\"Bash\\\",\\\"tool_input\\\":{\\\"command\\\":\\\"sleep 30\\\"}}'\\'' | pinrule_pre_tool_use.py\";
        sleep 1;
        echo \"{\\\"tool_name\\\":\\\"Bash\\\",\\\"tool_input\\\":{\\\"command\\\":\\\"sleep 30\\\"}}\" | ~/.claude/hooks/pinrule_pre_tool_use.py 2>&1 | head -10;
        sleep 3;
    '"
    echo "✓ 第 3 段录完: $OUT3"
fi

echo
echo "=== 全部录完 ==="
ls -la "$OUTPUT_DIR"/*"${TIMESTAMP}"* 2>/dev/null
echo
echo "下一步："
echo "  1. 本地预览: asciinema play <.cast 文件>"
echo "  2. 上传到 asciinema.org: asciinema upload <.cast 文件>"
echo "  3. 拿到 URL 后 README 顶部加："
echo "     [![asciicast](https://asciinema.org/a/XXXX.svg)](https://asciinema.org/a/XXXX)"
echo
echo "也可以转 GIF（用 agg 工具）："
echo "  $ brew install agg"
echo "  $ agg <.cast 文件> demo.gif"
