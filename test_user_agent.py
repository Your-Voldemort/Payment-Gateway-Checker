#!/usr/bin/env python3
"""
Test script to verify the user agent functions work correctly with fake-useragent.
"""
import sys
import os

# Add the current directory to the path so we can import user_agents
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from user_agents import get_random_user_agent, get_desktop_user_agent, get_mobile_user_agent

def test_user_agent_functions():
    """Test that the user agent functions return valid strings."""
    print("Testing user agent functions...")
    
    # Test random user agent
    try:
        ua_random = get_random_user_agent()
        print("Random UA: %s" % ua_random)
        assert isinstance(ua_random, str) and len(ua_random) > 0
        print("+ get_random_user_agent works")
    except Exception as e:
        print("- get_random_user_agent failed: %s" % e)
        return False
    
    # Test desktop user agent
    try:
        ua_desktop = get_desktop_user_agent()
        print("Desktop UA: %s" % ua_desktop)
        assert isinstance(ua_desktop, str) and len(ua_desktop) > 0
        print("+ get_desktop_user_agent works")
    except Exception as e:
        print("- get_desktop_user_agent failed: %s" % e)
        return False
        
    # Test mobile user agent
    try:
        ua_mobile = get_mobile_user_agent()
        print("Mobile UA: %s" % ua_mobile)
        assert isinstance(ua_mobile, str) and len(ua_mobile) > 0
        print("+ get_mobile_user_agent works")
    except Exception as e:
        print("- get_mobile_user_agent failed: %s" % e)
        return False
        
    # Test that we get different values on multiple calls (basic randomness check)
    uas = [get_random_user_agent() for _ in range(5)]
    if len(set(uas)) > 1:
        print("+ Random user agents show variation")
    else:
        print("? Warning: Random user agents did not vary in 5 calls (might be coincidental)")
        
    print("\nAll tests passed!")
    return True

if __name__ == "__main__":
    success = test_user_agent_functions()
    sys.exit(0 if success else 1)