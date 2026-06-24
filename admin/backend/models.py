"""
SQLAlchemy models for FAIA Chat System database.
All models are aligned with admin/db/faia_chat_system.sql.
"""

from sqlalchemy import Boolean, Column, Integer, String, DateTime, Text, Enum, ForeignKey
from sqlalchemy.types import DECIMAL
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from config import Base
import enum


class UserRole(str, enum.Enum):
    ADMIN = "ADMIN"
    PROFESSOR = "PROFESSOR"
    STUDENT = "STUDENT"


class UserStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    DEACTIVATED = "DEACTIVATED"
    SUSPENDED = "SUSPENDED"


class MessageSender(str, enum.Enum):
    USER = "user"
    AI = "ai"


class FileStatus(str, enum.Enum):
    VALIDATED = "VALIDATED"
    ANALYZED = "ANALYZED"
    ERROR = "ERROR"


class ReportStatus(str, enum.Enum):
    PENDING = "pending"
    VALIDATED = "validated"
    RESOLVED = "resolved"


class ModerationActionType(str, enum.Enum):
    WARNING = "warning"
    SUSPEND = "suspend"
    MARK_VIEWED = "mark_viewed"


class User(Base):
    __tablename__ = "users"

    user_id = Column(Integer, primary_key=True)
    username = Column(String(100), unique=True, index=True, nullable=False)
    email = Column(String(150), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    password_salt = Column(String(32), nullable=False)  # NOT NULL per schema
    role = Column(Enum(UserRole), nullable=False, default=UserRole.STUDENT)
    status = Column(Enum(UserStatus), nullable=False, default=UserStatus.ACTIVE)
    created_at = Column(DateTime, default=func.now())
    last_login = Column(DateTime)

    token_limits = relationship("TokenLimit", back_populates="user")
    sessions = relationship("Session", back_populates="user")
    audit_logs = relationship("AuditLog", back_populates="actor")
    chats = relationship("Chat", back_populates="user")
    uploaded_files = relationship("UploadedFile", back_populates="user")
    moderation_reports = relationship("ModerationReport", back_populates="reported_by_user")
    moderation_actions = relationship("ModerationAction", back_populates="admin")


class TokenLimit(Base):
    __tablename__ = "token_limits"

    limit_id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    max_tokens = Column(Integer, default=100000)
    used_tokens = Column(Integer, default=0)
    period_start = Column(DateTime, default=func.now())
    period_end = Column(DateTime)

    user = relationship("User", back_populates="token_limits")


class Session(Base):
    __tablename__ = "sessions"

    session_id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    login_time = Column(DateTime, default=func.now())
    logout_time = Column(DateTime)
    ip_address = Column(String(45))
    current_chat_id = Column(Integer, ForeignKey("chats.chat_id"), nullable=True)
    last_activity = Column(DateTime, default=func.now(), onupdate=func.now())
    status = Column(String(20), default="active")

    user = relationship("User", back_populates="sessions")
    current_chat = relationship("Chat", foreign_keys=[current_chat_id])


class AuditLog(Base):
    __tablename__ = "audit_logs"

    log_id = Column(Integer, primary_key=True)
    admin_id = Column(Integer, ForeignKey("users.user_id"), nullable=True)  # NULL allowed — schema uses ON DELETE SET NULL
    action = Column(String(255), nullable=False)
    target_id = Column(Integer)
    target_table = Column(String(100))
    details = Column(Text)  # present in schema, was missing from model
    timestamp = Column(DateTime, default=func.now())

    actor = relationship("User", back_populates="audit_logs")


class Chat(Base):
    __tablename__ = "chats"

    chat_id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    title = Column(String(255))
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    session_id = Column(Integer, ForeignKey("sessions.session_id"), nullable=True)
    is_active = Column(Boolean, default=True)

    user = relationship("User", back_populates="chats")
    messages = relationship("Message", back_populates="chat")
    uploaded_files = relationship("UploadedFile", back_populates="chat")


class Message(Base):
    __tablename__ = "messages"

    message_id = Column(Integer, primary_key=True)
    chat_id = Column(Integer, ForeignKey("chats.chat_id"), nullable=False)
    sender = Column(Enum(MessageSender), nullable=False)
    content = Column(Text, nullable=False)
    token_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=func.now())

    chat = relationship("Chat", back_populates="messages")
    moderation_reports = relationship("ModerationReport", back_populates="message")


class UploadedFile(Base):
    __tablename__ = "uploaded_files"

    file_id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    chat_id = Column(Integer, ForeignKey("chats.chat_id"), nullable=True)
    file_name = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    file_type = Column(String(50))
    upload_time = Column(DateTime, default=func.now())
    status = Column(String(50), default="validated")

    user = relationship("User", back_populates="uploaded_files")
    chat = relationship("Chat", back_populates="uploaded_files")


class ModerationReport(Base):
    __tablename__ = "moderation_reports"

    report_id = Column(Integer, primary_key=True)
    message_id = Column(Integer, ForeignKey("messages.message_id"), nullable=False)
    reported_by = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    reason = Column(Text, nullable=False)
    status = Column(Enum(ReportStatus), default=ReportStatus.PENDING)
    created_at = Column(DateTime, default=func.now())

    message = relationship("Message", back_populates="moderation_reports")
    reported_by_user = relationship("User", back_populates="moderation_reports")
    moderation_actions = relationship("ModerationAction", back_populates="report")


class ModerationAction(Base):
    __tablename__ = "moderation_actions"

    action_id = Column(Integer, primary_key=True)
    report_id = Column(Integer, ForeignKey("moderation_reports.report_id"), nullable=True)  # nullable — ON DELETE SET NULL
    admin_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    action_type = Column(Enum(ModerationActionType), nullable=False)
    action_note = Column(Text)
    action_time = Column(DateTime, default=func.now())

    report = relationship("ModerationReport", back_populates="moderation_actions")
    admin = relationship("User", back_populates="moderation_actions")
