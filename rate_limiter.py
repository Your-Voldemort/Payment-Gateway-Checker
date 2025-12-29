"""Rate limiting functionality for bot commands."""
import time
from collections import defaultdict
from typing import Dict
from config import Config
from logger import setup_logger

logger = setup_logger()


class RateLimiter:
    """Simple rate limiter to prevent spam."""
    
    def __init__(self):
        self.user_requests: Dict[int, list] = defaultdict(list)
    
    def is_allowed(self, user_id: int) -> bool:
        """
        Check if a user is allowed to make a request based on rate limits.
        
        Args:
            user_id: The Telegram user ID
            
        Returns:
            bool: True if allowed, False if rate limited
        """
        if not Config.ENABLE_RATE_LIMITING:
            return True
        
        current_time = time.time()
        
        # Remove old requests outside the time window
        self.user_requests[user_id] = [
            req_time for req_time in self.user_requests[user_id]
            if current_time - req_time < Config.RATE_LIMIT_WINDOW
        ]
        
        # Check if user has exceeded the limit
        if len(self.user_requests[user_id]) >= Config.RATE_LIMIT_MESSAGES:
            logger.warning(f"User {user_id} rate limited")
            return False
        
        # Add current request
        self.user_requests[user_id].append(current_time)
        return True
    
    def get_wait_time(self, user_id: int) -> int:
        """
        Get the remaining wait time for a rate-limited user.
        
        Args:
            user_id: The Telegram user ID
            
        Returns:
            int: Seconds to wait before next request
        """
        if not self.user_requests[user_id]:
            return 0
        
        current_time = time.time()
        oldest_request = min(self.user_requests[user_id])
        wait_time = Config.RATE_LIMIT_WINDOW - (current_time - oldest_request)
        
        return max(0, int(wait_time))
