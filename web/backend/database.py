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
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DB_PATH}")


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


if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    _ensure_healthy_sqlite_db(DB_PATH)

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False, "timeout": 15},
    pool_pre_ping=True,
)

if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA temp_store=MEMORY")
        cursor.execute("PRAGMA cache_size=-32000")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    migrations = (
        "ALTER TABLE users ADD COLUMN linkedin_cookie VARCHAR DEFAULT ''",
        "ALTER TABLE email_settings ADD COLUMN auth_method VARCHAR DEFAULT 'smtp'",
        "ALTER TABLE email_settings ADD COLUMN gmail_refresh_token TEXT DEFAULT ''",
        "ALTER TABLE cv_uploads ADD COLUMN persona_name VARCHAR DEFAULT 'Primary Resume'",
        "ALTER TABLE cv_uploads ADD COLUMN is_active BOOLEAN DEFAULT 1",
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
            # Purge any anonymous / blank-email user records
            anon_deleted = db.query(models.User).filter(
                (models.User.email == "") | (models.User.email.is_(None)) | (models.User.name == "")
            ).delete(synchronize_session=False)
            if anon_deleted:
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
