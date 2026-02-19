# 3D Visualization Integration Plan

**Date**: 2026-01-15
**Status**: ⏳ PENDING INTEGRATION

---

## Current Situation

### Created Components ✅ (But Not Integrated ❌)

I created 4 visualization components that are **not currently accessible** in the UI:

1. **SupplyChain3D.jsx** (400 lines)
   - Location: `frontend/src/components/visualization/SupplyChain3D.jsx`
   - Features: Interactive 3D supply chain with Three.js, animated flows, node selection
   - Status: ❌ Not imported or used anywhere

2. **TimelineVisualization.jsx** (350 lines)
   - Location: `frontend/src/components/visualization/TimelineVisualization.jsx`
   - Features: Historical game replay with playback controls, uses SupplyChain3D
   - Status: ❌ Not imported or used anywhere

3. **GeospatialSupplyChain.jsx** (350 lines)
   - Location: `frontend/src/components/visualization/GeospatialSupplyChain.jsx`
   - Features: Real-world map with Leaflet, location-based nodes, flow animations
   - Status: ❌ Not imported or used anywhere

4. **PredictiveAnalyticsDashboard.jsx** (500 lines)
   - Location: `frontend/src/components/analytics/PredictiveAnalyticsDashboard.jsx`
   - Features: Demand forecasting charts, bullwhip prediction, cost trajectories
   - Status: ❌ Not imported or used anywhere

### Why They're Not Working

These components are **standalone files** that:
- ❌ Are not imported in `App.js` routes
- ❌ Are not referenced by any existing pages
- ❌ Have no navigation menu items
- ❌ Have missing npm dependencies (Three.js, Leaflet)
- ❌ Are not connected to backend game data

**Result**: Users cannot access these visualizations at all.

---

## Integration Strategy

### Approach 1: Tabs in GameReport (RECOMMENDED) ⭐

**Pros**:
- Natural location - users already go to GameReport after games
- Keeps all analysis in one place
- Easy to switch between views
- Minimal navigation changes

**Cons**:
- GameReport becomes larger
- May need performance optimization for multiple heavy components

**Implementation**:

1. Add Material-UI Tabs to [GameReport.jsx](frontend/src/pages/GameReport.jsx:34-36)
2. Import the 4 new components
3. Create tab panels for each visualization
4. Fetch game history data and pass to components

```jsx
// In GameReport.jsx
import SupplyChain3D from '../components/visualization/SupplyChain3D'
import TimelineVisualization from '../components/visualization/TimelineVisualization'
import GeospatialSupplyChain from '../components/visualization/GeospatialSupplyChain'
import PredictiveAnalyticsDashboard from '../components/analytics/PredictiveAnalyticsDashboard'

const [tabValue, setTabValue] = useState(0)

<Tabs value={tabValue} onChange={(e, v) => setTabValue(v)}>
  <Tab label="Overview" />
  <Tab label="3D Visualization" />
  <Tab label="Timeline Replay" />
  <Tab label="Geospatial Map" />
  <Tab label="Predictive Analytics" />
</Tabs>

{tabValue === 0 && <ExistingCharts />}
{tabValue === 1 && <SupplyChain3D nodes={nodes} edges={edges} inventoryData={data} />}
{tabValue === 2 && <TimelineVisualization gameHistory={history} nodes={nodes} edges={edges} />}
{tabValue === 3 && <GeospatialSupplyChain nodes={nodes} edges={edges} inventoryData={data} />}
{tabValue === 4 && <PredictiveAnalyticsDashboard gameId={gameId} />}
```

### Approach 2: Separate Routes

**Pros**:
- Cleaner separation of concerns
- Better performance (components load on-demand)
- Dedicated URLs for bookmarking

**Cons**:
- Requires navigation menu updates
- Users might not discover the features
- More routing complexity

**Routes to Add**:
```jsx
// In App.js
<Route path="/games/:gameId/3d-view" element={<SupplyChain3DPage />} />
<Route path="/games/:gameId/timeline" element={<TimelineReplayPage />} />
<Route path="/games/:gameId/map" element={<GeospatialMapPage />} />
<Route path="/games/:gameId/analytics" element={<PredictiveAnalyticsPage />} />
```

### Approach 3: Modal/Drawer Overlays

**Pros**:
- Quick access from any page
- Doesn't navigate away from current view
- Can show visualizations while game is running

**Cons**:
- Limited screen space
- Complex state management
- May feel cramped for 3D views

---

## Required Dependencies

### npm Packages to Install

