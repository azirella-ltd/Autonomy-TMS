"""
Claude-powered Synthetic Data Generation Wizard

A conversational AI wizard that guides system administrators through
creating synthetic supply chain data for new groups/companies.

The wizard follows a structured conversation flow:
1. Welcome & Archetype Selection
2. Company Details
3. Network Topology Configuration
4. Product Configuration
5. Demand & Policy Configuration
6. Agent Configuration
7. Review & Generate

Each step collects information through natural language conversation
with structured prompts and validation.
"""

import json
import logging
import os
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum
from datetime import datetime

from openai import OpenAI

from app.services.synthetic_data_generator import (
    CompanyArchetype,
    AgentMode,
    DemandPattern,
    DistributionType,
    GenerationRequest,
    SyntheticDataGenerator,
    ARCHETYPE_CONFIGS,
    get_archetype_info,
    list_archetypes
)

logger = logging.getLogger(__name__)


class WizardStep(str, Enum):
    """Wizard conversation steps."""
    WELCOME = "welcome"
    ARCHETYPE = "archetype"
    COMPANY_DETAILS = "company_details"
    NETWORK_CONFIG = "network_config"
    PRODUCT_CONFIG = "product_config"
    DEMAND_CONFIG = "demand_config"
    AGENT_CONFIG = "agent_config"
    REVIEW = "review"
    GENERATING = "generating"
    COMPLETE = "complete"
    ERROR = "error"


@dataclass
class WizardState:
    """Current state of the wizard conversation."""
    session_id: str
    current_step: WizardStep = WizardStep.WELCOME

    # Collected data
    archetype: Optional[CompanyArchetype] = None
    company_name: Optional[str] = None
    group_name: Optional[str] = None
    admin_email: Optional[str] = None
    admin_name: Optional[str] = None

    # Network customization
    num_sites: Optional[int] = None
    num_suppliers: Optional[int] = None
    num_customers: Optional[int] = None

    # Product customization
    num_products: Optional[int] = None
    product_categories: Optional[int] = None

    # Demand configuration
    demand_pattern: Optional[DemandPattern] = None
    seasonality_amplitude: Optional[float] = None
    forecast_horizon_months: int = 12

    # Agent configuration
    agent_mode: AgentMode = AgentMode.COPILOT
    enable_gnn: bool = True
    enable_llm: bool = True
    enable_trm: bool = True

    # Conversation history
    messages: List[Dict[str, str]] = field(default_factory=list)

    # Generation result
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert state to dictionary for serialization."""
        data = {
            "session_id": self.session_id,
            "current_step": self.current_step.value,
            "archetype": self.archetype.value if self.archetype else None,
            "company_name": self.company_name,
            "group_name": self.group_name,
            "admin_email": self.admin_email,
            "admin_name": self.admin_name,
            "num_sites": self.num_sites,
            "num_suppliers": self.num_suppliers,
            "num_customers": self.num_customers,
            "num_products": self.num_products,
            "product_categories": self.product_categories,
            "demand_pattern": self.demand_pattern.value if self.demand_pattern else None,
            "seasonality_amplitude": self.seasonality_amplitude,
            "forecast_horizon_months": self.forecast_horizon_months,
            "agent_mode": self.agent_mode.value,
            "enable_gnn": self.enable_gnn,
            "enable_llm": self.enable_llm,
            "enable_trm": self.enable_trm,
            "messages": self.messages,
            "result": self.result,
            "error": self.error
        }
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WizardState":
        """Create state from dictionary."""
        state = cls(session_id=data["session_id"])
        state.current_step = WizardStep(data.get("current_step", "welcome"))

        if data.get("archetype"):
            state.archetype = CompanyArchetype(data["archetype"])
        state.company_name = data.get("company_name")
        state.group_name = data.get("group_name")
        state.admin_email = data.get("admin_email")
        state.admin_name = data.get("admin_name")

        state.num_sites = data.get("num_sites")
        state.num_suppliers = data.get("num_suppliers")
        state.num_customers = data.get("num_customers")
        state.num_products = data.get("num_products")
        state.product_categories = data.get("product_categories")

        if data.get("demand_pattern"):
            state.demand_pattern = DemandPattern(data["demand_pattern"])
        state.seasonality_amplitude = data.get("seasonality_amplitude")
        state.forecast_horizon_months = data.get("forecast_horizon_months", 12)

        state.agent_mode = AgentMode(data.get("agent_mode", "copilot"))
        state.enable_gnn = data.get("enable_gnn", True)
        state.enable_llm = data.get("enable_llm", True)
        state.enable_trm = data.get("enable_trm", True)

        state.messages = data.get("messages", [])
        state.result = data.get("result")
        state.error = data.get("error")

        return state


# System prompt for the Claude wizard
WIZARD_SYSTEM_PROMPT = """You are a friendly and knowledgeable Supply Chain Configuration Wizard for the Autonomy Supply Chain Platform. Your role is to guide system administrators through setting up synthetic data for testing and demonstration purposes.

