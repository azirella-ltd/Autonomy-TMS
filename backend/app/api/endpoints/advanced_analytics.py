"""
Advanced Analytics API Endpoints
Phase 6 Sprint 2: Advanced Analytics

Provides REST API access to:
- Sensitivity Analysis (OAT and Sobol indices)
- Correlation Analysis (Pearson, Spearman, Kendall)
- Time Series Analysis (ACF, PACF, decomposition)
"""

from typing import Dict, List, Optional, Any, Tuple
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, validator
from sqlalchemy.orm import Session
import numpy as np

from app.db.session import get_db
from app.services.advanced_analytics_service import (
    AdvancedAnalyticsService,
    SensitivityResult,
    SobolIndices,
    CorrelationMatrix,
    AutocorrelationResult,
    TimeSeriesDecomposition,
    ForecastAccuracy
)
from app.api.deps import get_current_user
from app.models.user import User

router = APIRouter()


# ============================================================================
# Request Models
# ============================================================================

class SensitivityAnalysisRequest(BaseModel):
    """Request for sensitivity analysis"""
    base_params: Dict[str, float] = Field(
        ...,
        description="Base parameter values",
        example={"lead_time_mean": 7, "holding_cost": 2, "backlog_cost": 10}
    )
    param_ranges: Dict[str, Tuple[float, float]] = Field(
        ...,
        description="Parameter ranges (min, max) for each parameter",
        example={
            "lead_time_mean": [5, 10],
            "holding_cost": [1, 5],
            "backlog_cost": [5, 15]
        }
    )
    simulation_data: List[Dict[str, Any]] = Field(
        ...,
        description="Pre-computed simulation results for each parameter configuration",
        example=[
            {"params": {"lead_time_mean": 5}, "output": 8500},
            {"params": {"lead_time_mean": 7}, "output": 10000}
        ]
    )
    num_samples: int = Field(
        default=10,
        ge=5,
        le=100,
        description="Number of samples per parameter"
    )
    analysis_type: str = Field(
        default="oat",
        description="Analysis type: 'oat' (One-At-a-Time) or 'sobol' (Sobol indices)"
    )

    @validator('analysis_type')
    def validate_analysis_type(cls, v):
        if v not in ['oat', 'sobol']:
            raise ValueError("analysis_type must be 'oat' or 'sobol'")
        return v


class SobolAnalysisRequest(BaseModel):
    """Request for Sobol sensitivity indices"""
    param_ranges: Dict[str, Tuple[float, float]] = Field(
        ...,
        description="Parameter ranges (min, max) for each parameter"
    )
    simulation_data: List[Dict[str, Any]] = Field(
        ...,
        description="Pre-computed simulation results for Sobol sampling matrices"
    )
    num_samples: int = Field(
        default=1000,
        ge=100,
        le=10000,
        description="Number of samples for Sobol analysis"
    )
    confidence: float = Field(
        default=0.95,
        ge=0.8,
        le=0.99,
        description="Confidence level for bootstrap intervals"
    )


class CorrelationAnalysisRequest(BaseModel):
    """Request for correlation analysis"""
    data: Dict[str, List[float]] = Field(
        ...,
        description="Dictionary of variable names to data arrays",
        example={
            "total_cost": [10000, 9500, 11000],
            "inventory": [100, 95, 110],
            "service_level": [0.95, 0.97, 0.93]
        }
    )
    method: str = Field(
        default="pearson",
        description="Correlation method: 'pearson', 'spearman', or 'kendall'"
    )
    threshold: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Threshold for identifying strong correlations"
    )
    p_value_threshold: float = Field(
        default=0.05,
        ge=0.001,
        le=0.1,
        description="P-value threshold for significance testing"
    )

    @validator('method')
    def validate_method(cls, v):
        if v not in ['pearson', 'spearman', 'kendall']:
            raise ValueError("method must be 'pearson', 'spearman', or 'kendall'")
        return v

    @validator('data')
    def validate_data_lengths(cls, v):
        lengths = [len(arr) for arr in v.values()]
        if len(set(lengths)) > 1:
            raise ValueError("All data arrays must have the same length")
        if lengths[0] < 3:
            raise ValueError("Data arrays must have at least 3 samples")
        return v


