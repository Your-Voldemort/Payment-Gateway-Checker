"""
Test for HTTP client singleton thread-safety.

This test verifies that the fixed singleton implementation correctly
returns the same instance under concurrent access, preventing the
race condition described in CRITICAL-001.
"""

import asyncio
from http_client import get_http_client


async def test_singleton_thread_safety():
    """
    Verify singleton returns the same instance under concurrent access.
    
    This test launches 100 concurrent requests for the singleton instance
    and verifies that all calls return the exact same object, confirming
    that the race condition has been fixed.
    """
    print("Testing singleton thread-safety with 100 concurrent requests...")
    
    # Launch 100 concurrent requests for the singleton
    tasks = [get_http_client() for _ in range(100)]
    clients = await asyncio.gather(*tasks)
    
    # All should be the same instance
    first_client = clients[0]
    first_client_id = id(first_client)
    
    failures = 0
    for i, client in enumerate(clients[1:], 1):
        if client is not first_client:
            failures += 1
            print(f"❌ FAIL: Client {i} is a different instance! "
                  f"(id={id(client)} vs {first_client_id})")
    
    if failures == 0:
        print(f"✅ PASS: All {len(clients)} clients are the same instance (id={first_client_id})")
        print(f"✅ Singleton implementation is thread-safe!")
        return True
    else:
        print(f"❌ FAILED: {failures} out of {len(clients)} clients were different instances")
        print(f"❌ Race condition still exists!")
        return False


async def test_singleton_session_consistency():
    """
    Verify that the session object is consistent across multiple calls.
    """
    print("\nTesting session consistency...")
    
    client1 = await get_http_client()
    session1 = client1.session
    
    client2 = await get_http_client()
    session2 = client2.session
    
    if session1 is session2:
        print(f"✅ PASS: Sessions are identical (id={id(session1)})")
        return True
    else:
        print(f"❌ FAIL: Sessions are different! "
              f"(session1_id={id(session1)} vs session2_id={id(session2)})")
        return False


async def test_concurrent_initialization():
    """
    Test that concurrent calls during initialization don't create multiple instances.
    
    This is the most critical test - it simulates the exact race condition
    that was fixed.
    """
    print("\nTesting concurrent initialization (race condition scenario)...")
    
    # Create tasks that will all try to initialize at the same time
    # This simulates the race condition where multiple coroutines
    # check for the instance before any has initialized it
    tasks = [get_http_client() for _ in range(50)]
    
    # Execute all at once
    clients = await asyncio.gather(*tasks)
    
    # Verify all are the same
    unique_clients = set(id(c) for c in clients)
    
    if len(unique_clients) == 1:
        print(f"✅ PASS: Only one instance created despite {len(clients)} concurrent calls")
        print(f"✅ Race condition successfully prevented!")
        return True
    else:
        print(f"❌ FAIL: {len(unique_clients)} different instances created!")
        print(f"❌ Race condition NOT fixed!")
        return False


async def main():
    """Run all singleton tests."""
    print("=" * 60)
    print("HTTP Client Singleton Test Suite")
    print("Testing fix for CRITICAL-001: Race Condition")
    print("=" * 60)
    
    results = []
    
    # Test 1: Thread safety
    results.append(await test_singleton_thread_safety())
    
    # Test 2: Session consistency
    results.append(await test_singleton_session_consistency())
    
    # Test 3: Concurrent initialization (race condition)
    results.append(await test_concurrent_initialization())
    
    print("\n" + "=" * 60)
    print("Test Results Summary")
    print("=" * 60)
    
    passed = sum(results)
    total = len(results)
    
    if all(results):
        print(f"✅ ALL TESTS PASSED ({passed}/{total})")
        print("✅ Race condition fix is working correctly!")
    else:
        print(f"❌ SOME TESTS FAILED ({passed}/{total} passed)")
        print("❌ Race condition may still exist!")
    
    print("=" * 60)
    
    # Cleanup
    from http_client import close_http_client
    await close_http_client()
    
    return all(results)


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
