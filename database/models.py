from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime
import pytz

Base = declarative_base()

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(Integer, unique=True, index=True, nullable=False)
    username = Column(String, nullable=True)
    full_name = Column(String, nullable=True)
    role = Column(String, default="user")  # 'admin' or 'user'
    created_at = Column(DateTime, default=datetime.utcnow)

    tasks = relationship("Task", back_populates="user")

    def __repr__(self):
        return f"<User(id={self.id}, telegram_id={self.telegram_id}, role={self.role})>"

class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    
    command = Column(String, nullable=False)  # e.g., "download_video"
    status = Column(String, default="pending") # pending, running, completed, failed
    result = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="tasks")

    def __repr__(self):
        return f"<Task(id={self.id}, cmd={self.command}, status={self.status})>"
