"""
Stochastic Distribution API Endpoints

Endpoints for working with stochastic distributions:
- Generate distribution previews (sample data)
- Validate distribution configurations
- Get distribution statistics
- Get available distribution types

Used by the admin UI for visualizing and configuring distributions.
"""

from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
import numpy as np

from app.services.stochastic import DistributionEngine
from app.api.deps import get_current_user
from app.models.user import User

router = APIRouter(prefix="/stochastic", tags=["stochastic"])


# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================

class DistributionPreviewRequest(BaseModel):
    """Request to generate distribution preview samples"""
    config: Dict[str, Any] = Field(..., description="Distribution configuration (JSON)")
    num_samples: int = Field(1000, description="Number of samples to generate", ge=100, le=10000)
    seed: Optional[int] = Field(None, description="Random seed for reproducibility")


class DistributionPreviewResponse(BaseModel):
    """Response with distribution preview samples and statistics"""
    samples: List[float] = Field(..., description="Generated samples")
    stats: Dict[str, float] = Field(..., description="Summary statistics")
    config: Dict[str, Any] = Field(..., description="Distribution configuration used")


class DistributionValidateRequest(BaseModel):
    """Request to validate distribution configuration"""
    config: Dict[str, Any] = Field(..., description="Distribution configuration to validate")


class DistributionValidateResponse(BaseModel):
    """Response with validation result"""
    valid: bool = Field(..., description="Whether configuration is valid")
    errors: List[str] = Field(default_factory=list, description="Validation errors if invalid")
    warnings: List[str] = Field(default_factory=list, description="Validation warnings")


class DistributionTypeInfo(BaseModel):
    """Information about a distribution type"""
    type: str = Field(..., description="Distribution type identifier")
    name: str = Field(..., description="Human-readable name")
    description: str = Field(..., description="Description of the distribution")
    parameters: List[Dict[str, Any]] = Field(..., description="Required/optional parameters")
    category: str = Field(..., description="Distribution category")


class DistributionTypesResponse(BaseModel):
    """Response with available distribution types"""
    types: List[DistributionTypeInfo] = Field(..., description="Available distribution types")


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def calculate_statistics(samples: np.ndarray) -> Dict[str, float]:
    """Calculate summary statistics from samples"""
    sorted_samples = np.sort(samples)
    n = len(sorted_samples)

    return {
        "count": int(n),
        "mean": float(np.mean(samples)),
        "std": float(np.std(samples)),
        "min": float(np.min(samples)),
        "max": float(np.max(samples)),
        "median": float(np.median(samples)),
        "p5": float(sorted_samples[int(n * 0.05)]),
        "p25": float(sorted_samples[int(n * 0.25)]),
        "p75": float(sorted_samples[int(n * 0.75)]),
        "p95": float(sorted_samples[int(n * 0.95)]),
    }