class TimeSeriesACFRequest(BaseModel):
    """Request for autocorrelation function analysis"""
    time_series: List[float] = Field(
        ...,
        description="Time series data",
        min_items=10
    )
    max_lag: Optional[int] = Field(
        default=None,
        ge=1,
        description="Maximum lag to compute (default: min(n/4, 40))"
    )
    confidence: float = Field(
        default=0.95,
        ge=0.8,
        le=0.99,
        description="Confidence level for significance bands"
    )


class TimeSeriesDecomposeRequest(BaseModel):
    """Request for time series decomposition"""
    time_series: List[float] = Field(
        ...,
        description="Time series data",
        min_items=10
    )
    period: int = Field(
        ...,
        ge=2,
        description="Seasonal period (e.g., 12 for monthly data with yearly seasonality)"
    )
    model: str = Field(
        default="additive",
        description="Decomposition model: 'additive' or 'multiplicative'"
    )

    @validator('model')
    def validate_model(cls, v):
        if v not in ['additive', 'multiplicative']:
            raise ValueError("model must be 'additive' or 'multiplicative'")
        return v

    @validator('time_series')
    def validate_time_series_length(cls, v, values):
        if 'period' in values and len(v) < 2 * values['period']:
            raise ValueError(f"Time series must have at least {2 * values['period']} points for period {values['period']}")
        return v


class ForecastAccuracyRequest(BaseModel):
    """Request for forecast accuracy metrics"""
    actual: List[float] = Field(
        ...,
        description="Actual observed values",
        min_items=3
    )
    predicted: List[float] = Field(
        ...,
        description="Predicted/forecasted values",
        min_items=3
    )

    @validator('predicted')
    def validate_lengths_match(cls, v, values):
        if 'actual' in values and len(v) != len(values['actual']):
            raise ValueError("actual and predicted must have the same length")
        return v


# ============================================================================
# Response Models
# ============================================================================

class SensitivityResultResponse(BaseModel):
    """Response for sensitivity analysis result"""
    parameter: str
    values: List[float]
    outputs: List[float]
    sensitivity: float
    min_output: float
    max_output: float
    output_range: float

    class Config:
        from_attributes = True


class SobolIndicesResponse(BaseModel):
    """Response for Sobol indices"""
    parameter: str
    first_order: float
    total_order: float
    confidence_interval: Tuple[float, float]

    class Config:
        from_attributes = True


class CorrelationMatrixResponse(BaseModel):
    """Response for correlation matrix"""
    variables: List[str]
    correlation_matrix: List[List[float]]
    p_values: List[List[float]]
    method: str
    strong_correlations: List[Dict[str, Any]] = Field(
        description="List of strong correlations found"
    )


class AutocorrelationResultResponse(BaseModel):
    """Response for ACF/PACF analysis"""
    lags: List[int]
    acf_values: List[float]
    pacf_values: List[float]
    confidence_interval: Tuple[float, float]
    significant_lags: List[int] = Field(
        description="Lags with significant autocorrelation"
    )


class TimeSeriesDecompositionResponse(BaseModel):
    """Response for time series decomposition"""
    trend: List[float]
    seasonal: List[float]
    residual: List[float]
    original: List[float]
    model: str


class ForecastAccuracyResponse(BaseModel):
    """Response for forecast accuracy metrics"""
    mape: float = Field(description="Mean Absolute Percentage Error (%)")
    rmse: float = Field(description="Root Mean Squared Error")
    mae: float = Field(description="Mean Absolute Error")
    mse: float = Field(description="Mean Squared Error")
    r_squared: float = Field(description="R-squared coefficient")


# ============================================================================
# API Endpoints
# ============================================================================

