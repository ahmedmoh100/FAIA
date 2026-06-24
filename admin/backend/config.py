"""
Database configuration for FAIA Admin Dashboard
Connects to MySQL database with faia_chat_system schema
"""

import os
import logging
from urllib.parse import quote_plus
from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import QueuePool

logger = logging.getLogger(__name__)

# Database configuration - all values from environment variables
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "3306")
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "faia_chat_system")

# URL-encode the password to handle special characters (@ : / ? # & = + %)
# Without this, passwords containing these characters silently break the connection URL
DATABASE_URL = (
    f"mysql+pymysql://{DB_USER}:{quote_plus(DB_PASSWORD)}"
    f"@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4"
)

# Create SQLAlchemy engine with optimized connection pooling
engine = create_engine(
    DATABASE_URL,
    poolclass=QueuePool,
    pool_size=10,          # Keep 10 connections open
    max_overflow=20,       # Allow 20 extra connections if needed (total 30)
    pool_pre_ping=True,    # Test connections before use (detects stale connections)
    pool_recycle=3600,     # Recycle connections after 1 hour (prevents MySQL timeout)
    pool_timeout=30,       # Wait up to 30 seconds for available connection
    echo=False,            # Set to True for SQL query logging during development
    connect_args={
        "connect_timeout": 10
    }
)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for SQLAlchemy models
Base = declarative_base()


def get_db():
    """Yield a database session and ensure it is closed after use."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def test_connection():
    """Test database connectivity. Returns True if successful."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            logger.info("Database connection successful: %s at %s:%s", DB_NAME, DB_HOST, DB_PORT)
            return True
    except Exception as e:
        logger.error("Database connection failed: %s", e)
        return False


def get_db_info():
    """Return database metadata for health check endpoints."""
    try:
        with engine.connect() as connection:
            version_result = connection.execute(text("SELECT VERSION()"))
            version = version_result.fetchone()[0]

            # Parameterized query — avoids f-string SQL even though DB_NAME is from env
            tables_result = connection.execute(
                text("""
                    SELECT COUNT(*) as table_count
                    FROM information_schema.tables
                    WHERE table_schema = :db_name
                """),
                {"db_name": DB_NAME}
            )
            table_count = tables_result.fetchone()[0]

            return {
                "connected": True,
                "version": version,
                "database": DB_NAME,
                "table_count": table_count,
                "host": DB_HOST,
                "port": DB_PORT,
                "type": "MySQL"
            }
    except Exception as e:
        logger.error("get_db_info failed: %s", e)
        return {
            "connected": False,
            "error": str(e),
            "database": DB_NAME,
            "host": DB_HOST,
            "port": DB_PORT,
            "type": "MySQL"
        }
