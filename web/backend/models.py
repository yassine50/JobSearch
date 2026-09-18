
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, LargeBinary, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from .database import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(String, default="seeker")
    created_at = Column(DateTime, default=datetime.utcnow)
    saved_jobs     = relationship("SavedJob",      back_populates="user")
    cv_uploads     = relationship("CvUpload",      back_populates="user")
    email_logs     = relationship("EmailLog",      back_populates="user")
    applications   = relationship("Application",   back_populates="user")
    email_settings = relationship("EmailSettings", back_populates="user", uselist=False)

class SavedJob(Base):
    __tablename__ = "saved_jobs"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    title = Column(String); company = Column(String)
    location = Column(String); url = Column(String)
    description = Column(Text); match_score = Column(Integer, default=0)
    saved_at = Column(DateTime, default=datetime.utcnow)
    user = relationship("User", back_populates="saved_jobs")

class CvUpload(Base):
    __tablename__ = "cv_uploads"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    filename = Column(String); text_content = Column(Text)
    file_data = Column(LargeBinary, nullable=True)
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    user = relationship("User", back_populates="cv_uploads")

class EmailLog(Base):
    __tablename__ = "email_logs"
    id = Column(Integer, primary_key=True, index=True)
    user_id        = Column(Integer, ForeignKey("users.id"))
    application_id = Column(Integer, ForeignKey("applications.id"), nullable=True)
    to_email       = Column(String); to_name = Column(String)
    subject        = Column(String); body = Column(Text)
    template_type  = Column(String)
    status         = Column(String, default="sent")
    sent_at        = Column(DateTime, default=datetime.utcnow)
    user        = relationship("User",        back_populates="email_logs")
    application = relationship("Application", back_populates="email_logs")

class Application(Base):
    __tablename__ = "applications"
    id = Column(Integer, primary_key=True, index=True)
    user_id    = Column(Integer, ForeignKey("users.id"))
    title      = Column(String); company = Column(String)
    location   = Column(String); url = Column(String)
    status     = Column(String, default="applied")
    notes      = Column(Text, default="")
    match_score = Column(Integer, default=0)
    applied_at  = Column(DateTime, default=datetime.utcnow)
    follow_up_date = Column(DateTime, nullable=True)
    tailored_cv_filename = Column(String, nullable=True)
    tailored_cv_data = Column(LargeBinary, nullable=True)
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
    user = relationship("User", back_populates="email_settings")

class CustomTemplate(Base):
    __tablename__ = 'custom_templates'
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    name = Column(String, nullable=False)
    subject = Column(String, default='')
    body = Column(Text, default='')
    created_at = Column(DateTime, default=datetime.utcnow)