## Your Personality
- Professional but approachable
- Patient and helpful
- Knowledgeable about supply chain concepts
- Proactive in offering suggestions and best practices

## Current Wizard Step: {current_step}

## Conversation Context
You are helping the user configure a synthetic supply chain for testing. The data generated will include:
- Groups (organizations)
- Users and administrators
- Supply chain configurations (nodes, lanes, items)
- Forecasts and inventory policies
- Planning hierarchy configurations
- AI agent configurations

## Available Company Archetypes

### 1. RETAILER
Multi-channel retail operations with focus on availability and inventory optimization.
- No manufacturing, buys FG from distributors/manufacturers
- Multiple sales channels (in-store, online)
- Geographic distribution (regions, stores)
- Primary KPIs: Fill Rate, Inventory Turns, Stockout Rate, Days of Supply
- Recommended Agent Mode: Copilot

### 2. DISTRIBUTOR
Wholesale distribution with focus on OTIF and efficient inventory management.
- Minimal manufacturing (bundling, kitting, palletization)
- Sells to retailers, buys from manufacturers
- Regional distribution networks
- Primary KPIs: OTIF, Inventory Turns, Order Fill Rate, Cycle Time
- Recommended Agent Mode: Copilot

### 3. MANUFACTURER
Production-focused operations with multi-tier manufacturing and supplier management.
- 1-3 layers of manufacturing
- Sells to distributors and some direct
- Regional and local DCs
- Multiple suppliers
- Primary KPIs: Gross Margin, OTIF, Inventory Turns, Production Efficiency
- Recommended Agent Mode: Autonomous

## Agent Modes
- **None**: No AI assistance - purely manual planning
- **Copilot**: AI provides suggestions, human approves all decisions
- **Autonomous**: AI makes decisions within defined guardrails

## Your Task for This Step

{step_instructions}

## Current Configuration So Far
{current_config}

## Response Format
Always respond with a JSON object containing:
{{
    "message": "Your conversational response to the user",
    "extracted_data": {{
        // Any data extracted from the user's message (or empty object if none)
        // Use snake_case keys matching the WizardState fields
    }},
    "validation_errors": [
        // Any validation issues (or empty array if none)
    ],
    "suggested_next_step": "current_step" | "next_step" | "previous_step",
    "options": [
        // Quick selection options for the user (if applicable)
        // e.g., ["Retailer", "Distributor", "Manufacturer"]
    ]
}}

Be helpful, clear, and guide the user through the process efficiently."""


STEP_INSTRUCTIONS = {
    WizardStep.WELCOME: """
Welcome the user and briefly explain what you'll help them create.
Ask them to choose a company archetype (Retailer, Distributor, or Manufacturer).
Briefly explain what each archetype represents.
""",

    WizardStep.ARCHETYPE: """
The user is selecting or confirming their company archetype.
Extract the archetype choice from their message.
Validate it's one of: retailer, distributor, manufacturer.
Once confirmed, explain what defaults come with their choice and ask for company details.
""",

    WizardStep.COMPANY_DETAILS: """
Collect basic company information:
- Company name (will be used for the supply chain config name)
- Group name (organization name, often same as company)
- Admin email (must be valid email format)
- Admin name (full name of the group administrator)

Validate email format and ensure all required fields are provided.
""",

    WizardStep.NETWORK_CONFIG: """
Configure the supply chain network topology. Show the defaults for their archetype and ask if they want to customize:
- Number of sites/locations (DCs, stores, plants)
- Number of suppliers
- Number of customers

Explain that reasonable defaults are provided based on their archetype.
Allow them to accept defaults or specify custom values.
""",

    WizardStep.PRODUCT_CONFIG: """
Configure product/item settings. Show defaults and ask for customization:
- Number of products/SKUs
- Product categories

Explain the product hierarchy (Category > Family > Group > Product).
""",

    WizardStep.DEMAND_CONFIG: """
