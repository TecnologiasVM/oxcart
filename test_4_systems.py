#!/usr/bin/env python3
"""
Test script to validate that only the 4 major philatelic catalog systems
are detected and that removed systems (Zumstein, CR_GR, Legacy_A) are ignored.
"""

from philatelic_chunk_logic import extract_catalog_numbers_secure, detect_efo_varieties_secure

def test_4_major_systems():
    """Test that only the 4 major systems work correctly."""
    
    test_cases = [
        # Valid cases that should be detected
        {
            "name": "Scott System",
            "text": "This stamp is catalogued as Scott 123 in the United States postal catalog.",
            "expected": ["Scott"],
            "should_detect": True
        },
        {
            "name": "Michel System", 
            "text": "According to Michel Nr. 456, this German stamp is worth €50.",
            "expected": ["Michel"],
            "should_detect": True
        },
        {
            "name": "Yvert et Tellier System",
            "text": "The French catalog Yvert et Tellier 789 shows this stamp from 1920.",
            "expected": ["Yvert"],
            "should_detect": True
        },
        {
            "name": "Stanley Gibbons System",
            "text": "Stanley Gibbons SG 101 is the reference for this British colonial stamp.",
            "expected": ["Stanley_Gibbons"],
            "should_detect": True
        },
        
        # Invalid cases that should NOT be detected (removed systems)
        {
            "name": "Zumstein System (REMOVED)",
            "text": "The Zumstein 123 catalog shows this Swiss stamp with special perforations.",
            "expected": [],
            "should_detect": False
        },
        {
            "name": "CR/GR System (REMOVED)",
            "text": "This Costa Rica stamp is numbered GR25 in the local catalog system.",
            "expected": [],
            "should_detect": False
        },
        {
            "name": "Legacy A System (REMOVED)", 
            "text": "The old catalog system used A147 for this particular Costa Rican issue.",
            "expected": [],
            "should_detect": False
        },
        
        # Ambiguous cases that should be rejected
        {
            "name": "Software Scott (SHOULD REJECT)",
            "text": "In the software configuration, Scott parameter 147 controls the timeout.",
            "expected": [],
            "should_detect": False
        }
    ]
    
    print("Testing 4 Major Philatelic Catalog Systems")
    print("=" * 60)
    
    total_tests = len(test_cases)
    passed_tests = 0
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n{i}. {test_case['name']}")
        print(f"Text: {test_case['text']}")
        
        # Extract using secure method with high confidence threshold
        results = extract_catalog_numbers_secure(test_case['text'], min_confidence=0.8)
        found_systems = [cat['system'] for cat in results]
        
        print(f"Found systems: {found_systems}")
        print(f"Expected: {test_case['expected']}")
        
        # Check if results match expectations
        if test_case['should_detect']:
            # Should detect the specified systems
            if set(found_systems) == set(test_case['expected']):
                print("[OK] PASS - Correctly detected expected systems")
                passed_tests += 1
            else:
                print("[FAIL] FAIL - Did not detect expected systems")
        else:
            # Should NOT detect anything
            if len(found_systems) == 0:
                print("[OK] PASS - Correctly rejected (no false positives)")
                passed_tests += 1
            else:
                print("[FAIL] FAIL - False positive detected")
        
        # Show detailed results for detected systems
        if results:
            for result in results:
                print(f"  -> {result['system']} {result['number']} (confidence: {result['confidence']:.2f})")
    
    print("\n" + "=" * 60)
    print(f"TEST SUMMARY: {passed_tests}/{total_tests} tests passed")
    
    if passed_tests == total_tests:
        print("[SUCCESS] ALL TESTS PASSED - System working correctly!")
        print("[OK] Only 4 major systems detected")
        print("[OK] Removed systems properly ignored")
        print("[OK] False positives correctly rejected")
    else:
        print("[WARNING] Some tests failed - review implementation")
    
    return passed_tests == total_tests

def test_specific_patterns():
    """Test specific pattern variations for each system."""
    
    pattern_tests = [
        # Scott variations
        ("Scott 123", ["Scott"]),
        ("Sc. 456", ["Scott"]), 
        ("Scott No. C45", ["Scott"]),
        
        # Michel variations
        ("Michel 789", ["Michel"]),
        ("Mi. 234", ["Michel"]),
        ("Michel Nr. 567", ["Michel"]),
        
        # Yvert variations
        ("Yvert 890", ["Yvert"]),
        ("Y&T 123", ["Yvert"]),
        ("Yvert et Tellier 456", ["Yvert"]),
        
        # Stanley Gibbons variations
        ("Stanley Gibbons 789", ["Stanley_Gibbons"]),
        ("SG 234", ["Stanley_Gibbons"]),
        
        # Should be rejected
        ("Zumstein 123", []),  # Removed system
        ("GR25", []),          # Removed system  
        ("A147", []),          # Removed system
        ("S 147", [])          # Too ambiguous
    ]
    
    print("\nTesting Specific Pattern Variations")
    print("-" * 40)
    
    pattern_passed = 0
    
    for text, expected in pattern_tests:
        # Add philatelic context to make patterns valid
        full_text = f"This philatelic stamp catalog entry shows {text} from the postal service."
        results = extract_catalog_numbers_secure(full_text, min_confidence=0.8)
        found = [cat['system'] for cat in results]
        
        if set(found) == set(expected):
            print(f"[OK] '{text}' -> {found}")
            pattern_passed += 1
        else:
            print(f"[FAIL] '{text}' -> Expected {expected}, got {found}")
    
    print(f"\nPattern Tests: {pattern_passed}/{len(pattern_tests)} passed")
    return pattern_passed == len(pattern_tests)

if __name__ == "__main__":
    print("[TEST] Testing Refined Philatelic Catalog System")
    print("[SCOPE] Validating only 4 major international systems")
    print()
    
    # Run main system tests
    main_passed = test_4_major_systems()
    
    # Run pattern variation tests
    pattern_passed = test_specific_patterns()
    
    print("\n" + "=" * 60)
    print("FINAL RESULTS:")
    print(f"Main System Tests: {'PASS' if main_passed else 'FAIL'}")
    print(f"Pattern Tests: {'PASS' if pattern_passed else 'FAIL'}")
    
    if main_passed and pattern_passed:
        print("\n[SUCCESS] REFINEMENT SUCCESSFUL!")
        print("[OK] Only 4 major systems: Scott, Michel, Yvert, Stanley Gibbons")
        print("[OK] Removed systems: Zumstein, CR_GR, Legacy_A")
        print("[OK] Improved security with higher confidence threshold (0.8)")
        print("[OK] Better anchor patterns to prevent false positives")
    else:
        print("\n[WARNING] REFINEMENT NEEDS ATTENTION")
        print("Some tests failed - check implementation")