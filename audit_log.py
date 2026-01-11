"""Audit logging for administrative actions."""
from datetime import datetime
from typing import Optional, List, Dict, Any
from logger import setup_logger

logger = setup_logger()


async def log_admin_action(
    admin_user_id: int,
    action: str,
    target_user_id: Optional[int] = None,
    details: str = ""
):
    """
    Log administrative action to database.
    
    Args:
        admin_user_id: ID of admin performing action
        action: Action type (broadcast, addsub, etc.)
        target_user_id: Optional target user ID
        details: Additional details
    """
    try:
        # Import here to avoid circular dependency
        from database import get_database
        
        db = await get_database()
        
        async with db.get_connection() as conn:
            # Create audit log table if not exists
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    admin_user_id INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    target_user_id INTEGER,
                    details TEXT,
                    timestamp TEXT NOT NULL
                )
            """)
            
            # Create index for performance
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_log_timestamp
                ON audit_log(timestamp DESC)
            """)
            
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_log_admin
                ON audit_log(admin_user_id, timestamp DESC)
            """)
            
            # Insert audit log entry
            await conn.execute("""
                INSERT INTO audit_log (
                    admin_user_id, action, target_user_id, details, timestamp
                ) VALUES (?, ?, ?, ?, ?)
            """, (
                admin_user_id, action, target_user_id, details,
                datetime.now().isoformat()
            ))
            
            await conn.commit()
            
            logger.info(
                f"Audit log: User {admin_user_id} performed '{action}' "
                f"on user {target_user_id}: {details}"
            )
            
    except Exception as e:
        logger.error(f"Failed to write audit log: {e}")


async def get_audit_logs(
    limit: int = 50,
    admin_user_id: Optional[int] = None,
    action: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Get audit logs with optional filtering.
    
    Args:
        limit: Maximum number of logs to return
        admin_user_id: Filter by specific admin user
        action: Filter by specific action type
    
    Returns:
        List of audit log entries
    """
    try:
        from database import get_database
        
        db = await get_database()
        
        async with db.get_connection() as conn:
            # Build query based on filters
            query = """
                SELECT id, admin_user_id, action, target_user_id, details, timestamp
                FROM audit_log
                WHERE 1=1
            """
            params = []
            
            if admin_user_id is not None:
                query += " AND admin_user_id = ?"
                params.append(admin_user_id)
            
            if action is not None:
                query += " AND action = ?"
                params.append(action)
            
            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)
            
            cursor = await conn.execute(query, params)
            rows = await cursor.fetchall()
            
            return [
                {
                    'id': row[0],
                    'admin_id': row[1],
                    'action': row[2],
                    'target_id': row[3],
                    'details': row[4],
                    'timestamp': row[5]
                }
                for row in rows
            ]
            
    except Exception as e:
        logger.error(f"Failed to retrieve audit logs: {e}")
        return []


async def get_audit_log_stats() -> Dict[str, Any]:
    """
    Get statistics about audit log entries.
    
    Returns:
        Dictionary containing audit log statistics
    """
    try:
        from database import get_database
        
        db = await get_database()
        
        async with db.get_connection() as conn:
            # Total entries
            cursor = await conn.execute("SELECT COUNT(*) FROM audit_log")
            total = (await cursor.fetchone())[0]
            
            # Actions by type
            cursor = await conn.execute("""
                SELECT action, COUNT(*) as count
                FROM audit_log
                GROUP BY action
                ORDER BY count DESC
            """)
            action_counts = {row[0]: row[1] for row in await cursor.fetchall()}
            
            # Recent activity (last 24 hours)
            from datetime import timedelta
            yesterday = (datetime.now() - timedelta(days=1)).isoformat()
            cursor = await conn.execute("""
                SELECT COUNT(*) FROM audit_log
                WHERE timestamp > ?
            """, (yesterday,))
            recent_count = (await cursor.fetchone())[0]
            
            # Most active admin
            cursor = await conn.execute("""
                SELECT admin_user_id, COUNT(*) as count
                FROM audit_log
                GROUP BY admin_user_id
                ORDER BY count DESC
                LIMIT 1
            """)
            most_active = await cursor.fetchone()
            
            return {
                'total_entries': total,
                'actions_by_type': action_counts,
                'last_24h': recent_count,
                'most_active_admin': {
                    'user_id': most_active[0] if most_active else None,
                    'action_count': most_active[1] if most_active else 0
                }
            }
            
    except Exception as e:
        logger.error(f"Failed to get audit log stats: {e}")
        return {
            'total_entries': 0,
            'actions_by_type': {},
            'last_24h': 0,
            'most_active_admin': {'user_id': None, 'action_count': 0}
        }


async def clear_old_audit_logs(days: int = 90) -> int:
    """
    Clear audit logs older than specified days.
    
    Args:
        days: Number of days to keep logs
    
    Returns:
        Number of deleted entries
    """
    try:
        from database import get_database
        from datetime import timedelta
        
        db = await get_database()
        cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
        
        async with db.get_connection() as conn:
            cursor = await conn.execute("""
                DELETE FROM audit_log
                WHERE timestamp < ?
            """, (cutoff_date,))
            
            deleted = cursor.rowcount
            await conn.commit()
            
            if deleted > 0:
                logger.info(f"Cleared {deleted} old audit log entries (older than {days} days)")
            
            return deleted
            
    except Exception as e:
        logger.error(f"Failed to clear old audit logs: {e}")
        return 0
