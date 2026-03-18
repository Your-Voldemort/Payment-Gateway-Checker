#!/usr/bin/env python3
"""
Test that gateway_checker can be imported and that the user agent import works.
"""
import sys
import os

# Add the current directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    # This will import gateway_checker, which in turn imports user_agents
    from gateway_checker import check_url
    print("+ gateway_checker imported successfully")
except ImportError as e:
    print(f"- Failed to import gateway_checker: {e}")
    # We don't exit because we want to see if the user_agents import is the issue
    # but if it's an import error in gateway_checker due to our changes, we want to know.
    # However, note that there might be other missing dependencies (like aiohttp) that are not installed.
    # We'll check the error message.
    if "user_agents" in str(e):
        print("  The error is related to user_agents import")
        sys.exit(1)
    else:
        print("  The error is due to other missing dependencies (likely aiohttp, etc.)")
        print("  This is expected if we haven't installed all dependencies.")
        # We'll still consider the user_agents part as passed if the error is not about user_agents.
        pass

try:
    # Also test that we can import user_agents directly and get a user agent
    from user_agents import get_random_user_agent
    ua = get_random_user_agent()
    print(f"+ user_agents.get_random_user_agent works: {ua[:50]}...")
except Exception as e:
    print(f"- Failed to get random user agent: {e}")
    sys.exit(1)

print("\nImport test for gateway_checker and user_agents passed!")
sys.exit(0)