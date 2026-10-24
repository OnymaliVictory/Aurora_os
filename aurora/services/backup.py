"""Backups. A copy of the whole database is taken safely (even while the shop is selling)
every day automatically, and on demand. Optionally also copied to a second place such as a USB drive."""
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from .. import paths
from ..db import connect, get_setting, init_db
from . import stock

PREFIX = "aurora-"


def make_backup(label="auto") -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = paths.backup_dir() / f"{PREFIX}{stamp}-{label}.db"
    src = connect()
    try:
        out = sqlite3.connect(str(dest))
        with out:
            src.backup(out)                    # consistent snapshot, no matter what is happening
        out.close()
        keep = int(get_setting(src, "backup_keep", 14) or 14)
        extra = (get_setting(src, "backup_folder", "") or "").strip()
    finally:
        src.close()
    if extra:
        try:
            Path(extra).mkdir(parents=True, exist_ok=True)
            shutil.copy2(dest, Path(extra) / dest.name)
        except OSError:
            pass                                # a missing USB stick must never stop the shop
    files = sorted(paths.backup_dir().glob(f"{PREFIX}*.db"))
    for old in files[:-keep] if keep > 0 else []:
        try:
            old.unlink()
        except OSError:
            pass
    return dest


def list_backups():
    out = []
    for f in sorted(paths.backup_dir().glob(f"{PREFIX}*.db"), reverse=True):
        out.append({"name": f.name, "size": f.stat().st_size,
                    "when": datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M")})
    return out


def restore_backup(name: str) -> None:
    """Replace today's data with a backup. A safety copy of the current data is made first."""
    src = (paths.backup_dir() / Path(name).name)          # .name strips any folder tricks
    if not src.exists() or not src.name.startswith(PREFIX):
        raise FileNotFoundError("Backup not found.")
    test = sqlite3.connect(str(src))
    try:
        ok = test.execute("PRAGMA integrity_check").fetchone()[0]
        has = test.execute("SELECT name FROM sqlite_master WHERE name='products'").fetchone()
    finally:
        test.close()
    if ok != "ok" or not has:
        raise ValueError("That backup file is damaged or is not an Aurora OS backup.")
    make_backup("before-restore")
    # Copy the backup INTO the live database with SQLite's own backup tool. We never delete or
    # swap files, because Windows refuses to delete a database file that is open anywhere.
    snap = sqlite3.connect(str(src))
    live = connect()
    try:
        snap.backup(live)
        live.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        snap.close()
        live.close()
    init_db()                                   # upgrades an older backup to the current structure


def run_startup_tasks():
    conn = connect()
    try:
        if get_setting(conn, "setup_done") == "1":
            if get_setting(conn, "auto_backup") == "1":
                today = datetime.now().strftime("%Y%m%d")
                if not list(paths.backup_dir().glob(f"{PREFIX}{today}-*.db")):
                    conn.close()
                    make_backup("auto")
                    conn = connect()
            conn.execute("BEGIN")
            stock.scan_expiry(conn)
            conn.execute("COMMIT")
    except Exception:
        pass                                    # chores must never stop the app from opening
    finally:
        try:
            conn.close()
        except Exception:
            pass
