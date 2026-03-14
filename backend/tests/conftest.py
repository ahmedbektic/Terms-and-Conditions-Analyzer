from pathlib import Path
import os
import sys

# Keep test runs on the lightweight in-memory persistence backend by default.
os.environ.setdefault("PERSISTENCE_BACKEND", "memory")

sys.path.append(str(Path(__file__).resolve().parents[1]))
