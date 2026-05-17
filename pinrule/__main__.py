"""Allow `python -m pinrule` — delegates to the `pinrule` console script entrypoint."""

from pinrule.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
