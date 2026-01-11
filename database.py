"""SQLite database management for Gateway Checker Bot."""
import sqlite3
import asyncio
import aiosqlite
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
from logger import setup_logger

logger = setup_logger()

# Database file path
DB_FILE = "gateway_checker.db"

# Schema version for migrations
SCHEMA_VERSION = 1


class Database:
    """Async SQLite database manager with connection pooling."""
    
    def __init__(self, db_path: str = DB_FILE):
        self.db_path = db_path
        self._initialized = False
    
    async def initialize(self):
        """Initialize database schema."""
        if self._initialized:
            return
        
        async with aiosqlite.connect(self.db_path) as db:
            # Enable foreign keys
            await db.execute("PRAGMA foreign_keys = ON")
            
            # Users table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    registered_at TEXT NOT NULL,
                    subscription_expiry TEXT,
                    is_active BOOLEAN DEFAULT 1,
                    migrated BOOLEAN DEFAULT 0
                )
            """)
            
            # Scan history table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS scan_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    url TEXT NOT NULL,
                    scanned_at TEXT NOT NULL,
                    status_code INTEGER,
                    gateways_detected TEXT,
                    security_type TEXT,
                    cvv_status TEXT,
                    cloudflare BOOLEAN,
                    captcha BOOLEAN,
                    inbuilt_payment BOOLEAN,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            """)
            
            # Rate limiter persistence table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS rate_limits (
                    user_id INTEGER PRIMARY KEY,
                    request_timestamps TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            
            # Gateway statistics table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS gateway_stats (
                    gateway_name TEXT PRIMARY KEY,
                    detection_count INTEGER DEFAULT 0,
                    last_detected TEXT,
                    first_detected TEXT
                )
            """)
            
            # Audit log table for admin actions
            await db.execute("""
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    admin_user_id INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    target_user_id INTEGER,
                    details TEXT,
                    timestamp TEXT NOT NULL
                )
            """)
            
            # Scan cache table for result caching
            await db.execute("""
                CREATE TABLE IF NOT EXISTS scan_cache (
                    url_hash TEXT PRIMARY KEY,
                    url TEXT NOT NULL,
                    result_data TEXT NOT NULL,
                    cached_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                )
            """)
            
            # Indexes for performance
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_scan_history_user 
                ON scan_history(user_id, scanned_at DESC)
            """)
            
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_scan_history_url 
                ON scan_history(url, scanned_at DESC)
            """)
            
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_users_subscription 
                ON users(subscription_expiry)
            """)
            
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_log_timestamp
                ON audit_log(timestamp DESC)
            """)
            
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_log_admin
                ON audit_log(admin_user_id, timestamp DESC)
            """)
            
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_scan_cache_expires
                ON scan_cache(expires_at)
            """)
            
            # Schema version tracking
            await db.execute("""
                CREATE TABLE IF NOT EXISTS schema_info (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            
            await db.execute("""
                INSERT OR IGNORE INTO schema_info (key, value) 
                VALUES ('version', ?)
            """, (str(SCHEMA_VERSION),))
            
            await db.commit()
            logger.info(f"Database initialized: {self.db_path}")
        
        self._initialized = True
    
    @asynccontextmanager
    async def get_connection(self):
        """Get database connection (context manager)."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA foreign_keys = ON")
            yield db


# Global database instance
_db_instance: Optional[Database] = None


async def get_database() -> Database:
    """Get or create the global database instance."""
    global _db_instance
    if _db_instance is None:
        _db_instance = Database()
        await _db_instance.initialize()
    return _db_instance


# ============================================================================
# USER MANAGEMENT FUNCTIONS
# ============================================================================

async def register_user_db(user_id: int, username: Optional[str] = None, 
                           first_name: Optional[str] = None) -> str:
    """
    Register a user in the database.
    
    Returns:
        'new', 'existing', or 'error'
    """
    db = await get_database()
    
    try:
        async with db.get_connection() as conn:
            # Check if user exists
            cursor = await conn.execute(
                "SELECT user_id FROM users WHERE user_id = ?",
                (user_id,)
            )
            existing = await cursor.fetchone()
            
            if existing:
                return 'existing'
            
            # Insert new user
            await conn.execute("""
                INSERT INTO users (user_id, username, first_name, registered_at)
                VALUES (?, ?, ?, ?)
            """, (user_id, username, first_name, datetime.now().isoformat()))
            
            await conn.commit()
            logger.info(f"User {user_id} registered in database")
            return 'new'
            
    except Exception as e:
        logger.error(f"Error registering user {user_id}: {e}")
        return 'error'


async def is_user_registered_db(user_id: int) -> bool:
    """Check if user is registered."""
    db = await get_database()
    
    try:
        async with db.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT 1 FROM users WHERE user_id = ? AND is_active = 1",
                (user_id,)
            )
            result = await cursor.fetchone()
            return result is not None
    except Exception as e:
        logger.error(f"Error checking user registration: {e}")
        return False


async def get_user_count_db() -> int:
    """Get total number of registered users."""
    db = await get_database()
    
    try:
        async with db.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT COUNT(*) FROM users WHERE is_active = 1"
            )
            result = await cursor.fetchone()
            return result[0] if result else 0
    except Exception as e:
        logger.error(f"Error getting user count: {e}")
        return 0


async def get_all_user_ids_db() -> List[int]:
    """Get all registered user IDs for broadcast functionality."""
    db = await get_database()
    
    try:
        async with db.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT user_id FROM users WHERE is_active = 1"
            )
            rows = await cursor.fetchall()
            return [row[0] for row in rows]
    except Exception as e:
        logger.error(f"Error getting all user IDs: {e}")
        return []


async def add_subscription_db(user_id: int, duration_str: str) -> Optional[str]:
    """
    Add subscription time to user.
    
    Returns:
        New expiry datetime string or None
    """
    db = await get_database()
    
    try:
        async with db.get_connection() as conn:
            # Get current subscription
            cursor = await conn.execute(
                "SELECT subscription_expiry FROM users WHERE user_id = ?",
                (user_id,)
            )
            row = await cursor.fetchone()
            
            if not row:
                # Auto-register user
                await register_user_db(user_id)
                current_expiry = datetime.now()
            else:
                expiry_str = row[0]
                if expiry_str:
                    try:
                        current_expiry = datetime.fromisoformat(expiry_str)
                        if current_expiry < datetime.now():
                            current_expiry = datetime.now()
                    except ValueError:
                        current_expiry = datetime.now()
                else:
                    current_expiry = datetime.now()
            
            # Parse duration
            duration_str = duration_str.lower()
            if duration_str.endswith('d'):
                delta = timedelta(days=int(duration_str[:-1]))
            elif duration_str.endswith('m'):
                delta = timedelta(days=int(duration_str[:-1]) * 30)
            elif duration_str.endswith('y'):
                delta = timedelta(days=int(duration_str[:-1]) * 365)
            else:
                if duration_str.isdigit():
                    delta = timedelta(days=int(duration_str))
                else:
                    logger.error(f"Invalid duration format: {duration_str}")
                    return None
            
            new_expiry = current_expiry + delta
            
            # Update database
            await conn.execute("""
                UPDATE users 
                SET subscription_expiry = ? 
                WHERE user_id = ?
            """, (new_expiry.isoformat(), user_id))
            
            await conn.commit()
            return new_expiry.strftime("%Y-%m-%d %H:%M:%S")
            
    except Exception as e:
        logger.error(f"Error adding subscription for {user_id}: {e}")
        return None


async def check_subscription_db(user_id: int, owner_id: int) -> bool:
    """Check if user has active subscription."""
    if user_id == owner_id:
        return True
    
    db = await get_database()
    
    try:
        async with db.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT subscription_expiry FROM users WHERE user_id = ?",
                (user_id,)
            )
            row = await cursor.fetchone()
            
            if not row or not row[0]:
                return False
            
            expiry = datetime.fromisoformat(row[0])
            return expiry > datetime.now()
            
    except Exception as e:
        logger.error(f"Error checking subscription: {e}")
        return False


async def get_subscription_expiry_db(user_id: int) -> Optional[datetime]:
    """Get user subscription expiry."""
    db = await get_database()
    
    try:
        async with db.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT subscription_expiry FROM users WHERE user_id = ?",
                (user_id,)
            )
            row = await cursor.fetchone()
            
            if row and row[0]:
                return datetime.fromisoformat(row[0])
            return None
            
    except Exception as e:
        logger.error(f"Error getting subscription expiry: {e}")
        return None


# ============================================================================
# SCAN HISTORY FUNCTIONS
# ============================================================================

async def save_scan_result(
    user_id: int,
    url: str,
    status_code: int,
    gateways: List[str],
    security_type: str,
    cvv_status: str,
    cloudflare: bool,
    captcha: bool,
    inbuilt_payment: bool
) -> bool:
    """Save scan result to history."""
    db = await get_database()
    
    try:
        async with db.get_connection() as conn:
            import json
            
            await conn.execute("""
                INSERT INTO scan_history (
                    user_id, url, scanned_at, status_code,
                    gateways_detected, security_type, cvv_status,
                    cloudflare, captcha, inbuilt_payment
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                user_id, url, datetime.now().isoformat(), status_code,
                json.dumps(gateways), security_type, cvv_status,
                cloudflare, captcha, inbuilt_payment
            ))
            
            # Update gateway statistics
            for gateway in gateways:
                await conn.execute("""
                    INSERT INTO gateway_stats (gateway_name, detection_count, first_detected, last_detected)
                    VALUES (?, 1, ?, ?)
                    ON CONFLICT(gateway_name) DO UPDATE SET
                        detection_count = detection_count + 1,
                        last_detected = ?
                """, (gateway, datetime.now().isoformat(), datetime.now().isoformat(),
                      datetime.now().isoformat()))
            
            await conn.commit()
            return True
            
    except Exception as e:
        logger.error(f"Error saving scan result: {e}")
        return False


