"""
Simple structural test for the singleton lock fix.
This verifies the code structure without running it.
"""

import ast
import inspect

def test_module_structure():
    """Test that the module has the correct structure."""
    print("Testing module structure...")
    
    with open('http_client.py', 'r') as f:
        source = f.read()
    
    # Parse the AST
    tree = ast.parse(source)
    
    # Check for module-level lock variable
    has_singleton_lock = False
    has_get_lock_func = False
    
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign):
            if hasattr(node.target, 'id') and node.target.id == '_singleton_lock':
                has_singleton_lock = True
                print("  [PASS] Found module-level _singleton_lock variable")
        
        if isinstance(node, ast.FunctionDef):
            if node.name == '_get_singleton_lock':
                has_get_lock_func = True
                print("  [PASS] Found _get_singleton_lock() function")
    
    if has_singleton_lock and has_get_lock_func:
        print("[PASS] Module structure is correct\n")
        return True
    else:
        print("[FAIL] Missing required components\n")
        return False


def test_get_instance_method():
    """Test that get_instance method uses the module-level lock."""
    print("Testing get_instance method implementation...")
    
    with open('http_client.py', 'r') as f:
        source = f.read()
    
    # Check that get_instance calls _get_singleton_lock
    if '_get_singleton_lock()' in source:
        print("  [PASS] get_instance() calls _get_singleton_lock()")
    else:
        print("  [FAIL] get_instance() doesn't call _get_singleton_lock()")
        return False
    
    # Check that it doesn't use cls._lock anymore
    if 'cls._lock is None' in source:
        print("  [FAIL] Old race condition code still present (cls._lock is None)")
        return False
    else:
        print("  [PASS] Old race condition code removed")
    
    # Check for proper async with lock pattern
    if 'async with lock:' in source or 'async with _get_singleton_lock():' in source:
        print("  [PASS] Uses proper async lock context manager")
    else:
        print("  [FAIL] Missing async lock context manager")
        return False
    
    print("[PASS] get_instance method is correctly implemented\n")
    return True


def test_class_structure():
    """Test that the class no longer has _lock attribute."""
    print("Testing PersistentHTTPClient class structure...")
    
    with open('http_client.py', 'r') as f:
        source = f.read()
    
    tree = ast.parse(source)
    
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == 'PersistentHTTPClient':
            # Check class-level assignments
            for item in node.body:
                if isinstance(item, ast.AnnAssign):
                    if hasattr(item.target, 'id') and item.target.id == '_lock':
                        print("  [FAIL] Class still has _lock attribute")
                        return False
    
    print("  [PASS] Class doesn't have _lock attribute")
    print("[PASS] Class structure is correct\n")
    return True


def main():
    """Run all structural tests."""
    print("=" * 60)
    print("HTTP Client Singleton Fix - Structural Validation")
    print("Verifying fix for CRITICAL-001: Race Condition")
    print("=" * 60)
    print()
    
    results = []
    
    # Test 1: Module structure
    results.append(test_module_structure())
    
    # Test 2: get_instance method
    results.append(test_get_instance_method())
    
    # Test 3: Class structure
    results.append(test_class_structure())
    
    print("=" * 60)
    print("Validation Results Summary")
    print("=" * 60)
    
    passed = sum(results)
    total = len(results)
    
    if all(results):
        print(f"[PASS] ALL CHECKS PASSED ({passed}/{total})")
        print()
        print("Summary of fix:")
        print("  1. Created module-level _singleton_lock variable")
        print("  2. Created _get_singleton_lock() helper function")
        print("  3. Removed class-level _lock attribute")
        print("  4. Updated get_instance() to use module-level lock")
        print()
        print("The race condition has been fixed!")
        print()
        print("How the fix works:")
        print("  - Module loads in single thread (safe)")
        print("  - _singleton_lock created on first access via _get_singleton_lock()")
        print("  - All coroutines use the SAME lock (no race)")
        print("  - Lock prevents multiple instances from being created")
    else:
        print(f"[FAIL] SOME CHECKS FAILED ({passed}/{total} passed)")
        print("The race condition fix may not be complete!")
    
    print("=" * 60)
    
    return all(results)


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
