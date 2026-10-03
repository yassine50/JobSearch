
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "jobsearcher.db")
SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH}"

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
    from sqlalchemy import text
    try:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE users ADD COLUMN linkedin_cookie VARCHAR DEFAULT ''"))
            conn.commit()
    except Exception:
        pass

    try:
        from . import models
        db = SessionLocal()
        try:
            blocked_entries = [
                ("jnahar@dashkar.com", "Message bloqué (550 5.4.1 Recipient address rejected / Dead mailbox)"),
                ("laura.peters@fartherforward.com", "Message non distribué (Problème temporaire 47h / Dead host)"),
                ("samuel.winter@tide-forecast.com", "Adresse introuvable (Address not found / 550)"),
                ("mads.bording@rib-software.es", "Message bloqué (550 5.4.1 Recipient address rejected: Access denied)"),
            ]
            for bl_email, bl_reason in blocked_entries:
                existing = db.query(models.EmailBlacklist).filter(models.EmailBlacklist.email == bl_email).first()
                if not existing:
                    bl_entry = models.EmailBlacklist(
                        user_id=None,
                        email=bl_email,
                        reason=bl_reason,
                        source="gmail_bounce"
                    )
                    db.add(bl_entry)
                    db.commit()
                    print(f"[init_db] Added {bl_email} to EmailBlacklist")

            all_blacklisted = {r[0].strip().lower() for r in db.query(models.EmailBlacklist.email).all() if r[0]}

            # Decouple and mark EmailLogs as bounced
            db.query(models.EmailLog).filter(
                models.EmailLog.to_email.in_(list(all_blacklisted))
            ).update({"status": "bounced", "application_id": None}, synchronize_session=False)

            # Find linked application IDs from EmailLog
            linked_log_ids = {
                r[0] for r in db.query(models.EmailLog.application_id).filter(
                    models.EmailLog.application_id.isnot(None),
                    models.EmailLog.to_email.in_(list(all_blacklisted))
                ).all() if r[0]
            }

            # Find and DELETE applications matching blacklisted recipients or domains
            apps = db.query(models.Application).all()
            for app in apps:
                notes = (app.notes or "").lower()
                url = (app.url or "").lower()
                company = (app.company or "").lower()
                is_match = (app.id in linked_log_ids)
                if not is_match:
                    for bl in all_blacklisted:
                        bl_domain = bl.split('@')[-1] if '@' in bl else ''
                        domain_name = bl_domain.split('.')[0] if bl_domain else ''
                        if bl in notes or bl in url or (bl_domain and bl_domain in url) or (domain_name and len(domain_name) > 3 and domain_name in company):
                            is_match = True
                            break
                if is_match:
                    print(f"[init_db] Purging dead/bounced application: {app.title} at {app.company} (ID: {app.id})")
                    db.query(models.EmailLog).filter(models.EmailLog.application_id == app.id).update(
                        {"status": "bounced", "application_id": None}, synchronize_session=False
                    )
                    db.delete(app)

            db.commit()

            try:
                import recruiter_hunter
                recruiter_hunter.load_blacklisted_emails(force_reload=True)
            except Exception:
                pass

        finally:
            db.close()
    except Exception as e:
        print("[init_db] Blacklist error:", e)

