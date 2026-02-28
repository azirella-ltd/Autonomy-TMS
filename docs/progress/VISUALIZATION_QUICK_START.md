# 3D Visualization Quick Start Guide

## How to Access

**URL**: `http://localhost:8088/games/{gameId}/visualizations`

Replace `{gameId}` with your game ID (e.g., `1`, `2`, `3`)

## Example URLs

- Game 1: `http://localhost:8088/games/1/visualizations`
- Game 2: `http://localhost:8088/games/2/visualizations`
- Game 3: `http://localhost:8088/games/3/visualizations`

## Login Credentials

- **Email**: `systemadmin@autonomy.ai`
- **Password**: `Autonomy@2026`

## 4 Visualization Tabs

### 1. 3D Visualization
- Interactive Three.js 3D supply chain
- Click nodes to see details
- Mouse drag to rotate, scroll to zoom
- Colors: Green (Retailer), Blue (Wholesaler), Purple (Distributor), Red (Factory), Orange (Supplier)

### 2. Timeline Replay
- Historical playback of game rounds
- Play/pause/step controls
- Speed adjustment (0.5x to 4x)
- Shows inventory/backlog evolution over time
- **Note**: Requires game to have played rounds

### 3. Geospatial Map
- Real-world map with node locations
- Animated flow lines between nodes
- Inventory circles (size = inventory level)
- Pan/zoom map controls
- **Note**: Locations are auto-generated based on supply chain role

### 4. Predictive Analytics
- Demand forecasting charts
- Bullwhip effect predictions
- Cost trajectory scenarios
- AI explainability (SHAP values)
- **Note**: Requires backend API integration

## Quick Test

1. Login at `http://localhost:8088/login`
2. Go to `http://localhost:8088/games/1/visualizations`
3. Check that 3D nodes appear
4. Click a node to see details
5. Switch to Map tab - verify markers show
6. Try Timeline tab (may be disabled if no rounds played)

## Troubleshooting

**Q**: No nodes appear?
**A**: Check that game has players. Go to game report first.

**Q**: Timeline tab is grayed out?
**A**: Game needs at least 1 round played. Play some rounds first.

**Q**: Map is blank?
**A**: Check browser console for errors. May need to refresh page.

**Q**: Predictive Analytics shows error?
**A**: Backend API may not be ready yet. This is expected.

## Files to Check

- Main page: `frontend/src/pages/GameVisualizations.jsx`
- Data helpers: `frontend/src/utils/visualizationDataHelpers.js`
- 3D component: `frontend/src/components/visualization/SupplyChain3D.jsx`
- Map component: `frontend/src/components/visualization/GeospatialSupplyChain.jsx`
- Timeline: `frontend/src/components/visualization/TimelineVisualization.jsx`

## Next Steps

1. Add "View Visualizations" button to GameReport page
2. Play a few game rounds to test Timeline tab
3. Add real geospatial coordinates to supply chain config (optional)
4. Complete predictive analytics backend integration

---

**Full Documentation**: See `VISUALIZATION_INTEGRATION_COMPLETE.md`

**Integration Plan**: See `VISUALIZATION_INTEGRATION_PLAN.md`