Configure demand characteristics:
- Demand pattern: constant, seasonal, trending, promotional, random
- Seasonality amplitude (0-1, only if seasonal)
- Forecast horizon in months (typically 12)

Explain each demand pattern and recommend based on their archetype.
""",

    WizardStep.AGENT_CONFIG: """
Configure AI agent settings:
- Agent mode: none, copilot, autonomous
- Enable GNN (Graph Neural Network) agent: true/false
- Enable LLM (Language Model) agent: true/false
- Enable TRM (Tiny Recursive Model) agent: true/false

Explain each agent type briefly and recommend based on archetype.
""",

    WizardStep.REVIEW: """
Show a complete summary of all configuration settings.
Ask the user to confirm or make any changes.
List everything that will be created:
- Group and admin user
- Supply chain config with X nodes, Y lanes
- Z products across N categories
- Forecasts for M months
- Inventory policies
- Planning hierarchy configurations
- Agent configurations

Ask for final confirmation to proceed with generation.
""",

    WizardStep.GENERATING: """
The system is generating data. Acknowledge and provide progress updates.
This step is transitional - data generation happens in the backend.
""",

    WizardStep.COMPLETE: """
Generation is complete! Summarize what was created:
- Group ID and name
- Admin user credentials (remind them of default password)
- Supply chain config ID
- Counts of nodes, lanes, products, forecasts, policies

Provide next steps:
1. Log in with the admin credentials
2. Review the supply chain configuration
3. Run a test game or planning cycle
4. Explore the AI agent recommendations
""",

    WizardStep.ERROR: """
