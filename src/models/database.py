"""
SQLAlchemy database models for the Naukri Profile Refresh web app.
"""

from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()


class User(db.Model):
    """Platform user — registers and logs into the web app."""
    __tablename__ = "users"

    id            = db.Column(db.Integer, primary_key=True)
    email         = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)

    # One-to-one relationship with profile
    profile = db.relationship("Profile", backref="user", uselist=False, cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "email": self.email,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Profile(db.Model):
    """Naukri automation settings for a user."""
    __tablename__ = "profiles"

    id                = db.Column(db.Integer, primary_key=True)
    user_id           = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)
    naukri_username    = db.Column(db.String(255))
    naukri_password    = db.Column(db.Text)       # Fernet encrypted
    resume_drive_link  = db.Column(db.String(500))
    headline_1         = db.Column(db.Text)
    headline_2         = db.Column(db.Text)
    summary_1          = db.Column(db.Text)
    summary_2          = db.Column(db.Text)
    refresh_interval   = db.Column(db.Integer, default=3600)
    is_active          = db.Column(db.Boolean, default=True)
    last_refreshed     = db.Column(db.DateTime)
    last_status        = db.Column(db.String(50))   # 'success' | 'failed'
    last_error         = db.Column(db.Text)
    total_refreshes    = db.Column(db.Integer, default=0)
    created_at         = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at         = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "naukri_username": self.naukri_username,
            "resume_drive_link": self.resume_drive_link,
            "headline_1": self.headline_1,
            "headline_2": self.headline_2,
            "summary_1": self.summary_1,
            "summary_2": self.summary_2,
            "refresh_interval": self.refresh_interval,
            "is_active": self.is_active,
            "last_refreshed": self.last_refreshed.isoformat() if self.last_refreshed else None,
            "last_status": self.last_status,
            "last_error": self.last_error,
            "total_refreshes": self.total_refreshes or 0,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
