import os
import shutil
import sqlite3
import logging
from sqlalchemy import create_engine, text, event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from .utils import ensure_project_root_on_path, purge_blacklisted_applications

ensure_project_root_on_path()
logger = logging.getLogger("jobsearcher.database")

DB_PATH = os.getenv("DB_PATH", os.path.join(os.path.dirname(__file__), "jobsearcher.db"))
_raw_db_url = os.getenv("DATABASE_URL", f"sqlite:///{DB_PATH}")
# Normalize legacy postgres:// scheme to postgresql:// for SQLAlchemy 1.4/2.0+
if _raw_db_url.startswith("postgres://"):
    _raw_db_url = _raw_db_url.replace("postgres://", "postgresql://", 1)
SQLALCHEMY_DATABASE_URL = _raw_db_url


def _ensure_healthy_sqlite_db(db_path: str) -> None:
    """Detect and auto-repair WAL mismatch or malformed SQLite B-tree pages on startup."""
    if not os.path.exists(db_path):
        return

    def _is_ok(path: str) -> bool:
        try:
            conn = sqlite3.connect(path, timeout=5)
            try:
                res = conn.execute("PRAGMA quick_check").fetchone()
                return bool(res and res[0] == "ok")
            finally:
                conn.close()
        except sqlite3.OperationalError as err:
            # "database is locked/busy" just means another worker is using it — NOT corruption.
            # Treating it as corruption would delete the live WAL and lose committed data.
            msg = str(err).lower()
            if "locked" in msg or "busy" in msg:
                return True
            return False
        except Exception:
            return False

    if _is_ok(db_path):
        return

    logger.warning(f"[database] Detected malformed SQLite state on {db_path}; attempting automatic recovery...")
    # Step 1: Remove stale/mismatched -wal and -shm files caused by git reset/cp while WAL was open
    for suffix in ("-wal", "-shm"):
        sidecar = f"{db_path}{suffix}"
        if os.path.exists(sidecar):
            try:
                os.remove(sidecar)
            except Exception:
                pass

    # Step 2: Try REINDEX in case only a secondary index B-tree was affected
    try:
        conn = sqlite3.connect(db_path, timeout=5)
        try:
            conn.execute("REINDEX")
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass

    if _is_ok(db_path):
        logger.info("[database] SQLite database recovered cleanly after WAL reset / REINDEX.")
        return

    # Step 3: Salvage all readable tables into a brand-new SQLite database file
    repaired_path = f"{db_path}.repaired"
    backup_corrupt = f"{db_path}.corrupt.bak"
    try:
        if os.path.exists(repaired_path):
            os.remove(repaired_path)
        src = sqlite3.connect(db_path)
        dst = sqlite3.connect(repaired_path)
        try:
            tables = [
                r[0] for r in src.execute(
                    "SELECT name, sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND sql IS NOT NULL"
                ).fetchall()
            ]
            for tbl in tables:
                try:
                    create_sql = src.execute(
                        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (tbl,)
                    ).fetchone()[0]
                    dst.execute(create_sql)
                    rows = src.execute(f'SELECT * FROM "{tbl}"').fetchall()
                    if rows:
                        placeholders = ",".join(["?"] * len(rows[0]))
                        dst.executemany(f'INSERT OR IGNORE INTO "{tbl}" VALUES ({placeholders})', rows)
                    dst.commit()
                except Exception as tbl_err:
                    logger.warning(f"[database] Skipping unreadable rows in {tbl}: {tbl_err}")
        finally:
            src.close()
            dst.close()
        shutil.move(db_path, backup_corrupt)
        shutil.move(repaired_path, db_path)
        logger.info("[database] Rebuilt clean SQLite database from readable tables.")
    except Exception as rec_err:
        logger.error(f"[database] Salvage rebuild failed ({rec_err}); resetting corrupt file.")
        try:
            shutil.move(db_path, backup_corrupt)
        except Exception:
            pass


