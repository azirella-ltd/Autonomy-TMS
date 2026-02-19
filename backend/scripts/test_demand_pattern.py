import os
import sys

# Add the parent directory to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.demand_patterns import DemandGenerator


def test_classic_demand_pattern() -> None:
    """Classic pattern should step from 4 to 8 after five rounds."""
    expected = [4, 4, 4, 4, 4, 8, 8, 8, 8, 8]
    pattern = DemandGenerator.generate_classic(
        num_rounds=10,
        initial_demand=4,
        change_week=6,
        final_demand=8,
    )
    assert pattern == expected