def validate_distribution_config(config: Dict[str, Any]) -> tuple[bool, List[str], List[str]]:
    """
    Validate distribution configuration

    Returns:
        (valid, errors, warnings)
    """
    errors = []
    warnings = []

    # Check required fields
    if not config:
        errors.append("Configuration is empty")
        return False, errors, warnings

    if "type" not in config:
        errors.append("Missing required field: 'type'")
        return False, errors, warnings

    dist_type = config["type"]

    # Validate based on distribution type
    if dist_type == "deterministic":
        if "value" not in config:
            errors.append("Deterministic distribution requires 'value' parameter")

    elif dist_type == "uniform":
        if "min" not in config or "max" not in config:
            errors.append("Uniform distribution requires 'min' and 'max' parameters")
        elif config["min"] >= config["max"]:
            errors.append("'min' must be less than 'max'")

    elif dist_type in ["normal", "truncated_normal"]:
        if "mean" not in config:
            errors.append(f"{dist_type} distribution requires 'mean' parameter")
        if "stddev" not in config:
            errors.append(f"{dist_type} distribution requires 'stddev' parameter")
        elif config.get("stddev", 1) <= 0:
            errors.append("'stddev' must be positive")

        if dist_type == "truncated_normal":
            if "min" not in config or "max" not in config:
                errors.append("Truncated normal requires 'min' and 'max' parameters")
            elif config.get("min", 0) >= config.get("max", 1):
                errors.append("'min' must be less than 'max'")

    elif dist_type == "lognormal":
        if "mean_log" not in config:
            errors.append("Lognormal distribution requires 'mean_log' parameter")
        if "stddev_log" not in config:
            errors.append("Lognormal distribution requires 'stddev_log' parameter")
        elif config.get("stddev_log", 1) <= 0:
            errors.append("'stddev_log' must be positive")

    elif dist_type == "gamma":
        if "shape" not in config or "scale" not in config:
            errors.append("Gamma distribution requires 'shape' and 'scale' parameters")
        if config.get("shape", 1) <= 0:
            errors.append("'shape' must be positive")
        if config.get("scale", 1) <= 0:
            errors.append("'scale' must be positive")

    elif dist_type == "beta":
        if "alpha" not in config or "beta" not in config:
            errors.append("Beta distribution requires 'alpha' and 'beta' parameters")
        if config.get("alpha", 1) <= 0:
            errors.append("'alpha' must be positive")
        if config.get("beta", 1) <= 0:
            errors.append("'beta' must be positive")

    elif dist_type == "poisson":
        if "lambda" not in config:
            errors.append("Poisson distribution requires 'lambda' parameter")
        elif config.get("lambda", 1) <= 0:
            errors.append("'lambda' must be positive")

    elif dist_type == "mixture":
        if "components" not in config:
            errors.append("Mixture distribution requires 'components' parameter")
        else:
            components = config["components"]
            if not isinstance(components, list) or len(components) == 0:
                errors.append("'components' must be a non-empty list")
            else:
                # Validate weights sum to 1
                total_weight = sum(c.get("weight", 0) for c in components)
                if abs(total_weight - 1.0) > 0.001:
                    warnings.append(f"Component weights sum to {total_weight:.3f}, should be 1.0")

                # Validate each component
                for i, component in enumerate(components):
                    if "weight" not in component:
                        errors.append(f"Component {i} missing 'weight'")
                    if "distribution" not in component:
                        errors.append(f"Component {i} missing 'distribution'")

    else:
        warnings.append(f"Unknown distribution type: '{dist_type}'. Validation may be incomplete.")

    valid = len(errors) == 0
    return valid, errors, warnings


# ============================================================================
# API ENDPOINTS
# ============================================================================

