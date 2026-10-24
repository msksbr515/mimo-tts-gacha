# -*- coding: utf-8 -*-
"""支持 `python -m ttsgen`：以包所在目录作为项目根。"""

import sys
from pathlib import Path

from .cli import main

if __name__ == "__main__":
    sys.exit(main(Path(__file__).resolve().parent.parent))
