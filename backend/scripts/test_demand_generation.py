import sys
from pathlib import Path

# Add the backend directory to the Python path
sys.path.append(str(Path(__file__).parent.parent))

from app.core.demand_patterns import get_demand_pattern, DemandPatternType

def test_classic_demand_pattern():
    """Test the classic demand pattern generation."""
    print("\n=== Testing Classic Demand Pattern ===")
    
    # Test parameters
    config = {
        "type": DemandPatternType.CLASSIC,
        "params": {
            "initial_demand": 4,
            "change_week": 6,
            "final_demand": 8
        }
    }
    
    # Generate pattern for 12 rounds (to test beyond the stable period)
    num_rounds = 12
    print(f"Generating demand pattern for {num_rounds} rounds...")
    demands = get_demand_pattern(config, num_rounds)
    
    # Expected pattern: 5 rounds of 4, then 7 rounds of 8
    expected = [4, 4, 4, 4, 4, 8, 8, 8, 8, 8, 8, 8]
    
    # Verify the generated pattern
    print("\nVerifying demand pattern...")
    print(f"Round {'Demand':>8} {'Expected':>8} {'Status':>10}")
    print("-" * 35)
    
    all_passed = True
    for i, (actual, expected_val) in enumerate(zip(demands, expected), 1):
        status = "✅" if actual == expected_val else "❌"
        if status == "❌":
            all_passed = False
        print(f"{i:>5} {actual:>8} {expected_val:>8} {status:>10}")
    
    if all_passed:
        print("\n✅ All demand pattern tests passed!")
    else:
        print("\n❌ Some tests failed. Please check the output above.")
    
    return all_passed

def test_different_parameters():
    """Test demand pattern with different parameters."""
    print("\n=== Testing Different Parameters ===")
    
    test_cases = [
        {
            "name": "Longer Stable Period",
            "config": {
                "type": DemandPatternType.CLASSIC,
                "params": {"initial_demand": 4, "change_week": 9, "final_demand": 8}
            },
            "rounds": 10,
            "expected": [4]*8 + [8]*2  # 8 rounds of 4, then 2 of 8
        },
        {
            "name": "Larger Step Increase",
            "config": {
                "type": DemandPatternType.CLASSIC,
                "params": {"initial_demand": 4, "change_week": 4, "final_demand": 10}
            },
            "rounds": 5,
            "expected": [4, 4, 4, 10, 10]  # 3 rounds of 4, then 10 (4+6)
        }
    ]
    
    all_passed = True
    
    for case in test_cases:
        print(f"\nTest Case: {case['name']}")
        print(f"Config: {case['config']}")
        
        demands = get_demand_pattern(case['config'], case['rounds'])
        
        print("\nRound   Demand  Expected  Status")
        print("-" * 35)
        
        case_passed = True
        for i, (actual, expected) in enumerate(zip(demands, case['expected']), 1):
            status = "✅" if actual == expected else "❌"
            if status == "❌":
                case_passed = False
                all_passed = False
            print(f"{i:>5} {actual:>8} {expected:>8} {status:>10}")
        
        if case_passed:
            print("✅ Test case passed!")
        else:
            print("❌ Test case failed!")
    
    return all_passed

if __name__ == "__main__":
    print("=== Starting Demand Pattern Tests ===\n")
    
    # Run tests
    classic_passed = test_classic_demand_pattern()
    param_passed = test_different_parameters()
    
    # Final result
    print("\n=== Test Summary ===")
    print(f"Classic Pattern: {'✅ Passed' if classic_passed else '❌ Failed'}")
    print(f"Parameter Tests: {'✅ Passed' if param_passed else '❌ Failed'}")
    
    if classic_passed and param_passed:
        print("\n🎉 All tests passed successfully!")
        sys.exit(0)
    else:
        print("\n❌ Some tests failed. Please check the output above.")
        sys.exit(1)
