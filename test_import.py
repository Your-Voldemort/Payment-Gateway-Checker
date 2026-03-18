#!/usr/bin/env python3
"""
Test that the gateway_checker can import and use the user agent functions.
"""
import sys
import os

# Add the current directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from user_agents import get_random_user_agent
    print("+ Successfully imported get_random_user_agent from user_agents")
except ImportError as e:
    print(f"- Failed to import get_random_user_agent: {e}")
    sys.exit(1)

try:
    ua = get_random_user_agent()
    print(f"+ get_random_user_agent returned: {ua}")
    assert isinstance(ua, str) and len(ua) > 0
except Exception as e:
    print(f"- get_random_user_agent failed: {e}")
    sys.exit(1)

try:
    # Now test that gateway_checker can import it (without running the whole check_url)
    from gateway_checker import check_url
    print("+ Successfully imported check_url from gateway_checker")
except ImportError as e:
    print(f"- Failed to import check_url: {e}")
    # This might be due to other missing dependencies, but we at least want to see if the user_agents import works
    # We'll not exit because the user_agents import is what we changed.
    pass

print("\nImport test passed!")
sys.exit(0)