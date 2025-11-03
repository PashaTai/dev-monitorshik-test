"""
Yandex Sentiment Analysis API integration using Yandex Cloud ML SDK
"""
import logging
import asyncio
import re
from typing import Optional, Tuple
from yandex_cloud_ml_sdk import YCloudML

logger = logging.getLogger(__name__)


def parse_sentiment_result(response_text: str) -> dict:
    """
    Парсит ответ модели и извлекает тональность и индекс уверенности
    
    Args:
        response_text: Текст ответа модели (например, "Негативный 0.9")
        
    Returns:
        dict: Словарь с полями sentiment (rus), confidence, status
    """
    # Определяем статус
    status = "Нет"
    sentiment = None
    confidence = None
    
    # Ищем слова тональности
    sentiment_pattern = r"(Негативный|Нейтральный|Позитивный)"
    match = re.search(sentiment_pattern, response_text, re.IGNORECASE)
    
    if match:
        sentiment = match.group(1)
        status = "Успешно"
        
        # Ищем числовое значение уверенности (0.0 - 1.0)
        confidence_pattern = r"([0-9]\.[0-9]+|[0-9]+)"
        confidence_match = re.search(confidence_pattern, response_text)
        
        if confidence_match:
            try:
                confidence = float(confidence_match.group(1))
                # Нормализуем значение между 0 и 1
                if confidence > 1:
                    confidence = confidence / 10
                confidence = min(1.0, max(0.0, confidence))
            except ValueError:
                confidence = None
    
    return {
        "sentiment": sentiment,
        "confidence": confidence,
        "status": status
    }


def convert_sentiment_to_db_format(sentiment_rus: Optional[str]) -> Optional[str]:
    """
    Конвертирует русскую тональность в формат для БД
    
    Args:
        sentiment_rus: Тональность на русском ("Негативный", "Нейтральный", "Позитивный")
        
    Returns:
        Тональность в формате БД ('negative', 'neutral', 'positive') или None
    """
    mapping = {
        "Негативный": "negative",
        "Нейтральный": "neutral",
        "Позитивный": "positive"
    }
    return mapping.get(sentiment_rus) if sentiment_rus else None


def validate_comment_text(text: str) -> tuple[bool, Optional[str]]:
    """
    Валидирует текст комментария для анализа тональности
    
    Args:
        text: Текст для проверки
        
    Returns:
        Tuple (is_valid, reason)
        - is_valid: True если текст можно анализировать, False если нет
        - reason: Причина отклонения (если is_valid=False)
    """
    if not text:
        return False, "Пустой текст"
    
    text_stripped = text.strip()
    
    # Проверка на пустой текст после удаления пробелов
    if not text_stripped:
        return False, "Только пробелы"
    
    # Проверка на минимальную длину (меньше 3 символов - вероятно мусор)
    if len(text_stripped) < 3:
        return False, "Слишком короткий текст (< 3 символов)"
    
    # Проверка на то, что текст состоит только из URL/ссылок
    url_pattern = r'https?://\S+|www\.\S+|t\.me/\S+|vk\.com/\S+'
    text_without_urls = re.sub(url_pattern, '', text_stripped, flags=re.IGNORECASE).strip()
    if len(text_without_urls) < 3:
        return False, "Только ссылки, нет текста для анализа"
    
    # Проверка на то, что текст состоит только из специальных символов (не эмодзи)
    # Эмодзи - это валидный контент для анализа тональности
    # Проверяем только на специальные символы типа !, ?, #, $ и т.д.
    # Если после удаления всех букв, цифр, пробелов и эмодзи остается больше 50% - это мусор
    # Эмодзи в Unicode обычно в диапазоне 0x1F300-0x1F9FF и других
    text_without_emoji = re.sub(
        r'[\U0001F300-\U0001F9FF\U0001FA00-\U0001FAFF\U00002600-\U000027BF\U0001F900-\U0001F9FF\U0001F1E0-\U0001F1FF]',
        '', 
        text_stripped, 
        flags=re.UNICODE
    )
    text_letters_digits = re.sub(r'[^\w\s]', '', text_without_emoji, flags=re.UNICODE)
    if len(text_letters_digits) < len(text_without_emoji) * 0.5 and len(text_without_emoji) > 3:
        return False, "Только специальные символы, недостаточно текста"
    
    # Проверка на слишком длинный текст (более 8000 символов - ограничение API)
    if len(text_stripped) > 8000:
        return False, "Слишком длинный текст (> 8000 символов)"
    
    return True, None


