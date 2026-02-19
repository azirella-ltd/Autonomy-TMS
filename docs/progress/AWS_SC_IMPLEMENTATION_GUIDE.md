# AWS Supply Chain Implementation Guide

**Date**: 2026-01-23
**Goal**: Achieve 75-80% AWS Supply Chain functional parity
**Timeline**: 11-15 weeks (3 phases, 6 sprints)
**Current Coverage**: ~45%

---

## Critical Architectural Reminders

**🔴 ALWAYS REMEMBER**:
1. **Data Lake**: Using Databricks (external platform) - Integration deferred
2. **Demand Planning**: External system integration - View-only with delta analysis
3. **AWS SC Data Model**: All entities must comply with AWS SC schema (see [backend/app/models/sc_entities.py](../../backend/app/models/sc_entities.py))

---

## Table of Contents

1. [Phase 1: Core AWS SC Features (6-8 weeks)](#phase-1-core-aws-sc-features)
   - [Sprint 1: Enhanced Insights & Risk (3-4 weeks)](#sprint-1-enhanced-insights--risk)
   - [Sprint 2: Material Visibility (2-3 weeks)](#sprint-2-material-visibility)
   - [Sprint 3: Demand Plan Viewing (1 week)](#sprint-3-demand-plan-viewing)
2. [Phase 2: Collaboration & Recommendations (4-5 weeks)](#phase-2-collaboration--recommendations)
   - [Sprint 4: Recommended Actions (2-3 weeks)](#sprint-4-recommended-actions)
   - [Sprint 5: Collaboration (2-3 weeks)](#sprint-5-collaboration)
3. [Phase 3: Advanced Features (1-2 weeks)](#phase-3-advanced-features)
   - [Sprint 6: Additional Order Types (1-2 weeks)](#sprint-6-additional-order-types)
4. [Testing & Validation](#testing--validation)
5. [Deployment Checklist](#deployment-checklist)

---

## Phase 1: Core AWS SC Features (6-8 weeks)

**Objective**: Complete high-priority AWS SC features that provide immediate value

### Sprint 1: Enhanced Insights & Risk (3-4 weeks)

**Goal**: Build ML-powered risk detection and predictive analytics

#### 1.1 Backend: Risk Detection Service

**File**: `backend/app/services/risk_detection_service.py` (NEW)

**Implementation Steps**:

1. **Create Risk Detection Service**:
```python
"""
Risk Detection Service
Implements ML-based risk identification for AWS SC Insights
"""

class RiskDetectionService:
    def __init__(self, db: Session):
        self.db = db

    async def detect_stockout_risk(
        self,
        product_id: str,
        site_id: str,
        horizon_days: int = 30
    ) -> Dict:
        """
        Detect stock-out risk using:
        - Current inventory levels
        - Demand forecast
        - Lead times
        - Safety stock policies

        Returns probability (0-100) and risk level (LOW/MEDIUM/HIGH/CRITICAL)
        """
        pass

    async def detect_overstock_risk(
        self,
        product_id: str,
        site_id: str,
        threshold_days: int = 90
    ) -> Dict:
        """
        Detect excess inventory using:
        - Days of supply calculation
        - Demand trends
        - Shelf life constraints

        Returns excess quantity and cost impact
        """
        pass

    async def predict_vendor_leadtime(
        self,
        vendor_id: str,
        product_id: str
    ) -> Dict:
        """
        Predict vendor lead time using:
        - Historical lead times
        - Seasonal patterns
        - Vendor reliability score

        Returns P10/P50/P90 lead time predictions
        """
        pass

    async def generate_risk_alerts(
        self,
        site_id: Optional[str] = None,
        severity: Optional[str] = None
    ) -> List[Dict]:
        """
        Generate risk alerts across all monitored items

        Returns list of alerts with:
        - alert_id, product_id, site_id
        - risk_type (stockout, overstock, leadtime)
        - severity (LOW/MEDIUM/HIGH/CRITICAL)
        - probability, impact_cost
        - recommended_actions
        """
        pass
```

2. **Add Database Models for Risk Tracking**:

**File**: `backend/app/models/risk.py` (NEW)

```python
from sqlalchemy import Column, String, Float, DateTime, JSON
from app.db.base_class import Base

class RiskAlert(Base):
    __tablename__ = "risk_alerts"

    id = Column(String(36), primary_key=True)
    product_id = Column(String(40), nullable=False, index=True)
    site_id = Column(String(40), nullable=False, index=True)
    risk_type = Column(String(20), nullable=False)  # stockout, overstock, leadtime
    severity = Column(String(20), nullable=False)   # LOW, MEDIUM, HIGH, CRITICAL
    probability = Column(Float, nullable=False)     # 0-100
    impact_cost = Column(Float)
    recommended_actions = Column(JSON)
    created_at = Column(DateTime, nullable=False)
    resolved_at = Column(DateTime)
    is_resolved = Column(String(1), default="N")

class Watchlist(Base):
    __tablename__ = "watchlists"

    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    description = Column(String(500))
    filters = Column(JSON)  # product_ids, site_ids, risk_types, thresholds
    notification_settings = Column(JSON)  # email, sms, dashboard
    is_active = Column(String(1), default="Y")
    created_at = Column(DateTime, nullable=False)
```

3. **Create Risk Detection API Endpoints**:

**File**: `backend/app/api/endpoints/risk_analysis.py` (NEW)

```python
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from app.api import deps
from app.services.risk_detection_service import RiskDetectionService
from app.models.user import User

router = APIRouter()

@router.get("/alerts")
async def get_risk_alerts(
    *,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    site_id: Optional[str] = None,
    severity: Optional[str] = Query(None, regex="^(LOW|MEDIUM|HIGH|CRITICAL)$"),
    risk_type: Optional[str] = Query(None, regex="^(stockout|overstock|leadtime)$"),
    limit: int = 100
):
    """Get risk alerts with optional filtering"""
    service = RiskDetectionService(db)
    return await service.generate_risk_alerts(site_id, severity)

@router.post("/detect/stockout")
async def detect_stockout_risk(
    *,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    product_id: str,
    site_id: str,
    horizon_days: int = 30
):
    """Detect stock-out risk for specific product/site"""
    service = RiskDetectionService(db)
    return await service.detect_stockout_risk(product_id, site_id, horizon_days)

@router.post("/watchlists")
async def create_watchlist(
    *,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    watchlist: WatchlistCreate
):
    """Create a custom watchlist"""
    # Implementation
    pass

@router.get("/watchlists")
async def list_watchlists(
    *,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user)
):
    """List user's watchlists"""
    # Implementation
    pass

@router.get("/predictions/leadtime/{vendor_id}/{product_id}")
async def predict_leadtime(
    *,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    vendor_id: str,
    product_id: str
):
    """Predict vendor lead time"""
    service = RiskDetectionService(db)
    return await service.predict_vendor_leadtime(vendor_id, product_id)
```

4. **Register Router in main.py**:

```python
from app.api.endpoints.risk_analysis import router as risk_router
api.include_router(risk_router, prefix="/risk-analysis", tags=["risk-analysis", "insights"])
```

#### 1.2 Frontend: Risk Analysis Page

**File**: `frontend/src/pages/analytics/RiskAnalysis.jsx` (NEW)

**Implementation Steps**:

1. **Create Risk Analysis Page Component**:

```jsx
import React, { useState, useEffect } from 'react';
import {
  Box, Card, CardContent, Typography, Grid, Chip, Alert,
  Table, TableBody, TableCell, TableContainer, TableHead, TableRow,
  Select, MenuItem, FormControl, InputLabel, Button, IconButton
} from '@mui/material';
import { Warning, Error, Info, CheckCircle, Refresh } from '@mui/icons-material';
import api from '../../services/api';

const RiskAnalysis = () => {
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(false);
  const [severityFilter, setSeverityFilter] = useState('ALL');
  const [riskTypeFilter, setRiskTypeFilter] = useState('ALL');

  const fetchRiskAlerts = async () => {
    setLoading(true);
    try {
      const params = {};
      if (severityFilter !== 'ALL') params.severity = severityFilter;
      if (riskTypeFilter !== 'ALL') params.risk_type = riskTypeFilter;

      const response = await api.get('/api/v1/risk-analysis/alerts', { params });
      setAlerts(response.data);
    } catch (error) {
      console.error('Failed to fetch risk alerts:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchRiskAlerts();
  }, [severityFilter, riskTypeFilter]);

  const getSeverityIcon = (severity) => {
    switch (severity) {
      case 'CRITICAL': return <Error color="error" />;
      case 'HIGH': return <Warning color="warning" />;
      case 'MEDIUM': return <Info color="info" />;
      case 'LOW': return <CheckCircle color="success" />;
      default: return null;
    }
  };

  const getSeverityColor = (severity) => {
    switch (severity) {
      case 'CRITICAL': return 'error';
      case 'HIGH': return 'warning';
      case 'MEDIUM': return 'info';
      case 'LOW': return 'success';
      default: return 'default';
    }
  };

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h4" gutterBottom>
        Risk Analysis
      </Typography>

      {/* Filters */}
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Grid container spacing={2} alignItems="center">
            <Grid item xs={12} md={4}>
              <FormControl fullWidth>
                <InputLabel>Severity</InputLabel>
                <Select
                  value={severityFilter}
                  onChange={(e) => setSeverityFilter(e.target.value)}
                >
                  <MenuItem value="ALL">All Severities</MenuItem>
                  <MenuItem value="CRITICAL">Critical</MenuItem>
                  <MenuItem value="HIGH">High</MenuItem>
                  <MenuItem value="MEDIUM">Medium</MenuItem>
                  <MenuItem value="LOW">Low</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} md={4}>
              <FormControl fullWidth>
                <InputLabel>Risk Type</InputLabel>
                <Select
                  value={riskTypeFilter}
                  onChange={(e) => setRiskTypeFilter(e.target.value)}
                >
                  <MenuItem value="ALL">All Types</MenuItem>
                  <MenuItem value="stockout">Stock-Out</MenuItem>
                  <MenuItem value="overstock">Overstock</MenuItem>
                  <MenuItem value="leadtime">Lead Time</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} md={4}>
              <Button
                variant="contained"
                startIcon={<Refresh />}
                onClick={fetchRiskAlerts}
                disabled={loading}
                fullWidth
              >
                Refresh
              </Button>
            </Grid>
          </Grid>
        </CardContent>
      </Card>

      {/* Risk Alerts Table */}
      <Card>
        <CardContent>
          <TableContainer>
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell>Severity</TableCell>
                  <TableCell>Product</TableCell>
                  <TableCell>Site</TableCell>
                  <TableCell>Risk Type</TableCell>
                  <TableCell>Probability</TableCell>
                  <TableCell>Impact ($)</TableCell>
                  <TableCell>Actions</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {alerts.map((alert) => (
                  <TableRow key={alert.id}>
                    <TableCell>
                      <Chip
                        icon={getSeverityIcon(alert.severity)}
                        label={alert.severity}
                        color={getSeverityColor(alert.severity)}
                        size="small"
                      />
                    </TableCell>
                    <TableCell>{alert.product_id}</TableCell>
                    <TableCell>{alert.site_id}</TableCell>
                    <TableCell>
                      <Chip label={alert.risk_type} size="small" />
                    </TableCell>
                    <TableCell>{alert.probability}%</TableCell>
                    <TableCell>
                      ${alert.impact_cost?.toLocaleString() || 'N/A'}
                    </TableCell>
                    <TableCell>
                      <Button size="small" variant="outlined">
                        View Details
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        </CardContent>
      </Card>
    </Box>
  );
};

export default RiskAnalysis;
```

2. **Add Route to App.js**:

```jsx
import RiskAnalysis from './pages/analytics/RiskAnalysis';

// In routes:
<Route path="/analytics/risk" element={<RiskAnalysis />} />
```

3. **Update Navigation Config**:

**File**: `frontend/src/config/navigationConfig.js`

```javascript
{
  label: 'Risk Analysis',
  path: '/analytics/risk',
  icon: 'Warning',
  capability: 'view_risk_analysis',
  comingSoon: false  // Change from true to false
}
```

#### 1.3 Add RBAC Capabilities

**File**: `backend/app/core/rbac.py`

Add to capabilities dictionary:

```python
'view_risk_analysis': {
    'description': 'View risk analysis and alerts',
    'category': 'analytics'
},
'manage_watchlists': {
    'description': 'Create and manage watchlists',
    'category': 'analytics'
},
'view_predictions': {
    'description': 'View predictive analytics',
    'category': 'analytics'
}
```

#### 1.4 Testing Checklist - Sprint 1

- [ ] Backend: Risk detection service identifies stock-out risks correctly
- [ ] Backend: Overstock detection calculates excess inventory
- [ ] Backend: Lead time prediction returns P10/P50/P90 values
- [ ] API: `/api/v1/risk-analysis/alerts` returns filtered alerts
- [ ] API: Watchlist CRUD operations work
- [ ] Frontend: Risk Analysis page displays alerts
- [ ] Frontend: Severity and type filters work correctly
- [ ] Frontend: Alert details modal shows recommended actions
- [ ] RBAC: Capabilities restrict access correctly
- [ ] Integration: Real-time alerts trigger for threshold violations

---

### Sprint 2: Material Visibility (2-3 weeks)

**Goal**: Build shipment tracking and delivery risk analytics

#### 2.1 Backend: Shipment Tracking Service

**File**: `backend/app/services/shipment_tracking_service.py` (NEW)

**Implementation Steps**:

1. **Create Shipment Tracking Service**:

```python
"""
Shipment Tracking Service
Real-time tracking of in-transit inventory
"""

class ShipmentTrackingService:
    def __init__(self, db: Session):
        self.db = db

    async def track_shipment(
        self,
        shipment_id: str
    ) -> Dict:
        """
        Get real-time shipment status

        Returns:
        - shipment_id, carrier, tracking_number
        - current_location, destination
        - status (in_transit, delivered, delayed, exception)
        - eta, actual_delivery_date
        - delivery_risk (probability of delay)
        """
        pass

    async def get_in_transit_inventory(
        self,
        product_id: Optional[str] = None,
        site_id: Optional[str] = None
    ) -> List[Dict]:
        """
        Get all in-transit inventory
        """
        pass

    async def calculate_delivery_risk(
        self,
        shipment_id: str
    ) -> Dict:
        """
        Calculate delivery risk using:
        - Historical carrier performance
        - Weather conditions
        - Route congestion
        - Port/customs delays

        Returns probability of on-time delivery
        """
        pass

    async def recommend_mitigation(
        self,
        shipment_id: str
    ) -> List[Dict]:
        """
        Recommend mitigation actions for at-risk shipments:
        - Expedite shipping
        - Reroute via alternate carrier
        - Increase safety stock at destination
        - Notify customer of delay
        """
        pass
```

2. **Add Shipment Models**:

**File**: `backend/app/models/shipment.py` (NEW)

```python
from sqlalchemy import Column, String, Float, DateTime, JSON
from app.db.base_class import Base

class Shipment(Base):
    __tablename__ = "shipments"

    id = Column(String(36), primary_key=True)
    order_id = Column(String(40), nullable=False, index=True)
    product_id = Column(String(40), nullable=False)
    from_site_id = Column(String(40), nullable=False)
    to_site_id = Column(String(40), nullable=False)
    carrier = Column(String(100))
    tracking_number = Column(String(100))
    quantity = Column(Float, nullable=False)
    ship_date = Column(DateTime)
    expected_delivery_date = Column(DateTime)
    actual_delivery_date = Column(DateTime)
    status = Column(String(20))  # in_transit, delivered, delayed, exception
    current_location = Column(String(200))
    delivery_risk_score = Column(Float)  # 0-100
    events = Column(JSON)  # Tracking events history
```

3. **Create Shipment Tracking API**:

**File**: `backend/app/api/endpoints/shipment_tracking.py` (NEW)

```python
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List, Optional

from app.api import deps
from app.services.shipment_tracking_service import ShipmentTrackingService

router = APIRouter()

@router.get("/{shipment_id}")
async def get_shipment_status(
    *,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    shipment_id: str
):
    """Get real-time shipment status"""
    service = ShipmentTrackingService(db)
    return await service.track_shipment(shipment_id)

@router.get("/in-transit")
async def get_in_transit_inventory(
    *,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    product_id: Optional[str] = None,
    site_id: Optional[str] = None
):
    """Get all in-transit inventory"""
    service = ShipmentTrackingService(db)
    return await service.get_in_transit_inventory(product_id, site_id)

@router.get("/{shipment_id}/risk")
async def get_delivery_risk(
    *,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    shipment_id: str
):
    """Calculate delivery risk"""
    service = ShipmentTrackingService(db)
    return await service.calculate_delivery_risk(shipment_id)

@router.get("/{shipment_id}/mitigations")
async def get_mitigation_recommendations(
    *,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    shipment_id: str
):
    """Get mitigation recommendations"""
    service = ShipmentTrackingService(db)
    return await service.recommend_mitigation(shipment_id)
```

4. **Register Router**:

```python
from app.api.endpoints.shipment_tracking import router as shipment_router
api.include_router(shipment_router, prefix="/shipment-tracking", tags=["shipment-tracking", "visibility"])
```

#### 2.2 Frontend: Shipment Tracking Page

**File**: `frontend/src/pages/execution/ShipmentTracking.jsx` (NEW)

**Implementation**: (Similar pattern to Risk Analysis page, with shipment-specific fields)

#### 2.3 Testing Checklist - Sprint 2

- [ ] Backend: Shipment tracking returns real-time status
- [ ] Backend: In-transit inventory calculation is accurate
- [ ] Backend: Delivery risk scoring works
- [ ] API: All shipment tracking endpoints functional
- [ ] Frontend: Shipment Tracking page displays data
- [ ] Frontend: Map visualization shows shipment locations
- [ ] Frontend: Risk alerts trigger for at-risk shipments
- [ ] Integration: Carrier API integration works (if applicable)

---

### Sprint 3: Demand Plan Viewing (1 week)

**Goal**: View-only demand plan display with delta analysis

#### 3.1 Backend: Demand Plan API

**File**: `backend/app/api/endpoints/demand_plan.py` (NEW)

**Implementation Steps**:

1. **Create Demand Plan Endpoints**:

```python
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime

from app.api import deps
from app.models.aws_sc_planning import Forecast

router = APIRouter()

@router.get("/current")
async def get_current_demand_plan(
    *,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    product_id: Optional[str] = None,
    site_id: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None
):
    """
    Get current demand plan (read-only)
    Filters by product, site, date range
    """
    query = db.query(Forecast).filter(Forecast.is_active == "Y")

    if product_id:
        query = query.filter(Forecast.product_id == product_id)
    if site_id:
        query = query.filter(Forecast.site_id == site_id)
    if start_date:
        query = query.filter(Forecast.forecast_date >= start_date)
    if end_date:
        query = query.filter(Forecast.forecast_date <= end_date)

    forecasts = query.all()
    return forecasts

@router.get("/versions")
async def get_demand_plan_versions(
    *,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user)
):
    """List all demand plan versions"""
    # Get distinct plan versions from forecast table
    pass

@router.get("/delta")
async def get_demand_plan_delta(
    *,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    version1: str,
    version2: str,
    product_id: Optional[str] = None
):
    """
    Compare two demand plan versions
    Returns delta (changes) between versions
    """
    # Compare forecasts between two versions
    # Return increases/decreases by product/site/date
    pass

@router.post("/integrate")
async def receive_external_demand_plan(
    *,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    demand_plan: ExternalDemandPlanSchema
):
    """
    POST endpoint for external demand planning system
    Maps external format to AWS SC forecast table
    Performs version tracking
    """
    # Map external demand plan to Forecast model
    # Create new version
    # Archive historical versions
    pass
```

2. **Add Pydantic Schemas**:

```python
class ExternalDemandPlanSchema(BaseModel):
    plan_id: str
    plan_name: str
    effective_date: datetime
    created_by: str
    forecasts: List[ForecastItem]

class ForecastItem(BaseModel):
    product_id: str
    site_id: str
    forecast_date: datetime
    quantity_p50: float
    quantity_p10: Optional[float] = None
    quantity_p90: Optional[float] = None
```

#### 3.2 Frontend: Demand Plan View Page

**File**: `frontend/src/pages/planning/DemandPlanView.jsx` (NEW)

**Implementation**: (Similar to Risk Analysis, with forecast-specific visualizations)

#### 3.3 Testing Checklist - Sprint 3

- [ ] Backend: Current demand plan retrieval works
- [ ] Backend: Version comparison (delta) calculates correctly
- [ ] API: External demand plan integration endpoint functional
- [ ] API: Version tracking and archival works
- [ ] Frontend: Demand Plan View displays forecasts
- [ ] Frontend: P10/P50/P90 confidence intervals shown
- [ ] Frontend: Delta analysis highlights changes
- [ ] Integration: External system can POST demand plans

---

## Phase 2: Collaboration & Recommendations (4-5 weeks)

### Sprint 4: Recommended Actions (2-3 weeks)

**Goal**: Build rebalancing recommendations engine

#### 4.1 Backend: Recommendations Engine

**File**: `backend/app/services/recommendations_engine.py` (NEW)

**Implementation Steps**:

1. **Create Recommendations Engine**:

```python
"""
Recommendations Engine
Generates inventory rebalancing recommendations
"""

class RecommendationsEngine:
    def __init__(self, db: Session):
        self.db = db

    async def generate_rebalancing_recommendations(
        self,
        network_id: Optional[str] = None
    ) -> List[Dict]:
        """
        Generate inventory rebalancing recommendations

        Algorithm:
        1. Identify sites with excess inventory (DOS > threshold)
        2. Identify sites with deficit (DOS < safety stock)
        3. Calculate optimal transfers using linear programming
        4. Score recommendations by:
           - Risk resolution (40 points)
           - Distance (20 points)
           - Sustainability (15 points)
           - Service level impact (15 points)
           - Inventory cost (10 points)

        Returns ranked list of recommendations
        """
        pass

    async def simulate_recommendation_impact(
        self,
        recommendation_id: str
    ) -> Dict:
        """
        Simulate impact of recommendation using Monte Carlo
        Returns expected impact on:
        - Service level
        - Inventory cost
        - CO2 emissions
        - Risk reduction
        """
        pass

    async def track_recommendation_decision(
        self,
        recommendation_id: str,
        decision: str,  # accepted, rejected, modified
        user_id: str,
        reason: Optional[str] = None
    ):
        """
        Track user decisions on recommendations
        Used for ML learning loop
        """
        pass
```

2. **Add Recommendation Models**:

**File**: `backend/app/models/recommendations.py` (NEW)

```python
class Recommendation(Base):
    __tablename__ = "recommendations"

    id = Column(String(36), primary_key=True)
    recommendation_type = Column(String(50))  # rebalance, expedite, safety_stock
    from_site_id = Column(String(40))
    to_site_id = Column(String(40))
    product_id = Column(String(40), nullable=False)
    quantity = Column(Float, nullable=False)

    # Scoring
    risk_resolution_score = Column(Float)  # 0-40
    distance_score = Column(Float)         # 0-20
    sustainability_score = Column(Float)   # 0-15
    service_level_score = Column(Float)    # 0-15
    cost_score = Column(Float)             # 0-10
    total_score = Column(Float)            # 0-100

    # Impact estimates
    estimated_cost_impact = Column(Float)
    estimated_service_level_impact = Column(Float)
    estimated_co2_impact = Column(Float)

    # Decision tracking
    status = Column(String(20))  # pending, accepted, rejected, executed
    decision_user_id = Column(String(36))
    decision_date = Column(DateTime)
    decision_reason = Column(String(500))

    created_at = Column(DateTime, nullable=False)
```

3. **Create Recommendations API**:

**File**: `backend/app/api/endpoints/recommendations.py` (NEW)

```python
@router.get("/")
async def get_recommendations(
    *,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    recommendation_type: Optional[str] = None,
    min_score: float = 0.0,
    status: Optional[str] = None
):
    """Get recommendations with optional filtering"""
    pass

@router.post("/generate")
async def generate_recommendations(
    *,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    network_id: Optional[str] = None
):
    """Generate new recommendations"""
    engine = RecommendationsEngine(db)
    return await engine.generate_rebalancing_recommendations(network_id)

@router.post("/{recommendation_id}/simulate")
async def simulate_impact(
    *,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    recommendation_id: str
):
    """Simulate recommendation impact"""
    engine = RecommendationsEngine(db)
    return await engine.simulate_recommendation_impact(recommendation_id)

@router.post("/{recommendation_id}/approve")
async def approve_recommendation(
    *,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    recommendation_id: str,
    decision: RecommendationDecision
):
    """Approve/reject recommendation"""
    engine = RecommendationsEngine(db)
    return await engine.track_recommendation_decision(
        recommendation_id,
        decision.action,
        current_user.id,
        decision.reason
    )
```

#### 4.2 Frontend: Recommendations Page

**File**: `frontend/src/pages/planning/Recommendations.jsx` (NEW)

#### 4.3 Testing Checklist - Sprint 4

- [ ] Backend: Rebalancing recommendations generated correctly
- [ ] Backend: Scoring algorithm produces reasonable results
- [ ] Backend: Impact simulation returns expected metrics
- [ ] API: All recommendations endpoints functional
- [ ] Frontend: Recommendations page displays ranked actions
- [ ] Frontend: Impact simulation shows before/after comparison
- [ ] Frontend: Approve/reject workflow works
- [ ] ML: Decision tracking captures user feedback

---

### Sprint 5: Collaboration (2-3 weeks)

**Goal**: Team messaging and approval workflows

#### 5.1 Backend: Collaboration Service

**File**: `backend/app/services/collaboration_service.py` (NEW)

**Implementation Steps**:

1. **Create Collaboration Service**:

```python
"""
Collaboration Service
Team messaging, commenting, and notifications
"""

class CollaborationService:
    def __init__(self, db: Session):
        self.db = db

    async def post_message(
        self,
        thread_id: str,
        user_id: str,
        content: str,
        mentions: List[str] = []
    ) -> Dict:
        """
        Post message to thread
        Notify mentioned users
        """
        pass

    async def add_comment(
        self,
        entity_type: str,  # order, plan, recommendation
        entity_id: str,
        user_id: str,
        comment: str
    ) -> Dict:
        """
        Add comment to entity (order, plan, recommendation)
        """
        pass

    async def send_notification(
        self,
        user_id: str,
        notification_type: str,
        title: str,
        message: str,
        link: Optional[str] = None
    ):
        """
        Send notification (email, SMS, dashboard)
        """
        pass

    async def get_activity_feed(
        self,
        user_id: Optional[str] = None,
        entity_type: Optional[str] = None,
        start_date: Optional[datetime] = None,
        limit: int = 50
    ) -> List[Dict]:
        """
        Get activity feed for user or entity
        """
        pass
```

2. **Add Collaboration Models**:

**File**: `backend/app/models/collaboration.py` (NEW)

```python
class Message(Base):
    __tablename__ = "messages"

    id = Column(String(36), primary_key=True)
    thread_id = Column(String(36), nullable=False, index=True)
    user_id = Column(String(36), nullable=False)
    content = Column(String(2000), nullable=False)
    mentions = Column(JSON)  # List of user_ids
    attachments = Column(JSON)
    created_at = Column(DateTime, nullable=False)
    edited_at = Column(DateTime)
    is_deleted = Column(String(1), default="N")

class Comment(Base):
    __tablename__ = "comments"

    id = Column(String(36), primary_key=True)
    entity_type = Column(String(50), nullable=False)  # order, plan, recommendation
    entity_id = Column(String(40), nullable=False, index=True)
    user_id = Column(String(36), nullable=False)
    comment = Column(String(1000), nullable=False)
    parent_comment_id = Column(String(36))  # For threading
    created_at = Column(DateTime, nullable=False)
    is_resolved = Column(String(1), default="N")

class Notification(Base):
    __tablename__ = "notifications"

    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), nullable=False, index=True)
    notification_type = Column(String(50))  # mention, alert, approval_required
    title = Column(String(200))
    message = Column(String(500))
    link = Column(String(200))
    is_read = Column(String(1), default="N")
    created_at = Column(DateTime, nullable=False)
```

3. **Create Collaboration API**:

**File**: `backend/app/api/endpoints/collaboration.py` (NEW)

```python
@router.post("/messages")
async def post_message(
    *,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    message: MessageCreate
):
    """Post a message"""
    service = CollaborationService(db)
    return await service.post_message(
        message.thread_id,
        current_user.id,
        message.content,
        message.mentions
    )

@router.get("/messages/{thread_id}")
async def get_thread_messages(
    *,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    thread_id: str
):
    """Get messages in thread"""
    pass

@router.post("/comments")
async def add_comment(
    *,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    comment: CommentCreate
):
    """Add comment to entity"""
    service = CollaborationService(db)
    return await service.add_comment(
        comment.entity_type,
        comment.entity_id,
        current_user.id,
        comment.comment
    )

@router.get("/notifications")
async def get_notifications(
    *,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    unread_only: bool = True
):
    """Get user notifications"""
    pass

@router.get("/activity")
async def get_activity_feed(
    *,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    entity_type: Optional[str] = None,
    limit: int = 50
):
    """Get activity feed"""
    service = CollaborationService(db)
    return await service.get_activity_feed(
        current_user.id,
        entity_type,
        None,
        limit
    )
```

#### 5.2 Frontend: Collaboration Components

**Files**:
- `frontend/src/pages/collaboration/Messaging.jsx` (NEW)
- `frontend/src/components/collaboration/CommentThread.jsx` (NEW)
- `frontend/src/components/collaboration/NotificationCenter.jsx` (NEW)

#### 5.3 Testing Checklist - Sprint 5

- [ ] Backend: Message posting and retrieval works
- [ ] Backend: Comment threading functional
- [ ] Backend: @mentions trigger notifications
- [ ] Backend: Activity feed aggregates events correctly
- [ ] API: All collaboration endpoints functional
- [ ] Frontend: Messaging interface works
- [ ] Frontend: Commenting on orders/plans works
- [ ] Frontend: Notification center displays alerts
- [ ] Real-time: WebSocket updates for new messages

---

## Phase 3: Advanced Features (1-2 weeks)

### Sprint 6: Additional Order Types (1-2 weeks)

**Goal**: Add project, maintenance, and turnaround orders

#### 6.1 Backend: Extended Order Types

**File**: Extend `backend/app/models/aws_sc_planning.py`

**Implementation Steps**:

1. **Add Order Type Fields**:

Update `SupplyPlan` model or create new order type models:

```python
class ProjectOrder(Base):
    __tablename__ = "project_orders"

    id = Column(String(36), primary_key=True)
    project_id = Column(String(40), nullable=False)
    project_name = Column(String(200))
    customer_id = Column(String(40))
    product_id = Column(String(40), nullable=False)
    site_id = Column(String(40), nullable=False)
    quantity = Column(Float, nullable=False)
    required_date = Column(DateTime)
    status = Column(String(20))  # planned, approved, in_progress, completed
    # ... other fields

class MaintenanceOrder(Base):
    __tablename__ = "maintenance_orders"

    id = Column(String(36), primary_key=True)
    asset_id = Column(String(40), nullable=False)
    maintenance_type = Column(String(50))  # preventive, corrective, predictive
    product_id = Column(String(40))  # Spare parts
    site_id = Column(String(40), nullable=False)
    scheduled_date = Column(DateTime)
    completion_date = Column(DateTime)
    status = Column(String(20))
    # ... other fields

class TurnaroundOrder(Base):
    __tablename__ = "turnaround_orders"

    id = Column(String(36), primary_key=True)
    return_order_id = Column(String(40))  # Original order
    product_id = Column(String(40), nullable=False)
    from_site_id = Column(String(40), nullable=False)
    to_site_id = Column(String(40), nullable=False)
    quantity = Column(Float, nullable=False)
    reason = Column(String(200))  # Return reason
    refurbishment_required = Column(String(1))
    status = Column(String(20))
    # ... other fields
```

2. **Create Order Type APIs**:

**Files**:
- `backend/app/api/endpoints/project_orders.py` (NEW)
- `backend/app/api/endpoints/maintenance_orders.py` (NEW)
- `backend/app/api/endpoints/turnaround_orders.py` (NEW)

#### 6.2 Frontend: Extended Order Pages

**Files**:
- `frontend/src/pages/planning/ProjectOrders.jsx` (NEW)
- `frontend/src/pages/planning/MaintenanceOrders.jsx` (NEW)
- `frontend/src/pages/planning/TurnaroundOrders.jsx` (NEW)

#### 6.3 Testing Checklist - Sprint 6

- [ ] Backend: Project order CRUD operations work
- [ ] Backend: Maintenance order lifecycle correct
- [ ] Backend: Turnaround order processing functional
- [ ] API: All order type endpoints operational
- [ ] Frontend: All order type pages display correctly
- [ ] Frontend: Order approval workflow works
- [ ] Integration: Orders integrate with existing supply planning

---

## Testing & Validation

### End-to-End Testing

After each sprint, perform these tests:

1. **Unit Tests**: All services have >80% code coverage
2. **Integration Tests**: API endpoints return expected data
3. **Frontend Tests**: UI components render correctly
4. **End-to-End Tests**: User workflows complete successfully
5. **Performance Tests**: API response times <500ms for 95th percentile
6. **Load Tests**: System handles 100 concurrent users

### Validation Checklist

- [ ] All AWS SC data model entities comply with schema
- [ ] RBAC capabilities restrict access correctly
- [ ] Frontend pages have no console errors
- [ ] API documentation (Swagger) is complete
- [ ] Database migrations are reversible
- [ ] Error handling covers edge cases
- [ ] Logging captures all critical events

---

## Deployment Checklist

### Pre-Deployment

- [ ] All tests passing
- [ ] Code reviewed and approved
- [ ] Documentation updated
- [ ] Database migrations prepared
- [ ] Environment variables configured
- [ ] RBAC capabilities added to roles

### Deployment Steps

1. **Backup Database**:
```bash
make db-backup
```

2. **Run Migrations**:
```bash
docker compose exec backend alembic upgrade head
```

3. **Restart Services**:
```bash
make restart-backend
make restart-frontend
```

4. **Verify Deployment**:
- Check API health endpoint
- Test critical user workflows
- Monitor error logs

### Post-Deployment

- [ ] Smoke tests completed
- [ ] User acceptance testing (UAT) passed
- [ ] Performance monitoring enabled
- [ ] Rollback plan documented

---

## Progress Tracking

### Sprint Completion Criteria

Each sprint is complete when:
1. All tasks in sprint checklist completed
2. All tests passing
3. Code reviewed and merged
4. Documentation updated
5. Demo prepared for stakeholders

### Milestone Tracking

| Milestone | Target Date | Status |
|-----------|-------------|--------|
| **Sprint 1 Complete** | Week 4 | 🔲 Pending |
| **Sprint 2 Complete** | Week 7 | 🔲 Pending |
| **Sprint 3 Complete** | Week 8 | 🔲 Pending |
| **Phase 1 Complete** | Week 8 | 🔲 Pending |
| **Sprint 4 Complete** | Week 11 | 🔲 Pending |
| **Sprint 5 Complete** | Week 13 | 🔲 Pending |
| **Phase 2 Complete** | Week 13 | 🔲 Pending |
| **Sprint 6 Complete** | Week 15 | 🔲 Pending |
| **Phase 3 Complete** | Week 15 | 🔲 Pending |
| **AWS SC Parity (75-80%)** | Week 15 | 🔲 Pending |

---

## Reference Documents

- [AWS SC Features Coverage Analysis](AWS_SC_FEATURES_COVERAGE_ANALYSIS.md) - Detailed feature-by-feature analysis
- [Executive Summary](../../EXECUTIVE_SUMMARY.md) - Aspirational vision document
- [AWS SC Data Model](../../backend/app/models/sc_entities.py) - Entity definitions
- [Navigation Config](../../frontend/src/config/navigationConfig.js) - UI routing
- [RBAC Config](../../backend/app/core/rbac.py) - Capability definitions

---

## Support & Escalation

**Questions**: Review this guide and reference documents
**Blockers**: Document blocker and escalate to technical lead
**Architecture Decisions**: Refer to architectural reminder at top of document

---

**Last Updated**: 2026-01-23
**Next Review**: After Sprint 1 completion
