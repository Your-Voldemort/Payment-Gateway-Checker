"""User management functionality."""
import os
import json
import tempfile
from typing import Set, Dict, Any
from datetime import datetime
from config import Config
from logger import setup_logger

logger = setup_logger()

# JSON file path (same directory as old txt file)
JSON_FILE = Config.USER_IDS_FILE.replace('.txt', '.json')


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


def load_user_ids() -> Set[int]:
    """
    Load user IDs from the JSON storage.
    
    Returns:
        Set of user IDs
    """
    try:
        data = _load_users_data()
        user_ids = {user_data['user_id'] for user_data in data.get('users', {}).values()}
        logger.info(f"Loaded {len(user_ids)} user IDs")
        return user_ids
    except Exception as e:
        logger.error(f"Error loading user IDs: {str(e)}")
        return set()


def save_user_id(user_id: int) -> bool:
    """
    Save a new user ID to the JSON storage.
    
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
