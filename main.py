#!/usr/bin/env python3
"""
Unified Monitor - объединенный монитор комментариев из VK и Telegram
"""
import asyncio
import logging
import os
import signal
import sys
from config.settings import Settings
from database.db_manager import DatabaseManager
from monitors.telegram_monitor import TelegramMonitor
from monitors.vk_monitor import VKMonitor
from sentiment.yandex_analyzer import YandexSentimentAnalyzer, SentimentWorker

# Configure logging
def setup_logging(log_dir: str = "logs"):
    """Setup logging with file and console handlers"""
    import os
    from logging.handlers import RotatingFileHandler
    
    # Create logs directory if it doesn't exist
    os.makedirs(log_dir, exist_ok=True)
    
    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # Clear existing handlers
    root_logger.handlers.clear()
    
    # Format
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # File handler - all logs
    file_handler = RotatingFileHandler(
        os.path.join(log_dir, 'unified-monitor.log'),
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)
    
    # Error file handler - only errors
    error_handler = RotatingFileHandler(
        os.path.join(log_dir, 'unified-monitor-errors.log'),
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding='utf-8'
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)
    root_logger.addHandler(error_handler)

# Setup logging
log_dir = os.getenv('LOG_DIR', 'logs')
setup_logging(log_dir)
logger = logging.getLogger(__name__)

# Global instances for graceful shutdown
db_manager: DatabaseManager = None
telegram_monitor: TelegramMonitor = None
vk_monitor: VKMonitor = None
sentiment_worker: SentimentWorker = None
shutdown_event = asyncio.Event()


def signal_handler(signum, frame):
    """Handle shutdown signals"""
    logger.info(f"Received signal {signum}, initiating graceful shutdown...")
    shutdown_event.set()


async def main():
    """Main application entry point"""
    global db_manager, telegram_monitor, vk_monitor, sentiment_worker
    
    logger.info("=" * 60)
    logger.info("Unified Monitor - VK & Telegram Comment Monitor")
    logger.info("=" * 60)
    
    # Load settings
    settings = Settings.load()
    is_valid, errors = settings.validate()
    
    if not is_valid:
        logger.error("Configuration validation failed:")
        for error in errors:
            logger.error(f"  - {error}")
        logger.error("\nPlease check your .env file")
        sys.exit(1)
    
    # Initialize database
    logger.info("Initializing database...")
    db_manager = DatabaseManager(settings.DB_PATH)
    try:
        db_manager.init_db()
        stats = db_manager.get_statistics()
        logger.info(f"Database initialized. Statistics:")
        logger.info(f"  Total comments: {stats['total']}")
        logger.info(f"  Telegram: {stats['telegram']}")
        logger.info(f"  VK: {stats['vk']}")
        logger.info(f"  Processed: {stats['processed']}")
        logger.info(f"  Unprocessed: {stats['unprocessed']}")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        sys.exit(1)
    
    # Start monitors
    tasks = []
    
    # Telegram monitor
    if settings.TG_CHANNELS and settings.TG_API_ID:
        logger.info("Starting Telegram monitor...")
        try:
            telegram_monitor = TelegramMonitor(
                db_manager,
                settings.get_telegram_config()
            )
            await telegram_monitor.start()
            
            # Run Telegram monitor in background
            tg_task = asyncio.create_task(telegram_monitor.run())
            tasks.append(tg_task)
            logger.info("Telegram monitor started")
        except Exception as e:
            logger.error(f"Failed to start Telegram monitor: {e}")
    else:
        logger.info("Telegram monitor skipped (not configured)")
    
    # VK monitor
    if settings.VK_GROUP_ID and settings.VK_ACCESS_TOKEN:
        logger.info("Starting VK monitor...")
        try:
            vk_monitor = VKMonitor(
                db_manager,
                settings.get_vk_config()
            )
            vk_monitor.start()  # Starts in background thread
            logger.info("VK monitor started")
        except Exception as e:
            logger.error(f"Failed to start VK monitor: {e}")
    else:
        logger.info("VK monitor skipped (not configured)")
    
    # Sentiment analysis worker
    if settings.YANDEX_API_KEY:
        logger.info("Starting sentiment analysis worker...")
        try:
            analyzer = YandexSentimentAnalyzer(settings.YANDEX_API_KEY)
            sentiment_worker = SentimentWorker(
                db_manager,
                analyzer,
                interval=settings.SENTIMENT_INTERVAL
            )
            await sentiment_worker.start()
            logger.info("Sentiment worker started")
        except Exception as e:
            logger.error(f"Failed to start sentiment worker: {e}")
    else:
        logger.warning("Sentiment analysis worker skipped (YANDEX_API_KEY not set)")
    
    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    logger.info("=" * 60)
    logger.info("All monitors started. Monitoring for new comments...")
    logger.info("Press Ctrl+C to stop")
    logger.info("=" * 60)
    
    try:
        # Wait for shutdown signal
        await shutdown_event.wait()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    finally:
        # Graceful shutdown
        logger.info("Shutting down...")
        
        # Stop sentiment worker
        if sentiment_worker:
            await sentiment_worker.stop()
            await analyzer.close()
        
        # Stop Telegram monitor
        if telegram_monitor:
            await telegram_monitor.stop()
        
        # Stop VK monitor
        if vk_monitor:
            await vk_monitor.stop()
        
        # Cancel any remaining tasks
        for task in tasks:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        # Final statistics
        if db_manager:
            stats = db_manager.get_statistics()
            logger.info("Final statistics:")
            logger.info(f"  Total comments: {stats['total']}")
            logger.info(f"  Telegram: {stats['telegram']}")
            logger.info(f"  VK: {stats['vk']}")
            logger.info(f"  Processed: {stats['processed']}")
            logger.info(f"  Unprocessed: {stats['unprocessed']}")
        
        logger.info("Shutdown complete")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)

