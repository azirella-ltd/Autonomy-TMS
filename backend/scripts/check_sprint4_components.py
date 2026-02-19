#!/usr/bin/env python3
"""
Sprint 4 Component Verification Script
Checks that all Sprint 4 components are properly installed and configured.
"""

import sys
import os
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

def check_file_exists(file_path: str, description: str) -> bool:
    """Check if a file exists."""
    path = Path(file_path)
    exists = path.exists()
    status = "✅" if exists else "❌"
    print(f"{status} {description}: {file_path}")
    return exists

def check_import(module_path: str, item_name: str, description: str) -> bool:
    """Check if a Python import works."""
    try:
        module = __import__(module_path, fromlist=[item_name])
        getattr(module, item_name)
        print(f"✅ {description}: {module_path}.{item_name}")
        return True
    except (ImportError, AttributeError) as e:
        print(f"❌ {description}: {module_path}.{item_name} - {e}")
        return False

def check_database_table(table_name: str) -> bool:
    """Check if a database table exists."""
    try:
        from app.db.session import sync_engine
        from sqlalchemy import inspect

        inspector = inspect(sync_engine)
        tables = inspector.get_table_names()
        exists = table_name in tables
        status = "✅" if exists else "❌"
        print(f"{status} Database table: {table_name}")
        return exists
    except Exception as e:
        print(f"❌ Database table {table_name}: {e}")
        return False

def main():
    print("=" * 80)
    print("Phase 7 Sprint 4 - Component Verification")
    print("=" * 80)

    all_checks_passed = True

    # =========================================================================
    # 1. API ENDPOINTS
    # =========================================================================
    print("\n1. API Endpoints")
    print("-" * 80)

    endpoints = [
        ("app/api/endpoints/conversation.py", "Conversation endpoint"),
        ("app/api/endpoints/pattern_analysis.py", "Pattern analysis endpoint"),
        ("app/api/endpoints/visibility.py", "Visibility endpoint"),
        ("app/api/endpoints/negotiation.py", "Negotiation endpoint"),
        ("app/api/endpoints/optimization.py", "Optimization endpoint"),
    ]

    for file_path, desc in endpoints:
        if not check_file_exists(file_path, desc):
            all_checks_passed = False

    # =========================================================================
    # 2. SERVICES
    # =========================================================================
    print("\n2. Service Layer")
    print("-" * 80)

    services = [
        ("app.services.conversation_service", "ConversationService", "Conversation service"),
        ("app.services.conversation_service", "get_conversation_service", "Conversation factory"),
        ("app.services.pattern_analysis_service", "PatternAnalysisService", "Pattern analysis service"),
        ("app.services.pattern_analysis_service", "get_pattern_analysis_service", "Pattern analysis factory"),
        ("app.services.visibility_service", "VisibilityService", "Visibility service"),
        ("app.services.visibility_service", "get_visibility_service", "Visibility factory"),
        ("app.services.negotiation_service", "NegotiationService", "Negotiation service"),
        ("app.services.negotiation_service", "get_negotiation_service", "Negotiation factory"),
    ]

    for module, item, desc in services:
        if not check_import(module, item, desc):
            all_checks_passed = False

    # =========================================================================
    # 3. DATABASE TABLES
    # =========================================================================
    print("\n3. Database Tables")
    print("-" * 80)

    tables = [
        "conversation_messages",
        "suggestion_outcomes",
        "player_patterns",
        "visibility_permissions",
        "visibility_snapshots",
        "negotiations",
        "negotiation_messages",
        "optimization_recommendations",
    ]

    for table in tables:
        if not check_database_table(table):
            all_checks_passed = False

    # =========================================================================
    # 4. FRONTEND COMPONENTS
    # =========================================================================
    print("\n4. Frontend Components")
    print("-" * 80)

    frontend_components = [
        ("../frontend/src/components/game/AIAnalytics.jsx", "AIAnalytics component"),
        ("../frontend/src/components/game/NegotiationPanel.jsx", "NegotiationPanel component"),
        ("../frontend/src/components/game/AISuggestion.jsx", "AISuggestion component (enhanced)"),
        ("../frontend/src/pages/GameRoom.jsx", "GameRoom page (enhanced)"),
    ]

    for file_path, desc in frontend_components:
        if not check_file_exists(file_path, desc):
            all_checks_passed = False

    # =========================================================================
    # 5. API SERVICE METHODS
    # =========================================================================
    print("\n5. Frontend API Methods")
    print("-" * 80)

    # Check if api.js has the new methods
    api_file = Path("../frontend/src/services/api.js")
    if api_file.exists():
        content = api_file.read_text()
        methods = [
            ("getPlayerPatterns", "Pattern analysis - get player patterns"),
            ("getAIEffectiveness", "Pattern analysis - get AI effectiveness"),
            ("getSuggestionHistory", "Pattern analysis - get suggestion history"),
            ("getInsights", "Pattern analysis - get insights"),
            ("createNegotiation", "Negotiation - create proposal"),
            ("respondToNegotiation", "Negotiation - respond to proposal"),
            ("getPlayerNegotiations", "Negotiation - get negotiations"),
            ("getNegotiationMessages", "Negotiation - get messages"),
            ("getNegotiationSuggestion", "Negotiation - get AI suggestion"),
            ("getGlobalOptimization", "Optimization - get global recommendations"),
        ]

        for method, desc in methods:
            if method in content:
                print(f"✅ {desc}: {method}()")
            else:
                print(f"❌ {desc}: {method}() NOT FOUND")
                all_checks_passed = False
    else:
        print(f"❌ Frontend API service file not found: {api_file}")
        all_checks_passed = False

    # =========================================================================
    # 6. ROUTER REGISTRATION
    # =========================================================================
    print("\n6. Router Registration in main.py")
    print("-" * 80)

    main_file = Path("main.py")
    if main_file.exists():
        content = main_file.read_text()
        routers = [
            ("conversation_router", "Conversation router"),
            ("pattern_analysis_router", "Pattern analysis router"),
            ("visibility_router", "Visibility router"),
            ("negotiation_router", "Negotiation router"),
            ("optimization_router", "Optimization router"),
        ]

        for router, desc in routers:
            if f"include_router({router})" in content:
                print(f"✅ {desc} registered")
            else:
                print(f"❌ {desc} NOT registered")
                all_checks_passed = False
    else:
        print(f"❌ main.py not found")
        all_checks_passed = False

    # =========================================================================
    # SUMMARY
    # =========================================================================
    print("\n" + "=" * 80)
    if all_checks_passed:
        print("✅ ALL CHECKS PASSED - Sprint 4 is fully deployed!")
    else:
        print("❌ SOME CHECKS FAILED - See details above")
    print("=" * 80)

    return 0 if all_checks_passed else 1

if __name__ == "__main__":
    sys.exit(main())
