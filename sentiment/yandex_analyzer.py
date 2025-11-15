"""
Yandex Sentiment Analysis API integration using Few-shot Text Classification
"""
import logging
import asyncio
import re
import requests
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


def parse_classifier_response(response_json: dict) -> dict:
    """
    Парсит ответ Few-shot классификатора
    
    Args:
        response_json: JSON ответ от API с predictions
        
    Returns:
        dict: Словарь с полями sentiment (rus), confidence, status
    """
    try:
        predictions = response_json.get("predictions", [])
        
        if not predictions:
            return {
                "sentiment": None,
                "confidence": None,
                "status": "Нет"
            }
        
        # Берем предсказание с максимальной уверенностью
        best_prediction = max(predictions, key=lambda x: x.get("confidence", 0))
        
        label = best_prediction.get("label")
        confidence = best_prediction.get("confidence")
        
        if label and confidence is not None:
            return {
                "sentiment": label,
                "confidence": float(confidence),
                "status": "Успешно"
            }
        
        return {
            "sentiment": None,
            "confidence": None,
            "status": "Нет"
        }
    
    except Exception as e:
        logger.error(f"Error parsing classifier response: {e}")
        return {
            "sentiment": None,
            "confidence": None,
            "status": "Ошибка"
        }


def convert_sentiment_to_db_format(sentiment_rus: Optional[str]) -> Optional[str]:
    """
    Конвертирует русскую тональность в формат для БД
    
    Args:
        sentiment_rus: Тональность на русском ("негативное", "нейтральное", "позитивное")
        
    Returns:
        Тональность в формате БД ('negative', 'neutral', 'positive') или None
    """
    if not sentiment_rus:
        return None
    
    # Приводим к нижнему регистру для сопоставления
    sentiment_lower = sentiment_rus.lower().strip()
    
    mapping = {
        "негативное": "negative",
        "нейтральное": "neutral",
        "позитивное": "positive",
        # Поддержка старого формата на всякий случай
        "негативный": "negative",
        "нейтральный": "neutral",
        "позитивный": "positive"
    }
    return mapping.get(sentiment_lower)


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
    
    # Расширенный паттерн для эмодзи (покрывает все основные Unicode диапазоны)
    emoji_pattern = re.compile(
        r'[\U0001F300-\U0001F9FF'  # Основные эмодзи (включая 👍, 😊 и т.д.)
        r'\U0001FA00-\U0001FAFF'   # Расширенные эмодзи
        r'\U00002600-\U000027BF'   # Разное (солнце, звезды и т.д.)
        r'\U0001F1E0-\U0001F1FF'   # Флаги
        r'\U00002300-\U000023FF'   # Технические символы
        r'\U00002B50-\U00002B55'   # ⭐ Звезды
        r'\U0001F004-\U0001F0CF'   # Игровые символы
        r'\u2764\uFE0F?'           # ❤ Красное сердце
        r'\u2665\uFE0F?'           # ♥ Черное сердце
        r'\u2661\uFE0F?'           # ♡ Белое сердце
        r'\u2763\uFE0F?'           # ❣ Тяжелое сердце
        r'\u2744\uFE0F?'           # ❄ Снежинка
        r'\u2B50'                  # ⭐ Звезда
        r'\u2705'                  # ✅ Галочка
        r'\u274C'                  # ❌ Крестик
        r'\u2714\uFE0F?'           # ✔ Жирная галочка
        r'\u2716\uFE0F?'           # ✖ Жирный крестик
        r'\u2728'                  # ✨ Искры
        r']',
        flags=re.UNICODE
    )
    
    # Проверяем наличие эмодзи в тексте
    has_emoji = bool(emoji_pattern.search(text_stripped))
    
    # НОВОЕ ПРАВИЛО: Если есть хотя бы один эмодзи - всегда разрешаем анализ
    if has_emoji:
        # Few-shot классификатор умеет понимать эмодзи
        return True, None
    
    # Проверка на минимальную длину (меньше 3 символов - вероятно мусор)
    # Эта проверка ПОСЛЕ проверки эмодзи, чтобы не блокировать одиночные эмодзи
    if len(text_stripped) < 3:
        return False, "Слишком короткий текст (< 3 символов)"
    
    # Если эмодзи нет - применяем стандартную валидацию
    
    # Проверка на то, что текст состоит только из URL/ссылок
    url_pattern = r'https?://\S+|www\.\S+|t\.me/\S+|vk\.com/\S+'
    text_without_urls = re.sub(url_pattern, '', text_stripped, flags=re.IGNORECASE).strip()
    if len(text_without_urls) < 3:
        return False, "Только ссылки, нет текста для анализа"
    
    # Проверяем наличие хотя бы одной буквы или цифры
    has_letters_or_digits = bool(re.search(r'[a-zA-Zа-яА-ЯёЁ0-9]', text_without_urls, re.UNICODE))
    
    if not has_letters_or_digits:
        # Нет букв, цифр и эмодзи - только спецсимволы
        return False, "Только специальные символы, нет букв/цифр"
    
    # Проверяем что букв/цифр достаточно
    text_letters_digits = re.sub(r'[^\w\s]', '', text_without_urls, flags=re.UNICODE)
    if len(text_letters_digits) < 2:
        return False, "Недостаточно текста для анализа"
    
    # Проверка на слишком длинный текст (более 8000 символов - ограничение API)
    if len(text_stripped) > 8000:
        return False, "Слишком длинный текст (> 8000 символов)"
    
    return True, None


