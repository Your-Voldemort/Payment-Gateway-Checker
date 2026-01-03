"""User management functionality with caching."""
import os
import json
import tempfile
import time
from typing import Set, Dict, Any, Optional
from datetime import datetime
from config import Config
from logger import setup_logger

logger = setup_logger()

# JSON file path (same directory as old txt file)
JSON_FILE = Config.USER_IDS_FILE.replace('.txt', '.json')

# =============================================================================
# USER CACHE - Reduces disk I/O by caching registered users in memory
# =============================================================================

class UserCache:
    """
    In-memory cache for registered users with TTL-based expiration.

    This significantly reduces disk I/O by avoiding JSON file reads
    on every message. The cache automatically refreshes when:
    - TTL expires (default 60 seconds)
    - A new user is registered (immediate invalidation)
    """

    def __init__(self, ttl_seconds: int = 60):
        self._cache: Optional[Set[int]] = None
        self._cache_time: float = 0
        self._ttl = ttl_seconds
        self._lock_flag = False  # Simple lock to prevent race conditions

    def _is_expired(self) -> bool:
        """Check if cache has expired."""
        return time.time() - self._cache_time > self._ttl

    def _refresh_cache(self) -> Set[int]:
        """Refresh cache from disk."""
        if self._lock_flag:
            # If another operation is in progress, return existing cache or empty set
            return self._cache or set()

        try:
            self._lock_flag = True
            self._cache = _load_user_ids_from_disk()
            self._cache_time = time.time()
            logger.debug(f"User cache refreshed with {len(self._cache)} users")
            return self._cache
        finally:
            self._lock_flag = False

    def get_users(self) -> Set[int]:
        """Get all registered users (from cache if valid)."""
        if self._cache is None or self._is_expired():
            return self._refresh_cache()
        return self._cache

    def is_registered(self, user_id: int) -> bool:
        """Check if a user is registered (uses cache)."""
        return user_id in self.get_users()

    def invalidate(self):
        """Force cache invalidation (call after adding new user)."""
        self._cache = None
        self._cache_time = 0
        logger.debug("User cache invalidated")

    def add_user(self, user_id: int):
        """Add user to cache without full refresh."""
        if self._cache is not None:
            self._cache.add(user_id)
            logger.debug(f"User {user_id} added to cache")

# Global cache instance
_user_cache = UserCache(ttl_seconds=60)


def _migrate_from_txt_to_json() -> None:
    """Migrate old user_ids.txt to JSON format if it exists."""
    if os.path.exists(Config.USER_IDS_FILE) and not os.path.exists(JSON_FILE):
        logger.info("Migrating user_ids.txt to JSON format...")
        try:
            with open(Config.USER_IDS_FILE, 'r') as f:
                user_ids = {int(line.strip()) for line in f.readlines() if line.strip()}
            
            # Create JSON structure with metadata
            users_data = {
                "users": {
                    str(user_id): {
                        "user_id": user_id,
                        "registered_at": datetime.now().isoformat(),
                        "migrated": True
                    }
                    for user_id in user_ids
                },
                "metadata": {
                    "version": "1.0",
                    "migrated_at": datetime.now().isoformat()
                }
            }
            
            _atomic_write_json(JSON_FILE, users_data)
            logger.info(f"Successfully migrated {len(user_ids)} users to JSON format")
            
            # Rename old file as backup
            backup_file = Config.USER_IDS_FILE + '.backup'
            os.rename(Config.USER_IDS_FILE, backup_file)
            logger.info(f"Backup created at {backup_file}")
            
        except Exception as e:
            logger.error(f"Error during migration: {str(e)}")


def _atomic_write_json(filepath: str, data: Dict[str, Any]) -> None:
    """
    Write JSON data atomically using temporary file.
    
    Args:
        filepath: Target file path
        data: Data to write
    """
    dir_path = os.path.dirname(filepath) or '.'
    
    # Write to temporary file first
    with tempfile.NamedTemporaryFile(mode='w', dir=dir_path, delete=False, suffix='.tmp') as tmp_file:
        json.dump(data, tmp_file, indent=2)
        tmp_name = tmp_file.name
    
    # Atomic rename
    os.replace(tmp_name, filepath)


