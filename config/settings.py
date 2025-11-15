"""
Configuration settings from environment variables
"""
import os
import logging
from typing import Optional
from dotenv import load_dotenv

# Load .env file
load_dotenv()

logger = logging.getLogger(__name__)


class Settings:
    """Application settings"""
    
    # Database
    DB_PATH: str = os.getenv('DB_PATH', 'comments.db')
    
    # Telegram monitor settings
    TG_API_ID: Optional[int] = None
    TG_API_HASH: Optional[str] = None
    TG_STRING_SESSION: Optional[str] = None
    TG_CHANNELS: Optional[str] = None
    TG_TZ: str = os.getenv('TZ', 'UTC')
    
    # VK monitor settings
    VK_ACCESS_TOKEN: Optional[str] = None
    VK_GROUP_ID: Optional[str] = None
    VK_POSTS_TO_CHECK: int = int(os.getenv('POSTS_TO_CHECK', '10'))
    VK_COMMENTS_PER_POST: int = int(os.getenv('COMMENTS_PER_POST', '20'))
    VK_CHECK_INTERVAL: int = int(os.getenv('CHECK_INTERVAL', '60'))
    VK_REQUEST_DELAY: float = float(os.getenv('REQUEST_DELAY', '0.4'))
    
    # Sentiment analysis
    YANDEX_API_KEY: Optional[str] = os.getenv('YANDEX_API_KEY')
    YANDEX_FOLDER_ID: Optional[str] = os.getenv('YANDEX_FOLDER_ID')
    SENTIMENT_INTERVAL: int = int(os.getenv('SENTIMENT_INTERVAL', '60'))
    
    # Optional: Telegram Bot (for notifications)
    BOT_TOKEN: Optional[str] = os.getenv('BOT_TOKEN')
    ALERT_CHAT_ID: Optional[str] = os.getenv('ALERT_CHAT_ID')
    
    # Logging
    LOG_DIR: str = os.getenv('LOG_DIR', 'logs')
    
    # API Server (for manual labeling)
    API_HOST: str = os.getenv('API_HOST', '0.0.0.0')
    API_PORT: int = int(os.getenv('API_PORT', '8000'))
    API_URL: str = os.getenv('API_URL', 'http://localhost:8000')
    API_USERNAME: str = os.getenv('API_USERNAME', 'admin')
    API_PASSWORD: str = os.getenv('API_PASSWORD', 'changeme')
    
    # Dashboard
    DASHBOARD_PASSWORD: str = os.getenv('DASHBOARD_PASSWORD', 'admin123')
    DASHBOARD_PORT: int = int(os.getenv('DASHBOARD_PORT', '8501'))
    
    @classmethod
    def load(cls):
        """Load settings from environment"""
        # Telegram
        tg_api_id = os.getenv('TG_API_ID')
        if tg_api_id:
            try:
                cls.TG_API_ID = int(tg_api_id)
            except ValueError:
                logger.error("TG_API_ID must be a number")
        
        cls.TG_API_HASH = os.getenv('TG_API_HASH')
        cls.TG_STRING_SESSION = os.getenv('TG_STRING_SESSION')
        cls.TG_CHANNELS = os.getenv('CHANNELS')
        
        # VK
        cls.VK_ACCESS_TOKEN = os.getenv('VK_ACCESS_TOKEN')
        cls.VK_GROUP_ID = os.getenv('VK_GROUP_ID')
        
        return cls
    
    @classmethod
    def get_telegram_config(cls) -> dict:
        """Get Telegram monitor configuration"""
        return {
            'TG_API_ID': cls.TG_API_ID,
            'TG_API_HASH': cls.TG_API_HASH,
            'TG_STRING_SESSION': cls.TG_STRING_SESSION,
            'CHANNELS': cls.TG_CHANNELS,
            'TZ': cls.TG_TZ,
            'BOT_TOKEN': cls.BOT_TOKEN,
            'ALERT_CHAT_ID': cls.ALERT_CHAT_ID
        }
    
    @classmethod
    def get_vk_config(cls) -> dict:
        """Get VK monitor configuration"""
        return {
            'VK_ACCESS_TOKEN': cls.VK_ACCESS_TOKEN,
            'VK_GROUP_ID': cls.VK_GROUP_ID,
            'POSTS_TO_CHECK': cls.VK_POSTS_TO_CHECK,
            'COMMENTS_PER_POST': cls.VK_COMMENTS_PER_POST,
            'CHECK_INTERVAL': cls.VK_CHECK_INTERVAL,
            'REQUEST_DELAY': cls.VK_REQUEST_DELAY,
            'TELEGRAM_BOT_TOKEN': cls.BOT_TOKEN,
            'TELEGRAM_CHAT_ID': cls.ALERT_CHAT_ID
        }
    
    @classmethod
    def validate(cls) -> tuple[bool, list[str]]:
        """Validate required settings"""
        errors = []
        
        # Check Telegram if channels are specified
        if cls.TG_CHANNELS:
            if not cls.TG_API_ID:
                errors.append("TG_API_ID is required for Telegram monitoring")
            if not cls.TG_API_HASH:
                errors.append("TG_API_HASH is required for Telegram monitoring")
            if not cls.TG_STRING_SESSION:
                errors.append("TG_STRING_SESSION is required for Telegram monitoring")
        
        # Check VK if group ID is specified
        if cls.VK_GROUP_ID:
            if not cls.VK_ACCESS_TOKEN:
                errors.append("VK_ACCESS_TOKEN is required for VK monitoring")
        
        return len(errors) == 0, errors

