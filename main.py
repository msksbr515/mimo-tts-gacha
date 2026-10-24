#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""入口脚本：python main.py [文本文件]

逻辑都在 ttsgen 包里，这里只负责把项目目录（config.yaml 所在处）交给它。
"""

import sys
from pathlib import Path

from ttsgen.cli import main

if __name__ == "__main__":
    sys.exit(main(Path(__file__).resolve().parent))
