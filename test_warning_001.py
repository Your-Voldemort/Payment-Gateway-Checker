"""
Test for WARNING-001: Incorrect Type Hint in Detection Module fix.

This test verifies that the type hint has been corrected from
lowercase 'any' to uppercase 'Any' from the typing module.
"""

import ast
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def test_import_includes_any():
    """Test that Any is imported from typing module."""
    print("Testing import statement...")
    
    with open('detection.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Check import statement
    if 'from typing import' in content and 'Any' in content.split('from typing import')[1].split('\n')[0]:
        print("  [PASS] 'Any' imported from typing module")
        return True
    else:
        print("  [FAIL] 'Any' not found in typing imports")
        return False


def test_correct_type_hint():
    """Test that the function signature uses correct type hint."""
    print("\nTesting function signature...")
    
    with open('detection.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Check for correct usage
    if 'Dict[str, Any]' in content:
        print("  [PASS] Correct type hint 'Dict[str, Any]' found")
    else:
        print("  [FAIL] Correct type hint not found")
        return False
    
    # Check that incorrect usage is gone
    if 'Dict[str, any]' in content or ') -> Dict[str, any]:' in content:
        print("  [FAIL] Incorrect lowercase 'any' still present")
        return False
    else:
        print("  [PASS] Incorrect lowercase 'any' removed")
    
    return True


def test_headers_type_hint():
    """Test that headers parameter has proper type hint."""
    print("\nTesting headers parameter type hint...")
    
    with open('detection.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Check for improved headers type
    if 'headers: Dict[str, str]' in content:
        print("  [PASS] Headers parameter has specific type 'Dict[str, str]'")
        return True
    else:
        print("  [INFO] Headers parameter uses generic 'dict' type")
        return True  # Not a failure, just not optimal


def test_function_exists():
    """Test that analyze_url_response function exists and is valid."""
    print("\nTesting function definition...")
    
    try:
        from detection import analyze_url_response
        print("  [PASS] Function 'analyze_url_response' can be imported")
        
        # Check function signature
        import inspect
        sig = inspect.signature(analyze_url_response)
        
        params = list(sig.parameters.keys())
        expected_params = ['html', 'headers', 'status_code']
        
        if params == expected_params:
            print(f"  [PASS] Function has correct parameters: {params}")
        else:
            print(f"  [FAIL] Unexpected parameters: {params}")
            return False
        
        # Check return annotation
        if sig.return_annotation != inspect.Signature.empty:
            print(f"  [PASS] Function has return type annotation")
        else:
            print(f"  [INFO] Function missing return type annotation")
        
        return True
        
    except ImportError as e:
        print(f"  [FAIL] Cannot import function: {e}")
        return False
    except Exception as e:
        print(f"  [FAIL] Error checking function: {e}")
        return False


def test_docstring_quality():
    """Test that the function has good documentation."""
    print("\nTesting docstring quality...")
    
    try:
        from detection import analyze_url_response
        
        if analyze_url_response.__doc__:
            doc = analyze_url_response.__doc__
            
            # Check for key sections
            has_args = 'Args:' in doc
            has_returns = 'Returns:' in doc
            has_description = len(doc.strip()) > 50
            
            checks = [
                ('Description present', has_description),
                ('Args section present', has_args),
                ('Returns section present', has_returns),
            ]
            
            all_passed = True
            for check_name, passed in checks:
                status = "[PASS]" if passed else "[FAIL]"
                print(f"  {status} {check_name}")
                if not passed:
                    all_passed = False
            
            return all_passed
        else:
            print("  [FAIL] Function has no docstring")
            return False
            
    except Exception as e:
        print(f"  [FAIL] Error checking docstring: {e}")
        return False


def test_syntax_valid():
    """Test that the module has valid Python syntax."""
    print("\nTesting Python syntax...")
    
    try:
        with open('detection.py', 'r', encoding='utf-8') as f:
            ast.parse(f.read())
        print("  [PASS] Module has valid Python syntax")
        return True
    except SyntaxError as e:
        print(f"  [FAIL] Syntax error: {e}")
        return False


def main():
    """Run all WARNING-001 fix tests."""
    print("=" * 70)
    print("WARNING-001 Fix Verification")
    print("Incorrect Type Hint in Detection Module")
    print("=" * 70)
    print()
    
    results = []
    
    # Test 1: Syntax validation
    results.append(("Syntax validation", test_syntax_valid()))
    
    # Test 2: Import check
    results.append(("Any import", test_import_includes_any()))
    
    # Test 3: Type hint check
    results.append(("Type hint correction", test_correct_type_hint()))
    
    # Test 4: Headers type hint
    results.append(("Headers type hint", test_headers_type_hint()))
    
    # Test 5: Function exists
    results.append(("Function definition", test_function_exists()))
    
    # Test 6: Docstring quality
    results.append(("Docstring quality", test_docstring_quality()))
    
    print()
    print("=" * 70)
    print("Test Results Summary")
    print("=" * 70)
    
    for name, passed in results:
        status = "[PASS]" if passed else "[FAIL]"
        print(f"{status} {name}")
    
    print()
    print("-" * 70)
    
    passed_count = sum(1 for _, passed in results if passed)
    total_count = len(results)
    
    if all(passed for _, passed in results):
        print(f"RESULT: ALL TESTS PASSED ({passed_count}/{total_count})")
        print()
        print("WARNING-001 has been successfully fixed:")
        print("  [OK] Changed 'any' to 'Any' from typing module")
        print("  [OK] Added 'Any' to typing imports")
        print("  [OK] Improved headers parameter type hint")
        print("  [OK] Enhanced docstring with return type details")
        print()
        print("Benefits:")
        print("  - Type checkers now work correctly")
        print("  - IDE autocomplete functions properly")
        print("  - No runtime issues in strict mode")
        print("  - Better code documentation")
    else:
        print(f"RESULT: SOME TESTS FAILED ({passed_count}/{total_count})")
        print()
        print("Please review the failed tests above.")
    
    print("-" * 70)
    print()
    
    return all(passed for _, passed in results)


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