```json
{
  "three": "^0.160.0",
  "@react-three/fiber": "^8.15.0",
  "@react-three/drei": "^9.92.0",
  "@react-three/postprocessing": "^2.15.0",
  "leaflet": "^1.9.4",
  "react-leaflet": "^4.2.1"
}
```

### Installation Command

```bash
cd frontend
npm install three @react-three/fiber @react-three/drei @react-three/postprocessing leaflet react-leaflet --legacy-peer-deps
```

### Leaflet CSS Import

Add to `frontend/src/index.js` or component:
```javascript
import 'leaflet/dist/leaflet.css'
```

---

## Data Integration Requirements

### 1. Supply Chain Network Data

Components need node and edge data:

```javascript
// Fetch from backend
const { data } = await mixedGameApi.getGameState(gameId)

const nodes = data.players.map(player => ({
  id: player.player_id,
  name: player.player_name,
  role: player.role,
  // For geospatial map:
  latitude: player.location?.latitude,
  longitude: player.location?.longitude,
  location: player.location?.name
}))

const edges = data.connections.map(conn => ({
  from: conn.upstream_player_id,
  to: conn.downstream_player_id,
  flowSpeed: 1
}))
```

### 2. Historical Game Data

TimelineVisualization needs round-by-round history:

```javascript
// Fetch from backend
const { data: gameHistory } = await mixedGameApi.getRounds(gameId)

// Format:
gameHistory = [
  {
    round_number: 1,
    players: [
      {
        player_id: 1,
        inventory_end: 20,
        backlog: 5,
        order_placed: 10,
        total_cost: 150
      },
      // ... more players
    ]
  },
  // ... more rounds
]
```

### 3. Inventory Data (Current State)

For SupplyChain3D and GeospatialSupplyChain:

```javascript
const inventoryData = {
  [playerId]: {
    inventory: 25,
    backlog: 3,
    cost: 180,
    order_placed: 12
  },
  // ... for each player
}
```

### 4. Active Flows

To animate material flowing between nodes:

```javascript
const activeFlows = [
  'player1-player2',  // Edge IDs that have recent orders
  'player2-player3'
]
```

### 5. Geospatial Locations

Nodes need real-world coordinates for map view:

```javascript
// Option 1: Store in supply chain config
// Option 2: Generate based on role (e.g., retailers near coasts, factories inland)
// Option 3: User-configurable in UI

const nodeLocations = {
  retailer1: { latitude: 40.7128, longitude: -74.0060, name: "New York" },
  wholesaler1: { latitude: 41.8781, longitude: -87.6298, name: "Chicago" },
  // ...
}
```

---

## Implementation Steps

### Phase 1: Install Dependencies (5 minutes)

1. Add packages to `frontend/package.json`
2. Run `npm install --legacy-peer-deps`
3. Import Leaflet CSS in `frontend/src/index.js`

### Phase 2: Integrate into GameReport (1-2 hours)

1. Import the 4 components in [GameReport.jsx](frontend/src/pages/GameReport.jsx)
2. Add Material-UI Tabs component
3. Create tab panels with conditional rendering
4. Fetch additional data needed:
   - Game history: `mixedGameApi.getRounds(gameId)`
   - Supply chain structure: Extract from game state
5. Pass data as props to components
6. Test each tab

### Phase 3: Data Preparation (30 minutes)

1. Create data transformation utilities:
   - `transformPlayersToNodes()` - Convert player data to node format
   - `transformConnectionsToEdges()` - Convert connections to edges
   - `buildInventoryData()` - Format inventory for visualization
   - `identifyActiveFlows()` - Detect recent order activity

2. Add helper file: `frontend/src/utils/visualizationDataHelpers.js`

### Phase 4: Location Data (30 minutes)

For geospatial map, add location data:

**Option A**: Manual assignment in supply chain config
```javascript
// Add lat/lon fields to node configuration
```

**Option B**: Auto-generate based on role
```javascript
// Retailers: Major cities
// Wholesalers: Regional hubs
// Distributors: Mid-tier cities
// Factories: Industrial areas
// Suppliers: Raw material locations
```

**Option C**: Use geocoding API (future enhancement)

### Phase 5: Polish & Testing (1 hour)

1. Test with different supply chain configurations
2. Verify playback controls work
3. Check map markers render correctly
4. Ensure 3D view performs well
5. Add loading states
6. Handle edge cases (no location data, empty history, etc.)

---

## Current Blockers

### Blocker 1: Missing Dependencies ⚠️

**Issue**: Three.js and Leaflet not installed
**Impact**: Components will throw import errors
**Resolution**: Run `npm install` (see Phase 1)

### Blocker 2: No Routes/Navigation ⚠️

