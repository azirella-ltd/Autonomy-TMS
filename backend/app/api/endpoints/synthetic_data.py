"""
Synthetic Data Generation API Endpoints

Provides API endpoints for:
1. Claude-powered wizard for guided synthetic data generation
2. Direct synthetic data generation for automated testing
3. Archetype information and templates
"""

import logging
from typing import Dict, List, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from pydantic import BaseModel, Field, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db as get_async_session
from app.core.security import get_current_user
from app.models.user import User, UserTypeEnum
from app.services.synthetic_data_generator import (
    CompanyArchetype,
    AgentMode,
    DemandPattern,
    GenerationRequest,
    SyntheticDataGenerator,
    get_archetype_info,
    list_archetypes
)
from app.services.synthetic_data_wizard import (
    SyntheticDataWizard,
    WizardState,
    WizardStep
)

logger = logging.getLogger(__name__)

router = APIRouter()

# In-memory session storage (production should use Redis)
_wizard_sessions: Dict[str, WizardState] = {}
_wizard_instance: Optional[SyntheticDataWizard] = None


def get_wizard() -> SyntheticDataWizard:
    """Get or create the wizard instance."""
    global _wizard_instance
    if _wizard_instance is None:
        _wizard_instance = SyntheticDataWizard()
    return _wizard_instance


# ============================================================================
# Pydantic Schemas
# ============================================================================

class ArchetypeInfoResponse(BaseModel):
    """Information about a company archetype."""
    archetype: str
    description: str
    recommended_agent_mode: str
    agent_strategies: List[str]
    primary_kpis: List[str]
    default_safety_stock_days: int
    default_service_level: float
    node_types: List[str]
    product_categories: int
    regions: int


class WizardSessionResponse(BaseModel):
    """Response for wizard session operations."""
    session_id: str
    step: str
    message: str
    options: List[Dict[str, Any]] = Field(default_factory=list)
    state: Dict[str, Any]
    extracted_data: Dict[str, Any] = Field(default_factory=dict)
    validation_errors: List[str] = Field(default_factory=list)


class WizardMessageRequest(BaseModel):
    """Request to send a message to the wizard."""
    message: str = Field(..., min_length=1, max_length=2000)


class DirectGenerationRequest(BaseModel):
    """Request for direct (non-wizard) data generation."""
    tenant_name: str = Field(..., min_length=1, max_length=100)
    company_name: str = Field(..., min_length=1, max_length=100)
    archetype: str = Field(..., description="Company archetype: retailer, distributor, or manufacturer")
    admin_email: EmailStr
    admin_name: str = Field(..., min_length=1, max_length=100)

    # Optional customization
    num_products: Optional[int] = Field(None, ge=1, le=10000)
    num_sites: Optional[int] = Field(None, ge=1, le=500)
    num_suppliers: Optional[int] = Field(None, ge=1, le=100)
    num_customers: Optional[int] = Field(None, ge=1, le=500)

    # Agent configuration
    agent_mode: str = Field("copilot", description="Agent mode: none, copilot, or autonomous")
    enable_gnn: bool = True
    enable_llm: bool = True
    enable_trm: bool = True

    # Forecast configuration
    forecast_horizon_months: int = Field(12, ge=1, le=60)

    # Seed for reproducibility
    random_seed: Optional[int] = None


class GenerationResultResponse(BaseModel):
    """Response for data generation result."""
    success: bool
    tenant_id: Optional[int] = None
    config_id: Optional[int] = None
    admin_user_id: Optional[int] = None
    nodes_created: Optional[int] = None
    lanes_created: Optional[int] = None
    products_created: Optional[int] = None
    forecasts_created: Optional[int] = None
    policies_created: Optional[int] = None
    summary: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


# ============================================================================
# Archetype Information Endpoints
# ============================================================================

@router.get(
    "/archetypes",
    response_model=List[ArchetypeInfoResponse],
    summary="List company archetypes",
    description="Get information about all available company archetypes"
)
async def get_archetypes(
    current_user: User = Depends(get_current_user)
):
    """
    List all available company archetypes.

    Returns information about:
    - Retailer: Multi-channel retail operations
    - Distributor: Wholesale distribution
    - Manufacturer: Production-focused operations
    """
    return list_archetypes()


@router.get(
    "/archetypes/{archetype}",
    response_model=ArchetypeInfoResponse,
    summary="Get archetype details",
    description="Get detailed information about a specific company archetype"
)
async def get_archetype_details(
    archetype: str,
    current_user: User = Depends(get_current_user)
):
    """
    Get detailed information about a specific company archetype.

    **Path Parameters:**
    - `archetype`: One of "retailer", "distributor", or "manufacturer"
    """
    try:
        archetype_enum = CompanyArchetype(archetype.lower())
        return get_archetype_info(archetype_enum)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid archetype: {archetype}. Must be one of: retailer, distributor, manufacturer"
        )


# ============================================================================
# Wizard Session Endpoints
# ============================================================================

