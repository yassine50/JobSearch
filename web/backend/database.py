import os
import logging
from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from .utils import ensure_project_root_on_path, purge_blacklisted_applications

ensure_project_root_on_path()
logger = logging.getLogger("jobsearcher.database")

DB_PATH = os.getenv("DB_PATH", os.path.join(os.path.dirname(__file__), "jobsearcher.db"))
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DB_PATH}")

engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
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
