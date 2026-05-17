"""pinrule v2 — 让 Agent 不在长任务中遗忘用户最重视的几条核心方向。"""

# 版本号从 pyproject.toml 单一来源读 — 避免双维护失同步
# （历史 bug：__init__.py 硬写 0.1.0 而 pyproject 已经 0.4.3，导致 pinrule --version 错）
try:
    from importlib.metadata import version as _pkg_version
    __version__ = _pkg_version("pinrule")
except Exception:
    # 开发期或没 install 的 fallback
    __version__ = "0.0.0-dev"
