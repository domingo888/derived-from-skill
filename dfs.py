"""仓库根启动器：python dfs.py <command>，无需安装即可运行。"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "runtime"))

from dfs_runtime.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
