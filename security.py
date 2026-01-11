"""Security utilities for input validation and sanitization."""
import re
from typing import List, Tuple
from urllib.parse import urlparse, urlunparse
from logger import setup_logger

logger = setup_logger()

# Dangerous URL schemes
BLOCKED_SCHEMES = ['javascript', 'data', 'vbscript', 'file']

# Suspicious URL patterns
SUSPICIOUS_PATTERNS = [
    r'<script',
    r'javascript:',
    r'onerror=',
    r'onload=',
    r'eval\(',
    r'\.\./',  # Path traversal
]


def sanitize_url(url: str) -> Tuple[str, bool]:
    """
    Sanitize and validate URL input.
    
    Args:
        url: Raw URL string from user
    
    Returns:
        Tuple of (sanitized_url, is_safe)
    """
    # Remove whitespace and control characters
    url = url.strip()
    url = ''.join(char for char in url if ord(char) >= 32)
    
    # Check for suspicious patterns
    url_lower = url.lower()
    for pattern in SUSPICIOUS_PATTERNS:
        if re.search(pattern, url_lower):
            logger.warning(f"Suspicious URL pattern detected: {pattern}")
            return url, False
    
    # Parse URL
    try:
        parsed = urlparse(url)
        
        # Block dangerous schemes
        if parsed.scheme.lower() in BLOCKED_SCHEMES:
            logger.warning(f"Blocked URL scheme: {parsed.scheme}")
            return url, False
        
        # Reconstruct URL (this normalizes it)
        sanitized = urlunparse(parsed)
        
        return sanitized, True
        
    except Exception as e:
        logger.error(f"Error parsing URL: {e}")
        return url, False


def sanitize_text_input(text: str, max_length: int = 1000) -> str:
    """
    Sanitize text input from users.
    
    Args:
        text: Raw text from user
        max_length: Maximum allowed length
    
    Returns:
        Sanitized text
    """
    # Remove null bytes
    text = text.replace('\x00', '')
    
    # Limit length
    if len(text) > max_length:
        text = text[:max_length]
        logger.warning(f"Text input truncated to {max_length} chars")
    
    return text


def validate_duration(duration_str: str) -> bool:
    """
    Validate subscription duration format.
    
    Args:
        duration_str: Duration like "1d", "3m", "1y"
    
    Returns:
        True if valid format
    """
    pattern = r'^\d+[dmy]$'
    return bool(re.match(pattern, duration_str.lower()))
