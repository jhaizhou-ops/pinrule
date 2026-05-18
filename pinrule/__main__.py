"""Allow `python -m pinrule` — delegates to the `pinrule` console script entrypoint."""

from pinrule._io_encoding import force_utf8_stdio
from pinrule.cli import main

if __name__ == "__main__":
    force_utf8_stdio()  # Windows zh-CN GBK 默认会让 `▸` / 🛑 print 崩溃
    raise SystemExit(main())
