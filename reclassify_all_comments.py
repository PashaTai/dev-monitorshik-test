#!/usr/bin/env python3
"""
Скрипт для переразметки всех комментариев в базе данных новой системой тональности
Использует Few-shot Yandex Classifier вместо старой системы
"""
import os
import sys
import asyncio
import logging
from datetime import datetime
from typing import Optional

from config.settings import Settings
from database.db_manager import DatabaseManager
from database.models import Comment
from sentiment.yandex_analyzer import YandexSentimentAnalyzer

# Создаем директорию для логов
os.makedirs('logs', exist_ok=True)

# Настройка логирования
log_filename = f"logs/reclassify_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_filename, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


async def reclassify_all_comments(batch_size: int = 50):
    """
    Переразметить все комментарии в базе данных
    
    Args:
        batch_size: Размер порции для обработки за раз
    """
    logger.info("=" * 80)
    logger.info("Начало переразметки всех комментариев")
    logger.info("=" * 80)
    
    # Загрузка настроек
    Settings.load()
    
    # Проверка наличия API ключей
    if not Settings.YANDEX_API_KEY or not Settings.YANDEX_FOLDER_ID:
        logger.error("YANDEX_API_KEY или YANDEX_FOLDER_ID не установлены!")
        logger.error("Проверьте файл .env")
        sys.exit(1)
    
    # Инициализация БД
    db_manager = DatabaseManager(Settings.DB_PATH)
    logger.info(f"Подключено к базе данных: {Settings.DB_PATH}")
    
    # Инициализация анализатора тональности
    analyzer = YandexSentimentAnalyzer(
        Settings.YANDEX_API_KEY,
        Settings.YANDEX_FOLDER_ID
    )
    logger.info("Инициализирован Few-shot анализатор тональности")
    
    # Получаем все комментарии
    session = db_manager.get_session()
    try:
        total_count = session.query(Comment).count()
        logger.info(f"Всего комментариев в базе: {total_count}")
        
        if total_count == 0:
            logger.info("Нет комментариев для обработки")
            return
        
        # Обрабатываем порциями
        processed = 0
        successful = 0
        failed = 0
        skipped = 0
        
        offset = 0
        while offset < total_count:
            # Получаем порцию комментариев
            comments = session.query(Comment).order_by(Comment.id).offset(offset).limit(batch_size).all()
            
            if not comments:
                break
            
            logger.info(f"\n--- Обработка порции {offset//batch_size + 1} ({offset+1}-{min(offset+len(comments), total_count)} из {total_count}) ---")
            
            for comment in comments:
                processed += 1
                
                try:
                    # Проверяем текст комментария
                    comment_text = comment.comment_text or ''
                    text_stripped = comment_text.strip()
                    has_media = comment.has_media == 1
                    
                    # Если медиа без текста - пропускаем
                    if has_media and not text_stripped:
                        logger.info(f"[{processed}/{total_count}] ID {comment.id}: Пропуск (медиа без текста)")
                        
                        # Обновляем как обработанный без тональности
                        success = db_manager.update_sentiment(
                            comment.id,
                            None,
                            None,
                            processed=1
                        )
                        
                        if success:
                            skipped += 1
                        else:
                            logger.error(f"Не удалось обновить комментарий {comment.id}")
                            failed += 1
                        
                        continue
                    
                    # Если текста нет совсем - пропускаем
                    if not text_stripped:
                        logger.info(f"[{processed}/{total_count}] ID {comment.id}: Пропуск (пустой текст)")
                        skipped += 1
                        continue
                    
                    # Анализируем тональность
                    logger.info(f"[{processed}/{total_count}] ID {comment.id}: Анализ тональности...")
                    result = await analyzer.analyze_text(comment_text)
                    
                    if result:
                        sentiment, score = result
                        
                        # Обновляем в БД
                        success = db_manager.update_sentiment(
                            comment.id,
                            sentiment,
                            score,
                            processed=1
                        )
                        
                        if success:
                            logger.info(
                                f"[{processed}/{total_count}] ID {comment.id}: "
                                f"✓ {sentiment} ({score:.2f})"
                            )
                            successful += 1
                        else:
                            logger.error(f"Не удалось обновить комментарий {comment.id}")
                            failed += 1
                    else:
                        # Анализ не удался
                        logger.warning(
                            f"[{processed}/{total_count}] ID {comment.id}: "
                            f"✗ Не удалось определить тональность"
                        )
                        
                        # Обновляем как обработанный без тональности
                        success = db_manager.update_sentiment(
                            comment.id,
                            None,
                            None,
                            processed=1
                        )
                        
                        if success:
                            failed += 1
                        else:
                            logger.error(f"Не удалось обновить комментарий {comment.id}")
                            failed += 1
                    
                    # Небольшая задержка между запросами (rate limiting)
                    await asyncio.sleep(0.5)
                    
                except Exception as e:
                    logger.error(
                        f"[{processed}/{total_count}] ID {comment.id}: "
                        f"Ошибка - {e}",
                        exc_info=True
                    )
                    failed += 1
            
            offset += batch_size
            
            # Логируем промежуточные результаты
            logger.info(f"\nПромежуточная статистика:")
            logger.info(f"  Обработано: {processed}/{total_count}")
            logger.info(f"  Успешно: {successful}")
            logger.info(f"  Пропущено: {skipped}")
            logger.info(f"  Ошибок: {failed}")
        
        # Финальная статистика
        logger.info("\n" + "=" * 80)
        logger.info("ФИНАЛЬНАЯ СТАТИСТИКА")
        logger.info("=" * 80)
        logger.info(f"Всего комментариев: {total_count}")
        logger.info(f"Успешно размечено: {successful}")
        logger.info(f"Пропущено (медиа/пусто): {skipped}")
        logger.info(f"Ошибок: {failed}")
        logger.info(f"Лог сохранен в: {log_filename}")
        logger.info("=" * 80)
        
    finally:
        session.close()
        await analyzer.close()


async def main():
    """Точка входа"""
    try:
        await reclassify_all_comments(batch_size=50)
        logger.info("\nПереразметка завершена успешно!")
    except KeyboardInterrupt:
        logger.info("\nПрервано пользователем")
        sys.exit(0)
    except Exception as e:
        logger.error(f"\nКритическая ошибка: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

