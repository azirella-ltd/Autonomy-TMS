"""
Test Stochastic Distribution Database Integration

Tests that the stochastic distribution fields were successfully added to the
database and can store/retrieve JSON distribution configurations.

Usage:
    docker compose exec backend python scripts/test_stochastic_db_integration.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app.core.config import get_settings
from app.models.aws_sc_planning import (
    Forecast,
    ProductBom,
    ProductionProcess,
    SourcingRules,
    VendorLeadTime,
    ProductionCapacity,
)

settings = get_settings()

# Create database connection using settings
engine = create_engine(settings.SQLALCHEMY_DATABASE_URI)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def test_table_columns():
    """Test that all distribution columns exist in database"""
    print("=" * 80)
    print("TEST 1: Verify Distribution Columns Exist")
    print("=" * 80)

    tests = [
        ("forecast", ["demand_dist", "forecast_error_dist"]),
        ("product_bom", ["scrap_rate_dist"]),
        ("production_process", ["mfg_lead_time_dist", "cycle_time_dist", "yield_dist", "setup_time_dist", "changeover_time_dist"]),
        ("sourcing_rules", ["sourcing_lead_time_dist"]),
        ("vendor_lead_time", ["lead_time_dist"]),
        ("production_capacity", ["capacity_dist"]),
    ]

    passed = 0
    failed = 0

    with engine.connect() as conn:
        for table_name, expected_columns in tests:
            result = conn.execute(text(f"DESCRIBE {table_name}"))
            columns = {row[0] for row in result}

            for col in expected_columns:
                if col in columns:
                    print(f"✅ {table_name}.{col} exists")
                    passed += 1
                else:
                    print(f"❌ {table_name}.{col} MISSING")
                    failed += 1

    print()
    print(f"Column Verification: {passed} passed, {failed} failed")
    return failed == 0


def test_json_storage():
    """Test storing and retrieving JSON distribution configs"""
    print()
    print("=" * 80)
    print("TEST 2: Test JSON Storage and Retrieval")
    print("=" * 80)

    test_distribution = {
        "type": "normal",
        "mean": 7.0,
        "stddev": 1.5,
        "min": 3.0,
        "max": 12.0,
        "seed": 42
    }

    db = SessionLocal()

    try:
        # Test ProductionProcess
        print("\n📝 Testing ProductionProcess...")
        prod_process = ProductionProcess(
            id="TEST_PROCESS_001",
            description="Test process for stochastic distributions",
            manufacturing_leadtime=7,
            mfg_lead_time_dist=test_distribution  # Store JSON
        )
        db.add(prod_process)
        db.commit()

        # Retrieve and verify
        retrieved = db.query(ProductionProcess).filter_by(id="TEST_PROCESS_001").first()
        if retrieved and retrieved.mfg_lead_time_dist == test_distribution:
            print("✅ ProductionProcess: JSON stored and retrieved successfully")
            print(f"   Distribution: {retrieved.mfg_lead_time_dist}")
        else:
            print("❌ ProductionProcess: JSON storage/retrieval failed")
            return False

        # Test backward compatibility (NULL value)
        print("\n📝 Testing backward compatibility (NULL distribution)...")
        prod_process_null = ProductionProcess(
            id="TEST_PROCESS_002",
            description="Test process with NULL distribution (deterministic)",
            manufacturing_leadtime=7,
            mfg_lead_time_dist=None  # NULL = deterministic
        )
        db.add(prod_process_null)
        db.commit()

        retrieved_null = db.query(ProductionProcess).filter_by(id="TEST_PROCESS_002").first()
        if retrieved_null and retrieved_null.mfg_lead_time_dist is None:
            print("✅ Backward Compatibility: NULL distributions work correctly")
            print(f"   Value: {retrieved_null.mfg_lead_time_dist} (deterministic)")
        else:
            print("❌ Backward Compatibility: NULL handling failed")
            return False

        # Cleanup
        db.delete(prod_process)
        db.delete(prod_process_null)
        db.commit()

        print("\n✅ All JSON storage tests passed!")
        return True

    except Exception as e:
        print(f"\n❌ Error during JSON storage test: {e}")
        db.rollback()
        return False
    finally:
        db.close()


def test_all_model_fields():
    """Test that all models have distribution fields accessible"""
    print()
    print("=" * 80)
    print("TEST 3: Verify Model Field Accessibility")
    print("=" * 80)

    test_dist = {"type": "deterministic", "value": 10.0}

    tests = [
        ("Forecast", Forecast, ["demand_dist", "forecast_error_dist"]),
        ("ProductBom", ProductBom, ["scrap_rate_dist"]),
        ("ProductionProcess", ProductionProcess, ["mfg_lead_time_dist", "cycle_time_dist", "yield_dist", "setup_time_dist", "changeover_time_dist"]),
        ("SourcingRules", SourcingRules, ["sourcing_lead_time_dist"]),
        ("VendorLeadTime", VendorLeadTime, ["lead_time_dist"]),
        ("ProductionCapacity", ProductionCapacity, ["capacity_dist"]),
    ]

    passed = 0
    failed = 0

    for model_name, model_class, fields in tests:
        for field in fields:
            if hasattr(model_class, field):
                print(f"✅ {model_name}.{field} accessible")
                passed += 1
            else:
                print(f"❌ {model_name}.{field} NOT ACCESSIBLE")
                failed += 1

    print()
    print(f"Model Field Accessibility: {passed} passed, {failed} failed")
    return failed == 0


def test_migration_revision():
    """Test that migration revision is correct"""
    print()
    print("=" * 80)
    print("TEST 4: Verify Migration Revision")
    print("=" * 80)

    with engine.connect() as conn:
        result = conn.execute(text("SELECT version_num FROM alembic_version"))
        version = result.scalar()

        if version == "20260113_stochastic_distributions":
            print(f"✅ Current revision: {version}")
            print("   Migration successfully applied!")
            return True
        else:
            print(f"⚠️  Current revision: {version}")
            print("   Expected: 20260113_stochastic_distributions")
            print("   Migration may not be at expected revision")
            return False


def run_all_tests():
    """Run all integration tests"""
    print("\n" + "=" * 80)
    print("STOCHASTIC DISTRIBUTION DATABASE INTEGRATION TESTS")
    print("=" * 80)
    print()
    print("Testing Phase 5 Sprint 2: Database Schema & Integration")
    print("Testing 11 distribution fields across 6 tables")
    print()

    results = []

    # Test 1: Column existence
    results.append(("Column Verification", test_table_columns()))

    # Test 2: JSON storage
    results.append(("JSON Storage & Retrieval", test_json_storage()))

    # Test 3: Model field accessibility
    results.append(("Model Field Accessibility", test_all_model_fields()))

    # Test 4: Migration revision
    results.append(("Migration Revision", test_migration_revision()))

    # Summary
    print()
    print("=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)

    total_tests = len(results)
    passed_tests = sum(1 for _, passed in results if passed)
    failed_tests = total_tests - passed_tests

    for test_name, passed in results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{test_name}: {status}")

    print()
    print(f"Total Tests: {total_tests}")
    print(f"Passed:      {passed_tests} ✅")
    print(f"Failed:      {failed_tests} ❌")
    print(f"Success Rate: {passed_tests / total_tests * 100:.1f}%")
    print()

    if failed_tests == 0:
        print("🎉 ALL TESTS PASSED! 🎉")
        print()
        print("Database integration complete:")
        print("- 11 distribution fields added across 6 tables")
        print("- JSON storage/retrieval working")
        print("- Backward compatibility preserved (NULL = deterministic)")
        print("- Model classes updated with distribution fields")
        print()
        print("✅ Ready for Sprint 3: Execution Adapter Integration")
        return True
    else:
        print("❌ SOME TESTS FAILED")
        print()
        print("Please review the failures above and fix any issues.")
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
