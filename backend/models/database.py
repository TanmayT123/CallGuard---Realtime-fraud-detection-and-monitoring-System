"""SQLAlchemy database models for fraud detection system."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, JSON, Float, Boolean, Text
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class Call(Base):
    """Represents a phone call session."""
    __tablename__ = "calls"

    id = Column(Integer, primary_key=True, index=True)
    call_id = Column(String, unique=True, index=True, nullable=False)
    phone_number = Column(String, nullable=True)
    caller_id = Column(String, nullable=True)
    start_time = Column(DateTime, default=datetime.utcnow, index=True)
    end_time = Column(DateTime, nullable=True)
    duration_seconds = Column(Integer, nullable=True)
    status = Column(String, default="active", index=True)  # active, completed, failed
    final_risk_score = Column(Integer, nullable=True)
    final_risk_level = Column(String, nullable=True)  # low, medium, high
    is_scam = Column(Boolean, default=False, index=True)
    call_metadata = Column(JSON, nullable=True)


class Transcript(Base):
    """Stores call transcripts."""
    __tablename__ = "transcripts"

    id = Column(Integer, primary_key=True, index=True)
    call_id = Column(String, index=True, nullable=False)
    text = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    confidence = Column(Float, nullable=True)
    language = Column(String, default="en")
    sequence = Column(Integer, nullable=True)  # Order of appearance


class Alert(Base):
    """Fraud detection alerts."""
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, index=True)
    alert_id = Column(String, unique=True, index=True, nullable=False)
    call_id = Column(String, index=True, nullable=False)
    risk_score = Column(Integer, nullable=False)
    risk_level = Column(String, nullable=False)  # low, medium, high
    detection_tier = Column(String, nullable=False)  # tier1, tier2
    message = Column(Text, nullable=True)
    red_flags = Column(JSON, nullable=True)  # List of detected red flags
    recommended_action = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    alert_metadata = Column(JSON, nullable=True)


class ScamPattern(Base):
    """Known scam patterns for detection."""
    __tablename__ = "scam_patterns"

    id = Column(Integer, primary_key=True, index=True)
    pattern_id = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    keywords = Column(JSON, nullable=True)  # List of keywords
    scam_type = Column(String, nullable=True)
    severity = Column(Integer, nullable=True)  # 0-100
    times_detected = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class DetectionLog(Base):
    """Logs of all detection attempts."""
    __tablename__ = "detection_logs"

    id = Column(Integer, primary_key=True, index=True)
    call_id = Column(String, index=True, nullable=False)
    transcript = Column(Text, nullable=False)
    tier1_score = Column(Integer, nullable=True)
    tier1_details = Column(JSON, nullable=True)
    tier2_triggered = Column(Boolean, default=False)
    tier2_score = Column(Integer, nullable=True)
    tier2_details = Column(JSON, nullable=True)
    final_decision = Column(JSON, nullable=True)
    processing_time_ms = Column(Integer, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)


class User(Base):
    """System users (optional for future auth)."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    password_hash = Column(String)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
