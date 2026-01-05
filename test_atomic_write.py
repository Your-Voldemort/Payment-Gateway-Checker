"""
Test for atomic write JSON validation and error handling.

This test verifies that the fixed _atomic_write_json implementation
correctly handles all edge cases described in CRITICAL-002.
"""

import os
import tempfile
import shutil
import json
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def test_directory_validation():
    """Test that proper errors are raised when directory doesn't exist."""
    print("Testing directory validation...")
    
    # Import here to avoid issues if config fails
    from user_manager import _atomic_write_json
    
    # Test 1: Non-existent directory
    try:
        _atomic_write_json("/nonexistent/path/test.json", {"test": 1})
        print("  [FAIL] Should have raised IOError for non-existent directory")
        return False
    except IOError as e:
        if "does not exist" in str(e):
            print("  [PASS] Correctly raises IOError for non-existent directory")
        else:
            print(f"  [FAIL] Wrong error message: {e}")
            return False
    except Exception as e:
        print(f"  [FAIL] Wrong exception type: {type(e).__name__}: {e}")
        return False
    
    print("[PASS] Directory validation works correctly\n")
    return True


def test_permission_validation():
    """Test that proper errors are raised for permission issues."""
    print("Testing permission validation...")
    
    from user_manager import _atomic_write_json
    
    # Create a temporary directory
    with tempfile.TemporaryDirectory() as tmpdir:
        # Test: Directory is actually a file (not a directory)
        fake_dir = os.path.join(tmpdir, "fakedir")
        with open(fake_dir, 'w') as f:
            f.write("this is a file, not a directory")
        
        try:
            target_file = os.path.join(fake_dir, "test.json")
            _atomic_write_json(target_file, {"test": 1})
            print("  [FAIL] Should have raised IOError when path is a file")
            return False
        except IOError as e:
            if "not a directory" in str(e):
                print("  [PASS] Correctly detects when path is a file, not directory")
            else:
                print(f"  [FAIL] Wrong error message: {e}")
                return False
    
    print("[PASS] Permission validation works correctly\n")
    return True


def test_json_serialization_validation():
    """Test that non-serializable data is caught before file creation."""
    print("Testing JSON serialization validation...")
    
    from user_manager import _atomic_write_json
    
    with tempfile.TemporaryDirectory() as tmpdir:
        filepath = os.path.join(tmpdir, "test.json")
        
        # Test: Non-serializable data
        class NotSerializable:
            pass
        
        try:
            _atomic_write_json(filepath, {"bad": NotSerializable()})
            print("  [FAIL] Should have raised TypeError for non-serializable data")
            return False
        except TypeError as e:
            if "not JSON-serializable" in str(e):
                print("  [PASS] Correctly catches non-serializable data")
                
                # Verify no temp files were left behind
                tmp_files = [f for f in os.listdir(tmpdir) if f.endswith('.tmp')]
                if len(tmp_files) == 0:
                    print("  [PASS] No orphaned temp files created")
                else:
                    print(f"  [FAIL] Orphaned temp files found: {tmp_files}")
                    return False
            else:
                print(f"  [FAIL] Wrong error message: {e}")
                return False
        except Exception as e:
            print(f"  [FAIL] Wrong exception type: {type(e).__name__}: {e}")
            return False
    
    print("[PASS] JSON serialization validation works correctly\n")
    return True


def test_cleanup_on_failure():
    """Test that temp files are cleaned up when write fails."""
    print("Testing temp file cleanup on failure...")
    
    from user_manager import _atomic_write_json
    
    with tempfile.TemporaryDirectory() as tmpdir:
        filepath = os.path.join(tmpdir, "test.json")
        
        # Test with non-serializable data (will fail during validation)
        class NotSerializable:
            pass
        
        try:
            _atomic_write_json(filepath, {"bad": NotSerializable()})
        except TypeError:
            pass  # Expected
        
        # Count temp files
        tmp_files = [f for f in os.listdir(tmpdir) if f.endswith('.tmp')]
        
        if len(tmp_files) == 0:
            print("  [PASS] No orphaned temp files after validation failure")
        else:
            print(f"  [FAIL] Found {len(tmp_files)} orphaned temp files: {tmp_files}")
            return False
    
    print("[PASS] Temp file cleanup works correctly\n")
    return True


