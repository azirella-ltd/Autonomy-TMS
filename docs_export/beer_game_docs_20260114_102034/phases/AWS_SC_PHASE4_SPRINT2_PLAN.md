# AWS SC Phase 4 - Sprint 2: Dashboard UI Plan

**Date**: 2026-01-13
**Status**: 🚧 **IN PROGRESS**

---

## Sprint 2 Overview

Sprint 2 focuses on creating dashboard UI components to visualize Phase 3 analytics (order aggregation and capacity constraints).

**Goal**: Provide intuitive, interactive visualizations of analytics data for users.

---

## Components to Build

### 1. Analytics Dashboard Page
**File**: `frontend/src/pages/AnalyticsDashboard.jsx`

**Features**:
- Game selector dropdown
- Tab navigation (Aggregation, Capacity, Policies, Comparison)
- Responsive layout
- Error handling
- Loading states

**Layout**:
```
+--------------------------------------------------+
| Analytics Dashboard                               |
+--------------------------------------------------+
| Game: [Dropdown Selector]              [Refresh] |
+--------------------------------------------------+
| [Aggregation] [Capacity] [Policies] [Comparison] |
+--------------------------------------------------+
|                                                   |
|  Chart/Table Content                              |
|                                                   |
+--------------------------------------------------+
```

---

### 2. Aggregation Analytics Component
**File**: `frontend/src/components/analytics/AggregationAnalytics.jsx`

**Visualizations**:
1. **Cost Savings Over Time** (Line Chart)
   - X-axis: Round number
   - Y-axis: Cost savings ($)
   - Shows cumulative savings trend

2. **Orders Aggregated by Round** (Bar Chart)
   - X-axis: Round number
   - Y-axis: Number of orders
   - Stacked: Individual orders vs. aggregated groups

3. **Site Pair Summary Table**
   - Columns: From Site, To Site, Groups Created, Total Aggregated, Total Savings
   - Sortable by any column
   - Show top 10 site pairs

4. **Summary Cards**
   - Total Orders Aggregated
   - Total Groups Created
   - Total Cost Savings
   - Avg Savings/Round

**API Call**: `GET /api/v1/analytics/aggregation/{game_id}`

---

### 3. Capacity Analytics Component
**File**: `frontend/src/components/analytics/CapacityAnalytics.jsx`

**Visualizations**:
1. **Capacity Utilization by Site** (Horizontal Bar Chart)
   - X-axis: Utilization %
   - Y-axis: Site names
   - Color coding: Green (<70%), Yellow (70-90%), Red (>90%)

2. **Utilization Over Time** (Line Chart)
   - X-axis: Round number
   - Y-axis: Utilization %
   - Multiple lines (one per site)

3. **Site Capacity Table**
   - Columns: Site, Max Capacity, Total Used, Utilization %
   - Sortable
   - Color-coded utilization

4. **Summary Cards**
   - Sites with Capacity
   - Total Capacity
   - Avg Utilization
   - Bottleneck Sites (>90% util)

**API Call**: `GET /api/v1/analytics/capacity/{game_id}`

---

### 4. Policy Effectiveness Component
**File**: `frontend/src/components/analytics/PolicyEffectiveness.jsx`

**Visualizations**:
1. **Policy Usage Chart** (Bar Chart)
   - X-axis: Policy ID or Site Pair
   - Y-axis: Usage count
   - Separate bars for aggregation vs. capacity policies

2. **Cost Savings by Policy** (Bar Chart)
   - X-axis: Policy ID
   - Y-axis: Total savings ($)
   - Only for aggregation policies

3. **Policy Effectiveness Table**
   - Columns: Type, From/To, Usage Count, Total Savings, Avg Savings/Use, Score
   - Filterable by type (aggregation/capacity)
   - Sortable

4. **Summary Cards**
   - Total Policies Active
   - Most Used Policy
   - Highest Savings Policy
   - Avg Effectiveness Score

**API Call**: `GET /api/v1/analytics/policies/{config_id}?group_id={group_id}`

---

### 5. Comparative Analytics Component
**File**: `frontend/src/components/analytics/ComparativeAnalytics.jsx`

**Visualizations**:
1. **Feature Impact Comparison** (Side-by-side Bar Chart)
   - Compare: Orders, Cost, Fulfillment Rate
   - Bars: Without Features vs. With Features
   - Show percentage improvement

2. **Efficiency Gains** (Gauge Chart or Progress Bar)
   - Show efficiency gain percentage
   - Visual indicator: Poor (<20%), Good (20-50%), Excellent (>50%)

3. **Feature Status Cards**
   - Aggregation: Enabled/Disabled
   - Capacity: Enabled/Disabled
   - With toggle indicators

4. **Impact Summary Table**
   - Metric, Without Features, With Features, Improvement
   - Rows: Total Orders, Total Cost, Fulfillment Rate

**API Call**: `GET /api/v1/analytics/comparison/{game_id}`

