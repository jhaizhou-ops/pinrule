#!/bin/bash
# karma 发版工作流脚本集合。
#
# 1. 验证本机 .venv 装的 karma 版本跟 pyproject.toml 一致。
# 2. 防 `&&` 链式 commit-tag-release 命令因 karma hook 拦截产生幽灵 release。
# 防止「改了代码 + commit + push + gh release 都做了但忘 reinstall」类
# 假完成（hook 仍跑旧字节码所有 fix 不生效）。
#
# 用法：
#   scripts/verify-installed.sh              # 仅验证
#   scripts/verify-installed.sh --reinstall  # 不一致就自动重装
#
# 真发现：v0.4.9/10/11 三次连发都没装到本机，hook 跑 v0.4.8 chinese-plain
# 旧逻辑，force_block 累积 6 次都没生效。这个脚本固化该步骤进发版流程。
set -e

cd "$(dirname "$0")/.."

PYPROJECT_VERSION=$(grep -E '^version = ' pyproject.toml | head -1 | sed -E 's/.*"([^"]+)".*/\1/')
INSTALLED_RAW=$(.venv/bin/karma --version 2>/dev/null || echo "karma not-installed")
INSTALLED_VERSION=$(echo "$INSTALLED_RAW" | awk '{print $2}' | sed 's/^v//')

if [ "$INSTALLED_VERSION" = "$PYPROJECT_VERSION" ]; then
    echo "OK: .venv karma v$INSTALLED_VERSION 跟 pyproject 一致"
    exit 0
fi

echo "MISMATCH: .venv 装的 v$INSTALLED_VERSION ≠ pyproject v$PYPROJECT_VERSION"

if [ "$1" = "--reinstall" ]; then
    echo "重装中..."
    uv pip install -e . --python .venv/bin/python --quiet
    NEW=$(.venv/bin/karma --version | awk '{print $2}' | sed 's/^v//')
    if [ "$NEW" = "$PYPROJECT_VERSION" ]; then
        echo "OK: 重装到 v$NEW"
        exit 0
    else
        echo "ERROR: 重装后仍是 v$NEW，pyproject 是 v$PYPROJECT_VERSION" >&2
        exit 1
    fi
fi

echo "→ 跑 scripts/verify-installed.sh --reinstall 自动重装" >&2
exit 1