class YandexSentimentAnalyzer:
    """Yandex sentiment analysis API client using Yandex Cloud ML SDK"""
    
    def __init__(self, api_key: str, folder_id: str):
        """
        Initialize Yandex sentiment analyzer
        
        Args:
            api_key: Yandex API key
            folder_id: Yandex Cloud folder ID (format: b1g8dn6s4m5k********)
        """
        self.api_key = api_key
        self.folder_id = folder_id
        
        # Инициализация SDK
        self.sdk = YCloudML(
            folder_id=folder_id,
            auth=api_key
        )
        
        # Выбор модели и настройка
        self.model = self.sdk.models.completions("yandexgpt", model_version="rc")
        self.model = self.model.configure(temperature=0.3)
        
        logger.info("Yandex Sentiment Analyzer initialized with SDK")
    
    def _get_system_prompt_template(self) -> str:
        """
        Возвращает шаблон системного промпта с плейсхолдером для текста комментария
        
        Returns:
            Шаблон промпта с плейсхолдером {comment_text}
        """
        return """Ты ИИ агент, мониторщик разметки тональности комментариев в социальных сетях, я буду давать тебе на вход текстовый комментарий, а ты выводить тональность этого комментария оценивая лексику, посыл и смысл этого комментария. 

есть три тональности комментария
Негативный
Нейтральный
Позитивный 

Вторая составляющая твоего ответа - это оценка насколько ты уверен что это именно такая тональность по шкале где ближе к 1 уверен, ближе к 0 не уверен

Твой ответ должен быть формата, пример 
Негативный 0.9

Текст комментария для анализа:
{comment_text}"""
    
    async def analyze_text(self, text: str) -> Optional[Tuple[str, float]]:
        """
        Analyze sentiment of text using Yandex GPT
        
        Args:
            text: Text to analyze
            
        Returns:
            Tuple of (sentiment, score) or None if error
            sentiment: 'positive', 'negative', or 'neutral'
            score: Confidence score from 0.0 to 1.0
        """
        # Валидация входных данных
        is_valid, reason = validate_comment_text(text)
        if not is_valid:
            logger.warning(f"Invalid comment text for sentiment analysis: {reason}")
            return None
        
        # Получаем шаблон промпта и подставляем текст комментария в плейсхолдер
        prompt_template = self._get_system_prompt_template()
        
        # Убеждаемся, что текст комментария подставлен в плейсхолдер
        try:
            system_prompt = prompt_template.format(comment_text=text.strip())
        except KeyError as e:
            logger.error(f"Error formatting prompt template: missing placeholder {e}")
            return None
        except Exception as e:
            logger.error(f"Error formatting prompt template: {e}")
            return None
        
        # Проверяем, что подстановка произошла
        if "{comment_text}" in system_prompt:
            logger.error("Placeholder {comment_text} was not replaced in prompt!")
            return None
        
        messages = [
            {
                "role": "system",
                "text": system_prompt
            }
        ]
        
        try:
            # SDK работает синхронно, оборачиваем в executor для async
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, self._call_model, messages)
            
            if result:
                # Парсим результат
                parsed = parse_sentiment_result(result)
                
                if parsed["status"] == "Успешно" and parsed["sentiment"] and parsed["confidence"] is not None:
                    # Конвертируем в формат БД
                    sentiment_db = convert_sentiment_to_db_format(parsed["sentiment"])
                    confidence = parsed["confidence"]
                    
                    if sentiment_db:
                        logger.debug(f"Sentiment analysis result: {sentiment_db} ({confidence:.2f})")
                        return (sentiment_db, confidence)
                    else:
                        logger.warning(f"Could not convert sentiment: {parsed['sentiment']}")
                        return None
                else:
                    logger.warning(f"Failed to parse sentiment result: {result}")
                    return None
            else:
                logger.warning("Empty result from Yandex GPT")
                return None
                
        except Exception as e:
            logger.error(f"Error in sentiment analysis: {e}", exc_info=True)
            return None
    
    def _call_model(self, messages: list) -> Optional[str]:
        """
        Синхронный вызов модели (выполняется в executor)
        
        Args:
            messages: Список сообщений для модели
            
        Returns:
            Текст ответа модели или None при ошибке
        """
        try:
            result = self.model.run(messages)
            for alternative in result:
                return alternative.text
            return None
        except Exception as e:
            logger.error(f"Error calling Yandex GPT model: {e}", exc_info=True)
            return None
    
    async def close(self):
        """Close analyzer (no-op for SDK, kept for compatibility)"""
        pass