async def get_user_scan_history(user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
    """Get user's recent scan history."""
    db = await get_database()
    
    try:
        async with db.get_connection() as conn:
            import json
            
            cursor = await conn.execute("""
                SELECT url, scanned_at, status_code, gateways_detected,
                       security_type, cvv_status, cloudflare, captcha
                FROM scan_history
                WHERE user_id = ?
                ORDER BY scanned_at DESC
                LIMIT ?
            """, (user_id, limit))
            
            rows = await cursor.fetchall()
            
            results = []
            for row in rows:
                results.append({
                    'url': row[0],
                    'scanned_at': row[1],
                    'status_code': row[2],
                    'gateways': json.loads(row[3]),
                    'security_type': row[4],
                    'cvv_status': row[5],
                    'cloudflare': bool(row[6]),
                    'captcha': bool(row[7])
                })
            
            return results
            
    except Exception as e:
        logger.error(f"Error getting scan history: {e}")
        return []


async def get_gateway_statistics(gateway_name: str = None) -> Dict[str, Any]:
    """Get detection statistics for gateways."""
    db = await get_database()
    
    try:
        async with db.get_connection() as conn:
            if gateway_name:
                cursor = await conn.execute("""
                    SELECT gateway_name, detection_count, first_detected, last_detected
                    FROM gateway_stats
                    WHERE gateway_name = ?
                """, (gateway_name,))
            else:
                cursor = await conn.execute("""
                    SELECT gateway_name, detection_count, first_detected, last_detected
                    FROM gateway_stats
                    ORDER BY detection_count DESC
                    LIMIT 20
                """)
            
            rows = await cursor.fetchall()
            
            if gateway_name:
                if rows:
                    row = rows[0]
                    return {
                        'gateway': row[0],
                        'count': row[1],
                        'first_seen': row[2],
                        'last_seen': row[3]
                    }
                return {}
            else:
                return {
                    row[0]: {
                        'count': row[1],
                        'first_seen': row[2],
                        'last_seen': row[3]
                    }
                    for row in rows
                }
                
    except Exception as e:
        logger.error(f"Error getting gateway statistics: {e}")
        return {}


# ============================================================================
# RATE LIMITER PERSISTENCE
# ============================================================================

async def save_rate_limit_state(user_id: int, timestamps: List[float]) -> bool:
    """Save rate limit state to database."""
    db = await get_database()
    
    try:
        async with db.get_connection() as conn:
            import json
            
            await conn.execute("""
                INSERT INTO rate_limits (user_id, request_timestamps, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    request_timestamps = ?,
                    updated_at = ?
            """, (
                user_id, json.dumps(timestamps), datetime.now().isoformat(),
                json.dumps(timestamps), datetime.now().isoformat()
            ))
            
            await conn.commit()
            return True
            
    except Exception as e:
        logger.error(f"Error saving rate limit state: {e}")
        return False


async def load_rate_limit_state(user_id: int) -> List[float]:
    """Load rate limit state from database."""
    db = await get_database()
    
    try:
        async with db.get_connection() as conn:
            import json
            
            cursor = await conn.execute(
                "SELECT request_timestamps FROM rate_limits WHERE user_id = ?",
                (user_id,)
            )
            row = await cursor.fetchone()
            
            if row and row[0]:
                return json.loads(row[0])
            return []
            
    except Exception as e:
        logger.error(f"Error loading rate limit state: {e}")
        return []


# ============================================================================
# MIGRATION FUNCTION
# ============================================================================

async def migrate_from_json(json_file: str = "user_ids.json"):
    """Migrate existing JSON data to SQLite."""
    import json
    import os
    
    if not os.path.exists(json_file):
        logger.info("No JSON file to migrate")
        return
    
    db = await get_database()
    
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        users_data = data.get('users', {})
        migrated_count = 0
        
        async with db.get_connection() as conn:
            for user_id_str, user_info in users_data.items():
                user_id = int(user_id_str)
                
                # Check if already migrated
                cursor = await conn.execute(
                    "SELECT user_id FROM users WHERE user_id = ?",
                    (user_id,)
                )
                if await cursor.fetchone():
                    continue
                
                await conn.execute("""
                    INSERT INTO users (
                        user_id, registered_at, subscription_expiry, migrated
                    ) VALUES (?, ?, ?, 1)
                """, (
                    user_id,
                    user_info.get('registered_at', datetime.now().isoformat()),
                    user_info.get('subscription_expiry')
                ))
                
                migrated_count += 1
            
            await conn.commit()
        
        logger.info(f"Migrated {migrated_count} users from JSON to SQLite")
        
        # Backup old file
        backup_file = f"{json_file}.migrated.backup"
        os.rename(json_file, backup_file)
        logger.info(f"Original JSON backed up to {backup_file}")
        
    except Exception as e:
        logger.error(f"Error during migration: {e}")
