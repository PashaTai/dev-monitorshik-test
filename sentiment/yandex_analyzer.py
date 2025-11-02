"""
Yandex Sentiment Analysis API integration
"""
import logging
import asyncio
import aiohttp
from typing import Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


class YandexSentimentAnalyzer:
    """Yandex sentiment analysis API client"""
    
    def __init__(self, api_key: str, api_url: Optional[str] = None):
        """
        Initialize Yandex sentiment analyzer
        
        Args:
            api_key: Yandex API key
            api_url: Optional custom API URL (defaults to standard Yandex API)
        """
        self.api_key = api_key
        # Using Yandex Cloud AI API for sentiment analysis
        # Documentation: https://cloud.yandex.ru/docs/ai/doc/speechsense/concepts/index
        self.api_url = api_url or "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
        
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session
    
    async def analyze_text(self, text: str) -> Optional[Tuple[str, float]]:
        """
        Analyze sentiment of text
        
        Args:
            text: Text to analyze
            
        Returns:
            Tuple of (sentiment, score) or None if error
            sentiment: 'positive', 'negative', or 'neutral'
            score: Confidence score from 0.0 to 1.0
        """
        if not text or not text.strip():
            logger.warning("Empty text provided for sentiment analysis")
            return ('neutral', 0.5)
        
        # For now, we'll use a simple placeholder implementation
        # You'll need to replace this with actual Yandex API call
        # when you have the API credentials
        
        # Example Yandex API call structure:
        # headers = {
        #     'Authorization': f'Api-Key {self.api_key}',
        #     'Content-Type': 'application/json'
        # }
        # payload = {
        #     'modelUri': '...',
        #     'completionOptions': {...},
        #     'messages': [{'role': 'user', 'text': text}]
        # }
        
        # Placeholder: simple keyword-based analysis
        # TODO: Replace with actual Yandex API integration
        try:
            sentiment, score = self._simple_sentiment_analysis(text)
            logger.debug(f"Sentiment analysis result: {sentiment} ({score:.2f})")
            return (sentiment, score)
        except Exception as e:
            logger.error(f"Error in sentiment analysis: {e}")
            return None
    
    def _simple_sentiment_analysis(self, text: str) -> Tuple[str, float]:
        """
        Simple placeholder sentiment analysis
        TODO: Replace with actual Yandex API call
        
        This is a basic implementation that should be replaced
        with the actual Yandex Cloud AI API integration
        """
        text_lower = text.lower()
        
        # Positive keywords (Russian)
        positive_words = [
            'отлично', 'прекрасно', 'хорошо', 'замечательно', 'супер',
            'класс', 'люблю', 'нравится', 'спасибо', 'благодарю',
            'восхитительно', 'великолепно', 'потрясающе'
        ]
        
        # Negative keywords (Russian)
        negative_words = [
            'плохо', 'ужасно', 'отвратительно', 'ненавижу', 'не нравится',
            'гадость', 'кошмар', 'ужас', 'мерзость', 'плохой',
            'негативный', 'проблема', 'ошибка'
        ]
        
        positive_count = sum(1 for word in positive_words if word in text_lower)
        negative_count = sum(1 for word in negative_words if word in text_lower)
        
        if positive_count > negative_count:
            score = min(0.9, 0.5 + (positive_count * 0.1))
            return ('positive', score)
        elif negative_count > positive_count:
            score = min(0.9, 0.5 + (negative_count * 0.1))
            return ('negative', score)
        else:
            return ('neutral', 0.5)
    
    async def close(self):
        """Close HTTP session"""
        if self.session and not self.session.closed:
            await self.session.close()


class SentimentWorker:
    """Background worker for processing comments sentiment"""
    
    def __init__(self, db_manager, analyzer: YandexSentimentAnalyzer, interval: int = 60):
        """
        Initialize sentiment worker
        
        Args:
            db_manager: DatabaseManager instance
            analyzer: YandexSentimentAnalyzer instance
            interval: Processing interval in seconds
        """
        self.db_manager = db_manager
        self.analyzer = analyzer
        self.interval = interval
        self._running = False
        self._task: Optional[asyncio.Task] = None
    
    async def start(self):
        """Start sentiment processing worker"""
        if self._running:
            logger.warning("Sentiment worker is already running")
            return
        
        self._running = True
        self._task = asyncio.create_task(self._processing_loop())
        logger.info("Sentiment worker started")
    
    async def stop(self):
        """Stop sentiment processing worker"""
        logger.info("Stopping sentiment worker...")
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Sentiment worker stopped")
    
    async def _processing_loop(self):
        """Main processing loop"""
        try:
            while self._running:
                await self._process_batch()
                
                # Sleep with periodic checks
                slept = 0
                while slept < self.interval and self._running:
                    await asyncio.sleep(min(1, self.interval - slept))
                    slept += 1
        
        except asyncio.CancelledError:
            logger.info("Sentiment worker cancelled")
        except Exception as e:
            logger.error(f"Error in sentiment processing loop: {e}")
    
    async def _process_batch(self):
        """Process a batch of unprocessed comments"""
        try:
            comments = self.db_manager.get_unprocessed_comments(limit=10)
            
            if not comments:
                logger.debug("No unprocessed comments for sentiment analysis")
                return
            
            logger.info(f"Processing {len(comments)} comments for sentiment analysis")
            
            for comment in comments:
                if not self._running:
                    break
                
                # Analyze sentiment
                result = await self.analyzer.analyze_text(comment.comment_text)
                
                if result:
                    sentiment, score = result
                    
                    # Update in database
                    success = self.db_manager.update_sentiment(
                        comment.id,
                        sentiment,
                        score,
                        processed=1
                    )
                    
                    if success:
                        logger.info(
                            f"Processed comment {comment.id}: "
                            f"{sentiment} ({score:.2f})"
                        )
                    else:
                        logger.warning(f"Failed to update sentiment for comment {comment.id}")
                
                # Small delay between requests to respect rate limits
                await asyncio.sleep(0.5)
        
        except Exception as e:
            logger.error(f"Error processing sentiment batch: {e}")

