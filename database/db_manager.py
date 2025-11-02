"""
Database manager for SQLite database
Handles initialization, table creation, and common operations
"""
import os
import logging
import time
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import SQLAlchemyError, OperationalError
from sqlalchemy.engine import Engine
from database.models import Base, Comment

logger = logging.getLogger(__name__)

# SQLite error codes
SQLITE_BUSY = 5
SQLITE_LOCKED = 6


class DatabaseManager:
    """Manages SQLite database connection and operations"""
    
    def __init__(self, db_path: str = "comments.db", timeout: float = 30.0):
        """
        Initialize database manager
        
        Args:
            db_path: Path to SQLite database file
            timeout: Timeout for database operations in seconds
        """
        self.db_path = db_path
        self.timeout = timeout
        self.engine = create_engine(
            f"sqlite:///{db_path}",
            echo=False,  # Set to True for SQL debugging
            connect_args={
                "check_same_thread": False,  # Needed for SQLite with async
                "timeout": timeout,  # Set timeout for locks
            },
            pool_pre_ping=True  # Verify connections before using
        )
        self.SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine
        )
        
        # Enable WAL mode for better concurrency
        self._enable_wal_mode()
    
    def _enable_wal_mode(self):
        """Enable WAL (Write-Ahead Logging) mode for better concurrency"""
        try:
            from sqlalchemy import text
            with self.engine.connect() as conn:
                conn.execute(text("PRAGMA journal_mode=WAL"))
                conn.execute(text("PRAGMA synchronous=NORMAL"))
                conn.execute(text("PRAGMA busy_timeout=30000"))  # 30 seconds
                conn.commit()
            logger.debug("WAL mode enabled for SQLite")
        except Exception as e:
            logger.warning(f"Could not enable WAL mode: {e}")
    
    def init_db(self):
        """Initialize database - create all tables and indexes"""
        try:
            Base.metadata.create_all(bind=self.engine)
            logger.info(f"Database initialized at {self.db_path}")
            logger.info("Tables and indexes created successfully")
        except SQLAlchemyError as e:
            logger.error(f"Error initializing database: {e}")
            raise
    
    def _retry_on_lock(self, func, max_retries: int = 5, base_delay: float = 0.1):
        """
        Retry function with exponential backoff on SQLite lock errors
        
        Args:
            func: Function to execute
            max_retries: Maximum number of retry attempts
            base_delay: Base delay in seconds for exponential backoff
            
        Returns:
            Result of function execution
        """
        last_exception = None
        for attempt in range(max_retries):
            try:
                return func()
            except OperationalError as e:
                # Check if it's a lock error
                error_code = getattr(e.orig, 'sqlite_errno', None)
                if error_code in (SQLITE_BUSY, SQLITE_LOCKED):
                    last_exception = e
                    if attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt)  # Exponential backoff
                        logger.warning(
                            f"SQLite lock error (attempt {attempt + 1}/{max_retries}), "
                            f"retrying in {delay:.2f}s: {e}"
                        )
                        time.sleep(delay)
                        continue
                    else:
                        logger.error(
                            f"SQLite lock error after {max_retries} attempts: {e}"
                        )
                        raise
                else:
                    # Not a lock error, re-raise immediately
                    raise
            except Exception as e:
                # Other errors, re-raise immediately
                raise
        
        # Should not reach here, but just in case
        if last_exception:
            raise last_exception
    
    def get_session(self) -> Session:
        """Get a new database session"""
        return self.SessionLocal()
    
    def save_comment(self, comment_data: dict) -> bool:
        """
        Save comment to database with deduplication and retry on locks
        
        Args:
            comment_data: Dictionary with comment fields matching Comment model
            
        Returns:
            True if comment was saved, False if it already exists (deduplication)
        """
        def _save():
            session = self.get_session()
            try:
                # Check if comment already exists
                existing = session.query(Comment).filter(
                    Comment.source_comment_id == comment_data['source_comment_id'],
                    Comment.source == comment_data['source']
                ).first()
                
                if existing:
                    logger.debug(
                        f"Comment already exists: {comment_data['source']}:{comment_data['source_comment_id']}"
                    )
                    return False
                
                # Create new comment
                comment = Comment(**comment_data)
                session.add(comment)
                session.commit()
                logger.info(f"Comment saved: {comment_data['source']}:{comment_data['source_comment_id']}")
                return True
                
            except SQLAlchemyError as e:
                session.rollback()
                raise
            finally:
                session.close()
        
        try:
            return self._retry_on_lock(_save)
        except SQLAlchemyError as e:
            logger.error(f"Error saving comment after retries: {e}")
            return False
    
    def get_unprocessed_comments(self, limit: int = 100) -> list:
        """
        Get unprocessed comments for sentiment analysis
        
        Args:
            limit: Maximum number of comments to return
            
        Returns:
            List of Comment objects
        """
        session = self.get_session()
        try:
            comments = session.query(Comment).filter(
                Comment.processed == 0
            ).limit(limit).all()
            return comments
        finally:
            session.close()
    
    def update_sentiment(
        self,
        comment_id: int,
        sentiment: str,
        sentiment_score: float,
        processed: int = 1
    ) -> bool:
        """
        Update sentiment analysis results for a comment with retry on locks
        
        Args:
            comment_id: Database ID of the comment
            sentiment: 'positive', 'negative', or 'neutral'
            sentiment_score: Score from 0.0 to 1.0
            processed: Set to 1 after processing
            
        Returns:
            True if successful, False otherwise
        """
        def _update():
            session = self.get_session()
            try:
                comment = session.query(Comment).filter(Comment.id == comment_id).first()
                if not comment:
                    logger.warning(f"Comment with id {comment_id} not found")
                    return False
                
                comment.sentiment = sentiment
                comment.sentiment_score = sentiment_score
                comment.processed = processed
                session.commit()
                logger.info(f"Sentiment updated for comment {comment_id}: {sentiment} ({sentiment_score})")
                return True
                
            except SQLAlchemyError as e:
                session.rollback()
                raise
            finally:
                session.close()
        
        try:
            return self._retry_on_lock(_update)
        except SQLAlchemyError as e:
            logger.error(f"Error updating sentiment after retries: {e}")
            return False
    
    def get_statistics(self) -> dict:
        """
        Get database statistics
        
        Returns:
            Dictionary with statistics
        """
        session = self.get_session()
        try:
            total = session.query(Comment).count()
            telegram = session.query(Comment).filter(Comment.source == 'telegram').count()
            vk = session.query(Comment).filter(Comment.source == 'vk').count()
            processed = session.query(Comment).filter(Comment.processed == 1).count()
            unprocessed = session.query(Comment).filter(Comment.processed == 0).count()
            
            return {
                'total': total,
                'telegram': telegram,
                'vk': vk,
                'processed': processed,
                'unprocessed': unprocessed
            }
        finally:
            session.close()