@router.post(
    "/wizard/sessions",
    response_model=WizardSessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Start wizard session",
    description="Start a new synthetic data generation wizard session"
)
async def start_wizard_session(
    current_user: User = Depends(get_current_user)
):
    """
    Start a new wizard session.

    The wizard guides you through creating synthetic supply chain data
    for testing and demonstration. The conversation follows these steps:

    1. **Welcome & Archetype Selection**: Choose company type
    2. **Company Details**: Name, admin user information
    3. **Network Configuration**: Sites, suppliers, customers
    4. **Product Configuration**: SKUs, categories
    5. **Demand Configuration**: Patterns, seasonality
    6. **Agent Configuration**: AI assistance settings
    7. **Review & Generate**: Final confirmation and creation
    """
    if current_user.user_type not in (UserTypeEnum.SYSTEM_ADMIN, UserTypeEnum.TENANT_ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only system administrators can create synthetic data"
        )

    try:
        wizard = get_wizard()
        state, response = await wizard.start_session()

        # Store session
        _wizard_sessions[state.session_id] = state

        return WizardSessionResponse(
            session_id=state.session_id,
            step=state.current_step.value,
            message=response.get("message", ""),
            options=response.get("options", []),
            state=state.to_dict(),
            extracted_data=response.get("extracted_data", {}),
            validation_errors=response.get("validation_errors", [])
        )

    except Exception as e:
        logger.error(f"Failed to start wizard session: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start wizard session: {str(e)}"
        )


@router.get(
    "/wizard/sessions/{session_id}",
    response_model=WizardSessionResponse,
    summary="Get wizard session",
    description="Get the current state of a wizard session"
)
async def get_wizard_session(
    session_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Get the current state of a wizard session.

    Returns the session state including:
    - Current step in the wizard flow
    - Collected configuration data
    - Conversation history
    """
    if current_user.user_type not in (UserTypeEnum.SYSTEM_ADMIN, UserTypeEnum.TENANT_ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only system administrators can access wizard sessions"
        )

    state = _wizard_sessions.get(session_id)
    if not state:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found"
        )

    wizard = get_wizard()
    options = wizard.get_quick_options(state)

    return WizardSessionResponse(
        session_id=state.session_id,
        step=state.current_step.value,
        message="",
        options=options,
        state=state.to_dict(),
        extracted_data={},
        validation_errors=[]
    )


@router.post(
    "/wizard/sessions/{session_id}/messages",
    response_model=WizardSessionResponse,
    summary="Send message to wizard",
    description="Send a message to the wizard and receive a response"
)
async def send_wizard_message(
    session_id: str,
    request: WizardMessageRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Send a message to the wizard.

    The wizard will:
    1. Interpret your message based on the current step
    2. Extract relevant configuration data
    3. Validate the data
    4. Respond with guidance or confirmation
    5. Optionally advance to the next step

    **Example Messages:**
    - "I want to create a retailer company"
    - "The company name is ACME Retail"
    - "Use 100 products instead of the default"
    - "Enable autonomous agent mode"
    """
    if current_user.user_type not in (UserTypeEnum.SYSTEM_ADMIN, UserTypeEnum.TENANT_ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only system administrators can use wizard sessions"
        )

    state = _wizard_sessions.get(session_id)
    if not state:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found"
        )

    try:
        wizard = get_wizard()
        state, response = await wizard.process_message(state, request.message)

        # Update stored session
        _wizard_sessions[session_id] = state

        options = wizard.get_quick_options(state)

        return WizardSessionResponse(
            session_id=state.session_id,
            step=state.current_step.value,
            message=response.get("message", ""),
            options=options if not response.get("options") else response.get("options"),
            state=state.to_dict(),
            extracted_data=response.get("extracted_data", {}),
            validation_errors=response.get("validation_errors", [])
        )

    except Exception as e:
        logger.error(f"Failed to process wizard message: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process message: {str(e)}"
        )


