"""User management functionality with caching and SQLite backend."""
import os
import json
import tempfile
import time
from typing import Set, Dict, Any, Optional, List
from datetime import datetime, timedelta
from config import Config
from logger import setup_logger

logger = setup_logger()

# Flag to determine if database backend is available
_USE_DATABASE = False
register_user_db = None
is_user_registered_db = None
get_user_count_db = None
get_all_user_ids_db = None
add_subscription_db = None
check_subscription_db = None
get_subscription_expiry_db = None
migrate_json_to_db = None

try:
    from database import (
        register_user_db,
        is_user_registered_db,
        get_user_count_db,
        get_all_user_ids_db,
        add_subscription_db,
        check_subscription_db,
        get_subscription_expiry_db,
        migrate_from_json as migrate_json_to_db
    )
    _USE_DATABASE = True
    logger.info("Database backend available - will use SQLite for user management")
except ImportError as e:
    logger.warning(f"Database backend not available, using JSON file storage: {e}")
    _USE_DATABASE = False

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


def _ensure_data_directory() -> None:
    """
    Ensure the data directory exists and is writable.
    
    Creates the directory if it doesn't exist.
    
    Raises:
        IOError: If directory cannot be created or is not writable
    """
    dir_path = os.path.dirname(JSON_FILE) or '.'
    
    # Create directory if it doesn't exist
    if not os.path.exists(dir_path):
        try:
            os.makedirs(dir_path, exist_ok=True)
            logger.info(f"Created data directory: {dir_path}")
        except OSError as e:
            raise IOError(f"Failed to create data directory {dir_path}: {str(e)}")
    
    # Verify it's a directory
    if not os.path.isdir(dir_path):
        raise IOError(f"Path exists but is not a directory: {dir_path}")
    
    # Check write permissions
    if not os.access(dir_path, os.W_OK):
        raise IOError(f"No write permission for directory: {dir_path}")
    
    logger.debug(f"Data directory verified: {dir_path}")


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
    Write JSON data atomically using temporary file with proper validation.

    This function ensures:
    1. Target directory exists and is writable
    2. Data is valid JSON before writing
    3. Temporary files are cleaned up on failure
    4. Atomic rename prevents partial writes

    Args:
        filepath: Target file path for the JSON data
        data: Dictionary to serialize as JSON

    Raises:
        IOError: If directory doesn't exist, permissions denied, or write fails
        TypeError: If data is not JSON-serializable
    """
    dir_path = os.path.dirname(filepath) or '.'
    tmp_name = None

    # === VALIDATION PHASE ===

    # Check directory exists
    if not os.path.exists(dir_path):
        raise IOError(
            f"Directory does not exist: {dir_path}\n"
            f"Please create the directory or check the file path: {filepath}"
        )

    # Check directory is actually a directory (not a file)
    if not os.path.isdir(dir_path):
        raise IOError(
            f"Path exists but is not a directory: {dir_path}\n"
            f"Cannot write to: {filepath}"
        )

    # Check write permissions
    if not os.access(dir_path, os.W_OK):
        raise IOError(
            f"No write permission for directory: {dir_path}\n"
            f"Please check file permissions for: {filepath}"
        )

    # Pre-validate JSON serialization (fail fast before creating temp file)
    try:
        json_str = json.dumps(data, indent=2)
    except (TypeError, ValueError) as e:
        raise TypeError(f"Data is not JSON-serializable: {str(e)}")

    # === WRITE PHASE ===

    try:
        # Write to temporary file first
        with tempfile.NamedTemporaryFile(
            mode='w',
            dir=dir_path,
            delete=False,
            suffix='.tmp',
            encoding='utf-8'
        ) as tmp_file:
            tmp_file.write(json_str)
            tmp_name = tmp_file.name

        # Atomic rename (POSIX guarantees atomicity; Windows since Vista)
        os.replace(tmp_name, filepath)
        tmp_name = None  # Clear so finally block doesn't try to delete

        logger.debug(f"Atomically wrote {len(json_str)} bytes to {filepath}")

    except OSError as e:
        raise IOError(f"Failed to write JSON file {filepath}: {str(e)}")

    finally:
        # === CLEANUP PHASE ===
        # Remove temp file if it still exists (write succeeded but rename failed,
        # or an exception occurred after temp file creation)
        if tmp_name and os.path.exists(tmp_name):
            try:
                os.remove(tmp_name)
                logger.warning(f"Cleaned up orphaned temp file: {tmp_name}")
            except OSError as cleanup_error:
                # Log but don't raise - we don't want cleanup failure to mask original error
                logger.error(f"Failed to cleanup temp file {tmp_name}: {cleanup_error}")


def _load_users_data() -> Dict[str, Any]:
    """
    Load users data from JSON file.
    
    Returns:
        Dictionary containing users data
    """
    # Ensure data directory exists and is writable
    _ensure_data_directory()
    
    # Check for migration first
    _migrate_from_txt_to_json()
    
    if os.path.exists(JSON_FILE):
        try:
            with open(JSON_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            logger.info(f"Loaded users data from {JSON_FILE}")
            return data
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in {JSON_FILE}: {str(e)}")
            # Backup corrupted file
            backup_file = f"{JSON_FILE}.corrupted.{int(time.time())}"
            try:
                os.rename(JSON_FILE, backup_file)
                logger.warning(f"Moved corrupted file to {backup_file}")
            except OSError:
                pass
            # Return empty structure
            return {"users": {}, "metadata": {"version": "1.0"}}
        except Exception as e:
            logger.error(f"Error loading JSON file: {str(e)}")
            # Return empty structure on error
            return {"users": {}, "metadata": {"version": "1.0"}}
    else:
        logger.info(f"JSON file not found, creating new: {JSON_FILE}")
        # Create initial file
        initial_data = {"users": {}, "metadata": {"version": "1.0"}}
        try:
            _atomic_write_json(JSON_FILE, initial_data)
        except Exception as e:
            logger.error(f"Failed to create initial JSON file: {str(e)}")
        return initial_data


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
            "migrated": False,
            "subscription_expiry": None
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
            "migrated": False,
            "subscription_expiry": None
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


def get_subscription_expiry(user_id: int) -> Optional[datetime]:
    """
    Get the subscription expiry datetime for a user.

    Args:
        user_id: The Telegram user ID

    Returns:
        datetime object if active/future expiry, None if expired or no subscription
    """
    try:
        # Load fresh data to ensure we have latest status
        data = _load_users_data()
        user_data = data['users'].get(str(user_id))

        if not user_data:
            return None

        expiry_str = user_data.get('subscription_expiry')
        if not expiry_str:
            return None

        expiry = datetime.fromisoformat(expiry_str)
        return expiry
    except Exception as e:
        logger.error(f"Error getting subscription for {user_id}: {str(e)}")
        return None


def check_subscription(user_id: int) -> bool:
    """
    Check if a user has an active subscription.

    Args:
        user_id: The Telegram user ID

    Returns:
        bool: True if subscription is active or user is owner
    """
    # Owner always has access
    if user_id == Config.OWNER_USER_ID:
        return True

    expiry = get_subscription_expiry(user_id)
    if not expiry:
        return False

    return expiry > datetime.now()


def add_subscription(user_id: int, duration_str: str) -> Optional[str]:
    """
    Add subscription time to a user.

    Args:
        user_id: The Telegram user ID
        duration_str: Duration string (e.g. "1d", "1m", "1y")

    Returns:
        str: New expiry date string if successful, None otherwise
    """
    try:
        data = _load_users_data()
        str_id = str(user_id)

        # Ensure user exists
        if str_id not in data['users']:
            # Auto-register if not exists
            register_user(user_id)
            # Reload data
            data = _load_users_data()

        current_expiry = None
        user_data = data['users'][str_id]

        if user_data.get('subscription_expiry'):
            try:
                current_expiry = datetime.fromisoformat(user_data['subscription_expiry'])
                # If expired, start from now. If active, extend.
                if current_expiry < datetime.now():
                    current_expiry = datetime.now()
            except ValueError:
                current_expiry = datetime.now()
        else:
            current_expiry = datetime.now()

        # Parse duration
        duration_str = duration_str.lower()
        delta = None

        if duration_str.endswith('d'):
            days = int(duration_str[:-1])
            delta = timedelta(days=days)
        elif duration_str.endswith('m'):
            # Approximation: 30 days per month
            months = int(duration_str[:-1])
            delta = timedelta(days=months * 30)
        elif duration_str.endswith('y'):
            years = int(duration_str[:-1])
            delta = timedelta(days=years * 365)
        else:
            # Fallback/Default
            if duration_str.isdigit():
                 delta = timedelta(days=int(duration_str))
            else:
                 logger.error(f"Invalid duration format: {duration_str}")
                 return None

        new_expiry = current_expiry + delta

        # Update user data
        data['users'][str_id]['subscription_expiry'] = new_expiry.isoformat()

        # Write to disk
        _atomic_write_json(JSON_FILE, data)

        return new_expiry.strftime("%Y-%m-%d %H:%M:%S")

    except Exception as e:
        logger.error(f"Error adding subscription for {user_id}: {str(e)}")
        return None


# =============================================================================
# ASYNC DATABASE WRAPPER FUNCTIONS
# =============================================================================
# These functions provide async interface to the database backend.
# They fall back to synchronous JSON storage if database is not available.
# =============================================================================

async def async_register_user(user_id: int, username: Optional[str] = None, first_name: Optional[str] = None) -> str:
    """
    Async register a user (uses database if available).
    
    Args:
        user_id: The Telegram user ID to register
        username: Optional username
        first_name: Optional first name
    
    Returns:
        str: Registration status - 'new', 'existing', or 'error'
    """
    if _USE_DATABASE and register_user_db:
        try:
            return await register_user_db(user_id, username, first_name)
        except Exception as e:
            logger.error(f"Database error in async_register_user, falling back to JSON: {e}")
            return register_user(user_id)
    else:
        # Fallback to sync JSON storage
        return register_user(user_id)


async def async_is_user_registered(user_id: int) -> bool:
    """
    Async check if user is registered (uses database if available).
    
    Args:
        user_id: The Telegram user ID to check
    
    Returns:
        bool: True if registered, False otherwise
    """
    if _USE_DATABASE and is_user_registered_db:
        try:
            return await is_user_registered_db(user_id)
        except Exception as e:
            logger.error(f"Database error in async_is_user_registered, falling back to JSON: {e}")
            return is_user_registered(user_id)
    else:
        # Fallback to sync JSON storage
        return is_user_registered(user_id)


async def async_get_user_count() -> int:
    """
    Async get total number of registered users (uses database if available).
    
    Returns:
        int: Number of registered users
    """
    if _USE_DATABASE and get_user_count_db:
        try:
            return await get_user_count_db()
        except Exception as e:
            logger.error(f"Database error in async_get_user_count, falling back to JSON: {e}")
            return get_user_count()
    else:
        # Fallback to sync JSON storage
        return get_user_count()


async def async_add_subscription(user_id: int, duration_str: str) -> Optional[str]:
    """
    Async add subscription to user (uses database if available).
    
    Args:
        user_id: The Telegram user ID
        duration_str: Duration string (e.g. "1d", "1m", "1y")
    
    Returns:
        str: New expiry date string if successful, None otherwise
    """
    if _USE_DATABASE and add_subscription_db:
        try:
            return await add_subscription_db(user_id, duration_str)
        except Exception as e:
            logger.error(f"Database error in async_add_subscription, falling back to JSON: {e}")
            return add_subscription(user_id, duration_str)
    else:
        # Fallback to sync JSON storage
        return add_subscription(user_id, duration_str)


async def async_check_subscription(user_id: int) -> bool:
    """
    Async check if user has active subscription (uses database if available).
    
    Args:
        user_id: The Telegram user ID
    
    Returns:
        bool: True if subscription is active or user is owner
    """
    if _USE_DATABASE and check_subscription_db:
        try:
            return await check_subscription_db(user_id, Config.OWNER_USER_ID)
        except Exception as e:
            logger.error(f"Database error in async_check_subscription, falling back to JSON: {e}")
            return check_subscription(user_id)
    else:
        # Fallback to sync JSON storage
        return check_subscription(user_id)


async def async_get_subscription_expiry(user_id: int) -> Optional[datetime]:
    """
    Async get user subscription expiry (uses database if available).
    
    Args:
        user_id: The Telegram user ID
    
    Returns:
        datetime object if active/future expiry, None if expired or no subscription
    """
    if _USE_DATABASE and get_subscription_expiry_db:
        try:
            return await get_subscription_expiry_db(user_id)
        except Exception as e:
            logger.error(f"Database error in async_get_subscription_expiry, falling back to JSON: {e}")
            return get_subscription_expiry(user_id)
    else:
        # Fallback to sync JSON storage
        return get_subscription_expiry(user_id)


async def async_get_all_user_ids() -> List[int]:
    """
    Async get all registered user IDs (uses database if available).
    
    Returns:
        List of registered user IDs
    """
    if _USE_DATABASE and get_all_user_ids_db:
        try:
            return await get_all_user_ids_db()
        except Exception as e:
            logger.error(f"Database error in async_get_all_user_ids, falling back to JSON: {e}")
            return list(load_user_ids())
    else:
        # Fallback to sync JSON storage
        return list(load_user_ids())


async def async_migrate_to_database():
    """
    Migrate existing JSON data to SQLite database.
    
    This should be called once during bot startup.
    """
    if _USE_DATABASE and migrate_json_to_db:
        try:
            logger.info("Migrating user data from JSON to SQLite database...")
            await migrate_json_to_db(JSON_FILE)
        except Exception as e:
            logger.error(f"Error during migration: {e}")
    else:
        logger.warning("Database backend not available, skipping migration")