**Issue**: No way for users to access the components
**Impact**: Features are invisible
**Resolution**: Add tabs to GameReport (see Phase 2)

### Blocker 3: Data Not Connected ⚠️

**Issue**: Components expect props that aren't being passed
**Impact**: Components will show empty or error
**Resolution**: Fetch and transform data (see Phase 3)

### Blocker 4: Location Data Missing ⚠️

**Issue**: GeospatialSupplyChain needs lat/lon coordinates
**Impact**: Map will be empty
**Resolution**: Add location data or auto-generate (see Phase 4)

---

## Alternative: Simpler Demo Integration

If full integration is too complex, create a **standalone demo page**:

### Quick Demo Page (30 minutes)

```jsx
// frontend/src/pages/VisualizationDemo.jsx

import React from 'react'
import { Box, Typography, Tabs, Tab } from '@mui/material'
import SupplyChain3D from '../components/visualization/SupplyChain3D'
import TimelineVisualization from '../components/visualization/TimelineVisualization'
import GeospatialSupplyChain from '../components/visualization/GeospatialSupplyChain'

// Mock data for demo
const mockNodes = [
  { id: 1, role: 'retailer', name: 'Retailer 1', latitude: 40.7128, longitude: -74.0060 },
  { id: 2, role: 'wholesaler', name: 'Wholesaler 1', latitude: 41.8781, longitude: -87.6298 },
  { id: 3, role: 'distributor', name: 'Distributor 1', latitude: 34.0522, longitude: -118.2437 },
  { id: 4, role: 'factory', name: 'Factory 1', latitude: 29.7604, longitude: -95.3698 },
]

const mockEdges = [
  { from: 2, to: 1 },
  { from: 3, to: 2 },
  { from: 4, to: 3 },
]

const mockInventoryData = {
  1: { inventory: 25, backlog: 5, cost: 180 },
  2: { inventory: 40, backlog: 2, cost: 250 },
  3: { inventory: 60, backlog: 0, cost: 320 },
  4: { inventory: 80, backlog: 0, cost: 400 },
}

export default function VisualizationDemo() {
  const [tab, setTab] = React.useState(0)

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h4" gutterBottom>
        3D Visualization Demo
      </Typography>

      <Tabs value={tab} onChange={(e, v) => setTab(v)}>
        <Tab label="3D View" />
        <Tab label="Geospatial Map" />
      </Tabs>

      <Box sx={{ height: '80vh', mt: 2 }}>
        {tab === 0 && (
          <SupplyChain3D
            nodes={mockNodes}
            edges={mockEdges}
            inventoryData={mockInventoryData}
            activeFlows={['2-1']}
          />
        )}
        {tab === 1 && (
          <GeospatialSupplyChain
            nodes={mockNodes}
            edges={mockEdges}
            inventoryData={mockInventoryData}
            activeFlows={['2-1']}
          />
        )}
      </Box>
    </Box>
  )
}
```

Add route in `App.js`:
```jsx
<Route path="/demo/visualization" element={<VisualizationDemo />} />
```

Access at: `http://localhost:8088/demo/visualization`

---

## Recommendation

**I recommend starting with the Quick Demo Page** to verify the components work, then proceeding with full integration into GameReport.

### Immediate Next Steps:

1. ✅ Install dependencies (5 min)
2. ✅ Create demo page with mock data (30 min)
3. ✅ Test that visualizations render (10 min)
4. ✅ Integrate into GameReport with tabs (1-2 hours)
5. ✅ Connect to real game data (1 hour)

---

## Testing Checklist

After integration, verify:

- [ ] 3D visualization renders with supply chain nodes
- [ ] Timeline playback controls work (play, pause, step)
- [ ] Map shows markers at correct locations
- [ ] Predictive analytics fetches data from backend
- [ ] Tabs switch correctly without errors
- [ ] Components handle missing data gracefully
- [ ] Performance is acceptable (60fps for 3D)
- [ ] Works in Chrome, Firefox, Safari
- [ ] Mobile responsive (or disabled on mobile)

---

## Success Metrics

Integration is complete when:

1. ✅ Users can access visualizations from GameReport
2. ✅ All 4 components render without errors
3. ✅ Components display real game data (not mock data)
4. ✅ Geospatial map shows nodes at correct locations
5. ✅ Timeline replay works for historical games
6. ✅ Predictive analytics connects to backend API
7. ✅ Navigation is intuitive and discoverable

---

**Status**: ⏳ Awaiting implementation
**Estimated Time**: 3-5 hours for full integration
**Next Action**: Install dependencies and create demo page
