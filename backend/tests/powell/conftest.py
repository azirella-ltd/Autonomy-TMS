"""Empty conftest for the powell test directory.

Deliberately empty: the original auto-stubber harness for ORM
integration tests turned out to break the reactor / aggregator
unit tests' own self-contained SQLite fixtures (module-level
class registration on Base.metadata polluted other tests).

Integration tests that need the full Core stubber harness inline
their own copy and gate on ``TMS_RUN_INTEGRATION_TESTS=1``. See
``test_product_lane_aggregator_integration.py`` for the pattern.
"""
