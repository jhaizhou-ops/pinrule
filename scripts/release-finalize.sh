#!/bin/bash
# 发版二阶段：commit + push 完成后跑这个做 tag + gh release。
#
# 分阶段防幽灵 release —— 一阶段如果失败（karma hook 拦 commit），脚本退出
# 不进入二阶段，不会产生 tag 指向错 commit 的幽灵 release。
#
# 用法：scripts/release-finalize.sh <version> "<release title>" <notes-file>
set -euo pipefail

if [ $# -lt 3 ]; then
    echo "用法: $0 <version> '<release title>' <notes-file>"
    echo "例: $0 0.4.23 'v0.4.23 — bugfix' notes.md"
    exit 1
fi

VERSION="$1"
TITLE="$2"
NOTES_FILE="$3"

cd "$(dirname "$0")/.."

# 验证 HEAD 含本版本改动 — pyproject.toml 版本必须等于参数
PYPROJECT_VERSION=$(grep -E '^version = ' pyproject.toml | head -1 | sed -E 's/.*"([^"]+)".*/\1/')
if [ "$PYPROJECT_VERSION" != "$VERSION" ]; then
    echo "ERROR: HEAD pyproject v$PYPROJECT_VERSION 不等于目标 v$VERSION" >&2
    echo "上次 commit 没含 pyproject 改动？检查 git log" >&2
    exit 1
fi

# 验证 HEAD 不超前 origin（push 真成功了）
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/main)
if [ "$LOCAL" != "$REMOTE" ]; then
    echo "ERROR: 本机 HEAD 不等于 origin/main" >&2
    echo "上次 push 没真完成？先跑 git push" >&2
    exit 1
fi

echo "=== HEAD 验证通过，开始 tag + release ==="

git tag "v$VERSION"
git push --tags
gh release create "v$VERSION" --title "$TITLE" --notes-file "$NOTES_FILE"

echo "v$VERSION 真发布到 GitHub"

# 自动重装本机
scripts/verify-installed.sh --reinstall
