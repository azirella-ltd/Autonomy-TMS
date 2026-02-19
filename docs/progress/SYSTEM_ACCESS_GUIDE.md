# The Continuous Autonomous Planning Platform - System Access Guide

**Date**: 2026-01-15
**System Status**: ✅ OPERATIONAL with GPU Support
**Version**: Phase 7 Complete + Options 3 & 4 Core Implementation

---

## 🚀 System Status

### Running Services
```
✅ beer-game-proxy          - Nginx reverse proxy (Port 8088)
✅ beer-game-frontend       - React frontend (Port 3000 → 8088)
✅ the_beer_game_backend_gpu - FastAPI backend with GPU (Port 8000)
✅ the_beer_game_db         - MariaDB database (Port 3306)
```

### Health Status
- **Frontend**: HEALTHY ✅
- **Backend**: HEALTHY (GPU-enabled) ✅
- **Database**: HEALTHY ✅
- **Proxy**: HEALTHY ✅

---

## 🌐 Access URLs

### Primary Access
- **Web Application**: http://localhost:8088
- **API Documentation**: http://localhost:8000/docs
- **API Base URL**: http://localhost:8088/api

### Admin Tools
- **Database Admin (phpMyAdmin)**: http://localhost:8080
  - Username: `root`
  - Password: `19890617`

### Remote Access (if configured)
- **HTTP**: http://172.29.20.187:8088
- **HTTPS**: https://172.29.20.187:8443

---

## 🔐 User Accounts & Logins

### 📊 Account Summary
- **Total Users**: 75 accounts
- **System/Group Admins**: 5 accounts
- **Players**: 70 accounts
- **Default Password**: `Autonomy@2025` (all accounts)

---

## 👤 Primary Accounts

### 1. System Administrator (RECOMMENDED)
```
Email:    systemadmin@autonomy.ai
Password: Autonomy@2025
Role:     PLAYER (with admin capabilities)
Access:   Full system access
```
**Use for**:
- System administration
- Game creation and management
- User management
- Configuration management
- All testing and development

---

## 👥 Group Administrator Accounts

### 2. Default TBG Administrator
```
Email:    tbg_admin@autonomy.ai
Password: Autonomy@2025
Role:     GROUP_ADMIN
Group:    Default TBG (Classic Beer Game)
```

### 3. Complex Supply Chain Administrator
```
Email:    complex_sc_admin@autonomy.ai
Password: Autonomy@2025
Role:     GROUP_ADMIN
Group:    Complex Supply Chain
```

### 4. Three Finished Goods TBG Administrator
```
Email:    ThreeTBG_admin@autonomy.ai
Password: Autonomy@2025
Role:     GROUP_ADMIN
Group:    Three FG TBG
```

### 5. Variable TBG Administrator
```
Email:    VarTBG_admin@autonomy.ai
Password: Autonomy@2025
Role:     GROUP_ADMIN
Group:    Variable TBG
```

---

## 🎮 Standard Beer Game Players

### Classic 4-Echelon Supply Chain
All passwords: `Autonomy@2025`

| Role | Email | Description |
|------|-------|-------------|
| **Retailer** | retailer@autonomy.ai | Serves end customers |
| **Wholesaler** | wholesaler@autonomy.ai | Supplies retailers |
| **Distributor** | distributor@autonomy.ai | Distributes to wholesalers |
| **Manufacturer** | manufacturer@autonomy.ai | Produces goods |
| **Case Mfg** | case_mfg@autonomy.ai | Packaging manufacturer |

---

## 🏭 Complex Supply Chain Players

### Distribution Centers (3 accounts)
```
dc_a@autonomy.ai       - Distribution Center A
dc_b@autonomy.ai       - Distribution Center B
dc_c@autonomy.ai       - Distribution Center C
```

### Manufacturing Plants (2 accounts)
```
plant_b1@autonomy.ai   - Plant B1
plant_b2@autonomy.ai   - Plant B2
```

### Component Suppliers - Group A (12 accounts)
```
component_supplier_a_01@autonomy.ai
component_supplier_a_02@autonomy.ai
component_supplier_a_03@autonomy.ai
component_supplier_a_04@autonomy.ai
component_supplier_a_05@autonomy.ai
component_supplier_a_06@autonomy.ai
component_supplier_a_07@autonomy.ai
component_supplier_a_08@autonomy.ai
component_supplier_a_09@autonomy.ai
component_supplier_a_10@autonomy.ai
component_supplier_a_11@autonomy.ai
component_supplier_a_12@autonomy.ai
```

