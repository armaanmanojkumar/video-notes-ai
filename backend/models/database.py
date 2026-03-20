import uuid
from datetime import datetime

from sqlalchemy import Column, String, Text, Float, DateTime, JSON, create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

from backend.config import settings

connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_engine(settings.DATABASE_URL, connect_args=connect_args)


@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_conn, _):
    if settings.DATABASE_URL.startswith("sqlite"):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class VideoSession(Base):
    __tablename__ = "video_sessions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String(512), nullable=True)
    source_url = Column(Text, nullable=True)
    source_type = Column(String(32))
    duration = Column(Float, nullable=True)
    language = Column(String(10), default="en")
    thumbnail = Column(Text, nullable=True)
    channel = Column(String(256), nullable=True)
    status = Column(String(32), default="pending")
    error = Column(Text, nullable=True)
    progress = Column(Float, default=0.0)
    stage = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    transcript = Column(Text, nullable=True)
    transcript_segments = Column(JSON, nullable=True)
    summary = Column(Text, nullable=True)
    executive_summary = Column(Text, nullable=True)
    chapters = Column(JSON, nullable=True)
    key_timestamps = Column(JSON, nullable=True)
    action_items = Column(JSON, nullable=True)
    key_points = Column(JSON, nullable=True)
    topics = Column(JSON, nullable=True)
    sentiment = Column(String(32), nullable=True)
    difficulty_level = Column(String(32), nullable=True)
    word_count = Column(JSON, nullable=True)
    questions_answered = Column(JSON, nullable=True)

    def to_dict(self):
        return {
            "session_id": self.id,
            "title": self.title,
            "source_url": self.source_url,
            "source_type": self.source_type,
            "duration": self.duration,
            "language": self.language,
            "thumbnail": self.thumbnail,
            "channel": self.channel,
            "status": self.status,
            "progress": self.progress,
            "stage": self.stage,
            "error": self.error,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "transcript": self.transcript,
            "transcript_segments": self.transcript_segments,
            "summary": self.summary,
            "executive_summary": self.executive_summary,
            "chapters": self.chapters,
            "key_timestamps": self.key_timestamps,
            "action_items": self.action_items,
            "key_points": self.key_points,
            "topics": self.topics,
            "sentiment": self.sentiment,
            "difficulty_level": self.difficulty_level,
            "word_count": self.word_count,
            "questions_answered": self.questions_answered,
        }


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String(36), nullable=False, index=True)
    role = Column(String(16))
    content = Column(Text)
    sources = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


def init_db():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