An error occurred during generation. Explain the error clearly.
Offer to retry or go back to review settings.
Be helpful and suggest possible causes/solutions.
"""
}


class SyntheticDataWizard:
    """
    Claude-powered wizard for guided synthetic data generation.

    Usage:
        wizard = SyntheticDataWizard()

        # Start a new session
        state, response = await wizard.start_session()

        # Process user messages
        state, response = await wizard.process_message(state, "I want to create a retailer")

        # Continue until complete
        state, response = await wizard.process_message(state, "ACME Retail")
        ...

        # Generate data when ready
        result = await wizard.generate_data(state, db_session)
    """

    def __init__(self, model: str = None):
        """Initialize the wizard with OpenAI-compatible client."""
        self.model = model or os.getenv("LLM_MODEL_NAME") or os.getenv("AUTONOMY_LLM_MODEL") or "qwen3-8b"

        api_key = (
            os.getenv("LLM_API_KEY")
            or os.getenv("OPENAI_API_KEY")
            or "not-needed"
        )
        base_url = os.getenv("LLM_API_BASE")
        kwargs: dict = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        if not base_url and api_key == "not-needed":
            raise ValueError(
                "No LLM provider configured. Set LLM_API_BASE for local LLM "
                "(vLLM/Ollama) or LLM_API_KEY for a hosted API."
            )

        self.client = OpenAI(**kwargs)

        # In-memory session storage (should be replaced with Redis in production)
        self._sessions: Dict[str, WizardState] = {}

    def _generate_session_id(self) -> str:
        """Generate a unique session ID."""
        import uuid
        return str(uuid.uuid4())

    def _build_system_prompt(self, state: WizardState) -> str:
        """Build the system prompt for the current step."""
        step_instructions = STEP_INSTRUCTIONS.get(
            state.current_step,
            "Guide the user through the current step."
        )

        current_config = self._format_current_config(state)

        return WIZARD_SYSTEM_PROMPT.format(
            current_step=state.current_step.value,
            step_instructions=step_instructions,
            current_config=current_config
        )

    def _format_current_config(self, state: WizardState) -> str:
        """Format the current configuration for the prompt."""
        config_items = []

        if state.archetype:
            config_items.append(f"- Archetype: {state.archetype.value}")
        if state.company_name:
            config_items.append(f"- Company Name: {state.company_name}")
        if state.group_name:
            config_items.append(f"- Group Name: {state.group_name}")
        if state.admin_email:
            config_items.append(f"- Admin Email: {state.admin_email}")
        if state.admin_name:
            config_items.append(f"- Admin Name: {state.admin_name}")
        if state.num_sites:
            config_items.append(f"- Number of Sites: {state.num_sites}")
        if state.num_suppliers:
            config_items.append(f"- Number of Suppliers: {state.num_suppliers}")
        if state.num_customers:
            config_items.append(f"- Number of Customers: {state.num_customers}")
        if state.num_products:
            config_items.append(f"- Number of Products: {state.num_products}")
        if state.demand_pattern:
            config_items.append(f"- Demand Pattern: {state.demand_pattern.value}")
        if state.agent_mode:
            config_items.append(f"- Agent Mode: {state.agent_mode.value}")

        if not config_items:
            return "No configuration collected yet."

        return "\n".join(config_items)

    def _get_archetype_defaults(self, archetype: CompanyArchetype) -> Dict[str, Any]:
        """Get default values for an archetype."""
        config = ARCHETYPE_CONFIGS[archetype]
        return {
            "num_sites": sum(t.count for t in config.node_templates if t.master_type in ("INVENTORY", "MANUFACTURER")),
            "num_suppliers": sum(t.count for t in config.node_templates if t.master_type == "MARKET_SUPPLY"),
            "num_customers": sum(t.count for t in config.node_templates if t.master_type == "MARKET_DEMAND"),
            "num_products": config.product_categories * config.product_families_per_category * config.products_per_family,
            "product_categories": config.product_categories,
            "demand_pattern": config.demand_pattern,
            "seasonality_amplitude": config.seasonality_amplitude,
            "agent_mode": config.recommended_agent_mode,
            "agent_strategies": config.agent_strategies,
            "primary_kpis": config.primary_kpis
        }

    async def start_session(self) -> Tuple[WizardState, Dict[str, Any]]:
        """Start a new wizard session."""
        session_id = self._generate_session_id()
        state = WizardState(session_id=session_id)

        # Generate welcome message
        response = await self._call_llm(state, None)

        # Store session
        self._sessions[session_id] = state

        return state, response

    async def process_message(
        self,
        state: WizardState,
        user_message: str
    ) -> Tuple[WizardState, Dict[str, Any]]:
        """Process a user message and update the wizard state."""
        # Add user message to history
        state.messages.append({
            "role": "user",
            "content": user_message
        })

        # Call LLM to process
        response = await self._call_llm(state, user_message)

        # Extract and apply data from response
        extracted = response.get("extracted_data", {})
        self._apply_extracted_data(state, extracted)

        # Handle step transitions
        suggested_next = response.get("suggested_next_step", state.current_step.value)
        if suggested_next == "next_step":
            state = self._advance_step(state)
        elif suggested_next == "previous_step":
            state = self._go_back_step(state)

        # Add assistant response to history
        state.messages.append({
            "role": "assistant",
            "content": response.get("message", "")
        })

        # Update session
        self._sessions[state.session_id] = state

        return state, response

    async def _call_llm(
        self,
        state: WizardState,
        user_message: Optional[str]
    ) -> Dict[str, Any]:
        """Call the LLM with the current context."""
        system_prompt = self._build_system_prompt(state)

        # Inject RAG knowledge base context relevant to the current wizard step
        try:
            from app.services.rag_context import get_rag_context
            rag_query = f"supply chain {state.current_step.value} configuration"
            if state.archetype:
                rag_query += f" {state.archetype.value}"
            if user_message:
                rag_query += f" {user_message[:100]}"
            kb_context = await get_rag_context(rag_query, top_k=3, max_tokens=1500)
            if kb_context:
                system_prompt += f"\n\n## Reference Knowledge\n{kb_context}"
        except Exception as e:
            logger.debug(f"RAG context not available for wizard: {e}")

        messages = [{"role": "system", "content": system_prompt}]

        # Add conversation history
        for msg in state.messages[-10:]:  # Keep last 10 messages for context
            messages.append(msg)

        # Add current user message if provided
        if user_message:
            messages.append({"role": "user", "content": user_message})
        else:
            # For initial message, prompt the assistant to start
            messages.append({"role": "user", "content": "Please start the wizard and guide me."})

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.7,
                max_tokens=1000,
                response_format={"type": "json_object"}
            )

            content = response.choices[0].message.content
            return json.loads(content)

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")
            return {
                "message": "I apologize, but I encountered an error processing your request. Could you please try again?",
                "extracted_data": {},
                "validation_errors": ["Failed to parse response"],
                "suggested_next_step": state.current_step.value,
                "options": []
            }
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return {
                "message": f"I apologize, but I encountered an error: {str(e)}. Please try again.",
                "extracted_data": {},
                "validation_errors": [str(e)],
                "suggested_next_step": state.current_step.value,
                "options": []
            }

    def _apply_extracted_data(self, state: WizardState, extracted: Dict[str, Any]):
        """Apply extracted data to the wizard state."""
        # Archetype
        if "archetype" in extracted:
            try:
                archetype_value = extracted["archetype"].lower()
                state.archetype = CompanyArchetype(archetype_value)
                # Apply archetype defaults
                defaults = self._get_archetype_defaults(state.archetype)
                state.num_sites = state.num_sites or defaults["num_sites"]
                state.num_suppliers = state.num_suppliers or defaults["num_suppliers"]
                state.num_customers = state.num_customers or defaults["num_customers"]
                state.num_products = state.num_products or defaults["num_products"]
                state.product_categories = state.product_categories or defaults["product_categories"]
                state.demand_pattern = state.demand_pattern or defaults["demand_pattern"]
                state.seasonality_amplitude = state.seasonality_amplitude or defaults["seasonality_amplitude"]
                state.agent_mode = state.agent_mode or defaults["agent_mode"]
            except ValueError:
                pass

        # Company details
        if "company_name" in extracted:
            state.company_name = extracted["company_name"]
        if "group_name" in extracted:
            state.group_name = extracted["group_name"]
        if "admin_email" in extracted:
            state.admin_email = extracted["admin_email"]
        if "admin_name" in extracted:
            state.admin_name = extracted["admin_name"]

        # Network config
        if "num_sites" in extracted:
            state.num_sites = int(extracted["num_sites"])
        if "num_suppliers" in extracted:
            state.num_suppliers = int(extracted["num_suppliers"])
        if "num_customers" in extracted:
            state.num_customers = int(extracted["num_customers"])

        # Product config
        if "num_products" in extracted:
            state.num_products = int(extracted["num_products"])
        if "product_categories" in extracted:
            state.product_categories = int(extracted["product_categories"])

        # Demand config
        if "demand_pattern" in extracted:
            try:
                state.demand_pattern = DemandPattern(extracted["demand_pattern"].lower())
            except ValueError:
                pass
        if "seasonality_amplitude" in extracted:
            state.seasonality_amplitude = float(extracted["seasonality_amplitude"])
        if "forecast_horizon_months" in extracted:
            state.forecast_horizon_months = int(extracted["forecast_horizon_months"])

        # Agent config
        if "agent_mode" in extracted:
            try:
                state.agent_mode = AgentMode(extracted["agent_mode"].lower())
            except ValueError:
                pass
        if "enable_gnn" in extracted:
            state.enable_gnn = bool(extracted["enable_gnn"])
        if "enable_llm" in extracted:
            state.enable_llm = bool(extracted["enable_llm"])
        if "enable_trm" in extracted:
            state.enable_trm = bool(extracted["enable_trm"])

    def _advance_step(self, state: WizardState) -> WizardState:
        """Advance to the next wizard step."""
        step_order = [
            WizardStep.WELCOME,
            WizardStep.ARCHETYPE,
            WizardStep.COMPANY_DETAILS,
            WizardStep.NETWORK_CONFIG,
            WizardStep.PRODUCT_CONFIG,
            WizardStep.DEMAND_CONFIG,
            WizardStep.AGENT_CONFIG,
            WizardStep.REVIEW
        ]

        try:
            current_idx = step_order.index(state.current_step)
            if current_idx < len(step_order) - 1:
                state.current_step = step_order[current_idx + 1]
        except ValueError:
            pass

        return state

    def _go_back_step(self, state: WizardState) -> WizardState:
        """Go back to the previous wizard step."""
        step_order = [
            WizardStep.WELCOME,
            WizardStep.ARCHETYPE,
            WizardStep.COMPANY_DETAILS,
            WizardStep.NETWORK_CONFIG,
            WizardStep.PRODUCT_CONFIG,
            WizardStep.DEMAND_CONFIG,
            WizardStep.AGENT_CONFIG,
            WizardStep.REVIEW
        ]

        try:
            current_idx = step_order.index(state.current_step)
            if current_idx > 0:
                state.current_step = step_order[current_idx - 1]
        except ValueError:
            pass

        return state

    def get_session(self, session_id: str) -> Optional[WizardState]:
        """Retrieve a session by ID."""
        return self._sessions.get(session_id)

    def validate_for_generation(self, state: WizardState) -> Tuple[bool, List[str]]:
        """Validate that the state has all required data for generation."""
        errors = []

        if not state.archetype:
            errors.append("Company archetype is required")
        if not state.company_name:
            errors.append("Company name is required")
        if not state.group_name:
            errors.append("Group name is required")
        if not state.admin_email:
            errors.append("Admin email is required")
        if not state.admin_name:
            errors.append("Admin name is required")

        # Validate email format
        if state.admin_email and "@" not in state.admin_email:
            errors.append("Invalid email format")

        return len(errors) == 0, errors

    def build_generation_request(self, state: WizardState) -> GenerationRequest:
        """Build a GenerationRequest from the wizard state."""
        return GenerationRequest(
            group_name=state.group_name,
            archetype=state.archetype,
            company_name=state.company_name,
            admin_email=state.admin_email,
            admin_name=state.admin_name,
            num_products=state.num_products,
            num_sites=state.num_sites,
            num_suppliers=state.num_suppliers,
            num_customers=state.num_customers,
            agent_mode=state.agent_mode,
            enable_gnn=state.enable_gnn,
            enable_llm=state.enable_llm,
            enable_trm=state.enable_trm,
            forecast_horizon_months=state.forecast_horizon_months
        )

    async def generate_data(
        self,
        state: WizardState,
        db_session
    ) -> Tuple[WizardState, Dict[str, Any]]:
        """Generate the synthetic data based on wizard state."""
        # Validate
        is_valid, errors = self.validate_for_generation(state)
        if not is_valid:
            state.current_step = WizardStep.ERROR
            state.error = "; ".join(errors)
            return state, {
                "message": f"Cannot generate data: {state.error}",
                "success": False,
                "errors": errors
            }

        state.current_step = WizardStep.GENERATING

        try:
            # Build request
            request = self.build_generation_request(state)

            # Generate data
            generator = SyntheticDataGenerator(db_session)
            result = await generator.generate(request)

            # Update state
            state.current_step = WizardStep.COMPLETE
            state.result = {
                "group_id": result.group_id,
                "config_id": result.config_id,
                "admin_user_id": result.admin_user_id,
                "nodes_created": result.nodes_created,
                "lanes_created": result.lanes_created,
                "products_created": result.products_created,
                "forecasts_created": result.forecasts_created,
                "policies_created": result.policies_created,
                "summary": result.summary
            }

            # Generate completion message
            completion_response = await self._call_llm(state, "Data generation complete. Please summarize what was created.")

            return state, {
                "message": completion_response.get("message", "Data generation complete!"),
                "success": True,
                "result": state.result
            }

        except Exception as e:
            logger.error(f"Data generation failed: {e}")
            state.current_step = WizardStep.ERROR
            state.error = str(e)

            return state, {
                "message": f"Data generation failed: {str(e)}",
                "success": False,
                "error": str(e)
            }

    def get_quick_options(self, state: WizardState) -> List[Dict[str, str]]:
        """Get quick selection options for the current step."""
        options = []

        if state.current_step == WizardStep.WELCOME:
            options = [
                {"value": "retailer", "label": "Retailer", "description": "Multi-channel retail operations"},
                {"value": "distributor", "label": "Distributor", "description": "Wholesale distribution"},
                {"value": "manufacturer", "label": "Manufacturer", "description": "Production-focused operations"}
            ]
        elif state.current_step == WizardStep.DEMAND_CONFIG:
            options = [
                {"value": "constant", "label": "Constant", "description": "Steady demand"},
                {"value": "seasonal", "label": "Seasonal", "description": "Cyclical patterns"},
                {"value": "trending", "label": "Trending", "description": "Growth or decline"},
                {"value": "promotional", "label": "Promotional", "description": "Spike-driven"},
                {"value": "random", "label": "Random", "description": "Unpredictable"}
            ]
        elif state.current_step == WizardStep.AGENT_CONFIG:
            options = [
                {"value": "none", "label": "None", "description": "No AI assistance"},
                {"value": "copilot", "label": "Copilot", "description": "AI suggests, human approves"},
                {"value": "autonomous", "label": "Autonomous", "description": "AI decides within guardrails"}
            ]

        return options


# Convenience function for API endpoints
async def create_wizard_session() -> Tuple[str, Dict[str, Any]]:
    """Create a new wizard session and return the session ID and initial response."""
    wizard = SyntheticDataWizard()
    state, response = await wizard.start_session()
    return state.session_id, {
        "session_id": state.session_id,
        "step": state.current_step.value,
        "message": response.get("message", ""),
        "options": response.get("options", []),
        "state": state.to_dict()
    }