### Component Suppliers - Group B (8 accounts)
```
component_supplier_b_01@autonomy.ai
component_supplier_b_02@autonomy.ai
component_supplier_b_03@autonomy.ai
component_supplier_b_04@autonomy.ai
component_supplier_b_05@autonomy.ai
component_supplier_b_06@autonomy.ai
component_supplier_b_07@autonomy.ai
component_supplier_b_08@autonomy.ai
```

### Component Suppliers - Group C (10 accounts)
```
component_supplier_c_01@autonomy.ai
component_supplier_c_02@autonomy.ai
component_supplier_c_03@autonomy.ai
component_supplier_c_04@autonomy.ai
component_supplier_c_05@autonomy.ai
component_supplier_c_06@autonomy.ai
component_supplier_c_07@autonomy.ai
component_supplier_c_08@autonomy.ai
component_supplier_c_09@autonomy.ai
component_supplier_c_10@autonomy.ai
```

### Tier 1 Suppliers - Group A (12 accounts)
```
tier1_a01@autonomy.ai through tier1_a12@autonomy.ai
```

### Tier 1 Suppliers - Group B (8 accounts)
```
tier1_b01@autonomy.ai through tier1_b08@autonomy.ai
```

### Tier 1 Suppliers - Group C (10 accounts)
```
tier1_c01@autonomy.ai through tier1_c10@autonomy.ai
```

**All Complex SC Players**: Password is `Autonomy@2025`

---

## 🎯 Quick Start Guide

### Step 1: Access the Application
1. Open browser: http://localhost:8088
2. You should see the Beer Game login page

### Step 2: Login as System Administrator
```
Email:    systemadmin@autonomy.ai
Password: Autonomy@2025
```

### Step 3: Explore the Dashboard
After login, you'll see:
- **Games**: View and create games
- **Supply Chain Configs**: 4 pre-configured supply chains
- **Users**: All 75 user accounts
- **Groups**: 4 game groups
- **Analytics**: Performance dashboards

### Step 4: Create Your First Game
1. Click "Create Game" or navigate to Games
2. Select a supply chain configuration:
   - **Default TBG**: Classic 4-echelon (simple)
   - **Three FG TBG**: Multi-product with 3 finished goods
   - **Variable TBG**: High demand variability
   - **Complex SC**: 20+ nodes, realistic topology
3. Assign players or AI agents
4. Click "Start Game"

### Step 5: Play a Round
1. View your role's current state (inventory, backlog, orders)
2. Decide order quantity
3. Submit decision
4. Watch other players/AI make decisions
5. See round results and costs

---

## 🆕 New Features (This Session)

### Option 4: Advanced AI/ML ✅ CORE COMPLETE

#### Reinforcement Learning Agents
Train supply chain agents with state-of-the-art RL algorithms:
- **PPO** (Proximal Policy Optimization)
- **SAC** (Soft Actor-Critic)
- **A2C** (Advantage Actor-Critic)

**Train an agent**:
```bash
cd backend
python scripts/training/train_rl_agents.py \
  --algorithm PPO \
  --total-timesteps 1000000 \
  --n-envs 4 \
  --device cuda
```

#### Enhanced GNN Architectures
- **GraphSAGE**: Inductive learning for unseen topologies
- **Heterogeneous GNN**: Handle multiple node/edge types
- **Temporal GNN**: Capture time-series patterns
- **Multi-task Learning**: Joint prediction (order + cost + bullwhip)

#### Predictive Analytics API
Six new endpoints for forecasting and analysis:

1. **Demand Forecasting**:
   ```bash
   POST /api/v1/predictive-analytics/forecast/demand
   {
     "game_id": 123,
     "node_id": 456,
     "horizon": 10,
     "confidence_level": 0.95
   }
   ```

2. **Bullwhip Prediction**:
   ```bash
   POST /api/v1/predictive-analytics/predict/bullwhip
   {
     "game_id": 123
   }
   ```

3. **Cost Trajectory**:
   ```bash
   POST /api/v1/predictive-analytics/forecast/cost-trajectory
   {
     "game_id": 123,
     "node_id": 456,
     "horizon": 10
   }
   ```

4. **SHAP Explanation**:
   ```bash
   POST /api/v1/predictive-analytics/explain/prediction
   {
     "game_id": 123,
     "node_id": 456,
     "round_number": 15
   }
   ```

5. **What-If Analysis**:
   ```bash
   POST /api/v1/predictive-analytics/analyze/what-if
   {
     "game_id": 123,
     "node_id": 456,
     "scenarios": [
       {"name": "Increase Stock", "changes": {"inventory": 30}}
     ]
   }
   ```

