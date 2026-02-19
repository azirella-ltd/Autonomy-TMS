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
        self.game_id = None
    
    def create_game(self) -> Dict[str, Any]:
        """Create a new agent game."""
        print("\n=== Creating a new agent game ===")
        game_data = {
            "name": "AI Agent Demo Game",
            "max_rounds": 10,
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
        self.game_id = result["game_id"]
        print(f"Created game with ID: {self.game_id}")
        return result
    
    def start_game(self) -> Dict[str, Any]:
        """Start the agent game."""
        if not self.game_id:
            raise ValueError("No game ID. Create a game first.")
            
        print("\n=== Starting the game ===")
        response = requests.post(
            f"{BASE_URL}/agent-games/{self.game_id}/start",
            headers=self.headers
        )
        response.raise_for_status()
        
        result = response.json()
        print(f"Game started: {result}")
        return result
    
    def set_agent_strategies(self) -> None:
        """Set different strategies for each agent."""
        if not self.game_id:
            raise ValueError("No game ID. Create a game first.")
            
        print("\n=== Setting agent strategies ===")
        strategies = {
            "retailer": "naive",
            "wholesaler": "bullwhip",
            "distributor": "conservative",
            "manufacturer": "random"
        }
        
        for role, strategy in strategies.items():
            response = requests.put(
                f"{BASE_URL}/agent-games/{self.game_id}/agent-strategy",
                params={"role": role, "strategy": strategy},
                headers=self.headers
            )
            response.raise_for_status()
            print(f"Set {role} strategy to {strategy}")
    
    def toggle_demand_visibility(self, visible: bool = True) -> None:
        """Toggle demand visibility for agents."""
        if not self.game_id:
            raise ValueError("No game ID. Create a game first.")
            
        print(f"\n=== Setting demand visibility to {visible} ===")
        response = requests.put(
            f"{BASE_URL}/agent-games/{self.game_id}/demand-visibility",
            params={"visible": visible},
            headers=self.headers
        )
        response.raise_for_status()
        print(f"Demand visibility set to {visible}")
    
    def play_round(self) -> Dict[str, Any]:
        """Play one round of the game."""
        if not self.game_id:
            raise ValueError("No game ID. Create a game first.")
            
        response = requests.post(
            f"{BASE_URL}/agent-games/{self.game_id}/play-round",
            headers=self.headers
        )
        response.raise_for_status()
        
        result = response.json()
        return result
    
    def get_game_state(self) -> Dict[str, Any]:
        """Get the current game state."""
        if not self.game_id:
            raise ValueError("No game ID. Create a game first.")
            
        response = requests.get(
            f"{BASE_URL}/agent-games/{self.game_id}/state",
            headers=self.headers
        )
        response.raise_for_status()
        
        return response.json()
    
    def print_game_state(self, state: Dict[str, Any] = None) -> None:
        """Print a formatted view of the game state."""
        if state is None:
            state = self.get_game_state()
        
        print(f"\n=== Game: {state['name']} ===")
        print(f"Status: {state['status']}")
        print(f"Round: {state['current_round']}/{state['max_rounds']}")
        
        print("\nPlayers:")
        for player in state['players']:
            print(f"\n{player['role'].upper()} ({player['name']}):")
            print(f"  Inventory: {player['inventory']}")
            print(f"  Backlog: {player['backlog']}")
            print(f"  Incoming: {player.get('incoming_shipment', 'N/A')}")
            print(f"  Outgoing: {player.get('outgoing_shipment', 'N/A')}")
        
        print("\nDemand Pattern:")
        print(json.dumps(state['demand_pattern'], indent=2))

def run_demo():
    """Run the agent game demo."""
    try:
        print("=== Starting Beer Game Agent Demo ===")
        print("Creating a game with AI agents...")
        
        demo = AgentGameDemo()
        
        print("\n1. Creating a new game...")
        demo.create_game()
        
        print("\n2. Starting the game...")
        demo.start_game()
        
        print("\n3. Setting agent strategies...")
        demo.set_agent_strategies()
        
        print("\n4. Playing first 3 rounds with demand visibility OFF")
        demo.toggle_demand_visibility(False)
        for i in range(3):
            print(f"\n--- Round {i+1} ---")
            demo.play_round()
            state = demo.get_game_state()
            demo.print_game_state(state)
            time.sleep(1)
        
        print("\n5. Playing next 3 rounds with demand visibility ON")
        demo.toggle_demand_visibility(True)
        for i in range(3, 6):
            print(f"\n--- Round {i+1} ---")
            demo.play_round()
            state = demo.get_game_state()
            demo.print_game_state(state)
            time.sleep(1)
        
        remaining_rounds = 10 - 6
        print(f"\n6. Playing remaining {remaining_rounds} rounds")
        for i in range(6, 10):
            print(f"\n--- Round {i+1} ---")
            demo.play_round()
            state = demo.get_game_state()
            demo.print_game_state(state)
            time.sleep(1)
        
        print("\n=== Demo completed successfully! ===")
        print("Game results:")
        final_state = demo.get_game_state()
        demo.print_game_state(final_state)
        
    except Exception as e:
        print(f"\n=== Demo failed! ===")
        print(f"Error: {str(e)}")
        if hasattr(e, 'response') and hasattr(e.response, 'text'):
            print(f"Response: {e.response.text}")
        return 1
    
    return 0

if __name__ == "__main__":
    run_demo()