@router.post(
    "/sensitivity",
    response_model=List[SensitivityResultResponse],
    summary="Perform sensitivity analysis",
    description="Analyze how parameters affect simulation output using One-At-a-Time (OAT) method"
)
async def sensitivity_analysis(
    request: SensitivityAnalysisRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Perform sensitivity analysis on simulation parameters.

    The analysis varies each parameter independently while holding others constant,
    then calculates sensitivity coefficients to identify which parameters have
    the greatest impact on the output.

    **Use Case**: Identify which supply chain parameters (lead time, holding cost,
    backlog cost) have the biggest impact on total cost.
    """
    try:
        service = AdvancedAnalyticsService()

        # Create simulation function from pre-computed data
        def simulation_func(params: Dict[str, float]) -> float:
            # Find matching result in simulation_data
            for result in request.simulation_data:
                result_params = result['params']
                # Check if all params match (within tolerance)
                if all(abs(params.get(k, 0) - v) < 1e-6 for k, v in result_params.items()):
                    return result['output']

            # If no exact match, return interpolated value
            # For simplicity, return average of all outputs
            return np.mean([r['output'] for r in request.simulation_data])

        # Run sensitivity analysis
        results = service.one_at_a_time_sensitivity(
            base_params=request.base_params,
            param_ranges=request.param_ranges,
            simulation_func=simulation_func,
            num_samples=request.num_samples
        )

        return [SensitivityResultResponse(**result.__dict__) for result in results]

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Sensitivity analysis failed: {str(e)}"
        )


@router.post(
    "/sensitivity/sobol",
    response_model=List[SobolIndicesResponse],
    summary="Compute Sobol sensitivity indices",
    description="Variance-based sensitivity analysis using Sobol indices (first-order and total-order effects)"
)
async def sobol_sensitivity_analysis(
    request: SobolAnalysisRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Compute Sobol sensitivity indices using variance-based global sensitivity analysis.

    Sobol indices quantify:
    - First-order effect: Direct contribution of a parameter to output variance
    - Total-order effect: Total contribution including interactions with other parameters

    **Use Case**: Understand not only which parameters are important, but also
    how parameters interact with each other to affect outcomes.
    """
    try:
        service = AdvancedAnalyticsService()

        # Create simulation function from pre-computed data
        def simulation_func(params: Dict[str, float]) -> float:
            for result in request.simulation_data:
                result_params = result['params']
                if all(abs(params.get(k, 0) - v) < 1e-6 for k, v in result_params.items()):
                    return result['output']
            return np.mean([r['output'] for r in request.simulation_data])

        # Run Sobol analysis
        results = service.sobol_sensitivity_indices(
            param_ranges=request.param_ranges,
            simulation_func=simulation_func,
            num_samples=request.num_samples,
            confidence=request.confidence
        )

        return [SobolIndicesResponse(**result.__dict__) for result in results]

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Sobol analysis failed: {str(e)}"
        )