6. **Insights Report**:
   ```bash
   POST /api/v1/predictive-analytics/insights/report
   {
     "game_id": 123
   }
   ```

### Option 3: 3D Visualization ✅ CORE COMPLETE

#### 3D Supply Chain Visualization
- Interactive Three.js 3D view
- Animated material flows
- Inventory-based node sizing
- Camera controls (rotate, zoom, pan)
- Role-based color coding

**Access**: Component available at `frontend/src/components/visualization/SupplyChain3D.jsx`

#### Timeline Playback
- Historical game replay
- Variable playback speed (0.5x - 4x)
- Round-by-round scrubbing
- Performance metrics overlay

**Access**: Component at `frontend/src/components/visualization/TimelineVisualization.jsx`

#### Geospatial Mapping
- Real-world location mapping
- Leaflet + OpenStreetMap integration
- Animated flow lines
- Inventory radius visualization

**Access**: Component at `frontend/src/components/visualization/GeospatialSupplyChain.jsx`

#### Predictive Analytics Dashboard
- Demand forecast charts
- Bullwhip risk heatmaps
- Cost trajectory scenarios
- Integrated with all prediction APIs

**Access**: Component at `frontend/src/components/analytics/PredictiveAnalyticsDashboard.jsx`

---

## 🔧 Database Access

### Connection Details
- **Host**: localhost
- **Port**: 3306
- **Database**: `beer_game`
- **User**: `beer_user`
- **Password**: `change-me-user`

### Useful Queries

**List all users**:
```sql
SELECT id, email, user_type, full_name, is_active
FROM users
ORDER BY user_type, email;
```

**Count users by type**:
```sql
SELECT user_type, COUNT(*) as count
FROM users
GROUP BY user_type;
```

**View recent games**:
```sql
SELECT id, name, status, created_at
FROM games
ORDER BY created_at DESC
LIMIT 10;
```

**Check supply chain configurations**:
```sql
SELECT id, name, description
FROM supply_chain_configs;
```

---

## 🔄 Common Operations

### Restart Services
```bash
# Restart all services
docker compose restart

# Restart specific service
docker compose restart backend
docker compose restart frontend

# View logs
docker compose logs -f backend
docker compose logs -f frontend
```

### Database Operations
```bash
# Connect to database
docker exec -it the_beer_game_db mysql -ubeer_user -p'change-me-user' beer_game

# Backup database
docker exec the_beer_game_db mysqldump -ubeer_user -p'change-me-user' beer_game > backup.sql

# Reset admin password
make reset-admin
```

### Training ML Models
```bash
# Train RL agent (PPO)
cd backend
python scripts/training/train_rl_agents.py --algorithm PPO --total-timesteps 100000

# Train GNN model
python scripts/training/train_gnn.py --config "Default TBG" --epochs 50

# View training logs
tensorboard --logdir logs/rl
```

---

## 📊 Testing the New Features

### Test Predictive Analytics

1. **Start a game** as `systemadmin@autonomy.ai`

2. **Play several rounds** (at least 10)

3. **Test API endpoints** using curl or Postman:
   ```bash
   # Get demand forecast
   curl -X POST http://localhost:8088/api/v1/predictive-analytics/forecast/demand \
     -H "Content-Type: application/json" \
     -d '{"game_id": 1, "node_id": 1, "horizon": 10}'

   # Get bullwhip prediction
   curl -X POST http://localhost:8088/api/v1/predictive-analytics/predict/bullwhip \
     -H "Content-Type: application/json" \
     -d '{"game_id": 1}'
   ```

4. **View results** in the analytics dashboard

### Test 3D Visualization

1. **Create a game** with multiple nodes

2. **Navigate to visualization tab** (once integrated)

3. **Interact with 3D view**:
   - Rotate: Left mouse drag
   - Zoom: Mouse wheel
   - Pan: Right mouse drag
   - Select: Click on nodes

4. **Try timeline playback**:
   - Play/pause controls
   - Adjust playback speed
   - Scrub timeline slider

5. **View geospatial map**:
   - See nodes on real-world map
   - Watch animated flows
   - Toggle inventory radius

---

## 🐛 Troubleshooting

### Cannot Login
- **Check password**: Default is `Autonomy@2025`
- **Check email format**: Must include `@autonomy.ai`
- **Reset password**: Use `make reset-admin`

### Services Not Running
```bash
# Check status
docker ps

# Restart services
docker compose restart

# View logs for errors
docker compose logs backend
docker compose logs frontend
```

