"""Rate limiting functionality for bot commands with database persistence."""
import time
from collections import defaultdict
from typing import Dict, List
from config import Config
from logger import setup_logger

logger = setup_logger()


class RateLimiter:
    """Rate limiter with database persistence and bounded memory usage."""

    def __init__(
        self,
        cleanup_interval: int = 3600,   # Cleanup every hour
        max_tracked_users: int = 50_000  # Cap in-memory user tracking
    ):
        self.user_requests: Dict[int, List[float]] = defaultdict(list)
        self._db_initialized = False
        self._dirty_users: set = set()  # Track users needing DB sync
        self._flush_interval = 5        # Flush every 5 seconds
        self._last_flush = time.time()
        self.cleanup_interval = cleanup_interval
        self.max_tracked_users = max_tracked_users
        self._last_cleanup = time.time()
        self._request_count = 0         # For periodic cleanup trigger

    async def _load_from_db(self, user_id: int):
        """Load rate limit state from database."""
        if not self._db_initialized:
            try:
                from database import load_rate_limit_state
                self._db_initialized = True
            except ImportError:
                logger.warning("Database module not available for rate limiting")
                return

        try:
            from database import load_rate_limit_state
            timestamps = await load_rate_limit_state(user_id)
            if timestamps:
                # Filter old timestamps outside the rate limit window
                current_time = time.time()
                self.user_requests[user_id] = [
                    ts for ts in timestamps
                    if current_time - ts < Config.RATE_LIMIT_WINDOW
                ]
                logger.debug(f"Loaded {len(self.user_requests[user_id])} rate limit entries for user {user_id}")
        except Exception as e:
            logger.warning(f"Could not load rate limit state for user {user_id}: {e}")

    async def _save_to_db(self, user_id: int):
        """Save rate limit state to database."""
        try:
            from database import save_rate_limit_state
            await save_rate_limit_state(user_id, self.user_requests[user_id])
            logger.debug(f"Saved rate limit state for user {user_id}")
        except Exception as e:
            logger.warning(f"Could not save rate limit state for user {user_id}: {e}")

    async def is_allowed(self, user_id: int) -> bool:
        """
        Check if a user is allowed to make a request based on rate limits.
        Now async and persists to database.

        Args:
            user_id: The Telegram user ID

        Returns:
            bool: True if allowed, False if rate limited
        """
        if not Config.ENABLE_RATE_LIMITING:
            return True

        # Load from database on first check for this user
        if user_id not in self.user_requests:
            await self._load_from_db(user_id)

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

        # Mark user as needing DB sync (batched writes for performance)
        self._dirty_users.add(user_id)

        # Periodic flush instead of per-request write
        if current_time - self._last_flush > self._flush_interval:
            await self._flush_dirty_users()

        # Periodic memory cleanup (every 1000 requests or hourly)
        self._request_count += 1
        if self._request_count >= 1000 or (
            current_time - self._last_cleanup > self.cleanup_interval
        ):
            self._cleanup_stale_entries(current_time)
            self._request_count = 0

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

    def _cleanup_stale_entries(self, current_time: float) -> None:
        """
        Remove stale user entries to prevent unbounded memory growth.

        Removes users who have had no activity within the rate limit window.
        If still over max_tracked_users, evicts oldest-activity users (LRU).

        Args:
            current_time: Current epoch time for cutoff calculation
        """
        cutoff = current_time - Config.RATE_LIMIT_WINDOW
        stale_users = [
            uid for uid, reqs in self.user_requests.items()
            if not reqs or max(reqs) < cutoff
        ]
        for uid in stale_users:
            del self.user_requests[uid]
            self._dirty_users.discard(uid)

        # If still over limit, evict oldest-activity users (LRU)
        if len(self.user_requests) > self.max_tracked_users:
            sorted_by_activity = sorted(
                self.user_requests.items(),
                key=lambda kv: max(kv[1]) if kv[1] else 0
            )
            excess = len(self.user_requests) - self.max_tracked_users
            for uid, _ in sorted_by_activity[:excess]:
                del self.user_requests[uid]
                self._dirty_users.discard(uid)
            logger.warning(
                f"Rate limiter evicted {excess} LRU entries "
                f"(max_tracked_users={self.max_tracked_users})"
            )

        if stale_users:
            logger.debug(
                f"Rate limiter cleanup: removed {len(stale_users)} stale entries, "
                f"{len(self.user_requests)} users tracked"
            )

        self._last_cleanup = current_time

    def get_stats(self) -> Dict[str, int]:
        """
        Get current rate limiter memory stats for monitoring.

        Returns:
            Dictionary with tracked_users, max_users, dirty_users counts
        """
        return {
            "tracked_users": len(self.user_requests),
            "max_users": self.max_tracked_users,
            "dirty_users": len(self._dirty_users),
            "cleanup_interval": self.cleanup_interval,
        }

    async def _flush_dirty_users(self):
        """
        Batch write all dirty users to database.
        Significantly reduces DB I/O by writing multiple users at once.
        """
        if not self._dirty_users:
            return

        logger.debug(f"Flushing rate limit state for {len(self._dirty_users)} users")

        for user_id in list(self._dirty_users):
            try:
                await self._save_to_db(user_id)
            except Exception as e:
                logger.warning(f"Failed to flush rate limit for user {user_id}: {e}")

        self._dirty_users.clear()
        self._last_flush = time.time()
