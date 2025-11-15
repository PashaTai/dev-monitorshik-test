#!/usr/bin/env python3
"""
REST API для ручной разметки тональности комментариев
FastAPI сервер для обновления sentiment в базе данных
"""
import os
import logging
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field
from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.middleware.cors import CORSMiddleware
import secrets

from config.settings import Settings
from database.db_manager import DatabaseManager
from database.models import Comment

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load settings
Settings.load()

# Initialize database
db_manager = DatabaseManager(Settings.DB_PATH)

# Initialize FastAPI
app = FastAPI(
    title="Sentiment Labeling API",
    description="API для ручной разметки тональности комментариев",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # В продакшене ограничить конкретными доменами
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Basic auth
security = HTTPBasic()

# API credentials from environment
API_USERNAME = os.getenv("API_USERNAME", "admin")
API_PASSWORD = os.getenv("API_PASSWORD", "changeme")


def verify_credentials(credentials: HTTPBasicCredentials = Depends(security)):
    """Verify HTTP Basic Auth credentials"""
    correct_username = secrets.compare_digest(credentials.username, API_USERNAME)
    correct_password = secrets.compare_digest(credentials.password, API_PASSWORD)
    
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверные учетные данные",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


# Pydantic models
class CommentResponse(BaseModel):
    """Comment model for API response"""
    id: int
    source: str
    group_channel_name: str
    author_name: str
    comment_text: str
    sentiment: Optional[str] = None
    sentiment_score: Optional[float] = None
    comment_published_at: datetime
    post_url: str
    comment_url: str
    
    class Config:
        from_attributes = True


class SentimentUpdate(BaseModel):
    """Request model for updating sentiment"""
    sentiment: str = Field(..., pattern="^(positive|negative|neutral)$")
    sentiment_score: Optional[float] = Field(default=0.95, ge=0.0, le=1.0)


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    database: str
    total_comments: int
    unprocessed_comments: int


# API endpoints
@app.get("/api/health", response_model=HealthResponse)
async def health_check():
    """Проверка работоспособности API и базы данных"""
    try:
        stats = db_manager.get_statistics()
        return HealthResponse(
            status="healthy",
            database=Settings.DB_PATH,
            total_comments=stats['total'],
            unprocessed_comments=stats['unprocessed']
        )
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@app.get("/api/comments/undefined", response_model=List[CommentResponse])
async def get_undefined_comments(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 100,
    username: str = Depends(verify_credentials)
):
    """
    Получить комментарии с неопределенной тональностью (sentiment IS NULL)
    
    Args:
        start_date: Начальная дата в формате YYYY-MM-DD (опционально)
        end_date: Конечная дата в формате YYYY-MM-DD (опционально)
        limit: Максимальное количество комментариев (по умолчанию 100)
    """
    try:
        session = db_manager.get_session()
        
        # Build query
        query = session.query(Comment).filter(Comment.sentiment == None)
        
        # Apply date filters if provided
        if start_date:
            try:
                start_dt = datetime.strptime(start_date, "%Y-%m-%d")
                query = query.filter(Comment.comment_published_at >= start_dt)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail="Неверный формат start_date. Используйте YYYY-MM-DD"
                )
        
        if end_date:
            try:
                end_dt = datetime.strptime(end_date, "%Y-%m-%d")
                # Add 23:59:59 to include the entire end date
                end_dt = end_dt.replace(hour=23, minute=59, second=59)
                query = query.filter(Comment.comment_published_at <= end_dt)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail="Неверный формат end_date. Используйте YYYY-MM-DD"
                )
        
        # Order by date (newest first) and apply limit
        comments = query.order_by(Comment.comment_published_at.desc()).limit(limit).all()
        
        session.close()
        
        logger.info(f"Retrieved {len(comments)} undefined comments")
        return comments
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving undefined comments: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@app.put("/api/comments/{comment_id}/sentiment")
async def update_comment_sentiment(
    comment_id: int,
    sentiment_data: SentimentUpdate,
    username: str = Depends(verify_credentials)
):
    """
    Обновить тональность комментария
    
    Args:
        comment_id: ID комментария в базе данных
        sentiment_data: Данные тональности (positive/negative/neutral)
    """
    try:
        # Verify comment exists
        session = db_manager.get_session()
        comment = session.query(Comment).filter(Comment.id == comment_id).first()
        session.close()
        
        if not comment:
            raise HTTPException(
                status_code=404,
                detail=f"Комментарий с ID {comment_id} не найден"
            )
        
        # Update sentiment
        success = db_manager.update_sentiment(
            comment_id=comment_id,
            sentiment=sentiment_data.sentiment,
            sentiment_score=sentiment_data.sentiment_score,
            processed=1
        )
        
        if not success:
            raise HTTPException(
                status_code=500,
                detail="Не удалось обновить тональность"
            )
        
        logger.info(
            f"Updated comment {comment_id} sentiment to {sentiment_data.sentiment} "
            f"by user {username}"
        )
        
        return {
            "success": True,
            "comment_id": comment_id,
            "sentiment": sentiment_data.sentiment,
            "sentiment_score": sentiment_data.sentiment_score
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating sentiment for comment {comment_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@app.get("/api/comments/{comment_id}", response_model=CommentResponse)
async def get_comment(
    comment_id: int,
    username: str = Depends(verify_credentials)
):
    """
    Получить информацию о конкретном комментарии
    
    Args:
        comment_id: ID комментария в базе данных
    """
    try:
        session = db_manager.get_session()
        comment = session.query(Comment).filter(Comment.id == comment_id).first()
        session.close()
        
        if not comment:
            raise HTTPException(
                status_code=404,
                detail=f"Комментарий с ID {comment_id} не найден"
            )
        
        return comment
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving comment {comment_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@app.get("/api/stats")
async def get_stats(username: str = Depends(verify_credentials)):
    """
    Получить статистику по базе данных
    """
    try:
        stats = db_manager.get_statistics()
        
        # Additional stats for undefined comments
        session = db_manager.get_session()
        undefined_count = session.query(Comment).filter(Comment.sentiment == None).count()
        session.close()
        
        return {
            "total_comments": stats['total'],
            "by_source": {
                "telegram": stats['telegram'],
                "vk": stats['vk']
            },
            "by_status": {
                "processed": stats['processed'],
                "unprocessed": stats['unprocessed']
            },
            "undefined_sentiment": undefined_count
        }
        
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("API_PORT", "8000"))
    host = os.getenv("API_HOST", "0.0.0.0")
    
    logger.info(f"Starting API server on {host}:{port}")
    logger.info(f"Database: {Settings.DB_PATH}")
    logger.info(f"API Username: {API_USERNAME}")
    
    uvicorn.run(
        "api_server:app",
        host=host,
        port=port,
        reload=False,
        log_level="info"
    )


