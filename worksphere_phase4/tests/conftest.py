import os
import sys
import tempfile
from pathlib import Path

# Must be set before the app package is imported.
os.environ.setdefault("SECRET_KEY", "test-secret-key-that-is-definitely-longer-than-32-chars")
os.environ.setdefault("DATABASE_URL", "sqlite:///" + str(Path(tempfile.mkdtemp()) / "test.db"))
os.environ.setdefault("EMAIL_ENABLED", "false")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
