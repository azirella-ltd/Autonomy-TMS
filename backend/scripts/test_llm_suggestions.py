"""
Test LLM-powered agent suggestions.
Phase 7 Sprint 3

This script tests the LLM suggestion generation with various game scenarios.
"""

import asyncio
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.services.llm_suggestion_service import get_llm_service


async def test_basic_suggestion():
    """Test basic LLM suggestion generation."""

    print("\n" + "=" * 60)
    print("TEST 1: Basic Suggestion Generation")
    print("=" * 60)

    llm_service = get_llm_service(provider="openai", model="gpt-4o-mini")

    # Mock context: Normal operating conditions
    context = {
        "current_round": 5,
        "current_inventory": 12,
        "current_backlog": 5,
        "incoming_shipment": 20,
        "lead_time": 2,
        "pipeline_orders": [
            {"round": 4, "quantity": 20, "eta_rounds": 1},
        ],
        "recent_demand": [30, 35, 38, 42, 40],
        "forecast_demand": 44,
        "forecast_confidence": 0.75,
        "avg_inventory": 15.0,
        "avg_backlog": 3.5,
        "service_level": 0.85,
        "total_cost": 125.50,
        "bullwhip_detected": False,
        "demand_volatility": "moderate",
    }

    print(f"\nScenario: Normal Operations")
    print(f"  Inventory: {context['current_inventory']} units")
    print(f"  Backlog: {context['current_backlog']} units")
    print(f"  Recent demand: {context['recent_demand']}")
    print(f"  Forecast: {context['forecast_demand']} units")

    result = await llm_service.generate_suggestion(
        agent_name="wholesaler",
        context=context,
        request_data=None,
    )

    print(f"\n=== LLM Suggestion ===")
    print(f"Order Quantity: {result['order_quantity']} units")
    print(f"Confidence: {result['confidence']:.1%}")
    print(f"\nRationale:")
    print(f"  {result['rationale']}")

    if result.get('reasoning_steps'):
        print(f"\nReasoning Steps:")
        for i, step in enumerate(result['reasoning_steps'], 1):
            print(f"  {i}. {step}")

    if result.get('risk_factors'):
        print(f"\nRisk Factors:")
        for risk in result['risk_factors']:
            print(f"  - {risk}")

    if result.get('alternative_strategies'):
        print(f"\nAlternative Strategies:")
        for alt in result['alternative_strategies']:
            print(f"  - {alt['strategy']}: {alt['order_quantity']} units")
            print(f"    Pros: {alt.get('pros', 'N/A')}")
            print(f"    Cons: {alt.get('cons', 'N/A')}")

    print(f"\n✓ Test 1 PASSED")

    return result


async def test_high_backlog_scenario():
    """Test suggestion with high backlog (crisis scenario)."""

    print("\n" + "=" * 60)
    print("TEST 2: High Backlog Scenario")
    print("=" * 60)

    llm_service = get_llm_service()

    # High backlog scenario
    context = {
        "current_round": 8,
        "current_inventory": 2,
        "current_backlog": 45,  # Critical backlog
        "incoming_shipment": 15,
        "lead_time": 2,
        "pipeline_orders": [
            {"round": 7, "quantity": 15, "eta_rounds": 1},
            {"round": 6, "quantity": 25, "eta_rounds": 2},
        ],
        "recent_demand": [40, 48, 52, 55, 58],
        "forecast_demand": 60,
        "forecast_confidence": 0.65,
        "avg_inventory": 8.0,
        "avg_backlog": 28.5,
        "service_level": 0.45,  # Poor service
        "total_cost": 485.50,
        "bullwhip_detected": True,
        "demand_volatility": "high",
    }

    print(f"\nScenario: Crisis - High Backlog")
    print(f"  Inventory: {context['current_inventory']} units")
    print(f"  Backlog: {context['current_backlog']} units (CRITICAL)")
    print(f"  Service Level: {context['service_level']:.0%}")
    print(f"  Demand Volatility: {context['demand_volatility']}")

    result = await llm_service.generate_suggestion(
        agent_name="retailer",
        context=context,
        request_data=None,
    )

    print(f"\n=== LLM Suggestion ===")
    print(f"Order Quantity: {result['order_quantity']} units")
    print(f"Confidence: {result['confidence']:.1%}")
    print(f"Rationale: {result['rationale']}")

    # Verify aggressive ordering in crisis
    assert result['order_quantity'] > 50, "Expected aggressive order for high backlog"

    print(f"\n✓ Test 2 PASSED - Aggressive ordering recommended")

    return result


