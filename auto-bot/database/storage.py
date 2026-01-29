from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from config.loader import config
from database.models import Base

# Create engine
# check_same_thread=False is needed for SQLite when using multiple threads (TaskQueue)
connect_args = {"check_same_thread": False} if "sqlite" in config.DB_URL else {}
engine = create_engine(config.DB_URL, connect_args=connect_args, echo=False)

# Create Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class DatabaseStorage:
    def __init__(self):
        self.engine = engine

    def init_db(self):
        """Create all tables in the database"""
        Base.metadata.create_all(bind=self.engine)
        print("Database tables created successfully.")

    def get_session(self):
        """Get a new DB session"""
        return SessionLocal()

# Singleton instance
storage = DatabaseStorage()
