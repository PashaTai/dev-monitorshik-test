"""
VK Comment Monitor
Adapted from monitorshik-vk/monitor.py
Monitors comments in VK groups and user pages
"""
import time
import re
import threading
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple
import requests
from dateutil import parser

from monitors.base import BaseMonitor
from database.db_manager import DatabaseManager

logger = logging.getLogger(__name__)


class VKMonitor(BaseMonitor):
    """VK comment monitor"""
    
    def __init__(self, db_manager: DatabaseManager, config: dict):
        """
        Initialize VK monitor
        
        Args:
            db_manager: DatabaseManager instance
            config: Configuration dictionary with VK API credentials
        """
        super().__init__(db_manager)
        self.config = config
        
        # VK API settings
        self.api_token = config.get('VK_ACCESS_TOKEN')
        self.vk_group_id = config.get('VK_GROUP_ID')
        self.api_version = '5.131'
        self.api_base = 'https://api.vk.com/method/'
        
        # Monitoring parameters
        self.posts_to_check = int(config.get('POSTS_TO_CHECK', '10'))
        self.comments_per_post = int(config.get('COMMENTS_PER_POST', '20'))
        self.check_interval = int(config.get('CHECK_INTERVAL', '60'))
        self.request_delay = float(config.get('REQUEST_DELAY', '0.4'))
        
        # Owner information
        self.owner_id: Optional[int] = None
        self.owner_type: Optional[str] = None
        self.owner_name: Optional[str] = None
        
        # Thread control
        self._running = False
        self._thread: Optional[threading.Thread] = None
    
    def start(self):
        """Start VK monitoring in background thread"""
        if self._running:
            logger.warning("VK monitor is already running")
            return
        
        # Resolve owner ID
        owner_id, owner_type, screen_name = self._resolve_vk_owner(self.vk_group_id)
        if not owner_id:
            logger.error(f"Failed to resolve VK owner: {self.vk_group_id}")
            raise ValueError(f"Cannot resolve VK owner: {self.vk_group_id}")
        
        self.owner_id = owner_id
        self.owner_type = owner_type
        
        # Get owner info
        owner_info = self._get_owner_info(owner_id, owner_type)
        self.owner_name = owner_info.get('name', 'Unknown Owner')
        
        logger.info(
            f"VK Monitor: Monitoring {self.owner_type} {self.owner_name} "
            f"(ID: {owner_id})"
        )
        logger.info(
            f"Parameters: {self.posts_to_check} posts × {self.comments_per_post} comments"
        )
        logger.info(f"Check interval: {self.check_interval} seconds")
        
        # Start monitoring thread
        self._running = True
        self._thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        self._thread.start()
        logger.info("VK monitor started")
    
    
    async def stop(self):
        """Stop VK monitoring (async wrapper for thread-based monitor)"""
        logger.info("Stopping VK monitor...")
        self._running = False
        if self._thread:
            # Wait for thread to finish in background
            import asyncio
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, lambda: self._thread.join(10))
        logger.info("VK monitor stopped")
    
    def _monitoring_loop(self):
        """Main monitoring loop (runs in thread) - точно как в оригинале"""
        cycle_count = 0
        try:
            while self._running:
                cycle_count += 1
                logger.info(f"--- Cycle #{cycle_count} ---")
                
                try:
                    self._process_comments()
                except Exception as e:
                    logger.error(f"Error in processing cycle: {e}")
                
                # Sleep точно как в оригинале
                if self._running:
                    logger.info(f"Sleeping for {self.check_interval} seconds...")
                    time.sleep(self.check_interval)
        
        except Exception as e:
            logger.error(f"VK monitoring loop error: {e}")
    
    def _vk_api_call(self, method: str, params: Dict[str, Any]) -> Optional[Dict]:
        """Call VK API method"""
        params['access_token'] = self.api_token
        params['v'] = self.api_version
        
        url = f'{self.api_base}{method}'
        
        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            if 'error' in data:
                error = data['error']
                logger.error(
                    f"VK API Error: {error.get('error_msg', 'Unknown')} "
                    f"(code: {error.get('error_code')})"
                )
                return None
            
            return data.get('response')
        
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error calling VK API: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error calling VK API: {e}")
            return None
    
    def _resolve_vk_owner(self, owner_input: str) -> Tuple[Optional[int], Optional[str], str]:
        """Resolve VK owner ID from any format"""
        owner_input = owner_input.strip()
        original_input = owner_input
        
        # Remove minus if present (group indicator)
        if owner_input.startswith('-'):
            owner_input = owner_input[1:]
            is_group = True
        else:
            is_group = False
        
        # Check for id prefix (user)
        if owner_input.startswith('id'):
            match = re.match(r'id(\d+)', owner_input)
            if match:
                user_id = int(match.group(1))
                return (user_id, 'user', original_input)
        
        # Check for club/public prefix (group)
        if owner_input.startswith('club') or owner_input.startswith('public'):
            match = re.match(r'(club|public)(\d+)', owner_input)
            if match:
                group_id = int(match.group(2))
                return (-group_id, 'group', original_input)
        
        # If pure number
        if owner_input.isdigit():
            num_id = int(owner_input)
            if is_group:
                return (-num_id, 'group', original_input)
            owner_input = str(num_id)
        
        # Extract screen_name from URL
        url_match = re.match(r'https?://vk\.com/([a-zA-Z0-9_]+)', owner_input)
        if url_match:
            owner_input = url_match.group(1)
        
        # Use utils.resolveScreenName
        response = self._vk_api_call('utils.resolveScreenName', {'screen_name': owner_input})
        
        if response:
            obj_type = response.get('type')
            obj_id = response.get('object_id')
            
            if obj_type == 'user':
                return (obj_id, 'user', owner_input)
            elif obj_type == 'group':
                return (-obj_id, 'group', owner_input)
        
        logger.error(f"Failed to resolve owner: {original_input}")
        return (None, None, None)
    
    def _get_owner_info(self, owner_id: int, owner_type: str) -> Dict:
        """Get owner information"""
        if owner_type == 'user':
            response = self._vk_api_call('users.get', {
                'user_ids': owner_id,
                'fields': 'screen_name'
            })
            
            if response and len(response) > 0:
                user = response[0]
                return {
                    'name': f"{user.get('first_name', '')} {user.get('last_name', '')}".strip(),
                    'id': owner_id,
                    'screen_name': user.get('screen_name', '')
                }
        else:  # group
            response = self._vk_api_call('groups.getById', {
                'group_id': abs(owner_id)
            })
            
            if response and len(response) > 0:
                group = response[0]
                return {
                    'name': group.get('name', 'Unknown Group'),
                    'id': owner_id,
                    'screen_name': group.get('screen_name', '')
                }
        
        return {'name': 'Unknown Owner', 'id': owner_id}
    
    def _get_wall_posts(self, owner_id: int, count: int) -> List[Dict]:
        """Get wall posts"""
        response = self._vk_api_call('wall.get', {
            'owner_id': owner_id,
            'count': count,
            'filter': 'owner'
        })
        
        if not response:
            return []
        
        posts = response.get('items', [])
        logger.debug(f"Fetched {len(posts)} posts from owner {owner_id}")
        return posts
    
    def _get_post_comments(self, owner_id: int, post_id: int, count: int) -> List[Dict]:
        """Get post comments"""
        response = self._vk_api_call('wall.getComments', {
            'owner_id': owner_id,
            'post_id': post_id,
            'count': count,
            'sort': 'desc',
            'need_likes': 0,
            'extended': 1
        })
        
        if not response:
            return []
        
        comments = response.get('items', [])
        profiles = response.get('profiles', [])
        groups = response.get('groups', [])
        
        # Create lookup dicts
        profiles_dict = {profile['id']: profile for profile in profiles}
        groups_dict = {group['id']: group for group in groups}
        
        # Add author info to comments
        for comment in comments:
            from_id = comment.get('from_id')
            if from_id > 0:
                comment['author_info'] = profiles_dict.get(from_id, {})
            else:
                comment['author_info'] = groups_dict.get(abs(from_id), {})
        
        return comments
    
    def _process_comments(self):
        """Process comments for current owner"""
        if not self.owner_id:
            return
        
        # Get posts
        posts = self._get_wall_posts(self.owner_id, self.posts_to_check)
        
        if not posts:
            logger.warning("No posts fetched, skipping cycle")
            return
        
        new_comments_count = 0
        
        for post in posts:
            post_id = post.get('id')
            post_url = f"https://vk.com/wall{self.owner_id}_{post_id}"
            
            # Get post date (VK возвращает UTC, добавляем +3 часа для МСК)
            post_date = datetime.fromtimestamp(post.get('date', 0)) + timedelta(hours=3)
            
            # Get comments
            comments = self._get_post_comments(
                self.owner_id,
                post_id,
                self.comments_per_post
            )
            
            time.sleep(self.request_delay)
            
            if not comments:
                continue
            
            # Process comments
            for comment in comments:
                comment_id = comment.get('id')
                
                # Добавляем информацию о посте в комментарий (как в оригинале)
                comment['post_owner_id'] = self.owner_id
                comment['post_id'] = post_id
                
                # Prepare comment data
                author_info = comment.get('author_info', {})
                from_id = comment.get('from_id', 0)
                
                if from_id > 0:  # User
                    author_name = f"{author_info.get('first_name', '')} {author_info.get('last_name', '')}".strip()
                    author_id = str(from_id)
                    author_username = author_info.get('screen_name')
                    if author_username:
                        author_username = f"@{author_username}"
                else:  # Group
                    author_name = author_info.get('name', 'Unknown Group')
                    author_id = str(abs(from_id))
                    author_username = None
                
                # Comment text
                comment_text = comment.get('text', '').strip()
                
                # Check for media
                attachments = comment.get('attachments', [])
                has_media = len(attachments) > 0
                media_type = None
                if has_media and attachments:
                    # Determine media type from first attachment
                    att = attachments[0]
                    att_type = att.get('type', '')
                    if att_type == 'photo':
                        media_type = 'photo'
                    elif att_type == 'video':
                        media_type = 'video'
                
                # Comment date (VK возвращает UTC, добавляем +3 часа для МСК)
                comment_date = datetime.fromtimestamp(comment.get('date', 0)) + timedelta(hours=3)
                
                # Comment URL
                comment_url = f"https://vk.com/wall{self.owner_id}_{post_id}?reply={comment_id}"
                
                # Format comment data
                comment_data = self.format_comment_data(
                    source='vk',
                    source_comment_id=str(comment_id),
                    group_channel_name=self.owner_name,
                    author_name=author_name or 'Unknown',
                    author_id=author_id,
                    comment_text=comment_text,
                    has_media=has_media,
                    media_type=media_type,
                    post_url=post_url,
                    post_published_at=post_date,
                    comment_url=comment_url,
                    comment_published_at=comment_date,
                    author_username=author_username
                )
                
                # Save to database
                saved = self.save_comment_to_db(comment_data)
                if saved:
                    new_comments_count += 1
                    logger.info(
                        f"New VK comment saved: {author_name} on post {post_id}"
                    )
                    
                    # NOTE: Уведомления НЕ отправляются здесь!
                    # Новая логика: комментарий сохранен → sentiment worker обработает → 
                    # → отправит уведомление с тональностью
                else:
                    logger.debug(f"VK comment duplicate: {comment_id}")
        
        if new_comments_count > 0:
            logger.info(f"Processed {new_comments_count} new VK comments")
    
    def _format_notification(
        self, comment: Dict, post_url: str, comment_url: str, owner_name: str
    ) -> str:
        """Format VK comment for Telegram notification"""
        author_info = comment.get('author_info', {})
        from_id = comment.get('from_id', 0)
        
        if from_id > 0:  # User
            first_name = author_info.get('first_name', 'Unknown')
            last_name = author_info.get('last_name', 'User')
            author_name = f"{first_name} {last_name}"
            author_url = f"https://vk.com/id{from_id}"
            author_id = from_id
        else:  # Group
            author_name = author_info.get('name', 'Unknown Group')
            author_url = f"https://vk.com/club{abs(from_id)}"
            author_id = abs(from_id)
        
        # Comment time (timestamp в секундах) - МОСКОВСКОЕ ВРЕМЯ
        timestamp = comment.get('date', 0)
        dt = datetime.fromtimestamp(timestamp) + timedelta(hours=3)  # +3 часа для московского времени
        time_str = dt.strftime('%H:%M %d.%m.%Y')
        
        # Comment text
        text = comment.get('text', '').strip()
        attachments = comment.get('attachments', [])
        has_media = len(attachments) > 0
        
        if text:
            message = f"""🔵 <b>VK</b> | {owner_name}
👤 <a href="{author_url}">{author_name}</a>
🆔 <code>{author_id}</code>
🕐 {time_str}
━━━━━━━━━━━━━━━━━━
<blockquote>{text}</blockquote>

<a href="{post_url}">🔗 Открыть пост</a>
<a href="{comment_url}">💬 Открыть комментарий</a>"""
        else:
            message = f"""🔵 <b>VK</b> | {owner_name}
👤 <a href="{author_url}">{author_name}</a>
🆔 <code>{author_id}</code>
🕐 {time_str}
━━━━━━━━━━━━━━━━━━
<b>Пользователь прислал медиафайл, пожалуйста откройте комментарий чтобы увидеть содержание</b>

<a href="{post_url}">🔗 Открыть пост</a>
<a href="{comment_url}">💬 Открыть комментарий</a>"""
        
        return message
    
    def _send_telegram_notification(self, message: str, bot_token: str, chat_id: str) -> bool:
        """
        Send notification to Telegram (synchronous)
        Returns True if successful, False on error - точно как в оригинале
        """
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        
        params = {
            'chat_id': chat_id,
            'text': message,
            'parse_mode': 'HTML',
            'disable_web_page_preview': False
        }
        
        retry_count = 3
        for attempt in range(retry_count):
            try:
                response = requests.post(url, json=params, timeout=10)
                
                if response.status_code == 429:
                    # Rate limit exceeded
                    retry_after = response.json().get('parameters', {}).get('retry_after', 5)
                    logger.warning(f"Telegram rate limit hit, waiting {retry_after} seconds")
                    time.sleep(retry_after)
                    continue
                
                response.raise_for_status()
                logger.debug("VK notification sent successfully")
                return True
                
            except requests.exceptions.RequestException as e:
                logger.warning(
                    f"Error sending Telegram message (attempt {attempt + 1}/{retry_count}): {e}"
                )
                if attempt < retry_count - 1:
                    time.sleep(2)
        
        logger.error(f"Failed to send VK notification after {retry_count} attempts")
        return False