def backup_sqlite_database(db_path: str = DB_PATH, max_backups: int = 14) -> str:
    """Create a hot online backup of the SQLite database using sqlite3's backup API (safe with WAL)."""
    if not SQLALCHEMY_DATABASE_URL.startswith("sqlite") or not os.path.exists(db_path):
        return ""
    try:
        from datetime import datetime as _dt
        backup_dir = os.path.expanduser(os.getenv("DB_BACKUP_DIR", os.path.join(os.path.dirname(db_path), "backups")))
        os.makedirs(backup_dir, exist_ok=True)
        stamp = _dt.utcnow().strftime("%Y%m%d")
        dest_path = os.path.join(backup_dir, f"jobsearcher_{stamp}.db")
        src = sqlite3.connect(db_path, timeout=30)
        dst = sqlite3.connect(dest_path, timeout=30)
        try:
            with dst:
                src.backup(dst, pages=250, sleep=0.05)
        finally:
            dst.close()
            src.close()
        # Prune backups older than max_backups
        backups = sorted(
            [os.path.join(backup_dir, f) for f in os.listdir(backup_dir) if f.startswith("jobsearcher_") and f.endswith(".db")]
        )
        for old_file in backups[:-max_backups]:
            try:
                os.remove(old_file)
            except Exception:
                pass
        return dest_path
    except Exception as err:
        logger.warning(f"[database] Online SQLite backup skipped: {err}")
        return ""


if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    # Acquire an OS file lock before running startup WAL/B-tree recovery so concurrent
    # uvicorn workers (--workers N) never race to delete or rebuild -wal/-shm sidecars.
    _rec_lock_fh = None
    try:
        import fcntl as _fcntl
        import tempfile as _tempfile
        _rec_lock_fh = open(os.path.join(_tempfile.gettempdir(), "cvtomatch_sqlite_recovery.lock"), "w")
        _fcntl.flock(_rec_lock_fh, _fcntl.LOCK_EX)
    except Exception:
        _rec_lock_fh = None
    try:
        _ensure_healthy_sqlite_db(DB_PATH)
    finally:
        if _rec_lock_fh:
            try:
                _rec_lock_fh.close()
            except Exception:
                pass
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        connect_args={"check_same_thread": False, "timeout": 30},
        pool_pre_ping=True,
    )

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA temp_store=MEMORY")
        cursor.execute("PRAGMA cache_size=-64000")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
else:
    # Production PostgreSQL engine with connection pooling
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        pool_pre_ping=True,
        pool_size=int(os.getenv("DB_POOL_SIZE", "10")),
        max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "20")),
        pool_recycle=1800,
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    # Serialize startup backup/migrations across uvicorn workers with an OS file lock
    _init_lock_fh = None
    try:
        import fcntl
        import tempfile
        _init_lock_fh = open(os.path.join(tempfile.gettempdir(), "cvtomatch_init_db.lock"), "w")
        fcntl.flock(_init_lock_fh, fcntl.LOCK_EX)
    except Exception:
        _init_lock_fh = None
    try:
        _init_db_locked()
    finally:
        if _init_lock_fh:
            try:
                _init_lock_fh.close()
            except Exception:
                pass