### Database Connection Errors
```bash
# Check database is running
docker ps | grep db

# Test connection
docker exec the_beer_game_db mysql -ubeer_user -p'change-me-user' -e "SELECT 1"

# Restart database
docker compose restart db
```

### GPU Not Detected
```bash
# Check GPU availability
docker exec the_beer_game_backend_gpu python -c "import torch; print(torch.cuda.is_available())"

# Check NVIDIA drivers
nvidia-smi

# Rebuild with GPU support
make rebuild-backend FORCE_GPU=1
```

---

## 📚 Documentation

### Executive & Business
- **Executive Summary**: `EXECUTIVE_SUMMARY.md` (18,000 words)
  - AWS SC DM comparison
  - Business value and ROI (40x first year)
  - Use cases and competitive analysis

### Implementation Status
- **Implementation Summary**: `IMPLEMENTATION_COMPLETE_SUMMARY.md`
  - All completed work
  - Code statistics
  - Testing checklist

- **Implementation Status**: `POST_PHASE7_IMPLEMENTATION_STATUS.md`
  - Progress tracking
  - Remaining work
  - Timeline estimates

### Technical Guides
- **Option 4 Guide**: `OPTION4_ADVANCED_AI_ML_README.md`
  - RL training workflows
  - GNN architectures
  - API usage examples

- **Get Started**: `GET_STARTED.md`
  - Basic setup
  - First game walkthrough

- **CLAUDE.md**: Project instructions for AI assistance

---

## 🎓 Learning Resources

### Understanding the Beer Game
1. **What is it?**: Classic supply chain simulation demonstrating the bullwhip effect
2. **Key Concept**: Small demand variations amplify upstream
3. **Goal**: Minimize total supply chain cost while maintaining service levels

### Key Metrics
- **Inventory Holding Cost**: $0.50 per unit per round
- **Backlog Cost**: $1.00 per unit per round
- **Total Cost**: Sum of holding + backlog costs
- **Service Level**: % of orders fulfilled without backlog

### Winning Strategies
1. **Stable Ordering**: Avoid over-reacting to demand changes
2. **Information Sharing**: Coordinate with supply chain partners
3. **Lead Time Awareness**: Account for 2-round delivery delays
4. **Base Stock Policy**: Maintain target inventory level
5. **AI Assistance**: Use ML forecasts to inform decisions

---

## 🚀 Next Steps

### For Developers
1. **Integrate new features** into main UI
2. **Complete Option 4**: AutoML, advanced training (7-12 days)
3. **Complete Option 3**: VR/AR, animations (5-9 days)
4. **Start Option 2**: Mobile app (10-15 days)
5. **Start Option 1**: Enterprise features (7-10 days)

### For Business Users
1. **Test the platform** with various scenarios
2. **Run pilot programs** with 10-20 users
3. **Gather feedback** on new predictive features
4. **Create case studies** documenting results
5. **Plan commercial launch** (Q2 2026)

### For Researchers
1. **Train custom RL agents** on different supply chains
2. **Experiment with GNN architectures**
3. **Validate predictions** against historical data
4. **Publish findings** on bullwhip mitigation
5. **Contribute to open source** codebase

---

## 📞 Support

### System Issues
- Check logs: `docker compose logs`
- Restart services: `docker compose restart`
- Full rebuild: `make rebuild-db && make up`

### Feature Questions
- Review documentation in `/docs`
- Check API docs: http://localhost:8000/docs
- Read source code comments

### Development Help
- Follow `CLAUDE.md` instructions
- Use provided Makefile commands
- Refer to architecture docs

---

## ✅ Pre-Flight Checklist

Before presenting to stakeholders:

- [ ] System is running (all 4 containers healthy)
- [ ] Can login as `systemadmin@autonomy.ai`
- [ ] Can view games dashboard
- [ ] Can create a new game
- [ ] Can play at least one round
- [ ] Can view analytics
- [ ] API documentation is accessible
- [ ] Database is accessible
- [ ] New features are documented
- [ ] Executive summary is ready

---

## 🎉 Summary

**The Continuous Autonomous Planning Platform is OPERATIONAL** with:
- ✅ 75 user accounts ready for testing
- ✅ 4 supply chain configurations
- ✅ GPU-enabled ML training
- ✅ Advanced AI/ML core features (Option 4)
- ✅ 3D visualization core features (Option 3)
- ✅ Comprehensive predictive analytics
- ✅ Production-ready infrastructure

**Access Now**: http://localhost:8088
**Login**: `systemadmin@autonomy.ai` / `Autonomy@2025`

---

**Document Version**: 1.0
**Last Updated**: 2026-01-15
**Status**: System Operational
**Next Review**: As needed
