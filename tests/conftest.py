import sys
from pathlib import Path

# Ensure project root (one level up from tests) is on sys.path so tests can import app.*
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