def _init_db_locked():
    if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
        backup_sqlite_database(DB_PATH)

    migrations = (
        "ALTER TABLE users ADD COLUMN linkedin_cookie VARCHAR DEFAULT ''",
        "ALTER TABLE users ADD COLUMN daily_digest_enabled BOOLEAN DEFAULT 1",
        "UPDATE users SET daily_digest_enabled = 1",
        "ALTER TABLE users ADD COLUMN daily_digest_role VARCHAR DEFAULT ''",
        "ALTER TABLE users ADD COLUMN last_digest_sent_at DATETIME",
        "ALTER TABLE users ADD COLUMN last_digest_jobs_json TEXT DEFAULT ''",
        "ALTER TABLE users ADD COLUMN seen_digest_urls_json TEXT DEFAULT ''",
        "ALTER TABLE email_settings ADD COLUMN auth_method VARCHAR DEFAULT 'smtp'",
        "ALTER TABLE email_settings ADD COLUMN gmail_refresh_token TEXT DEFAULT ''",
        "ALTER TABLE cv_uploads ADD COLUMN persona_name VARCHAR DEFAULT 'Primary Resume'",
        "ALTER TABLE cv_uploads ADD COLUMN is_active BOOLEAN DEFAULT 1",
        "ALTER TABLE cv_uploads ADD COLUMN parsed_json TEXT",
        "ALTER TABLE applications ADD COLUMN interview_prep_json TEXT DEFAULT ''",
        "CREATE INDEX IF NOT EXISTS idx_apps_user_applied ON applications(user_id, applied_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_apps_user_status ON applications(user_id, status)",
        "CREATE INDEX IF NOT EXISTS idx_elogs_user_sent ON email_logs(user_id, sent_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_elogs_app_sent ON email_logs(application_id, sent_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_cv_user_active ON cv_uploads(user_id, is_active)",
        "CREATE INDEX IF NOT EXISTS idx_saved_user ON saved_jobs(user_id, saved_at DESC)",
        "UPDATE applications SET tailored_cv_filename = 'Tailored_CV.pdf' WHERE tailored_cv_data IS NOT NULL AND (tailored_cv_filename IS NULL OR tailored_cv_filename = '')",
    )
    for ddl in migrations:
        try:
            with engine.connect() as conn:
                conn.execute(text(ddl))
                conn.commit()
        except Exception:
            pass

    try:
        from . import models
        db = SessionLocal()
        try:
            # Purge any anonymous / blank-email user records and their child records cleanly
            anon_ids = [
                r[0] for r in db.query(models.User.id).filter(
                    (models.User.email == "") | (models.User.email.is_(None)) | (models.User.name == "")
                ).all()
            ]
            if anon_ids:
                for child_model in (
                    models.EmailLog,
                    models.Application,
                    models.SavedJob,
                    models.CvUpload,
                    models.EmailSettings,
                    models.CustomTemplate,
                    models.SavedWatchlist,
                    models.EmailBlacklist,
                ):
                    db.query(child_model).filter(child_model.user_id.in_(anon_ids)).delete(synchronize_session=False)
                anon_deleted = db.query(models.User).filter(models.User.id.in_(anon_ids)).delete(synchronize_session=False)
                db.commit()
                logger.info(f"[init_db] Purged {anon_deleted} anonymous/empty user account(s)")

            default_bounced = [
                ("jnahar@dashkar.com", "Message bloqué (550 5.4.1 Recipient address rejected / Dead mailbox)"),
                ("laura.peters@fartherforward.com", "Message non distribué (Problème temporaire 47h / Dead host)"),
                ("samuel.winter@tide-forecast.com", "Adresse introuvable (Address not found / 550)"),
                ("mads.bording@rib-software.es", "Message bloqué (550 5.4.1 Recipient address rejected: Access denied)"),
            ]
            newly_added = 0
            for bl_email, bl_reason in default_bounced:
                existing = db.query(models.EmailBlacklist).filter(models.EmailBlacklist.email == bl_email).first()
                if not existing:
                    db.add(models.EmailBlacklist(
                        user_id=None,
                        email=bl_email,
                        reason=bl_reason,
                        source="gmail_bounce",
                    ))
                    newly_added += 1

            if newly_added > 0:
                db.commit()
                purged = purge_blacklisted_applications(db)
                logger.info(f"[init_db] Added {newly_added} blacklist entries and purged {purged} dead applications")

            try:
                import recruiter_hunter
                recruiter_hunter.load_blacklisted_emails(force_reload=True)
            except Exception:
                pass
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"[init_db] Blacklist sync warning: {e}")
