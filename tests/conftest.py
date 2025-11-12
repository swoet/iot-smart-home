import sys
from pathlib import Path

# Ensure src is importable when running tests without installation
sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))