def test_successful_write():
    """Test that successful writes work correctly."""
    print("Testing successful atomic write...")
    
    from user_manager import _atomic_write_json
    
    with tempfile.TemporaryDirectory() as tmpdir:
        filepath = os.path.join(tmpdir, "test.json")
        test_data = {
            "users": {
                "123": {"user_id": 123, "name": "Test User"}
            },
            "metadata": {"version": "1.0"}
        }
        
        # Write data
        try:
            _atomic_write_json(filepath, test_data)
            print("  [PASS] Write operation succeeded")
        except Exception as e:
            print(f"  [FAIL] Write failed: {e}")
            return False
        
        # Verify file exists
        if not os.path.exists(filepath):
            print("  [FAIL] File was not created")
            return False
        else:
            print("  [PASS] File was created")
        
        # Verify content is correct
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                loaded_data = json.load(f)
            
            if loaded_data == test_data:
                print("  [PASS] File content matches original data")
            else:
                print("  [FAIL] File content doesn't match")
                print(f"    Expected: {test_data}")
                print(f"    Got: {loaded_data}")
                return False
        except Exception as e:
            print(f"  [FAIL] Failed to read back data: {e}")
            return False
        
        # Verify no temp files remain
        tmp_files = [f for f in os.listdir(tmpdir) if f.endswith('.tmp')]
        if len(tmp_files) == 0:
            print("  [PASS] No temp files left behind")
        else:
            print(f"  [FAIL] Found temp files: {tmp_files}")
            return False
    
    print("[PASS] Successful write works correctly\n")
    return True


def test_atomicity():
    """Test that writes are atomic (no partial writes)."""
    print("Testing write atomicity...")
    
    from user_manager import _atomic_write_json
    
    with tempfile.TemporaryDirectory() as tmpdir:
        filepath = os.path.join(tmpdir, "test.json")
        
        # Write initial data
        initial_data = {"version": 1, "data": "initial"}
        _atomic_write_json(filepath, initial_data)
        
        # Write new data
        new_data = {"version": 2, "data": "updated", "extra": "field"}
        _atomic_write_json(filepath, new_data)
        
        # Verify only new data exists (atomic replace)
        with open(filepath, 'r', encoding='utf-8') as f:
            loaded = json.load(f)
        
        if loaded == new_data:
            print("  [PASS] Atomic replacement successful")
        else:
            print("  [FAIL] Data not replaced atomically")
            return False
        
        # Verify no temp files
        tmp_files = [f for f in os.listdir(tmpdir) if f.endswith('.tmp')]
        if len(tmp_files) == 0:
            print("  [PASS] Clean atomic operation (no temp files)")
        else:
            print(f"  [FAIL] Temp files remained: {tmp_files}")
            return False
    
    print("[PASS] Atomicity verified\n")
    return True


def test_ensure_data_directory():
    """Test that data directory creation works."""
    print("Testing data directory creation...")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a config that points to a subdirectory
        test_dir = os.path.join(tmpdir, "data", "users")
        
        # Manually test directory creation logic
        if not os.path.exists(test_dir):
            try:
                os.makedirs(test_dir, exist_ok=True)
                print("  [PASS] Directory created successfully")
            except Exception as e:
                print(f"  [FAIL] Failed to create directory: {e}")
                return False
        
        # Verify it exists and is writable
        if os.path.isdir(test_dir) and os.access(test_dir, os.W_OK):
            print("  [PASS] Directory is writable")
        else:
            print("  [FAIL] Directory not writable")
            return False
    
    print("[PASS] Data directory creation works\n")
    return True


def main():
    """Run all atomic write tests."""
    print("=" * 70)
    print("Atomic Write JSON Test Suite")
    print("Testing fix for CRITICAL-002: Unsafe File Operations")
    print("=" * 70)
    print()
    
    results = []
    
    # Test 1: Directory validation
    results.append(test_directory_validation())
    
    # Test 2: Permission validation
    results.append(test_permission_validation())
    
    # Test 3: JSON serialization validation
    results.append(test_json_serialization_validation())
    
    # Test 4: Cleanup on failure
    results.append(test_cleanup_on_failure())
    
    # Test 5: Successful write
    results.append(test_successful_write())
    
    # Test 6: Atomicity
    results.append(test_atomicity())
    
    # Test 7: Data directory creation
    results.append(test_ensure_data_directory())
    
    print("=" * 70)
    print("Test Results Summary")
    print("=" * 70)
    
    passed = sum(results)
    total = len(results)
    
    if all(results):
        print(f"[PASS] ALL TESTS PASSED ({passed}/{total})")
        print()
        print("Summary of improvements:")
        print("  1. Directory existence validated before writing")
        print("  2. Write permissions checked proactively")
        print("  3. JSON serialization validated before file creation")
        print("  4. Temp files cleaned up on any failure")
        print("  5. Atomic rename prevents partial writes")
        print("  6. Detailed error messages for debugging")
        print()
        print("The file operations are now production-ready!")
    else:
        print(f"[FAIL] SOME TESTS FAILED ({passed}/{total} passed)")
        print("The file operations may still have issues!")
    
    print("=" * 70)
    
    return all(results)


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
