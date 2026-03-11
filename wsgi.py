"""
WSGI entry point so Render/gunicorn can find the app when run from repo root.
Adds the project root to sys.path so imports like instance_generator work.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.main import app
