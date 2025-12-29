"""User management functionality."""
import os
from typing import Set
from config import Config
from logger import setup_logger

logger = setup_logger()


def load_user_ids() -> Set[int]:
    """
    Load user IDs from the storage file.
    
    Returns:
        Set of user IDs
    """
    if os.path.exists(Config.USER_IDS_FILE):
        try:
            with open(Config.USER_IDS_FILE, 'r') as f:
                user_ids = {int(line.strip()) for line in f.readlines() if line.strip()}
            logger.info(f"Loaded {len(user_ids)} user IDs from {Config.USER_IDS_FILE}")
            return user_ids
        except Exception as e:
            logger.error(f"Error loading user IDs: {str(e)}")
            return set()
    else:
        logger.info(f"User IDs file not found: {Config.USER_IDS_FILE}")
        return set()


def save_user_id(user_id: int) -> bool:
    """
    Save a new user ID to the storage file.
    
    Args:
        user_id: The Telegram user ID to save
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Load existing users to avoid duplicates
        existing_users = load_user_ids()
        
        if user_id in existing_users:
            logger.info(f"User ID {user_id} already registered")
            return True
        
        # Append new user ID
        with open(Config.USER_IDS_FILE, 'a') as f:
            f.write(f"{user_id}\n")
        
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
