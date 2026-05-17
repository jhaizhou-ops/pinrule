"""Allow `python -m karma` — delegates to the `karma` console script entrypoint."""

from karma.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
