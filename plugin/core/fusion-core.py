"""fusion-core launcher: no installation required; runs code directly from the plugin directory."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fusion_core.cli import main

sys.exit(main())
