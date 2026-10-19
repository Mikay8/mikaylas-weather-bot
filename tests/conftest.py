import sys
from pathlib import Path

# tests run with the repo's src/ layout (same PYTHONPATH=src convention as
# .railway/railway.ts); make `weatherbot` importable without installing.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
