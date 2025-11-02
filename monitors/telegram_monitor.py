"""
Telegram Comment Monitor
Adapted from monitorshik-tg/worker.py
Monitors comments in Telegram channel discussion groups
"""
import asyncio
import os
import logging
from datetime import datetime
from typing import Dict, Optional, Tuple

import aiohttp
import pytz
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.functions.channels import GetFullChannelRequest, JoinChannelRequest
from telethon.tl.types import Channel, MessageMediaPhoto, MessageMediaDocument
from telethon.errors import (
    ChannelPrivateError,
    InviteHashExpiredError,
    UserAlreadyParticipantError,
)

from monitors.base import BaseMonitor
from database.db_manager import DatabaseManager

logger = logging.getLogger(__name__)


class TelegramMonitor(BaseMonitor):
    """Telegram comment monitor"""
    
    def __init__(self, db_manager: DatabaseManager, config: dict):
        """
        Initialize Telegram monitor
        
        Args:
            db_manager: DatabaseManager instance
            config: Configuration dictionary with Telegram API credentials
        """
        super().__init__(db_manager)
        self.config = config
        
        # Initialize Telegram client
        self.client = TelegramClient(
            StringSession(config.get('TG_STRING_SESSION')),
            config.get('TG_API_ID'),
            config.get('TG_API_HASH')
        )
        
        # Mapping: linked_chat_id -> (channel_username, channel_title)
        self.linked_groups: Dict[int, Tuple[Optional[str], str]] = {}
        self.group_entities = []
        self.http_session: Optional[aiohttp.ClientSession] = None
        
        # Timezone
        try:
            self.tz = pytz.timezone(config.get('TZ', 'UTC'))
        except pytz.UnknownTimeZoneError:
            logger.warning(f"Unknown timezone {config.get('TZ')}, using UTC")
            self.tz = pytz.UTC
    
    async def start(self):
        """Start Telegram monitoring"""
        logger.info("Starting Telegram monitor setup...")
        
        await self.client.start()
        logger.info("Telegram client connected")
        
        # Create HTTP session for Bot API (if needed for notifications)
        self.http_session = aiohttp.ClientSession()
        
        # Setup channels
        channels = self.config.get('CHANNELS', '').split(',')
        channels = [ch.strip() for ch in channels if ch.strip()]
        
        for channel_username in channels:
            await self._setup_channel(channel_username)
        
        if not self.linked_groups:
            logger.error("Failed to connect to any discussion groups")
            raise RuntimeError("No discussion groups available")
        
        # Subscribe to events in linked groups
        @self.client.on(events.NewMessage(chats=self.group_entities))
        async def handle_comment(event):
            await self._handle_new_message(event)
        
        logger.info(f"Telegram monitoring started for {len(self.linked_groups)} discussion groups")
    
    async def stop(self):
        """Stop Telegram monitoring"""
        logger.info("Stopping Telegram monitor...")
        if self.http_session:
            await self.http_session.close()
        await self.client.disconnect()
        logger.info("Telegram monitor stopped")
    
    async def _setup_channel(self, channel_username: str):
        """Setup one channel: resolve, join, get linked group"""
        try:
            logger.info(f"Processing channel: {channel_username}")
            entity = await self.client.get_entity(channel_username)
            
            if not isinstance(entity, Channel):
                logger.warning(f"{channel_username} is not a channel, skipping")
                return
            
            # Try to join channel
            try:
                await self.client(JoinChannelRequest(entity))
                logger.info(f"Joined channel {channel_username}")
            except UserAlreadyParticipantError:
                logger.info(f"Already subscribed to channel {channel_username}")
            except (ChannelPrivateError, InviteHashExpiredError):
                logger.warning(f"Channel {channel_username} is private/unavailable, skipping")
                return
            except Exception as e:
                logger.warning(f"Error joining channel {channel_username}: {e}")
            
            # Get full channel info
            full_channel = await self.client(GetFullChannelRequest(entity))
            linked_chat_id = full_channel.full_chat.linked_chat_id
            
            if not linked_chat_id:
                logger.info(f"Channel {channel_username} has no linked discussion group, skipping")
                return
            
            # Get linked group entity
            linked_entity = await self.client.get_entity(linked_chat_id)
            
            # Try to join discussion group
            try:
                await self.client(JoinChannelRequest(linked_entity))
                logger.info(f"Joined discussion group for channel {channel_username}")
            except UserAlreadyParticipantError:
                logger.info(f"Already in discussion group for channel {channel_username}")
            except (ChannelPrivateError, InviteHashExpiredError):
                logger.warning(
                    f"Discussion group for {channel_username} is private/unavailable, skipping"
                )
                return
            except Exception as e:
                logger.warning(f"Error joining discussion group for {channel_username}: {e}")
            
            # Convert to negative format for supergroups
            if linked_chat_id > 0:
                linked_chat_id = -int(f"100{linked_chat_id}")
            
            # Save mapping
            channel_title = entity.title
            channel_user = entity.username
            self.linked_groups[linked_chat_id] = (channel_user, channel_title)
            self.group_entities.append(linked_entity)
            
            logger.info(
                f"✓ Channel {channel_username} configured. "
                f"Group: {linked_chat_id}, Title: {channel_title}"
            )
            
        except Exception as e:
            logger.error(f"Error processing channel {channel_username}: {e}")
    
    async def _handle_new_message(self, event):
        """Handle new messages in discussion groups"""
        message = event.message
        
        # Filter: only messages with reply (comments/replies)
        if not message.reply_to:
            return
        
        # Get discussion post ID
        discussion_post_id = message.reply_to.reply_to_top_id or message.reply_to.reply_to_msg_id
        chat_id = event.chat_id
        
        # Get channel info from mapping
        channel_info = self.linked_groups.get(chat_id)
        if not channel_info:
            logger.warning(f"Message from unknown group {chat_id}")
            return
        
        channel_username, channel_title = channel_info
        
        # Get original message to find channel post ID and post date
        channel_post_id = discussion_post_id  # Default
        post_date = None  # Will get from original message
        try:
            original_message = await self.client.get_messages(chat_id, ids=discussion_post_id)
            
            if original_message:
                # Get post date from original message
                if original_message.date:
                    post_date = original_message.date.astimezone(self.tz)
                
                # Get channel post ID
                if original_message.fwd_from:
                    if hasattr(original_message.fwd_from, 'channel_post') and original_message.fwd_from.channel_post:
                        channel_post_id = original_message.fwd_from.channel_post
                    elif hasattr(original_message.fwd_from, 'saved_from_msg_id') and original_message.fwd_from.saved_from_msg_id:
                        channel_post_id = original_message.fwd_from.saved_from_msg_id
        except Exception as e:
            logger.error(f"Error getting original message: {e}")
        
        # Time (for comment)
        msg_time = message.date
        local_time = msg_time.astimezone(self.tz)
        
        # Fallback to comment time if post date not found
        if post_date is None:
            post_date = msg_time
        
        # Get author info
        sender = await event.get_sender()
        author_first = sender.first_name or ""
        author_last = sender.last_name or ""
        author_name = f"{author_first} {author_last}".strip() or "Unknown"
        author_username = f"@{sender.username}" if sender.username else None
        author_id = str(sender.id)
        
        # Post URL
        if channel_username:
            post_url = f"https://t.me/{channel_username}/{channel_post_id}"
        else:
            post_url = str(channel_post_id)
        
        # Comment URL (approximate)
        comment_url = post_url  # Telegram doesn't have direct comment links
        
        # Detect media
        has_media = message.media is not None
        media_type = None
        if has_media:
            if hasattr(message.media, '__class__'):
                media_class = message.media.__class__.__name__
                if 'Photo' in media_class:
                    media_type = 'photo'
                elif 'Document' in media_class:
                    # Check for video, sticker, voice
                    if hasattr(message.media, 'document'):
                        doc = message.media.document
                        if hasattr(doc, 'mime_type') and doc.mime_type:
                            if 'video' in doc.mime_type:
                                media_type = 'video'
                            elif 'audio' in doc.mime_type:
                                media_type = 'voice'
                        # Check attributes for sticker
                        if hasattr(doc, 'attributes'):
                            for attr in doc.attributes:
                                if hasattr(attr, '__class__') and 'Sticker' in attr.__class__.__name__:
                                    media_type = 'sticker'
                                    break
        
        # Text
        comment_text = message.text or ""
        
        # Format comment data
        comment_data = self.format_comment_data(
            source='telegram',
            source_comment_id=str(message.id),
            group_channel_name=channel_title,
            author_name=author_name,
            author_id=author_id,
            comment_text=comment_text,
            has_media=has_media,
            media_type=media_type,
            post_url=post_url,
            post_published_at=post_date.replace(tzinfo=None) if post_date else local_time.replace(tzinfo=None),  # Use post date
            comment_url=comment_url,
            comment_published_at=local_time.replace(tzinfo=None),
            author_username=author_username
        )
        
        # Save to database
        saved = self.save_comment_to_db(comment_data)
        if saved:
            logger.info(
                f"New Telegram comment saved: {author_name} in {channel_title} "
                f"on post {channel_post_id}"
            )
            
            # Send notification if configured
            if self.config.get('BOT_TOKEN') and self.config.get('ALERT_CHAT_ID'):
                # Format time for notification
                time_str = local_time.strftime("%H:%M %d.%m.%Y")
                
                # Format base caption
                username_part = f" {author_username}" if author_username else ""
                base_caption = (
                    f"✈️ <b>TG</b> | {channel_title}\n"
                    f"👤 {author_name}{username_part}\n"
                    f"🆔 <code>{author_id}</code>\n"
                    f"🕐 {time_str}\n"
                    f"━━━━━━━━━━━━━━━━━━"
                )
                
                # Send notification with media handling
                if message.media:
                    await self._handle_media_notification(message, base_caption, post_link)
                elif comment_text:
                    await self._send_text_notification(base_caption, comment_text, post_link)
                else:
                    await self._send_fallback_notification(base_caption, post_link)
        else:
            logger.debug(f"Telegram comment duplicate: {message.id}")
    
    async def _send_text_notification(self, base_caption: str, text: str, post_link: str):
        """Send text notification with formatting"""
        notification = (
            f"{base_caption}\n"
            f"<blockquote>{text}</blockquote>\n\n"
            f"<a href=\"{post_link}\">🔗 Открыть пост</a>"
        )
        await self._send_telegram_message(notification)
    
    async def _send_fallback_notification(self, base_caption: str, post_link: str):
        """Send fallback notification when media failed or content is empty"""
        notification = (
            f"{base_caption}\n"
            f"<b>Пользователь прислал медиафайл, пожалуйста откройте пост чтобы увидеть содержание</b>\n\n"
            f"<a href=\"{post_link}\">🔗 Открыть пост</a>"
        )
        await self._send_telegram_message(notification)
    
    async def _handle_media_notification(self, message, base_caption: str, post_link: str):
        """Handle media message notifications (photo, video, sticker, voice)"""
        
        media = message.media
        
        if isinstance(media, MessageMediaPhoto):
            # Photo - always send
            logger.info("   📷 Обнаружено фото, отправляем...")
            await self._send_photo(message, base_caption, post_link)
        
        elif isinstance(media, MessageMediaDocument):
            doc = media.document
            mime_type = doc.mime_type if hasattr(doc, 'mime_type') else ''
            file_size = doc.size if hasattr(doc, 'size') else 0
            
            logger.info(f"   📎 Обнаружен документ: mime={mime_type}, size={file_size} bytes")
            
            # Check document type
            if 'video' in mime_type or any(
                attr for attr in doc.attributes 
                if attr.__class__.__name__ == 'DocumentAttributeVideo'
            ):
                # Video
                if file_size > 10 * 1024 * 1024:  # 10 MB
                    logger.info(f"   ⚠️ Видео слишком большое ({file_size} bytes), отправляем fallback")
                    await self._send_fallback_notification(base_caption, post_link)
                else:
                    logger.info("   🎥 Отправляем видео...")
                    await self._send_video(message, base_caption, post_link)
            
            elif any(
                attr for attr in doc.attributes 
                if attr.__class__.__name__ == 'DocumentAttributeSticker'
            ):
                # Sticker
                logger.info("   🖼️ Отправляем стикер...")
                await self._send_document(message, base_caption, post_link)
            
            elif any(
                attr for attr in doc.attributes 
                if attr.__class__.__name__ == 'DocumentAttributeAnimated'
            ) or 'gif' in mime_type:
                # GIF or animation
                logger.info("   🎬 Отправляем GIF/анимацию...")
                await self._send_document(message, base_caption, post_link)
            
            elif 'audio' in mime_type or any(
                attr for attr in doc.attributes 
                if attr.__class__.__name__ in ['DocumentAttributeAudio']
            ):
                # Voice or audio
                is_voice = any(
                    attr for attr in doc.attributes 
                    if attr.__class__.__name__ == 'DocumentAttributeAudio' 
                    and hasattr(attr, 'voice') and attr.voice
                )
                if is_voice:
                    logger.info("   🎤 Отправляем голосовое сообщение...")
                    await self._send_voice(message, base_caption, post_link)
                else:
                    logger.info("   🎵 Отправляем аудио как документ...")
                    await self._send_document(message, base_caption, post_link)
            else:
                # Other document
                logger.info("   📄 Отправляем документ...")
                await self._send_document(message, base_caption, post_link)
        else:
            # Unknown media type
            logger.warning(f"   ⚠️ Неизвестный тип медиа: {type(media)}")
            await self._send_fallback_notification(base_caption, post_link)
    
    async def _send_photo(self, message, base_caption: str, post_link: str):
        """Download and send photo with caption"""
        try:
            photo_bytes = BytesIO()
            await message.download_media(file=photo_bytes)
            photo_bytes.seek(0)
            
            # Add text to caption if present
            full_caption = base_caption
            if message.text:
                full_caption = f"{base_caption}\n<blockquote>{message.text}</blockquote>"
            
            await self._send_media_to_bot(
                'sendPhoto',
                photo_bytes,
                full_caption,
                'photo.jpg',
                post_link
            )
        except Exception as e:
            logger.error(f"   ❌ Ошибка при отправке фото: {e}")
            await self._send_fallback_notification(base_caption, post_link)
    
    async def _send_video(self, message, base_caption: str, post_link: str):
        """Download and send video with caption"""
        try:
            video_bytes = BytesIO()
            await message.download_media(file=video_bytes)
            video_bytes.seek(0)
            
            # Add text to caption if present
            full_caption = base_caption
            if message.text:
                full_caption = f"{base_caption}\n<blockquote>{message.text}</blockquote>"
            
            await self._send_media_to_bot(
                'sendVideo',
                video_bytes,
                full_caption,
                'video.mp4',
                post_link
            )
        except Exception as e:
            logger.error(f"   ❌ Ошибка при отправке видео: {e}")
            await self._send_fallback_notification(base_caption, post_link)
    
    async def _send_document(self, message, base_caption: str, post_link: str):
        """Download and send document (sticker/GIF) with caption"""
        try:
            # Check if it's a sticker
            is_sticker = False
            if hasattr(message.media, 'document'):
                doc = message.media.document
                is_sticker = any(
                    attr for attr in doc.attributes 
                    if attr.__class__.__name__ == 'DocumentAttributeSticker'
                )
            
            # For stickers: send text first, then sticker (stickers don't support caption)
            if is_sticker:
                # Send info as separate text message
                info_text = f"{base_caption}\n\n<b>📩 Пользователь отправил стикер</b>\n\n<a href=\"{post_link}\">🔗 Открыть пост</a>"
                await self._send_telegram_message(info_text)
                
                # Send sticker via Telethon (forward)
                try:
                    await self.client.send_file(
                        int(self.config['ALERT_CHAT_ID']),
                        message.media
                    )
                    logger.info("   ✅ Стикер успешно отправлен")
                except Exception as e:
                    logger.error(f"   ❌ Ошибка при отправке стикера: {e}")
            else:
                # For GIF and other documents - normal send with caption
                doc_bytes = BytesIO()
                await message.download_media(file=doc_bytes)
                doc_bytes.seek(0)
                
                # Determine filename
                filename = 'document'
                if hasattr(message.media, 'document'):
                    doc = message.media.document
                    for attr in doc.attributes:
                        if hasattr(attr, 'file_name'):
                            filename = attr.file_name
                            break
                
                # Add text to caption if present
                full_caption = base_caption
                if message.text:
                    full_caption = f"{base_caption}\n<blockquote>{message.text}</blockquote>"
                
                await self._send_media_to_bot(
                    'sendDocument',
                    doc_bytes,
                    full_caption,
                    filename,
                    post_link
                )
        except Exception as e:
            logger.error(f"   ❌ Ошибка при отправке документа: {e}")
            await self._send_fallback_notification(base_caption, post_link)
    
    async def _send_voice(self, message, base_caption: str, post_link: str):
        """Download and send voice message with caption"""
        try:
            voice_bytes = BytesIO()
            await message.download_media(file=voice_bytes)
            voice_bytes.seek(0)
            
            # Add text to caption if present
            full_caption = base_caption
            if message.text:
                full_caption = f"{base_caption}\n<blockquote>{message.text}</blockquote>"
            
            await self._send_media_to_bot(
                'sendVoice',
                voice_bytes,
                full_caption,
                'voice.ogg',
                post_link
            )
        except Exception as e:
            logger.error(f"   ❌ Ошибка при отправке голосового: {e}")
            await self._send_fallback_notification(base_caption, post_link)
    
    async def _send_media_to_bot(
        self, 
        method: str, 
        media_bytes: BytesIO, 
        caption: str,
        filename: str,
        post_link: str
    ):
        """Send media file via Bot API with caption"""
        
        url = f"https://api.telegram.org/bot{self.config['BOT_TOKEN']}/{method}"
        
        # Add post link to caption
        full_caption = f"{caption}\n\n<a href=\"{post_link}\">🔗 Открыть пост</a>"
        
        # Determine field name for different media types
        field_name_map = {
            'sendPhoto': 'photo',
            'sendVideo': 'video',
            'sendDocument': 'document',
            'sendVoice': 'voice'
        }
        field_name = field_name_map.get(method, 'document')
        
        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                # Create form data
                data = aiohttp.FormData()
                data.add_field('chat_id', str(self.config['ALERT_CHAT_ID']))
                data.add_field('caption', full_caption)
                data.add_field('parse_mode', 'HTML')
                
                # Add file
                media_bytes.seek(0)  # Reset to beginning
                data.add_field(
                    field_name,
                    media_bytes,
                    filename=filename,
                    content_type='application/octet-stream'
                )
                
                async with self.http_session.post(url, data=data) as response:
                    if response.status == 200:
                        logger.info(f"   ✅ Медиафайл успешно отправлен ({method})")
                        return
                    else:
                        error_text = await response.text()
                        logger.warning(
                            f"   Попытка {attempt}/{max_retries}: "
                            f"Ошибка отправки медиа (status {response.status}): {error_text}"
                        )
            except Exception as e:
                logger.warning(f"   Попытка {attempt}/{max_retries}: Ошибка отправки медиа: {e}")
            
            if attempt < max_retries:
                delay = 2 ** (attempt - 1)
                await asyncio.sleep(delay)
        
        # If failed, send fallback
        raise Exception(f"Не удалось отправить медиа после {max_retries} попыток")
    
    async def _send_telegram_message(self, text: str):
        """Send message via Telegram Bot API with retries"""
        if not self.config.get('BOT_TOKEN') or not self.config.get('ALERT_CHAT_ID'):
            return
        
        url = f"https://api.telegram.org/bot{self.config['BOT_TOKEN']}/sendMessage"
        payload = {
            "chat_id": self.config['ALERT_CHAT_ID'],
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }
        
        max_retries = 5
        for attempt in range(1, max_retries + 1):
            try:
                async with self.http_session.post(url, json=payload) as response:
                    if response.status == 200:
                        logger.debug("Telegram notification sent successfully")
                        return
                    else:
                        error_text = await response.text()
                        logger.warning(
                            f"Attempt {attempt}/{max_retries}: "
                            f"Error sending notification (status {response.status}): {error_text}"
                        )
            except Exception as e:
                logger.warning(f"Attempt {attempt}/{max_retries}: Error sending notification: {e}")
            
            if attempt < max_retries:
                delay = 2 ** (attempt - 1)  # 1s, 2s, 4s, 8s, 16s
                await asyncio.sleep(delay)
        
        logger.error(f"Failed to send Telegram notification after {max_retries} attempts")
    
    async def run(self):
        """Run monitoring loop"""
        try:
            await self.start()
            await self.client.run_until_disconnected()
        finally:
            await self.stop()