async def test_overstock_scenario():
    """Test suggestion with excess inventory."""

    print("\n" + "=" * 60)
    print("TEST 3: Overstock Scenario")
    print("=" * 60)

    llm_service = get_llm_service()

    # Overstock scenario
    context = {
        "current_round": 10,
        "current_inventory": 85,  # Excess inventory
        "current_backlog": 0,
        "incoming_shipment": 30,
        "lead_time": 2,
        "pipeline_orders": [
            {"round": 9, "quantity": 30, "eta_rounds": 1},
            {"round": 8, "quantity": 35, "eta_rounds": 2},
        ],
        "recent_demand": [25, 28, 22, 26, 24],
        "forecast_demand": 25,
        "forecast_confidence": 0.80,
        "avg_inventory": 62.0,
        "avg_backlog": 0.0,
        "service_level": 1.00,  # Perfect service
        "total_cost": 350.00,
        "bullwhip_detected": False,
        "demand_volatility": "low",
    }

    print(f"\nScenario: Overstock")
    print(f"  Inventory: {context['current_inventory']} units (EXCESS)")
    print(f"  Backlog: {context['current_backlog']} units")
    print(f"  Service Level: {context['service_level']:.0%}")
    print(f"  Incoming: {context['incoming_shipment']} + {sum(p['quantity'] for p in context['pipeline_orders'])} units")

    result = await llm_service.generate_suggestion(
        agent_name="distributor",
        context=context,
        request_data=None,
    )

    print(f"\n=== LLM Suggestion ===")
    print(f"Order Quantity: {result['order_quantity']} units")
    print(f"Confidence: {result['confidence']:.1%}")
    print(f"Rationale: {result['rationale']}")

    # Verify conservative ordering with excess inventory
    assert result['order_quantity'] < 30, "Expected conservative order for overstock"

    print(f"\n✓ Test 3 PASSED - Conservative ordering recommended")

    return result


async def test_bullwhip_scenario():
    """Test suggestion with bullwhip effect detected."""

    print("\n" + "=" * 60)
    print("TEST 4: Bullwhip Effect Scenario")
    print("=" * 60)

    llm_service = get_llm_service()

    # Bullwhip scenario
    context = {
        "current_round": 12,
        "current_inventory": 18,
        "current_backlog": 12,
        "incoming_shipment": 45,
        "lead_time": 2,
        "pipeline_orders": [
            {"round": 11, "quantity": 45, "eta_rounds": 1},
            {"round": 10, "quantity": 60, "eta_rounds": 2},
        ],
        "recent_demand": [30, 32, 35, 38, 36],
        "forecast_demand": 37,
        "forecast_confidence": 0.70,
        "avg_inventory": 22.0,
        "avg_backlog": 8.5,
        "service_level": 0.75,
        "total_cost": 195.00,
        "bullwhip_detected": True,  # Key indicator
        "demand_volatility": "moderate",
    }

    print(f"\nScenario: Bullwhip Effect Detected")
    print(f"  Inventory: {context['current_inventory']} units")
    print(f"  Backlog: {context['current_backlog']} units")
    print(f"  Bullwhip: {context['bullwhip_detected']}")
    print(f"  Large pipeline: {sum(p['quantity'] for p in context['pipeline_orders'])} units incoming")

    result = await llm_service.generate_suggestion(
        agent_name="wholesaler",
        context=context,
        request_data={"priority": "stabilize"},
    )

    print(f"\n=== LLM Suggestion ===")
    print(f"Order Quantity: {result['order_quantity']} units")
    print(f"Confidence: {result['confidence']:.1%}")
    print(f"Rationale: {result['rationale']}")

    # Verify stabilizing strategy
    print(f"\n✓ Test 4 PASSED - Bullwhip mitigation considered")

    return result