def _load_users_data() -> Dict[str, Any]:
    """
    Load users data from JSON file.
    
    Returns:
        Dictionary containing users data
    """
    # Check for migration first
    _migrate_from_txt_to_json()
    
    if os.path.exists(JSON_FILE):
        try:
            with open(JSON_FILE, 'r') as f:
                data = json.load(f)
            logger.info(f"Loaded users data from {JSON_FILE}")
            return data
        except Exception as e:
            logger.error(f"Error loading JSON file: {str(e)}")
            # Return empty structure on error
            return {"users": {}, "metadata": {"version": "1.0"}}
    else:
        logger.info(f"JSON file not found, creating new: {JSON_FILE}")
        return {"users": {}, "metadata": {"version": "1.0"}}


def _load_user_ids_from_disk() -> Set[int]:
    """
    Load user IDs directly from JSON storage (bypasses cache).

    This is used internally by the cache system.

    Returns:
        Set of user IDs
    """
    try:
        data = _load_users_data()
        user_ids = {user_data['user_id'] for user_data in data.get('users', {}).values()}
        logger.debug(f"Loaded {len(user_ids)} user IDs from disk")
        return user_ids
    except Exception as e:
        logger.error(f"Error loading user IDs from disk: {str(e)}")
        return set()


def load_user_ids() -> Set[int]:
    """
    Load user IDs using the cache (recommended).

    This function uses an in-memory cache with 60-second TTL to minimize
    disk I/O. Most requests will be served from cache.

    Returns:
        Set of user IDs
    """
    return _user_cache.get_users()


def is_user_registered(user_id: int) -> bool:
    """
    Check if a user is registered (optimized, uses cache).

    This is faster than `user_id in load_user_ids()` because it
    uses the cache's direct lookup method.

    Args:
        user_id: The Telegram user ID to check

    Returns:
        bool: True if registered, False otherwise
    """
    return _user_cache.is_registered(user_id)


def save_user_id(user_id: int) -> bool:
    """
    Save a new user ID to the JSON storage and update cache.

    Args:
        user_id: The Telegram user ID to save

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        data = _load_users_data()

        # Check if user already exists
        if str(user_id) in data['users']:
            logger.info(f"User ID {user_id} already registered")
            return True

        # Add new user with metadata
        data['users'][str(user_id)] = {
            "user_id": user_id,
            "registered_at": datetime.now().isoformat(),
            "migrated": False
        }

        # Write atomically
        _atomic_write_json(JSON_FILE, data)

        # Update cache immediately (avoid waiting for TTL expiration)
        _user_cache.add_user(user_id)

        logger.info(f"Saved new user ID: {user_id}")
        return True
    except Exception as e:
        logger.error(f"Error saving user ID {user_id}: {str(e)}")
        return False


def get_user_count() -> int:
    """
    Get the total number of registered users.
    
    Returns:
        int: Number of registered users
    """
    return len(load_user_ids())


def register_user(user_id: int) -> str:
    """
    Register a user and return the registration status.

    Args:
        user_id: The Telegram user ID to register

    Returns:
        str: Registration status - 'new', 'existing', or 'error'
    """
    try:
        data = _load_users_data()

        # Check if user already exists
        if str(user_id) in data['users']:
            logger.info(f"User ID {user_id} already registered")
            return 'existing'

        # Add new user with metadata
        data['users'][str(user_id)] = {
            "user_id": user_id,
            "registered_at": datetime.now().isoformat(),
            "migrated": False
        }

        # Write atomically
        _atomic_write_json(JSON_FILE, data)

        # Update cache immediately (avoid waiting for TTL expiration)
        _user_cache.add_user(user_id)

        logger.info(f"Registered new user ID: {user_id}")
        return 'new'
    except Exception as e:
        logger.error(f"Error registering user ID {user_id}: {str(e)}")
        return 'error'