class SentimentWorker:
    """Background worker for processing comments sentiment and sending notifications"""
    
    def __init__(self, db_manager, analyzer: YandexSentimentAnalyzer, interval: int = 60, 
                 bot_token: Optional[str] = None, alert_chat_id: Optional[str] = None):
        """
        Initialize sentiment worker
        
        Args:
            db_manager: DatabaseManager instance
            analyzer: YandexSentimentAnalyzer instance
            interval: Processing interval in seconds
            bot_token: Telegram Bot token for sending notifications (optional)
            alert_chat_id: Telegram chat ID for notifications (optional)
        """
        self.db_manager = db_manager
        self.analyzer = analyzer
        self.interval = interval
        self.bot_token = bot_token
        self.alert_chat_id = alert_chat_id
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._http_session: Optional = None
    
    async def start(self):
        """Start sentiment processing worker"""
        if self._running:
            logger.warning("Sentiment worker is already running")
            return
        
        # Create HTTP session for sending notifications
        if self.bot_token and self.alert_chat_id:
            import aiohttp
            self._http_session = aiohttp.ClientSession()
            logger.info("HTTP session created for sending notifications")
        
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
        
        # Close HTTP session
        if self._http_session:
            await self._http_session.close()
            logger.info("HTTP session closed")
        
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
                try:
                    result = await self.analyzer.analyze_text(comment.comment_text)
                    
                    if result:
                        sentiment, score = result
                        
                        # Update in database with successful result
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
                            
                            # Обновляем объект comment для отправки уведомления
                            comment.sentiment = sentiment
                            comment.sentiment_score = score
                            
                            # Отправляем уведомление с тональностью
                            if self.bot_token and self.alert_chat_id:
                                await self._send_notification(comment)
                        else:
                            logger.warning(f"Failed to update sentiment for comment {comment.id}")
                    else:
                        # Анализ не удался (невалидный текст, ошибка API и т.д.)
                        # Помечаем как обработанный, но без тональности (sentiment=None)
                        success = self.db_manager.update_sentiment(
                            comment.id,
                            None,  # sentiment = None означает что анализ не выполнен
                            None,  # score = None
                            processed=1
                        )
                        
                        if success:
                            logger.info(
                                f"Marked comment {comment.id} as processed "
                                f"(sentiment analysis skipped/failed)"
                            )
                            
                            # Обновляем объект comment для отправки уведомления
                            comment.sentiment = None
                            comment.sentiment_score = None
                            
                            # Отправляем уведомление без тональности
                            if self.bot_token and self.alert_chat_id:
                                await self._send_notification(comment)
                        else:
                            logger.warning(f"Failed to mark comment {comment.id} as processed")
                
                except Exception as e:
                    # Критическая ошибка при анализе - помечаем как обработанный без результата
                    logger.error(f"Error analyzing comment {comment.id}: {e}", exc_info=True)
                    try:
                        success = self.db_manager.update_sentiment(
                            comment.id,
                            None,
                            None,
                            processed=1
                        )
                        
                        if success:
                            # Обновляем объект comment и отправляем уведомление
                            comment.sentiment = None
                            comment.sentiment_score = None
                            
                            if self.bot_token and self.alert_chat_id:
                                await self._send_notification(comment)
                    except Exception as db_error:
                        logger.error(f"Failed to mark comment {comment.id} as processed: {db_error}")
                
                # Small delay between requests to respect rate limits
                await asyncio.sleep(0.5)
        
        except Exception as e:
            logger.error(f"Error processing sentiment batch: {e}")
    
    def _get_sentiment_emoji(self, sentiment: Optional[str]) -> tuple[str, str]:
        """
        Возвращает эмодзи и текст для тональности
        
        Args:
            sentiment: 'positive', 'negative', 'neutral' или None
            
        Returns:
            Tuple (emoji, text_ru)
        """
        if sentiment == 'negative':
            return ('🔴', 'Негативный')
        elif sentiment == 'positive':
            return ('🟢', 'Позитивный')
        elif sentiment == 'neutral':
            return ('⚪️', 'Нейтральный')
        else:
            return ('⚫️', 'Не определена')
    
    def _format_notification(self, comment) -> str:
        """
        Форматирует уведомление с тональностью
        
        Args:
            comment: Comment object из БД
            
        Returns:
            Отформатированное сообщение для Telegram
        """
        # Определяем эмодзи источника
        source_emoji = "✈️" if comment.source == 'telegram' else "🔵"
        source_name = "TG" if comment.source == 'telegram' else "VK"
        
        # Форматируем время
        time_str = comment.comment_published_at.strftime('%H:%M %d.%m.%Y')
        
        # Получаем эмодзи и текст тональности
        sentiment_emoji, sentiment_text = self._get_sentiment_emoji(comment.sentiment)
        
        # Форматируем имя пользователя
        username_part = f" {comment.author_username}" if comment.author_username else ""
        
        # Базовая часть
        base = f"""{source_emoji} <b>{source_name}</b> | {comment.group_channel_name}
👤 {comment.author_name}{username_part}
🆔 <code>{comment.author_id}</code>
🕐 {time_str}
{sentiment_emoji} Тональность: {sentiment_text}
━━━━━━━━━━━━━━━━━━"""
        
        # Добавляем текст комментария если есть
        if comment.comment_text:
            message = f"""{base}
<blockquote>{comment.comment_text}</blockquote>

<a href="{comment.post_url}">🔗 Открыть пост</a>
<a href="{comment.comment_url}">💬 Открыть комментарий</a>"""
        else:
            message = f"""{base}
<b>Пользователь прислал медиафайл, пожалуйста откройте комментарий чтобы увидеть содержание</b>

<a href="{comment.post_url}">🔗 Открыть пост</a>
<a href="{comment.comment_url}">💬 Открыть комментарий</a>"""
        
        return message
    
    async def _send_notification(self, comment):
        """
        Отправляет уведомление в Telegram
        
        Args:
            comment: Comment object из БД
        """
        if not self._http_session or not self.bot_token or not self.alert_chat_id:
            return
        
        message = self._format_notification(comment)
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        
        payload = {
            "chat_id": self.alert_chat_id,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": False
        }
        
        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                async with self._http_session.post(url, json=payload) as response:
                    if response.status == 200:
                        logger.info(f"Notification sent for comment {comment.id}")
                        return True
                    elif response.status == 429:
                        # Rate limit
                        error_data = await response.json()
                        retry_after = error_data.get('parameters', {}).get('retry_after', 5)
                        logger.warning(f"Rate limit hit, waiting {retry_after} seconds")
                        await asyncio.sleep(retry_after)
                        continue
                    else:
                        error_text = await response.text()
                        logger.warning(
                            f"Attempt {attempt}/{max_retries}: "
                            f"Error sending notification (status {response.status}): {error_text}"
                        )
            except Exception as e:
                logger.warning(f"Attempt {attempt}/{max_retries}: Error sending notification: {e}")
            
            if attempt < max_retries:
                await asyncio.sleep(2 ** (attempt - 1))  # Exponential backoff
        
        logger.error(f"Failed to send notification for comment {comment.id} after {max_retries} attempts")
        return False

