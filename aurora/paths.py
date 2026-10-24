"""Where Aurora OS keeps its files.

Everything the shop owns (database, backups, product pictures) lives in ONE folder
outside the program folder, so updating or reinstalling the app never touches the data.

  Windows : C:\\Users\\<you>\\AppData\\Roaming\\AuroraOS
  Linux   : ~/.local/share/AuroraOS
  Override: set the AURORA_DATA_DIR environment variable (used by the tests).
"""
import os
import sys
from pathlib import Path


def app_dir() -> Path:
    """Folder that holds the program's own files (templates, static)."""
    if getattr(sys, "frozen", False):          # running from the PyInstaller exe
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent


def data_dir() -> Path:
    override = os.environ.get("AURORA_DATA_DIR")
    if override:
        base = Path(override)
    elif os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home())) / "AuroraOS"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "AuroraOS"
    base.mkdir(parents=True, exist_ok=True)
    return base


def db_path() -> Path:
    return data_dir() / "aurora.db"


def backup_dir() -> Path:
    p = data_dir() / "backups"
    p.mkdir(parents=True, exist_ok=True)
    return p


def upload_dir() -> Path:
    p = data_dir() / "uploads"
    p.mkdir(parents=True, exist_ok=True)
    return p
