"""
Base monitor class with common functionality
"""
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, Optional
from database.db_manager import DatabaseManager

logger = logging.getLogger(__name__)


class BaseMonitor(ABC):
    """Base class for all monitors"""
    
    def __init__(self, db_manager: DatabaseManager):
        """
        Initialize base monitor
        
        Args:
            db_manager: DatabaseManager instance for saving comments
        """
        self.db_manager = db_manager
    
    def start(self):
        """Start monitoring - must be implemented by subclasses"""
        pass
    
    async def stop(self):
        """Stop monitoring - must be implemented by subclasses"""
        pass
    
    def save_comment_to_db(self, comment_data: dict) -> bool:
        """
        Save comment to database
        
        Args:
            comment_data: Dictionary with comment fields
            
        Returns:
            True if saved, False if duplicate or error
        """
        # Ensure required fields are present
        required_fields = [
            'source', 'source_comment_id', 'group_channel_name',
            'author_name', 'author_id', 'comment_text',
            'has_media', 'post_url', 'post_published_at',
            'comment_url', 'comment_published_at'
        ]
        
        # Set defaults for optional fields
        comment_data.setdefault('author_username', None)
        comment_data.setdefault('media_type', None)
        comment_data.setdefault('sentiment', None)
        comment_data.setdefault('sentiment_score', None)
        comment_data.setdefault('processed', 0)
        comment_data.setdefault('parsed_at', datetime.utcnow())
        
        # Validate required fields
        missing = [field for field in required_fields if field not in comment_data]
        if missing:
            logger.error(f"Missing required fields: {missing}")
            return False
        
        # Ensure has_media is 0 or 1
        comment_data['has_media'] = 1 if comment_data.get('has_media') else 0
        
        return self.db_manager.save_comment(comment_data)
    
    def format_comment_data(
        self,
        source: str,
        source_comment_id: str,
        group_channel_name: str,
        author_name: str,
        author_id: str,
        comment_text: str,
        has_media: bool = False,
        media_type: Optional[str] = None,
        post_url: str = "",
        post_published_at: datetime = None,
        comment_url: str = "",
        comment_published_at: datetime = None,
        author_username: Optional[str] = None
    ) -> dict:
        """
        Format comment data for database
        
        Returns:
            Dictionary with properly formatted comment data
        """
        if post_published_at is None:
            post_published_at = datetime.utcnow()
        if comment_published_at is None:
            comment_published_at = datetime.utcnow()
        
        return {
            'source': source,
            'source_comment_id': str(source_comment_id),
            'group_channel_name': group_channel_name,
            'author_name': author_name,
            'author_id': str(author_id),
            'author_username': author_username,
            'comment_text': comment_text or '',  # Ensure not None
            'has_media': 1 if has_media else 0,
            'media_type': media_type,
            'post_url': post_url,
            'post_published_at': post_published_at,
            'comment_url': comment_url,
            'comment_published_at': comment_published_at,
            'parsed_at': datetime.utcnow(),
            'processed': 0
        }