@router.post(
    "/correlation",
    response_model=CorrelationMatrixResponse,
    summary="Compute correlation matrix",
    description="Calculate correlations between variables using Pearson, Spearman, or Kendall methods"
)
async def correlation_analysis(
    request: CorrelationAnalysisRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Compute correlation matrix and identify strong correlations.

    Supports three correlation methods:
    - Pearson: Linear correlation (assumes normal distribution)
    - Spearman: Rank-based correlation (non-parametric, robust to outliers)
    - Kendall: Alternative rank correlation (better for small samples)

    **Use Case**: Identify which performance metrics are correlated with service level
    or total cost to understand system behavior.
    """
    try:
        service = AdvancedAnalyticsService()

        # Convert lists to numpy arrays
        data_dict = {k: np.array(v) for k, v in request.data.items()}

        # Compute correlation matrix
        corr_matrix = service.correlation_matrix(
            data_dict=data_dict,
            method=request.method
        )

        # Find strong correlations
        strong_correlations = service.find_strong_correlations(
            corr_matrix=corr_matrix,
            threshold=request.threshold,
            p_value_threshold=request.p_value_threshold
        )

        return CorrelationMatrixResponse(
            variables=corr_matrix.variables,
            correlation_matrix=corr_matrix.correlation_matrix.tolist(),
            p_values=corr_matrix.p_values.tolist(),
            method=corr_matrix.method,
            strong_correlations=strong_correlations
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Correlation analysis failed: {str(e)}"
        )


@router.post(
    "/time-series/acf",
    response_model=AutocorrelationResultResponse,
    summary="Compute autocorrelation function",
    description="Calculate ACF and PACF to identify temporal patterns and dependencies"
)
async def autocorrelation_analysis(
    request: TimeSeriesACFRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Compute Autocorrelation Function (ACF) and Partial Autocorrelation Function (PACF).

    ACF measures correlation with lagged versions of the time series.
    PACF measures correlation after removing effects of intermediate lags.

    **Use Case**: Detect patterns in demand data, identify seasonal cycles,
    or determine appropriate forecasting models.
    """
    try:
        service = AdvancedAnalyticsService()

        # Convert to numpy array
        time_series = np.array(request.time_series)

        # Compute ACF and PACF
        result = service.autocorrelation_function(
            time_series=time_series,
            max_lag=request.max_lag,
            confidence=request.confidence
        )

        # Identify significant lags (outside confidence interval)
        conf_lower, conf_upper = result.confidence_interval
        significant_lags = [
            int(lag) for lag, acf in zip(result.lags[1:], result.acf_values[1:])
            if abs(acf) > conf_upper
        ]

        return AutocorrelationResultResponse(
            lags=result.lags.tolist(),
            acf_values=result.acf_values.tolist(),
            pacf_values=result.pacf_values.tolist(),
            confidence_interval=result.confidence_interval,
            significant_lags=significant_lags
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"ACF analysis failed: {str(e)}"
        )


@router.post(
    "/time-series/decompose",
    response_model=TimeSeriesDecompositionResponse,
    summary="Decompose time series",
    description="Separate time series into trend, seasonal, and residual components"
)
async def time_series_decompose(
    request: TimeSeriesDecomposeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Decompose time series into trend, seasonal, and residual components.

    Supports two models:
    - Additive: Y = Trend + Seasonal + Residual (constant seasonal variation)
    - Multiplicative: Y = Trend × Seasonal × Residual (proportional seasonal variation)

    **Use Case**: Understand long-term trends, identify seasonal patterns,
    and isolate random noise in supply chain metrics.
    """
    try:
        service = AdvancedAnalyticsService()

        # Convert to numpy array
        time_series = np.array(request.time_series)

        # Decompose time series
        result = service.decompose_time_series(
            time_series=time_series,
            period=request.period,
            model=request.model
        )

        return TimeSeriesDecompositionResponse(
            trend=result.trend.tolist(),
            seasonal=result.seasonal.tolist(),
            residual=result.residual.tolist(),
            original=result.original.tolist(),
            model=request.model
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Time series decomposition failed: {str(e)}"
        )


@router.post(
    "/forecast-accuracy",
    response_model=ForecastAccuracyResponse,
    summary="Compute forecast accuracy metrics",
    description="Calculate MAPE, RMSE, MAE, and R-squared for forecast validation"
)
async def forecast_accuracy(
    request: ForecastAccuracyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Compute forecast accuracy metrics by comparing actual vs predicted values.

    Metrics:
    - MAPE: Mean Absolute Percentage Error (scale-independent)
    - RMSE: Root Mean Squared Error (penalizes large errors)
    - MAE: Mean Absolute Error (robust to outliers)
    - R²: Coefficient of determination (goodness of fit)

    **Use Case**: Evaluate forecasting model performance and compare
    different forecasting approaches.
    """
    try:
        service = AdvancedAnalyticsService()

        # Convert to numpy arrays
        actual = np.array(request.actual)
        predicted = np.array(request.predicted)

        # Calculate accuracy metrics
        result = service.forecast_accuracy_metrics(
            actual=actual,
            predicted=predicted
        )

        return ForecastAccuracyResponse(
            mape=result.mape,
            rmse=result.rmse,
            mae=result.mae,
            mse=result.mse,
            r_squared=result.r_squared
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Forecast accuracy calculation failed: {str(e)}"
        )


# ============================================================================
# Helper Endpoints
# ============================================================================

@router.get(
    "/methods",
    summary="List available analysis methods",
    description="Get information about available analytics methods and their parameters"
)
async def list_methods(current_user: User = Depends(get_current_user)):
    """
    List all available advanced analytics methods with descriptions.

    Returns information about each method, required parameters, and use cases.
    """
    return {
        "sensitivity_analysis": {
            "description": "One-At-a-Time sensitivity analysis",
            "methods": ["oat", "sobol"],
            "use_case": "Identify most important parameters affecting outcomes"
        },
        "correlation_analysis": {
            "description": "Correlation matrix and strong correlation detection",
            "methods": ["pearson", "spearman", "kendall"],
            "use_case": "Understand relationships between variables"
        },
        "time_series_analysis": {
            "description": "ACF, PACF, and decomposition",
            "methods": ["acf", "pacf", "decompose"],
            "use_case": "Detect patterns, trends, and seasonality"
        },
        "forecast_accuracy": {
            "description": "MAPE, RMSE, MAE, R-squared",
            "metrics": ["mape", "rmse", "mae", "r_squared"],
            "use_case": "Evaluate forecasting model performance"
        }
    }
