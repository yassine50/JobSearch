
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey
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
    saved_jobs = relationship("SavedJob", back_populates="user")
    cv_uploads = relationship("CvUpload", back_populates="user")

class SavedJob(Base):
    __tablename__ = "saved_jobs"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    title = Column(String)
    company = Column(String)
    location = Column(String)
    url = Column(String)
    description = Column(Text)
    match_score = Column(Integer, default=0)
    saved_at = Column(DateTime, default=datetime.utcnow)
    user = relationship("User", back_populates="saved_jobs")

class CvUpload(Base):
    __tablename__ = "cv_uploads"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    filename = Column(String)
    text_content = Column(Text)
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    user = relationship("User", back_populates="cv_uploads")
