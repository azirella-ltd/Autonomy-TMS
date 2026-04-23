"""
Test Chat API Endpoints
Phase 7 Sprint 2

This script tests the A2A collaboration API endpoints.
"""

import requests
import json
from datetime import datetime
from typing import Dict, Any

# Configuration
BASE_URL = "http://localhost:8000"
API_BASE = f"{BASE_URL}/api/v1"

# Test credentials
TEST_USER = {
    "username": "systemadmin@autonomy.ai",
    "password": "Autonomy@2026"
}


class ChatAPITester:
    """Test harness for chat API."""

    def __init__(self):
        self.session = requests.Session()
        self.token = None
        self.scenario_id = None
        self.scenario_user_id = None

    def login(self):
        """Authenticate and get access token."""
        print("\n=== Logging in ===")
        response = self.session.post(
            f"{API_BASE}/auth/login",
            data=TEST_USER,  # Use form data instead of JSON
        )

        if response.status_code == 200:
            data = response.json()
            self.token = data.get("access_token")
            self.session.headers.update({
                "Authorization": f"Bearer {self.token}"
            })
            print(f"✓ Logged in successfully")
            return True
        else:
            print(f"✗ Login failed: {response.status_code}")
            print(response.text)
            return False

    def get_first_game(self):
        """Get first available scenario for testing."""
        print("\n=== Getting first scenario ===")
        # Try mixed-scenarios endpoint
        response = self.session.get(f"{API_BASE}/mixed-scenarios/")

        if response.status_code == 200:
            scenarios = response.json()
            if scenarios and len(scenarios) > 0:
                self.scenario_id = scenarios[0]["id"]
                print(f"✓ Using scenario ID: {self.scenario_id}")
                print(f"  Scenario: {scenarios[0]['name']}")
                return True
            else:
                print("✗ No scenarios found")
                return False
        else:
            print(f"✗ Failed to get scenarios: {response.status_code}")
            return False

    def test_send_message(self):
        """Test sending a chat message."""
        print("\n=== Testing send message ===")

        message_data = {
            "sender_id": f"scenario_user:1",
            "sender_name": "Test ScenarioUser",
            "sender_type": "scenario_user",
            "content": "Hello agents! Can you help me with my order?",
            "type": "text"
        }

        response = self.session.post(
            f"{API_BASE}/scenarios/{self.scenario_id}/chat/messages",
            json=message_data,
        )

        if response.status_code == 201:
            data = response.json()
            print(f"✓ Message sent successfully")
            print(f"  Message ID: {data['id']}")
            print(f"  Content: {data['content']}")
            print(f"  Created at: {data['created_at']}")
            return data["id"]
        else:
            print(f"✗ Failed to send message: {response.status_code}")
            print(response.text)
            return None

    def test_get_messages(self):
        """Test getting chat messages."""
        print("\n=== Testing get messages ===")

        response = self.session.get(
            f"{API_BASE}/scenarios/{self.scenario_id}/chat/messages",
            params={"limit": 20}
        )

        if response.status_code == 200:
            data = response.json()
            print(f"✓ Retrieved messages successfully")
            print(f"  Total messages: {data['total']}")
            print(f"  Returned: {len(data['messages'])}")
            print(f"  Has more: {data['has_more']}")

            if data["messages"]:
                msg = data["messages"][0]
                print(f"\n  Latest message:")
                print(f"    From: {msg['sender_name']} ({msg['sender_type']})")
                print(f"    Content: {msg['content'][:50]}...")
                print(f"    Read: {msg['read']}")

            return data["messages"]
        else:
            print(f"✗ Failed to get messages: {response.status_code}")
            print(response.text)
            return None

    def test_mark_messages_read(self, message_ids):
        """Test marking messages as read."""
        print("\n=== Testing mark messages as read ===")

        response = self.session.put(
            f"{API_BASE}/scenarios/{self.scenario_id}/chat/messages/read",
            json=message_ids,
        )

        if response.status_code == 200:
            data = response.json()
            print(f"✓ Marked {data['count']} messages as read")
            return True
        else:
            print(f"✗ Failed to mark messages as read: {response.status_code}")
            print(response.text)
            return False

    def test_request_suggestion(self):
        """Test requesting an agent suggestion."""
        print("\n=== Testing request suggestion ===")

        response = self.session.post(
            f"{API_BASE}/scenarios/{self.scenario_id}/chat/request-suggestion",
            params={"agent_name": "wholesaler"},
            json={"context": {}},
        )

        if response.status_code == 201:
            data = response.json()
            print(f"✓ Suggestion generated successfully")
            print(f"  Suggestion ID: {data['id']}")
            print(f"  Agent: {data['agent_name']}")
            print(f"  Order quantity: {data['order_quantity']} units")
            print(f"  Confidence: {data['confidence']:.1%}")
            print(f"  Rationale: {data['rationale'][:100]}...")
            print(f"\n  Context:")
            print(f"    Current inventory: {data['context']['current_inventory']}")
            print(f"    Current backlog: {data['context']['current_backlog']}")
            return data["id"]
        else:
            print(f"✗ Failed to request suggestion: {response.status_code}")
            print(response.text)
            return None

    def test_get_suggestions(self):
        """Test getting agent suggestions."""
        print("\n=== Testing get suggestions ===")

        response = self.session.get(
            f"{API_BASE}/scenarios/{self.scenario_id}/chat/suggestions",
            params={"pending_only": True}
        )

        if response.status_code == 200:
            data = response.json()
            print(f"✓ Retrieved suggestions successfully")
            print(f"  Total suggestions: {data['total']}")

            if data["suggestions"]:
                for i, sug in enumerate(data["suggestions"][:3], 1):
                    print(f"\n  Suggestion {i}:")
                    print(f"    Agent: {sug['agent_name']}")
                    print(f"    Order: {sug['order_quantity']} units")
                    print(f"    Confidence: {sug['confidence']:.1%}")
                    print(f"    Status: {'Pending' if sug['accepted'] is None else ('Accepted' if sug['accepted'] else 'Declined')}")

            return data["suggestions"]
        else:
            print(f"✗ Failed to get suggestions: {response.status_code}")
            print(response.text)
            return None

    def test_accept_suggestion(self, suggestion_id):
        """Test accepting a suggestion."""
        print("\n=== Testing accept suggestion ===")

        response = self.session.put(
            f"{API_BASE}/scenarios/{self.scenario_id}/chat/suggestions/{suggestion_id}/accept",
            json={"scenario_user_id": 1},  # Assuming scenario_user ID 1
        )

        if response.status_code == 200:
            data = response.json()
            print(f"✓ Suggestion accepted successfully")
            print(f"  Suggestion ID: {data['id']}")
            print(f"  Accepted: {data['accepted']}")
            print(f"  Decided at: {data['decided_at']}")
            return True
        else:
            print(f"✗ Failed to accept suggestion: {response.status_code}")
            print(response.text)
            return False

    def test_decline_suggestion(self, suggestion_id):
        """Test declining a suggestion."""
        print("\n=== Testing decline suggestion ===")

        response = self.session.put(
            f"{API_BASE}/scenarios/{self.scenario_id}/chat/suggestions/{suggestion_id}/decline",
            json={"scenario_user_id": 1},
        )

        if response.status_code == 200:
            data = response.json()
            print(f"✓ Suggestion declined successfully")
            print(f"  Suggestion ID: {data['id']}")
            print(f"  Accepted: {data['accepted']}")
            print(f"  Decided at: {data['decided_at']}")
            return True
        else:
            print(f"✗ Failed to decline suggestion: {response.status_code}")
            print(response.text)
            return False

    def test_what_if_analysis(self):
        """Test what-if analysis."""
        print("\n=== Testing what-if analysis ===")

        analysis_data = {
            "scenario_user_id": 1,
            "question": "What if I order 50 units instead of 40?",
            "scenario": {
                "order_quantity": 50,
                "current_order": 40
            }
        }

        response = self.session.post(
            f"{API_BASE}/scenarios/{self.scenario_id}/chat/what-if",
            json=analysis_data,
        )

        if response.status_code == 201:
            data = response.json()
            print(f"✓ What-if analysis created successfully")
            print(f"  Analysis ID: {data['id']}")
            print(f"  Question: {data['question']}")
            print(f"  Completed: {data['completed']}")
            return data["id"]
        else:
            print(f"✗ Failed to create what-if analysis: {response.status_code}")
            print(response.text)
            return None

    def run_all_tests(self):
        """Run all tests in sequence."""
        print("=" * 60)
        print("CHAT API TEST SUITE")
        print("Phase 7 Sprint 2 - A2A Collaboration")
        print("=" * 60)

        # Login
        if not self.login():
            print("\n✗ Tests aborted - login failed")
            return False

        # Get scenario
        if not self.get_first_game():
            print("\n✗ Tests aborted - no scenario available")
            return False

        # Test chat messages
        message_id = self.test_send_message()
        messages = self.test_get_messages()

        if messages and len(messages) > 0:
            message_ids = [msg["id"] for msg in messages[:3]]
            self.test_mark_messages_read(message_ids)

        # Test agent suggestions
        suggestion_id = self.test_request_suggestion()
        suggestions = self.test_get_suggestions()

        if suggestion_id:
            self.test_accept_suggestion(suggestion_id)

        # Request another suggestion for decline test
        suggestion_id_2 = self.test_request_suggestion()
        if suggestion_id_2:
            self.test_decline_suggestion(suggestion_id_2)

        # Test what-if analysis
        self.test_what_if_analysis()

        print("\n" + "=" * 60)
        print("TEST SUITE COMPLETE")
        print("=" * 60)

        return True


def main():
    """Run the test suite."""
    tester = ChatAPITester()
    tester.run_all_tests()


if __name__ == "__main__":
    main()
