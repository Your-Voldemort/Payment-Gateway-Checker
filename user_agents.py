"""User agent pool using fake-useragent for realistic, up-to-date user agents."""
import random

_FALLBACK_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Safari/605.1.15",
]

try:
    from fake_useragent import UserAgent
    _ua = UserAgent()
    _ua_desktop = UserAgent(platforms=['desktop'])
    _ua_mobile = UserAgent(platforms=['mobile'])
    _fake_ua_available = True
except Exception:
    _fake_ua_available = False


def get_random_user_agent() -> str:
    """Get a random user agent string."""
    if _fake_ua_available:
        return _ua.random
    return random.choice(_FALLBACK_USER_AGENTS)


def get_desktop_user_agent() -> str:
    """Get a random desktop user agent string."""
    if _fake_ua_available:
        return _ua_desktop.random
    return random.choice(_FALLBACK_USER_AGENTS)


def get_mobile_user_agent() -> str:
    """Get a random mobile user agent string."""
    if _fake_ua_available:
        return _ua_mobile.random
    return random.choice(_FALLBACK_USER_AGENTS)