@router.post("/preview", response_model=DistributionPreviewResponse)
async def generate_distribution_preview(
    request: DistributionPreviewRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Generate preview samples for a distribution configuration

    Creates sample data for visualizing the distribution shape and statistics.
    Used by the admin UI to show distribution previews.

    Requires authentication.
    """
    try:
        # Validate configuration first
        valid, errors, warnings = validate_distribution_config(request.config)
        if not valid:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid distribution configuration: {'; '.join(errors)}"
            )

        # Create distribution engine
        engine = DistributionEngine(seed=request.seed)

        # Sample from distribution
        samples_dict = engine.sample(
            variable_configs={"preview": request.config},
            size=request.num_samples
        )

        samples = samples_dict["preview"]

        # Calculate statistics
        stats = calculate_statistics(samples)

        return DistributionPreviewResponse(
            samples=samples.tolist(),
            stats=stats,
            config=request.config
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate preview: {str(e)}"
        )


@router.post("/validate", response_model=DistributionValidateResponse)
async def validate_distribution(
    request: DistributionValidateRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Validate a distribution configuration

    Checks if the configuration is valid and returns any errors or warnings.

    Requires authentication.
    """
    try:
        valid, errors, warnings = validate_distribution_config(request.config)

        return DistributionValidateResponse(
            valid=valid,
            errors=errors,
            warnings=warnings
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to validate configuration: {str(e)}"
        )


@router.get("/types", response_model=DistributionTypesResponse)
async def get_distribution_types(
    current_user: User = Depends(get_current_user)
):
    """
    Get available distribution types

    Returns metadata about all supported distribution types,
    including parameters and descriptions.

    Requires authentication.
    """
    # Distribution type definitions
    types = [
        DistributionTypeInfo(
            type="deterministic",
            name="Deterministic",
            description="Fixed value (no uncertainty)",
            parameters=[
                {"name": "value", "type": "number", "required": True, "description": "Fixed value"}
            ],
            category="Basic"
        ),
        DistributionTypeInfo(
            type="uniform",
            name="Uniform",
            description="All values equally likely between min and max",
            parameters=[
                {"name": "min", "type": "number", "required": True, "description": "Minimum value"},
                {"name": "max", "type": "number", "required": True, "description": "Maximum value"}
            ],
            category="Basic"
        ),
        DistributionTypeInfo(
            type="normal",
            name="Normal (Gaussian)",
            description="Bell-shaped distribution with mean and standard deviation",
            parameters=[
                {"name": "mean", "type": "number", "required": True, "description": "Mean (center)"},
                {"name": "stddev", "type": "number", "required": True, "description": "Standard deviation"},
                {"name": "min", "type": "number", "required": False, "description": "Minimum bound (optional)"},
                {"name": "max", "type": "number", "required": False, "description": "Maximum bound (optional)"}
            ],
            category="Symmetric"
        ),
        DistributionTypeInfo(
            type="truncated_normal",
            name="Truncated Normal",
            description="Normal distribution with hard bounds",
            parameters=[
                {"name": "mean", "type": "number", "required": True, "description": "Mean (center)"},
                {"name": "stddev", "type": "number", "required": True, "description": "Standard deviation"},
                {"name": "min", "type": "number", "required": True, "description": "Minimum bound"},
                {"name": "max", "type": "number", "required": True, "description": "Maximum bound"}
            ],
            category="Symmetric"
        ),
        DistributionTypeInfo(
            type="lognormal",
            name="Lognormal",
            description="Right-skewed distribution (good for lead times, repair times)",
            parameters=[
                {"name": "mean_log", "type": "number", "required": True, "description": "Mean in log scale"},
                {"name": "stddev_log", "type": "number", "required": True, "description": "Std dev in log scale"},
                {"name": "min", "type": "number", "required": False, "description": "Minimum bound (optional)"},
                {"name": "max", "type": "number", "required": False, "description": "Maximum bound (optional)"}
            ],
            category="Right-Skewed"
        ),
        DistributionTypeInfo(
            type="gamma",
            name="Gamma",
            description="Flexible right-skewed distribution",
            parameters=[
                {"name": "shape", "type": "number", "required": True, "description": "Shape parameter (α)"},
                {"name": "scale", "type": "number", "required": True, "description": "Scale parameter (θ)"},
                {"name": "min", "type": "number", "required": False, "description": "Minimum bound (optional)"}
            ],
            category="Right-Skewed"
        ),
        DistributionTypeInfo(
            type="beta",
            name="Beta",
            description="Bounded [0,1] distribution (good for yields, percentages)",
            parameters=[
                {"name": "alpha", "type": "number", "required": True, "description": "Alpha parameter"},
                {"name": "beta", "type": "number", "required": True, "description": "Beta parameter"},
                {"name": "min", "type": "number", "required": False, "description": "Rescale minimum (default 0)"},
                {"name": "max", "type": "number", "required": False, "description": "Rescale maximum (default 1)"}
            ],
            category="Bounded"
        ),
        DistributionTypeInfo(
            type="poisson",
            name="Poisson",
            description="Discrete count distribution (good for demand, arrivals)",
            parameters=[
                {"name": "lambda", "type": "number", "required": True, "description": "Mean (λ)"}
            ],
            category="Discrete"
        ),
        DistributionTypeInfo(
            type="mixture",
            name="Mixture",
            description="Combination of multiple distributions (e.g., normal + disruptions)",
            parameters=[
                {"name": "components", "type": "array", "required": True, "description": "List of {weight, distribution} components"}
            ],
            category="Advanced"
        ),
    ]

    return DistributionTypesResponse(types=types)
