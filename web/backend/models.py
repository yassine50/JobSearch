
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, LargeBinary, Boolean
from sqlalchemy.orm import relationship, deferred
from datetime import datetime
from .database import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(String, default="seeker")
    linkedin_cookie = Column(String, default="", nullable=True)
    daily_digest_enabled = Column(Boolean, default=True)
    daily_digest_role = Column(String, default="")
    last_digest_sent_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    saved_jobs     = relationship("SavedJob",      back_populates="user")
    cv_uploads     = relationship("CvUpload",      back_populates="user")
    email_logs     = relationship("EmailLog",      back_populates="user")
    applications   = relationship("Application",   back_populates="user")
    email_settings = relationship("EmailSettings", back_populates="user", uselist=False)
    blacklisted_emails = relationship("EmailBlacklist", back_populates="user")

class SavedJob(Base):
    __tablename__ = "saved_jobs"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    title = Column(String); company = Column(String)
    location = Column(String); url = Column(String)
    description = Column(Text); match_score = Column(Integer, default=0)
    saved_at = Column(DateTime, default=datetime.utcnow)
    user = relationship("User", back_populates="saved_jobs")

class CvUpload(Base):
    __tablename__ = "cv_uploads"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    persona_name = Column(String, default="Primary Resume")
    is_active = Column(Boolean, default=True)
    filename = Column(String); text_content = Column(Text)
    file_data = deferred(Column(LargeBinary, nullable=True))
    # User-reviewed structured CV (CV.to_dict() JSON). When set, tailoring uses it instead of re-parsing file_data.
    parsed_json = Column(Text, nullable=True)
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    user = relationship("User", back_populates="cv_uploads")

class EmailLog(Base):
    __tablename__ = "email_logs"
    id = Column(Integer, primary_key=True, index=True)
    user_id        = Column(Integer, ForeignKey("users.id"), index=True)
    application_id = Column(Integer, ForeignKey("applications.id"), nullable=True, index=True)
    to_email       = Column(String); to_name = Column(String)
    subject        = Column(String); body = Column(Text)
    template_type  = Column(String)
    status         = Column(String, default="sent")
    sent_at        = Column(DateTime, default=datetime.utcnow, index=True)
    user        = relationship("User",        back_populates="email_logs")
    application = relationship("Application", back_populates="email_logs")

class Application(Base):
    __tablename__ = "applications"
    id = Column(Integer, primary_key=True, index=True)
    user_id    = Column(Integer, ForeignKey("users.id"), index=True)
    title      = Column(String); company = Column(String)
    location   = Column(String); url = Column(String)
    status     = Column(String, default="applied", index=True)
    notes      = Column(Text, default="")
    match_score = Column(Integer, default=0)
    applied_at  = Column(DateTime, default=datetime.utcnow, index=True)
    follow_up_date = Column(DateTime, nullable=True)
    tailored_cv_filename = Column(String, nullable=True)
    tailored_cv_data = deferred(Column(LargeBinary, nullable=True))
    interview_prep_json = deferred(Column(Text, default=""))
    user       = relationship("User",     back_populates="applications")
    email_logs = relationship("EmailLog", back_populates="application")

class EmailSettings(Base):
    __tablename__ = "email_settings"
    user_id       = Column(Integer, ForeignKey("users.id"), primary_key=True)
    smtp_host     = Column(String, default="smtp.gmail.com")
    smtp_port     = Column(Integer, default=587)
    smtp_user     = Column(String, default="")
    smtp_password = Column(String, default="")
    sender_name   = Column(String, default="")
    auth_method   = Column(String, default="smtp")   # "smtp" (App Password) | "gmail_oauth" (Connect Gmail)
    gmail_refresh_token = Column(Text, default="")
    user = relationship("User", back_populates="email_settings")

class CustomTemplate(Base):
    __tablename__ = 'custom_templates'
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    name = Column(String, nullable=False)
    subject = Column(String, default='')
    body = Column(Text, default='')
    created_at = Column(DateTime, default=datetime.utcnow)

class EmailBlacklist(Base):
    __tablename__ = "email_blacklist"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    email = Column(String, index=True, nullable=False)
    reason = Column(String, default="Bounced")
    source = Column(String, default="gmail_bounce")
    created_at = Column(DateTime, default=datetime.utcnow)
    user = relationship("User", back_populates="blacklisted_emails")


class JobSighting(Base):
    """
    Global history of every posting seen in searches (career-ops scan-history).
    Powers ghost-job detection: the same company+title re-posted under new URLs,
    or a listing that has stayed open for months, is a strong ghost-posting signal.
    """
    __tablename__ = "job_sightings"
    id = Column(Integer, primary_key=True, index=True)
    fingerprint = Column(String, index=True, nullable=False)   # norm(company)|norm(title)
    url_key     = Column(String, index=True, nullable=False)   # canonical URL
    title       = Column(String); company = Column(String)
    first_seen  = Column(DateTime, default=datetime.utcnow)
    last_seen   = Column(DateTime, default=datetime.utcnow)
    times_seen  = Column(Integer, default=1)


class VerifiedRecruiterPost(Base):
    """
    Persistent index of verified LinkedIn recruiter posts with exact Snowflake timestamps
    and MX-verified emails, allowing searches to accumulate high-accuracy posts over time.
    """
    __tablename__ = "verified_recruiter_posts"
    id               = Column(Integer, primary_key=True, index=True)
    post_id          = Column(String, unique=True, index=True, nullable=False)
    post_url         = Column(String, unique=True, index=True, nullable=False)
    role_key         = Column(String, index=True, nullable=False)  # normalized role family e.g. "flutter developer"
    role_title       = Column(String, default="")
    company          = Column(String, default="Hiring Team")
    author_name      = Column(String, default="LinkedIn Recruiter")
    author_headline  = Column(String, default="")
    author_profile_url = Column(String, default="")
    location         = Column(String, default="Worldwide")
    full_text        = Column(Text, default="")
    recruiter_emails_json = Column(Text, default="[]")
    matched_skills_json   = Column(Text, default="[]")
    hiring_signals_json   = Column(Text, default="[]")
    role_fit_score   = Column(Integer, default=75)
    date_published   = Column(String, nullable=True)  # ISO-8601 UTC from Snowflake / JSON-LD
    published_epoch  = Column(Integer, index=True, default=0)
    discovered_at    = Column(DateTime, default=datetime.utcnow)


class SavedWatchlist(Base):
    """
    User-defined Auto-Pilot Watchlist for recurring role & location harvesting.
    """
    __tablename__ = "saved_watchlists"
    id                  = Column(Integer, primary_key=True, index=True)
    user_id             = Column(Integer, ForeignKey("users.id"), index=True)
    role                = Column(String, nullable=False)
    locations_json      = Column(Text, default='["Worldwide"]')
    auto_pilot          = Column(Boolean, default=True)
    min_match_score     = Column(Integer, default=65)
    new_matches_count   = Column(Integer, default=0)
    cached_results_json = Column(Text, default="[]")
    last_run_at         = Column(DateTime, nullable=True)
    created_at          = Column(DateTime, default=datetime.utcnow)