@router.post(
    "/wizard/sessions/{session_id}/generate",
    response_model=GenerationResultResponse,
    summary="Generate data from wizard",
    description="Generate synthetic data based on the wizard session configuration"
)
async def generate_from_wizard(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Generate synthetic data based on the wizard session.

    The wizard must have collected all required information:
    - Archetype
    - Company name
    - Group name
    - Admin email and name

    **What Gets Created:**
    - Group (organization)
    - Admin user with default password "Autonomy@2026"
    - Supply chain configuration (nodes, lanes, items)
    - Site and product hierarchies
    - Forecasts and inventory levels
    - Inventory policies
    - Planning hierarchy configurations
    - AI agent configurations
    """
    if current_user.user_type not in (UserTypeEnum.SYSTEM_ADMIN, UserTypeEnum.TENANT_ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only system administrators can generate synthetic data"
        )

    state = _wizard_sessions.get(session_id)
    if not state:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found"
        )

    try:
        wizard = get_wizard()

        # Validate
        is_valid, errors = wizard.validate_for_generation(state)
        if not is_valid:
            return GenerationResultResponse(
                success=False,
                error="; ".join(errors)
            )

        # Generate
        state, result = await wizard.generate_data(state, db)

        # Update stored session
        _wizard_sessions[session_id] = state

        if result.get("success"):
            return GenerationResultResponse(
                success=True,
                **result.get("result", {})
            )
        else:
            return GenerationResultResponse(
                success=False,
                error=result.get("error", "Unknown error")
            )

    except Exception as e:
        logger.error(f"Failed to generate data: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate data: {str(e)}"
        )


@router.delete(
    "/wizard/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete wizard session",
    description="Delete a wizard session"
)
async def delete_wizard_session(
    session_id: str,
    current_user: User = Depends(get_current_user)
):
    """Delete a wizard session."""
    if current_user.user_type not in (UserTypeEnum.SYSTEM_ADMIN, UserTypeEnum.TENANT_ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only system administrators can delete wizard sessions"
        )

    if session_id in _wizard_sessions:
        del _wizard_sessions[session_id]


# ============================================================================
# Direct Generation Endpoints
# ============================================================================

@router.post(
    "/generate",
    response_model=GenerationResultResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate synthetic data directly",
    description="Generate synthetic data without using the wizard"
)
async def generate_synthetic_data(
    request: DirectGenerationRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Generate synthetic data directly without the wizard.

    This endpoint is useful for automated testing or when you
    know exactly what configuration you want.

    **Required Fields:**
    - `tenant_name`: Organization name
    - `company_name`: Company name for supply chain config
    - `archetype`: "retailer", "distributor", or "manufacturer"
    - `admin_email`: Email for the admin user
    - `admin_name`: Full name for the admin user

    **Optional Customization:**
    - `num_products`: Override default product count
    - `num_sites`: Override default site count
    - `num_suppliers`: Override default supplier count
    - `num_customers`: Override default customer count
    - `agent_mode`: "none", "copilot", or "autonomous"
    - `enable_gnn/llm/trm`: Enable specific AI agents
    """
    if current_user.user_type not in (UserTypeEnum.SYSTEM_ADMIN, UserTypeEnum.TENANT_ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only system administrators can generate synthetic data"
        )

    try:
        archetype = CompanyArchetype(request.archetype.lower())
        agent_mode = AgentMode(request.agent_mode.lower())
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

    try:
        gen_request = GenerationRequest(
            tenant_name=request.tenant_name,
            archetype=archetype,
            company_name=request.company_name,
            admin_email=request.admin_email,
            admin_name=request.admin_name,
            num_products=request.num_products,
            num_sites=request.num_sites,
            num_suppliers=request.num_suppliers,
            num_customers=request.num_customers,
            agent_mode=agent_mode,
            enable_gnn=request.enable_gnn,
            enable_llm=request.enable_llm,
            enable_trm=request.enable_trm,
            forecast_horizon_months=request.forecast_horizon_months,
            random_seed=request.random_seed
        )

        generator = SyntheticDataGenerator(db)
        result = await generator.generate(gen_request)

        return GenerationResultResponse(
            success=True,
            tenant_id=result.tenant_id,
            config_id=result.config_id,
            admin_user_id=result.admin_user_id,
            nodes_created=result.nodes_created,
            lanes_created=result.lanes_created,
            products_created=result.products_created,
            forecasts_created=result.forecasts_created,
            policies_created=result.policies_created,
            summary=result.summary
        )

    except Exception as e:
        logger.error(f"Failed to generate synthetic data: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate data: {str(e)}"
        )


# ============================================================================
# Utility Endpoints
# ============================================================================

@router.get(
    "/defaults/{archetype}",
    summary="Get archetype defaults",
    description="Get default configuration values for an archetype"
)
async def get_archetype_defaults(
    archetype: str,
    current_user: User = Depends(get_current_user)
):
    """
    Get default configuration values for a company archetype.

    Returns sensible defaults for:
    - Network topology (sites, suppliers, customers)
    - Product structure
    - Demand patterns
    - Agent configuration
    """
    try:
        archetype_enum = CompanyArchetype(archetype.lower())
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid archetype: {archetype}"
        )

    wizard = get_wizard()
    defaults = wizard._get_archetype_defaults(archetype_enum)

    # Convert enums to strings for JSON serialization
    return {
        "archetype": archetype_enum.value,
        "num_sites": defaults["num_sites"],
        "num_suppliers": defaults["num_suppliers"],
        "num_customers": defaults["num_customers"],
        "num_products": defaults["num_products"],
        "product_categories": defaults["product_categories"],
        "demand_pattern": defaults["demand_pattern"].value,
        "seasonality_amplitude": defaults["seasonality_amplitude"],
        "agent_mode": defaults["agent_mode"].value,
        "agent_strategies": defaults["agent_strategies"],
        "primary_kpis": defaults["primary_kpis"]
    }