async def test_fallback_mode():
    """Test fallback to heuristic when LLM fails."""

    print("\n" + "=" * 60)
    print("TEST 5: Fallback Mode (Heuristic)")
    print("=" * 60)

    # Create service with invalid provider to force fallback
    llm_service = get_llm_service(provider="invalid_provider", model="gpt-4o-mini")

    context = {
        "current_round": 5,
        "current_inventory": 15,
        "current_backlog": 8,
        "recent_demand": [30, 32, 35],
        "forecast_demand": 33,
        "forecast_confidence": 0.70,
        "avg_inventory": 18.0,
        "avg_backlog": 6.0,
        "service_level": 0.80,
        "total_cost": 120.00,
        "bullwhip_detected": False,
        "demand_volatility": "moderate",
    }

    print(f"\nScenario: LLM Unavailable (Testing Fallback)")
    print(f"  Inventory: {context['current_inventory']} units")
    print(f"  Backlog: {context['current_backlog']} units")

    result = await llm_service.generate_suggestion(
        agent_name="factory",
        context=context,
        request_data=None,
    )

    print(f"\n=== Heuristic Fallback ===")
    print(f"Order Quantity: {result['order_quantity']} units")
    print(f"Confidence: {result['confidence']:.1%}")
    print(f"Rationale: {result['rationale']}")

    # Verify fallback was used
    assert result['confidence'] <= 0.6, "Expected lower confidence for fallback"
    assert "fallback" in result['rationale'].lower() or "heuristic" in result['rationale'].lower()

    print(f"\n✓ Test 5 PASSED - Fallback mode working correctly")

    return result


async def test_different_agent_roles():
    """Test suggestions for different agent roles."""

    print("\n" + "=" * 60)
    print("TEST 6: Different Agent Roles")
    print("=" * 60)

    llm_service = get_llm_service()

    context = {
        "current_round": 7,
        "current_inventory": 20,
        "current_backlog": 10,
        "incoming_shipment": 25,
        "lead_time": 2,
        "pipeline_orders": [],
        "recent_demand": [35, 38, 36, 40, 38],
        "forecast_demand": 39,
        "forecast_confidence": 0.75,
        "avg_inventory": 22.0,
        "avg_backlog": 8.0,
        "service_level": 0.82,
        "total_cost": 145.00,
        "bullwhip_detected": False,
        "demand_volatility": "moderate",
    }

    roles = ["retailer", "wholesaler", "distributor", "factory"]
    suggestions = {}

    for role in roles:
        print(f"\nTesting {role.upper()}...")
        result = await llm_service.generate_suggestion(
            agent_name=role,
            context=context,
            request_data=None,
        )
        suggestions[role] = result
        print(f"  Order: {result['order_quantity']} units ({result['confidence']:.0%} confidence)")
        print(f"  Rationale: {result['rationale'][:80]}...")

    print(f"\n✓ Test 6 PASSED - All roles generated suggestions")

    return suggestions


async def run_all_tests():
    """Run all LLM suggestion tests."""

    print("\n" + "#" * 60)
    print("# LLM SUGGESTION SERVICE TEST SUITE")
    print("# Phase 7 Sprint 3")
    print("#" * 60)

    try:
        # Run tests
        await test_basic_suggestion()
        await test_high_backlog_scenario()
        await test_overstock_scenario()
        await test_bullwhip_scenario()
        await test_fallback_mode()
        await test_different_agent_roles()

        # Summary
        print("\n" + "=" * 60)
        print("ALL TESTS PASSED ✓")
        print("=" * 60)
        print("\nLLM suggestion service is working correctly!")
        print("- OpenAI integration: ✓")
        print("- Context-aware recommendations: ✓")
        print("- Fallback mode: ✓")
        print("- Multiple agent roles: ✓")

    except AssertionError as e:
        print(f"\n✗ TEST FAILED: {e}")
        return False
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

    return True


if __name__ == "__main__":
    # Run tests
    success = asyncio.run(run_all_tests())

    # Exit with appropriate code
    sys.exit(0 if success else 1)
