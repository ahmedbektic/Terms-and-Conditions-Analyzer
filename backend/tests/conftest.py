from pathlib import Path
import os
import sys

# Keep test runs on the lightweight in-memory persistence backend by default.
os.environ.setdefault("PERSISTENCE_BACKEND", "memory")
# JWT-only auth is the default runtime behavior. Tests disable signature
# verification unless they explicitly exercise signature checks.
os.environ.setdefault("AUTH_REQUIRE_JWT_SIGNATURE_VERIFICATION", "false")

sys.path.append(str(Path(__file__).resolve().parents[1]))
