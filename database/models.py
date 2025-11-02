"""
SQLAlchemy models for comments database
Based on schema from db.md
"""
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Index, UniqueConstraint
)
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class Comment(Base):
    """Comment model - stores comments from VK and Telegram"""
    
    __tablename__ = 'comments'
    
    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Source identification
    source = Column(String, nullable=False)  # 'telegram' or 'vk'
    source_comment_id = Column(String, nullable=False)  # Unique ID for deduplication
    
    # Channel/Group information
    group_channel_name = Column(String, nullable=False)
    
    # Author information
    author_name = Column(String, nullable=False)
    author_id = Column(String, nullable=False)
    author_username = Column(String, nullable=True)
    
    # Comment content
    comment_text = Column(String, nullable=False)
    has_media = Column(Integer, nullable=False, default=0)  # 0 or 1
    media_type = Column(String, nullable=True)  # 'photo'/'video'/'sticker'/'voice'/'large_video'
    
    # Post information
    post_url = Column(String, nullable=False)
    post_published_at = Column(DateTime, nullable=False)
    
    # Comment information
    comment_url = Column(String, nullable=False)
    comment_published_at = Column(DateTime, nullable=False)
    
    # Sentiment analysis (initially nullable)
    sentiment = Column(String, nullable=True)  # 'positive'/'negative'/'neutral'
    sentiment_score = Column(Float, nullable=True)
    
    # Metadata
    parsed_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    processed = Column(Integer, nullable=False, default=0)  # 0 or 1
    
    # Unique constraint for deduplication
    __table_args__ = (
        UniqueConstraint('source_comment_id', 'source', name='uq_source_comment'),
        # Indexes for fast queries
        Index('idx_source_comment', 'source_comment_id', 'source'),
        Index('idx_comment_published_at', 'comment_published_at'),
        Index('idx_processed', 'processed'),
    )
    
    def __repr__(self):
        return f"<Comment(id={self.id}, source={self.source}, comment_id={self.source_comment_id})>"

