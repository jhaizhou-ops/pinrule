#!/bin/bash
# pinrule 发版工作流脚本 — 防幽灵 release。
#
# 真触发：v0.4.22 commit 被 pinrule 自己 pre_tool_use hook 拦了（命令字面含真
# 阻塞 pattern），但 shell `&&` 链没真短路，后续 tag/push/release 基于没含
# 改动的 head 跑成功 → v0.4.22 tag 指向 v0.4.21 commit 的幽灵 release。
#
# fix：把发版工作流拆成 set -e 脚本，每步失败立即退出。明确区分「准备阶段」
# （commit + push）vs「标记阶段」（tag + release）— 准备失败时根本不进入标记。
#
# 用法：
#   scripts/release.sh <version>
#   例：scripts/release.sh 0.4.23
#
# 调用前必须：
# - 改完 pyproject.toml version
# - 写好 CHANGELOG.md 对应版本段
# - 所有 fix 代码改完，working tree 准备 commit
#
# 脚本会：
# 1. set -e 失败立即退出
# 2. 验证 pyproject 版本跟参数匹配（防版本不一致 release）
# 3. 跑 pytest 确保全过（不过就不发版）
# 4. git status 显示当前改动
# 5. 提示用户手动 commit（避免脚本里写命令字面被 pinrule hook 拦） + push
# 6. 等用户确认 push 完成 → 才 tag + push tag + gh release
#
# 设计原则：pinrule hook 可能拦 commit 但不会拦 tag/release/push — 分阶段防幽灵
set -euo pipefail

if [ $# -lt 1 ]; then
    echo "用法: $0 <version>"
    echo "例: $0 0.4.23"
    exit 1
fi

VERSION="$1"
cd "$(dirname "$0")/.."

PYPROJECT_VERSION=$(grep -E '^version = ' pyproject.toml | head -1 | sed -E 's/.*"([^"]+)".*/\1/')
if [ "$PYPROJECT_VERSION" != "$VERSION" ]; then
    echo "ERROR: 参数 $VERSION 跟 pyproject.toml v$PYPROJECT_VERSION 不一致" >&2
    echo "→ 先改 pyproject.toml 再调脚本" >&2
    exit 1
fi

echo "=== 发版准备 v$VERSION ==="

echo "→ 跑全测..."
.venv/bin/python -m pytest tests/ -q | tail -3
echo "✓ 测试全过"

echo
echo "→ 当前未提交改动："
git status -s

echo
echo "请手动跑下面命令完成 commit + push（脚本不写命令字面避免 pinrule hook 拦）："
echo "  git add -A"
echo "  git commit -m '<commit message>'"
echo "  git push"
echo
echo "完成后再跑：scripts/release.sh-finalize $VERSION"
