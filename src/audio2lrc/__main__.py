"""Allow `python -m audio2lrc`."""

import sys

from audio2lrc.cli import main

if __name__ == "__main__":
    sys.exit(main())