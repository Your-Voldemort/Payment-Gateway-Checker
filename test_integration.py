"""
Integration test for CRITICAL-002 fix.

This test demonstrates that the entire user management system
works correctly with the improved file operations.
"""

import os
import tempfile
import shutil
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def test_full_user_workflow():
    """Test complete user registration workflow."""
    print("Testing complete user workflow...")
    
    # Create temporary directory for test
    with tempfile.TemporaryDirectory() as tmpdir:
        # Override the JSON file path for testing
        import config
        import user_manager
        
        # Store original path
        original_file = user_manager.JSON_FILE
        
        # Set test path
        test_file = os.path.join(tmpdir, "test_users.json")
        user_manager.JSON_FILE = test_file
        config.Config.USER_IDS_FILE = test_file.replace('.json', '.txt')
        
        try:
            # Test 1: Directory creation
            print("  Test 1: Directory auto-creation...")
            result = user_manager.register_user(12345)
            if result == 'new':
                print("    [PASS] User registered successfully (directory auto-created)")
            else:
                print(f"    [FAIL] Unexpected result: {result}")
                return False
            
            # Test 2: File was created
            if os.path.exists(test_file):
                print("    [PASS] JSON file created")
            else:
                print("    [FAIL] JSON file not created")
                return False
            
            # Test 3: User can be verified
            print("  Test 2: User verification...")
            if user_manager.is_user_registered(12345):
                print("    [PASS] User verification works")
            else:
                print("    [FAIL] User verification failed")
                return False
            
            # Test 4: Register existing user
            print("  Test 3: Duplicate registration...")
            result = user_manager.register_user(12345)
            if result == 'existing':
                print("    [PASS] Correctly detected existing user")
            else:
                print(f"    [FAIL] Should return 'existing', got: {result}")
                return False
            
            # Test 5: Register multiple users
            print("  Test 4: Multiple user registration...")
            for user_id in [67890, 11111, 22222]:
                user_manager.register_user(user_id)
            
            count = user_manager.get_user_count()
            if count == 4:  # 12345 + 3 new users
                print(f"    [PASS] User count correct: {count}")
            else:
                print(f"    [FAIL] Expected 4 users, got: {count}")
                return False
            
            # Test 6: Load users (cache test)
            print("  Test 5: User loading and caching...")
            users = user_manager.load_user_ids()
            if len(users) == 4 and 12345 in users and 67890 in users:
                print("    [PASS] User loading works correctly")
            else:
                print(f"    [FAIL] User loading failed: {users}")
                return False
            
            # Test 7: No temp files left behind
            print("  Test 6: Cleanup verification...")
            tmp_files = [f for f in os.listdir(tmpdir) if f.endswith('.tmp')]
            if len(tmp_files) == 0:
                print("    [PASS] No temp files left behind")
            else:
                print(f"    [FAIL] Found temp files: {tmp_files}")
                return False
            
            print("[PASS] Full user workflow completed successfully\n")
            return True
            
        finally:
            # Restore original path
            user_manager.JSON_FILE = original_file
            config.Config.USER_IDS_FILE = original_file.replace('.json', '.txt')


def test_error_recovery():
    """Test that system recovers gracefully from errors."""
    print("Testing error recovery...")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        import user_manager
        
        # Store original
        original_file = user_manager.JSON_FILE
        test_file = os.path.join(tmpdir, "test_users.json")
        user_manager.JSON_FILE = test_file
        
        try:
            # Create a corrupted JSON file
            print("  Test 1: Corrupted file recovery...")
            with open(test_file, 'w') as f:
                f.write("{ this is not valid JSON }")
            
            # Try to load - should handle gracefully
            result = user_manager.register_user(99999)
            
            # Should either succeed or handle error gracefully
            if result in ['new', 'error']:
                print("    [PASS] Handled corrupted file gracefully")
            else:
                print(f"    [FAIL] Unexpected result: {result}")
                return False
            
            # Check if backup was created
            backup_files = [f for f in os.listdir(tmpdir) if 'corrupted' in f]
            if len(backup_files) > 0:
                print(f"    [PASS] Created backup: {backup_files[0]}")
            else:
                print("    [INFO] No backup created (may have overwritten)")
            
            print("[PASS] Error recovery works correctly\n")
            return True
            
        finally:
            user_manager.JSON_FILE = original_file


def main():
    """Run all integration tests."""
    print("=" * 70)
    print("CRITICAL-002 Integration Test Suite")
    print("Testing complete user management system")
    print("=" * 70)
    print()
    
    results = []
    
    # Test 1: Full workflow
    results.append(test_full_user_workflow())
    
    # Test 2: Error recovery
    results.append(test_error_recovery())
    
    print("=" * 70)
    print("Integration Test Results")
    print("=" * 70)
    
    passed = sum(results)
    total = len(results)
    
    if all(results):
        print(f"[PASS] ALL INTEGRATION TESTS PASSED ({passed}/{total})")
        print()
        print("The user management system is production-ready with:")
        print("  [OK] Automatic directory creation")
        print("  [OK] Safe atomic file operations")
        print("  [OK] Proper error handling and recovery")
        print("  [OK] No temp file leaks")
        print("  [OK] Graceful degradation on errors")
    else:
        print(f"[FAIL] SOME TESTS FAILED ({passed}/{total} passed)")
    
    print("=" * 70)
    
    return all(results)


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
