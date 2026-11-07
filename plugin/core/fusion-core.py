"""fusion-core 的启动脚本:不依赖安装,直接用插件目录里的代码。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fusion_core.cli import main

sys.exit(main())