---

## Shared Components

### AnalyticsSummaryCard
**File**: `frontend/src/components/analytics/AnalyticsSummaryCard.jsx`

**Props**:
- `title` (string): Card title
- `value` (string/number): Main metric value
- `subtitle` (string, optional): Secondary info
- `icon` (component, optional): MUI icon
- `color` (string, optional): Card accent color

**Example**:
```jsx
<AnalyticsSummaryCard
  title="Total Cost Savings"
  value="$1,234.56"
  subtitle="Across 10 rounds"
  icon={<AttachMoneyIcon />}
  color="success"
/>
```

---

## Technical Stack

### Libraries to Use
1. **Recharts** (Already in project)
   - Line charts
   - Bar charts
   - Area charts

2. **Material-UI** (Already in project)
   - Cards, Tables, Tabs
   - Grid layout
   - Icons

3. **React Query** or **useState/useEffect**
   - API data fetching
   - Caching
   - Automatic refetching

### API Service Methods
**File**: `frontend/src/services/api.js`

Add methods:
```javascript
// Get aggregation metrics
export const getAggregationMetrics = (gameId) => {
  return api.get(`/analytics/aggregation/${gameId}`);
};

// Get capacity metrics
export const getCapacityMetrics = (gameId) => {
  return api.get(`/analytics/capacity/${gameId}`);
};

// Get policy effectiveness
export const getPolicyEffectiveness = (configId, groupId) => {
  return api.get(`/analytics/policies/${configId}`, {
    params: { group_id: groupId }
  });
};

// Get comparative analytics
export const getComparativeAnalytics = (gameId) => {
  return api.get(`/analytics/comparison/${gameId}`);
};

// Get analytics summary
export const getAnalyticsSummary = (gameId) => {
  return api.get(`/analytics/summary/${gameId}`);
};
```

---

## Implementation Plan

### Step 1: API Service Methods ✅
- Add analytics API methods to `api.js`
- Test API calls from browser console

### Step 2: Shared Components
- Create `AnalyticsSummaryCard.jsx`
- Create loading/error state components

### Step 3: Individual Tab Components
- Build `AggregationAnalytics.jsx`
- Build `CapacityAnalytics.jsx`
- Build `PolicyEffectiveness.jsx`
- Build `ComparativeAnalytics.jsx`

### Step 4: Main Dashboard Page
- Create `AnalyticsDashboard.jsx`
- Add routing
- Integrate all tab components

### Step 5: Testing & Polish
- Test with real game data
- Responsive design adjustments
- Loading states and error handling

---

## File Structure

```
frontend/src/
├── pages/
│   └── AnalyticsDashboard.jsx          (Main dashboard page)
├── components/
│   └── analytics/
│       ├── AnalyticsSummaryCard.jsx    (Shared card component)
│       ├── AggregationAnalytics.jsx    (Aggregation tab)
│       ├── CapacityAnalytics.jsx       (Capacity tab)
│       ├── PolicyEffectiveness.jsx     (Policies tab)
│       └── ComparativeAnalytics.jsx    (Comparison tab)
└── services/
    └── api.js                          (Add analytics methods)
```

---

## Design Guidelines

### Color Scheme
- **Success (Green)**: Good performance, savings, high efficiency
- **Warning (Yellow)**: Medium utilization, approaching limits
- **Error (Red)**: Over capacity, bottlenecks, poor performance
- **Info (Blue)**: Neutral metrics, informational

### Chart Guidelines
- Clear axis labels
- Legends for multi-series charts
- Tooltips on hover
- Responsive sizing
- Consistent color palette

### UX Guidelines
- Loading skeletons while fetching data
- Error messages with retry buttons
- Empty states when no data available
- Refresh button for manual data reload
- Export buttons (Sprint 3)

---

## Success Criteria

✅ All 4 analytics tabs implemented
✅ Charts render correctly with real data
✅ Responsive design (desktop + tablet)
✅ Loading states and error handling
✅ Game selector working
✅ Tab navigation functional
✅ Routing configured

---

## Estimated Effort

- API service methods: 30 lines
- Shared components: ~100 lines
- Aggregation tab: ~200 lines
- Capacity tab: ~200 lines
- Policy effectiveness tab: ~200 lines
- Comparative tab: ~150 lines
- Main dashboard: ~150 lines

**Total Estimated**: ~1,030 lines

---

## Next Steps

1. ✅ Create API service methods
2. ⏳ Create shared `AnalyticsSummaryCard` component
3. ⏳ Build `AggregationAnalytics` component
4. ⏳ Build `CapacityAnalytics` component
5. ⏳ Build `PolicyEffectiveness` component
6. ⏳ Build `ComparativeAnalytics` component
7. ⏳ Create main `AnalyticsDashboard` page
8. ⏳ Add routing for analytics dashboard
9. ⏳ Test with real game data

---

**Status**: Ready to begin implementation
**Target Completion**: 2026-01-13