class YandexSentimentAnalyzer:
    """Yandex sentiment analysis using Few-shot Text Classification API"""
    
    def __init__(self, api_key: str, folder_id: str):
        """
        Initialize Yandex sentiment analyzer with Few-shot classifier
        
        Args:
            api_key: Yandex API key
            folder_id: Yandex Cloud folder ID (format: b1g8dn6s4m5k********)
        """
        self.api_key = api_key
        self.folder_id = folder_id
        self.api_url = "https://llm.api.cloud.yandex.net/foundationModels/v1/fewShotTextClassification"
        
        # Подготовка примеров для Few-shot классификации
        self.samples = [
            {
                "text": "Отличный сервис, всё понравилось! Буду рекомендовать друзьям",
                "label": "позитивное"
            },
            {
                "text": "Супер! Молодцы! Так держать 👍",
                "label": "позитивное"
            },
            {
                "text": "Очень хорошо получилось! Спасибо большое",
                "label": "позитивное"
            },
            {
                "text": "Ужасное обслуживание, потерял время и деньги",
                "label": "негативное"
            },
            {
                "text": "Полный провал, очень разочарован",
                "label": "негативное"
            },
            {
                "text": "Не могу понять зачем это нужно, только время тратится",
                "label": "негативное"
            },
            {
                "text": "Обычный магазин, ничего особенного",
                "label": "нейтральное"
            },
            {
                "text": "Товар соответствует описанию",
                "label": "нейтральное"
            },
            {
                "text": "Видел, принял к сведению",
                "label": "нейтральное"
            }
        ]
        
        logger.info("Yandex Sentiment Analyzer initialized with Few-shot Classifier")
    
    async def analyze_text(self, text: str) -> Optional[Tuple[str, float]]:
        """
        Analyze sentiment of text using Yandex Few-shot classifier
        
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
        
        # Формируем запрос к Few-shot классификатору
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Api-Key {self.api_key}"
        }
        
        data = {
            "modelUri": f"cls://{self.folder_id}/yandexgpt-lite",
            "taskDescription": "Определи тональность комментария в социальных сетях: позитивное, негативное или нейтральное",
            "labels": [
                "позитивное",
                "негативное",
                "нейтральное"
            ],
            "text": text.strip(),
            "samples": self.samples
        }
        
        try:
            # Выполняем синхронный запрос в executor для async
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, self._call_classifier, headers, data)
            
            if result:
                # Парсим ответ
                parsed = parse_classifier_response(result)
                
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
                    logger.warning(f"Failed to parse classifier result: {parsed}")
                    return None
            else:
                logger.warning("Empty result from Yandex Classifier")
                return None
                
        except Exception as e:
            logger.error(f"Error in sentiment analysis: {e}", exc_info=True)
            return None
    
    def _call_classifier(self, headers: dict, data: dict) -> Optional[dict]:
        """
        Синхронный вызов Few-shot классификатора (выполняется в executor)
        
        Args:
            headers: HTTP заголовки
            data: Данные запроса
            
        Returns:
            JSON ответ или None при ошибке
        """
        try:
            response = requests.post(
                self.api_url,
                headers=headers,
                json=data,
                timeout=30
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(
                    f"Classifier API error: status {response.status_code}, "
                    f"response: {response.text}"
                )
                return None
                
        except requests.exceptions.Timeout:
            logger.error("Request to classifier API timed out")
            return None
        except Exception as e:
            logger.error(f"Error calling classifier API: {e}", exc_info=True)
            return None
    
    async def close(self):
        """Close analyzer (no-op, kept for compatibility)"""
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
                    # Проверяем: если есть медиа БЕЗ текста - пропускаем анализ
                    # Во всех остальных случаях пытаемся анализировать
                    comment_text = comment.comment_text or ''
                    text_stripped = comment_text.strip()
                    has_media = comment.has_media == 1
                    
                    # Логика: "не определена" только для медиа без текста
                    # Для всех остальных случаев (с текстом) - всегда пытаемся анализировать
                    if has_media and not text_stripped:
                        # Медиа без текста - пропускаем анализ
                        logger.info(
                            f"Comment {comment.id} has media without text, "
                            f"skipping sentiment analysis"
                        )
                        success = self.db_manager.update_sentiment(
                            comment.id,
                            None,  # sentiment = None (не определена)
                            None,  # score = None
                            processed=1
                        )
                        
                        if success:
                            comment.sentiment = None
                            comment.sentiment_score = None
                            if self.bot_token and self.alert_chat_id:
                                await self._send_notification(comment)
                    else:
                        # Есть текст - пытаемся анализировать
                        # Для текстовых сообщений валидация менее строгая
                        result = await self.analyzer.analyze_text(comment_text)
                        
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
                            # Анализ не удался - но для текстовых сообщений это необычно
                            # Логируем предупреждение и помечаем как обработанный без тональности
                            logger.warning(
                                f"Sentiment analysis failed for comment {comment.id} "
                                f"(text: '{text_stripped[:50]}...')"
                            )
                            success = self.db_manager.update_sentiment(
                                comment.id,
                                None,  # sentiment = None (не удалось определить)
                                None,  # score = None
                                processed=1
                            )
                            
                            if success:
                                comment.sentiment = None
                                comment.sentiment_score = None
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

