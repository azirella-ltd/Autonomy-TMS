import requests
import time
from typing import Dict, Any
import json

# Configuration
BASE_URL = "http://localhost:8000/api/v1"
AUTH = ("admin@example.com", "Admin123!")  # Default credentials - update if different

def login() -> str:
    """Login and get access token."""
    try:
        response = requests.post(
            f"{BASE_URL}/auth/token",
            data={"username": AUTH[0], "password": AUTH[1]},
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        response.raise_for_status()
        return response.json()["access_token"]
    except requests.exceptions.RequestException as e:
        print(f"Error during login: {e}")
        print(f"Response: {e.response.text if hasattr(e, 'response') else 'No response'}")
        raise

class AgentGameDemo:
    def __init__(self):
        self.token = login()
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
        self.scenario_id = None

    def create_scenario(self) -> Dict[str, Any]:
        """Create a new agent scenario."""
        print("\n=== Creating a new agent scenario ===")
        game_data = {
            "name": "AI Agent Demo Scenario",
            "max_periods": 10,
            "demand_pattern": {
                "type": "classic",
                "params": {
                    "initial_demand": 4,
                    "change_week": 4,
                    "final_demand": 8
                }
            }
        }
        
        response = requests.post(
            f"{BASE_URL}/agent-games/",
            headers=self.headers,
            json=game_data
        )
        response.raise_for_status()
        
        result = response.json()
        self.scenario_id = result["scenario_id"]
        print(f"Created scenario with ID: {self.scenario_id}")
        return result

    def start_scenario(self) -> Dict[str, Any]:
        """Start the agent scenario."""
        if not self.scenario_id:
            raise ValueError("No scenario ID. Create a scenario first.")

        print("\n=== Starting the scenario ===")
        response = requests.post(
            f"{BASE_URL}/agent-games/{self.scenario_id}/start",
            headers=self.headers
        )
        response.raise_for_status()
        
        result = response.json()
        print(f"Scenario started: {result}")
        return result

    def set_agent_strategies(self) -> None:
        """Set different strategies for each agent."""
        if not self.scenario_id:
            raise ValueError("No scenario ID. Create a scenario first.")
            
        print("\n=== Setting agent strategies ===")
        strategies = {
            "retailer": "naive",
            "wholesaler": "bullwhip",
            "distributor": "conservative",
            "manufacturer": "random"
        }
        
        for role, strategy in strategies.items():
            response = requests.put(
                f"{BASE_URL}/agent-games/{self.scenario_id}/agent-strategy",
                params={"role": role, "strategy": strategy},
                headers=self.headers
            )
            response.raise_for_status()
            print(f"Set {role} strategy to {strategy}")
    
    def toggle_demand_visibility(self, visible: bool = True) -> None:
        """Toggle demand visibility for agents."""
        if not self.scenario_id:
            raise ValueError("No scenario ID. Create a scenario first.")
            
        print(f"\n=== Setting demand visibility to {visible} ===")
        response = requests.put(
            f"{BASE_URL}/agent-games/{self.scenario_id}/demand-visibility",
            params={"visible": visible},
            headers=self.headers
        )
        response.raise_for_status()
        print(f"Demand visibility set to {visible}")
    
    def play_round(self) -> Dict[str, Any]:
        """Play one period of the scenario."""
        if not self.scenario_id:
            raise ValueError("No scenario ID. Create a scenario first.")
            
        response = requests.post(
            f"{BASE_URL}/agent-games/{self.scenario_id}/play-round",
            headers=self.headers
        )
        response.raise_for_status()
        
        result = response.json()
        return result
    
    def get_scenario_state(self) -> Dict[str, Any]:
        """Get the current scenario state."""
        if not self.scenario_id:
            raise ValueError("No scenario ID. Create a scenario first.")
            
        response = requests.get(
            f"{BASE_URL}/agent-games/{self.scenario_id}/state",
            headers=self.headers
        )
        response.raise_for_status()
        
        return response.json()
    
    def print_scenario_state(self, state: Dict[str, Any] = None) -> None:
        """Print a formatted view of the scenario state."""
        if state is None:
            state = self.get_scenario_state()

        print(f"\n=== Scenario: {state['name']} ===")
        print(f"Status: {state['status']}")
        print(f"Round: {state['current_period']}/{state['max_periods']}")
        
        print("\nPlayers:")
        for scenario_user in state['scenario_users']:
            print(f"\n{scenario_user['role'].upper()} ({scenario_user['name']}):")
            print(f"  Inventory: {scenario_user['inventory']}")
            print(f"  Backlog: {scenario_user['backlog']}")
            print(f"  Incoming: {scenario_user.get('incoming_shipment', 'N/A')}")
            print(f"  Outgoing: {scenario_user.get('outgoing_shipment', 'N/A')}")
        
        print("\nDemand Pattern:")
        print(json.dumps(state['demand_pattern'], indent=2))

def run_demo():
    """Run the agent scenario demo."""
    try:
        print("=== Starting Supply Chain Agent Demo ===")
        print("Creating a scenario with AI agents...")

        demo = AgentGameDemo()

        print("\n1. Creating a new scenario...")
        demo.create_scenario()

        print("\n2. Starting the scenario...")
        demo.start_scenario()
        
        print("\n3. Setting agent strategies...")
        demo.set_agent_strategies()
        
        print("\n4. Playing first 3 rounds with demand visibility OFF")
        demo.toggle_demand_visibility(False)
        for i in range(3):
            print(f"\n--- Round {i+1} ---")
            demo.play_round()
            state = demo.get_scenario_state()
            demo.print_scenario_state(state)
            time.sleep(1)
        
        print("\n5. Playing next 3 rounds with demand visibility ON")
        demo.toggle_demand_visibility(True)
        for i in range(3, 6):
            print(f"\n--- Round {i+1} ---")
            demo.play_round()
            state = demo.get_scenario_state()
            demo.print_scenario_state(state)
            time.sleep(1)
        
        remaining_rounds = 10 - 6
        print(f"\n6. Playing remaining {remaining_rounds} rounds")
        for i in range(6, 10):
            print(f"\n--- Round {i+1} ---")
            demo.play_round()
            state = demo.get_scenario_state()
            demo.print_scenario_state(state)
            time.sleep(1)
        
        print("\n=== Demo completed successfully! ===")
        print("Scenario results:")
        final_state = demo.get_scenario_state()
        demo.print_scenario_state(final_state)
        
    except Exception as e:
        print(f"\n=== Demo failed! ===")
        print(f"Error: {str(e)}")
        if hasattr(e, 'response') and hasattr(e.response, 'text'):
            print(f"Response: {e.response.text}")
        return 1
    
    return 0

if __name__ == "__main__":
    run_demo()
