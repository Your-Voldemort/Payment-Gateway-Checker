"""Cache manager for scan results with database persistence."""
import hashlib
import json
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from logger import setup_logger

logger = setup_logger()

# Cache TTL in seconds (1 hour)
CACHE_TTL = 3600


def get_url_hash(url: str) -> str:
    """
    Get SHA256 hash of URL for cache key.
    
    Args:
        url: The URL to hash
        
    Returns:
        Hexadecimal hash string
    """
    return hashlib.sha256(url.encode('utf-8')).hexdigest()


async def get_cached_result(url: str) -> Optional[Dict[str, Any]]:
    """
    Get cached scan result for URL if available and not expired.
    
    Args:
        url: The URL to check cache for
        
    Returns:
        Cached result dictionary or None if not found/expired
        
    Result dictionary format:
        {
            'gateways': List[str],
            'status_code': int,
            'captcha': bool,
            'cloudflare': bool,
            'security_type': str,
            'cvv_status': str,
            'inbuilt_status': str
        }
    """
    try:
        from database import get_database
        
        db = await get_database()
        
        async with db.get_connection() as conn:
            # Ensure cache table exists
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS scan_cache (
                    url_hash TEXT PRIMARY KEY,
                    url TEXT NOT NULL,
                    result_data TEXT NOT NULL,
                    cached_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                )
            """)
            
            # Create index on expires_at for efficient cleanup
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_scan_cache_expires 
                ON scan_cache(expires_at)
            """)
            
            url_hash = get_url_hash(url)
            now = datetime.now().isoformat()
            
            cursor = await conn.execute("""
                SELECT result_data, expires_at
                FROM scan_cache
                WHERE url_hash = ? AND expires_at > ?
            """, (url_hash, now))
            
            row = await cursor.fetchone()
            
            if row:
                result_data = json.loads(row[0])
                expires_at = row[1]
                logger.info(f"Cache hit for URL: {url[:50]}... (expires: {expires_at})")
                return result_data
            
            logger.debug(f"Cache miss for URL: {url[:50]}...")
            return None
            
    except ImportError:
        logger.warning("Database module not available, caching disabled")
        return None
    except Exception as e:
        logger.error(f"Error reading cache for {url[:50]}...: {e}")
        return None


async def save_to_cache(url: str, result: Dict[str, Any]) -> bool:
    """
    Save scan result to cache with TTL.
    
    Args:
        url: The URL being cached
        result: The scan result dictionary to cache
        
    Returns:
        True if successfully cached, False otherwise
    """
    try:
        from database import get_database
        
        db = await get_database()
        
        async with db.get_connection() as conn:
            url_hash = get_url_hash(url)
            now = datetime.now()
            expires = now + timedelta(seconds=CACHE_TTL)
            
            # Insert or replace existing cache entry
            await conn.execute("""
                INSERT OR REPLACE INTO scan_cache (
                    url_hash, url, result_data, cached_at, expires_at
                ) VALUES (?, ?, ?, ?, ?)
            """, (
                url_hash,
                url,
                json.dumps(result),
                now.isoformat(),
                expires.isoformat()
            ))
            
            await conn.commit()
            logger.debug(f"Cached result for URL: {url[:50]}... (TTL: {CACHE_TTL}s)")
            return True
            
    except ImportError:
        logger.warning("Database module not available, caching disabled")
        return False
    except Exception as e:
        logger.error(f"Error saving to cache for {url[:50]}...: {e}")
        return False


async def clear_expired_cache() -> int:
    """
    Remove expired cache entries from database.
    
    Returns:
        Number of entries deleted
    """
    try:
        from database import get_database
        
        db = await get_database()
        
        async with db.get_connection() as conn:
            now = datetime.now().isoformat()
            
            cursor = await conn.execute("""
                DELETE FROM scan_cache
                WHERE expires_at < ?
            """, (now,))
            
            deleted = cursor.rowcount
            await conn.commit()
            
            if deleted > 0:
                logger.info(f"Cleared {deleted} expired cache entries")
            else:
                logger.debug("No expired cache entries to clear")
                
            return deleted
                
    except ImportError:
        logger.warning("Database module not available, cannot clear cache")
        return 0
    except Exception as e:
        logger.error(f"Error clearing expired cache: {e}")
        return 0


async def get_cache_stats() -> Dict[str, Any]:
    """
    Get cache statistics.
    
    Returns:
        Dictionary with cache statistics:
        {
            'total_entries': int,
            'expired_entries': int,
            'active_entries': int,
            'oldest_entry': str (ISO datetime),
            'newest_entry': str (ISO datetime)
        }
    """
    try:
        from database import get_database
        
        db = await get_database()
        
        async with db.get_connection() as conn:
            now = datetime.now().isoformat()
            
            # Total entries
            cursor = await conn.execute("SELECT COUNT(*) FROM scan_cache")
            row = await cursor.fetchone()
            total_entries = row[0] if row else 0
            
            # Expired entries
            cursor = await conn.execute(
                "SELECT COUNT(*) FROM scan_cache WHERE expires_at < ?",
                (now,)
            )
            row = await cursor.fetchone()
            expired_entries = row[0] if row else 0
            
            # Active entries
            active_entries = total_entries - expired_entries
            
            # Oldest and newest
            cursor = await conn.execute("""
                SELECT MIN(cached_at), MAX(cached_at) 
                FROM scan_cache 
                WHERE expires_at > ?
            """, (now,))
            row = await cursor.fetchone()
            oldest_entry = row[0] if row and row[0] else "N/A"
            newest_entry = row[1] if row and row[1] else "N/A"
            
            return {
                'total_entries': total_entries,
                'expired_entries': expired_entries,
                'active_entries': active_entries,
                'oldest_entry': oldest_entry,
                'newest_entry': newest_entry
            }
            
    except ImportError:
        logger.warning("Database module not available, cannot get cache stats")
        return {
            'total_entries': 0,
            'expired_entries': 0,
            'active_entries': 0,
            'oldest_entry': 'N/A',
            'newest_entry': 'N/A'
        }
    except Exception as e:
        logger.error(f"Error getting cache stats: {e}")
        return {
            'total_entries': 0,
            'expired_entries': 0,
            'active_entries': 0,
            'oldest_entry': 'N/A',
            'newest_entry': 'N/A',
            'error': str(e)
        }


async def clear_all_cache() -> int:
    """
    Clear all cache entries (not just expired).
    
    Returns:
        Number of entries deleted
    """
    try:
        from database import get_database
        
        db = await get_database()
        
        async with db.get_connection() as conn:
            cursor = await conn.execute("DELETE FROM scan_cache")
            deleted = cursor.rowcount
            await conn.commit()
            
            logger.info(f"Cleared all cache: {deleted} entries deleted")
            return deleted
                
    except ImportError:
        logger.warning("Database module not available, cannot clear cache")
        return 0
    except Exception as e:
        logger.error(f"Error clearing all cache: {e}")
        return 0
