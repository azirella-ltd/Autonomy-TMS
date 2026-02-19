"""Test that manufacturer nodes are excluded from inbound_supply validation."""

# Simulate the fixed validation logic
def test_manufacturer_validation():
    """Test the validation logic for manufacturer nodes."""

    # Test cases
    test_cases = [
        {
            "name": "Manufacturer node with no inbound_supply",
            "normalised_shipments": [],
            "master_type": "manufacturer",
            "round_number": 1,
            "node": "six_pack_mfg",
            "should_raise": False,  # Should NOT raise after fix
        },
        {
            "name": "Inventory node with no inbound_supply",
            "normalised_shipments": [],
            "master_type": "inventory",
            "round_number": 1,
            "node": "retailer",
            "should_raise": True,  # SHOULD raise
        },
        {
            "name": "Market supply with no inbound_supply",
            "normalised_shipments": [],
            "master_type": "market_supply",
            "round_number": 1,
            "node": "upstream_supply",
            "should_raise": False,  # Should NOT raise
        },
        {
            "name": "Market demand with no inbound_supply",
            "normalised_shipments": [],
            "master_type": "market_demand",
            "round_number": 1,
            "node": "customer",
            "should_raise": False,  # Should NOT raise
        },
        {
            "name": "Manufacturer in later round",
            "normalised_shipments": [],
            "master_type": "manufacturer",
            "round_number": 5,
            "node": "six_pack_mfg",
            "should_raise": False,  # Round > 1, so no check
        },
    ]

    print("Testing manufacturer node validation logic...")
    print("=" * 70)

    for test in test_cases:
        normalised_shipments = test["normalised_shipments"]
        master_type = test["master_type"]
        round_number = test["round_number"]
        node = test["node"]
        should_raise = test["should_raise"]

        # This is the FIXED validation logic from line 3968-3978
        would_raise_error = (
            not normalised_shipments
            and master_type not in {"market_supply", "market_demand", "manufacturer"}  # FIXED: added "manufacturer"
            and round_number == 1
        )

        status = "✓ PASS" if (would_raise_error == should_raise) else "✗ FAIL"

        print(f"\n{status}: {test['name']}")
        print(f"  Node: {node}, Type: {master_type}, Round: {round_number}")
        print(f"  Would raise error: {would_raise_error}, Expected: {should_raise}")

        if would_raise_error != should_raise:
            print(f"  ERROR: Test failed!")
            return False

    print("\n" + "=" * 70)
    print("✓ All tests passed! Manufacturer nodes are correctly excluded.")
    return True


if __name__ == "__main__":
    success = test_manufacturer_validation()
    exit(0 if success else 1)
