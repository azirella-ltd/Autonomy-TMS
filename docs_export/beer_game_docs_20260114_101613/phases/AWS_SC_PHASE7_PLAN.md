# Phase 7: Enterprise & Advanced Features

**Status**: Planning
**Start Date**: 2026-01-14
**Estimated Duration**: 30-45 days
**Priority**: High - Enterprise Expansion

---

## Phase Overview

Phase 7 transforms The Beer Game from a production-ready platform into an enterprise-grade solution with mobile support, real-time collaboration, advanced AI/ML capabilities, enterprise authentication, 3D visualization, and ERP integration.

**Prerequisites**: Phase 6 Complete ✅

**Key Goals**:
1. Mobile application for iOS/Android
2. Real-time agent-to-agent (A2A) collaboration
3. Advanced ML architectures and reinforcement learning
4. Enterprise SSO/LDAP and multi-tenancy
5. 3D supply chain visualization with geospatial mapping
6. SAP S/4HANA and SAP APO integration

---

## Sprint Breakdown

### Sprint 1: Mobile Application Foundation (5-7 days)

**Objective**: Build React Native mobile app with core features

**Deliverables**:

1. **React Native Setup**
   - Project initialization with Expo/React Native CLI
   - Navigation structure (React Navigation)
   - Authentication flow
   - API client integration
   - Offline support (AsyncStorage)

2. **Core Mobile Features**
   - Login/Registration screens
   - Dashboard view
   - Game list and detail views
   - Template browser (mobile-optimized)
   - Quick Start Wizard (mobile)

3. **Mobile-Specific UI**
   - Responsive layouts for phones/tablets
   - Touch-optimized controls
   - Native components (bottom sheets, modals)
   - Gesture support (swipe, pinch-to-zoom)

4. **Push Notifications**
   - Game event notifications
   - Round completion alerts
   - Turn reminders
   - Firebase Cloud Messaging integration

**Tech Stack**:
- React Native 0.73+
- Expo SDK 50+ (optional)
- React Navigation 6
- Redux Toolkit for state
- Axios for API
- Firebase for notifications

**Success Metrics**:
- App builds for iOS and Android
- Core features functional on mobile
- Performance: <2s screen load time
- Offline mode works

---

### Sprint 2: Real-time Collaboration with A2A (7-10 days)

**Objective**: Implement Agent-to-Agent communication with WebSocket architecture

**Deliverables**:

1. **WebSocket Infrastructure**
   - FastAPI WebSocket endpoints
   - Connection management (join/leave channels)
   - Message routing and broadcasting
   - Reconnection handling
   - Redis Pub/Sub for horizontal scaling

2. **A2A Protocol Implementation**
   - Agent-to-Agent message format (JSON Schema)
   - Prompt/Response pattern
   - Agent discovery and registration
   - Message history and replay
   - Conflict resolution

3. **Multi-Agent Planning**
   - Collaborative decision-making
   - Consensus algorithms (Raft/Paxos-like)
   - Global planner coordination
   - Agent negotiation protocols
   - Distributed constraint optimization

4. **Real-time UI Updates**
   - WebSocket client (frontend/mobile)
   - Live agent activity feed
   - Real-time metrics updates
   - Collaborative dashboard
   - Agent conversation viewer

5. **Human-Agent Interaction**
   - Human can observe agent conversations
   - Human can intervene in agent decisions
   - Agent can request human approval
   - Mixed-initiative planning

**Architecture**:
```
┌─────────────┐     WebSocket     ┌──────────────┐
│   Agent 1   │ ◄────────────────►│   Redis      │
└─────────────┘                   │   Pub/Sub    │
                                  └──────────────┘
┌─────────────┐     WebSocket            ▲
│   Agent 2   │ ◄────────────────────────┤
└─────────────┘                          │
                                         │
┌─────────────┐     WebSocket            │
│   Human     │ ◄────────────────────────┤
└─────────────┘                          │
                                         │
┌─────────────┐     WebSocket            │
│  Planner    │ ◄────────────────────────┘
└─────────────┘
```

**A2A Message Format**:
```json
{
  "type": "agent_message",
  "from": "agent_retailer",
  "to": "agent_wholesaler",
  "message_id": "msg_123",
  "parent_id": "msg_122",
  "timestamp": "2026-01-14T10:00:00Z",
  "content": {
    "action": "negotiate_order",
    "proposal": {
      "quantity": 150,
      "urgency": "high",
      "reasoning": "Demand spike detected"
    }
  },
  "response_required": true,
  "timeout_ms": 5000
}
```

**Success Metrics**:
- <100ms message latency
- Support 100+ concurrent WebSocket connections
- 99.9% message delivery reliability
- Consensus reached in <10 rounds

---

### Sprint 3: Advanced AI/ML Enhancements (7-10 days)

**Objective**: Implement advanced GNN architectures and reinforcement learning

**Deliverables**:

1. **Advanced GNN Architectures**
   - Graph Attention Networks (GAT) v2
   - GraphSAINT sampling
   - Heterogeneous GNN (HeteroGNN)
   - Temporal Graph Networks (TGN)
   - Graph Transformers

2. **Reinforcement Learning Agents**
   - DQN (Deep Q-Network) agent
   - PPO (Proximal Policy Optimization)
   - A3C (Asynchronous Advantage Actor-Critic)
   - Multi-agent RL (MARL)
   - Centralized training, decentralized execution (CTDE)

3. **Model Improvements**
   - Meta-learning for quick adaptation
   - Transfer learning across supply chains
   - Multi-task learning
   - Attention mechanisms
   - Uncertainty quantification

4. **Training Infrastructure**
   - Distributed training (PyTorch DDP)
   - Hyperparameter optimization (Optuna)
   - Experiment tracking (MLflow/Weights & Biases)
   - Model versioning
   - A/B testing framework

5. **RL Environment**
   - OpenAI Gym environment wrapper
   - Custom reward functions
   - State space design
   - Action space engineering
   - Episode management

**GNN Architectures**:
```python
# Advanced GAT with edge features
class SupplyChainGATv2(nn.Module):
    def __init__(self, in_channels, hidden_channels, out_channels, heads=8):
        super().__init__()
        self.conv1 = GATv2Conv(in_channels, hidden_channels, heads=heads,
                               edge_dim=16)
        self.conv2 = GATv2Conv(hidden_channels * heads, out_channels,
                               heads=1, edge_dim=16)

    def forward(self, x, edge_index, edge_attr):
        x = F.elu(self.conv1(x, edge_index, edge_attr))
        x = F.dropout(x, p=0.5, training=self.training)
        x = self.conv2(x, edge_index, edge_attr)
        return x

# Heterogeneous GNN for multi-type nodes
class HeteroSupplyChainGNN(nn.Module):
    def __init__(self, metadata):
        super().__init__()
        self.convs = nn.ModuleDict()
        for edge_type in metadata[1]:
            src, rel, dst = edge_type
            self.convs[f"{src}_{rel}_{dst}"] = HeteroConv({
                edge_type: SAGEConv((-1, -1), 128)
            })
```

**RL Agent**:
```python
class PPOAgent:
    def __init__(self, state_dim, action_dim):
        self.policy = PolicyNetwork(state_dim, action_dim)
        self.value = ValueNetwork(state_dim)
        self.optimizer = optim.Adam([
            *self.policy.parameters(),
            *self.value.parameters()
        ], lr=3e-4)

    def select_action(self, state):
        action_probs = self.policy(state)
        dist = Categorical(action_probs)
        action = dist.sample()
        return action, dist.log_prob(action)

    def update(self, trajectories):
        # PPO update with clipped objective
        pass
```

**Success Metrics**:
- GNN accuracy: >85% on test set
- RL convergence: <500 episodes
- Inference time: <50ms per decision
- Multi-agent coordination: >80% optimal

---

### Sprint 4: Enterprise Authentication & Multi-tenancy (5-7 days)

**Objective**: Implement SSO, LDAP, and multi-tenant architecture

**Deliverables**:

1. **SSO Integration**
   - SAML 2.0 support (python-saml3)
   - OAuth 2.0 / OpenID Connect
   - Azure AD integration
   - Okta integration
   - Google Workspace SSO
   - Custom IdP support

2. **LDAP Integration**
   - Active Directory connection
   - LDAP authentication (python-ldap)
   - User synchronization
   - Group mapping to roles
   - Nested group support

3. **Multi-tenancy Architecture**
   - Tenant isolation (database-level)
   - Tenant context middleware
   - Tenant-scoped queries
   - Cross-tenant data prevention
   - Tenant administration

4. **Role-Based Access Control (RBAC)**
   - Enhanced permission system
   - Custom roles per tenant
   - Resource-level permissions
   - Audit logging
   - Compliance reporting

5. **Tenant Management**
   - Tenant provisioning API
   - Tenant settings and branding
   - Resource quotas per tenant
   - Usage tracking and billing
   - Tenant analytics

**Multi-tenancy Models**:

**Option 1: Shared Database, Separate Schemas**
```sql
CREATE SCHEMA tenant_acme;
CREATE SCHEMA tenant_globex;

-- Tables with tenant_id
CREATE TABLE tenant_acme.games (...);
CREATE TABLE tenant_globex.games (...);
```

**Option 2: Tenant Column (Chosen)**
```python
class TenantModel(Base):
    __abstract__ = True
    tenant_id = Column(Integer, ForeignKey('tenants.id'), nullable=False)

class Game(TenantModel):
    # Automatically filtered by tenant_id
    pass

# Middleware
@app.middleware("http")
async def tenant_context_middleware(request: Request, call_next):
    tenant_id = extract_tenant_from_request(request)
    set_current_tenant(tenant_id)
    response = await call_next(request)
    return response
```

**SSO Configuration**:
```python
# backend/app/core/sso.py
class SSOProvider(BaseModel):
    provider_type: str  # saml, oidc, oauth2
    entity_id: str
    sso_url: str
    x509_cert: str
    attribute_mapping: Dict[str, str]

class SAMLAuth:
    def __init__(self, settings: SSOProvider):
        self.auth = OneLogin_Saml2_Auth(
            request_data,
            custom_base_path=settings_path
        )

    def process_response(self):
        self.auth.process_response()
        if self.auth.is_authenticated():
            user_attrs = self.auth.get_attributes()
            return self.create_or_update_user(user_attrs)
```

**Success Metrics**:
- SSO login: <2s
- LDAP sync: <1 minute for 1000 users
- Tenant isolation: 100% (zero cross-tenant leaks)
- RBAC enforcement: 100%

---

### Sprint 5: 3D Visualization & Geospatial Mapping (7-10 days)

**Objective**: Build 3D supply chain visualization with geographic mapping

**Deliverables**:

1. **3D Supply Chain Visualization**
   - Three.js / React Three Fiber
   - 3D node rendering (facilities, warehouses)
   - Animated flow visualization
   - Interactive controls (orbit, zoom, pan)
   - Timeline scrubbing

2. **Geospatial Mapping**
   - Mapbox GL JS integration
   - Site location management (lat/lon)
   - Distance-based routing
   - Heatmaps for demand/supply
   - Clustering for dense regions

3. **3D Features**
   - Node sizing by inventory level
   - Edge thickness by flow volume
   - Color coding by status
   - Animation of shipments in transit
   - Camera presets (bird's eye, follow shipment)

4. **Data Model Enhancement**
   - Add latitude/longitude to nodes
   - Geocoding service integration
   - Distance calculation
   - Route optimization hints
   - Timezone handling

5. **Performance Optimization**
   - Level of detail (LOD)
   - Frustum culling
   - Instancing for repeated objects
   - WebGL optimizations
   - GPU-accelerated rendering

**3D Architecture**:
```javascript
// frontend/src/components/3d/SupplyChainScene.jsx
import { Canvas } from '@react-three/fiber'
import { OrbitControls, PerspectiveCamera } from '@react-three/drei'

const SupplyChainScene = ({ supplyChain, flowData }) => (
  <Canvas>
    <PerspectiveCamera makeDefault position={[0, 50, 100]} />
    <OrbitControls />
    <ambientLight intensity={0.5} />
    <directionalLight position={[10, 10, 5]} intensity={1} />

    {/* Render nodes as 3D facilities */}
    {supplyChain.nodes.map(node => (
      <Facility
        key={node.id}
        position={[node.lat, 0, node.lon]}
        type={node.type}
        inventoryLevel={node.inventory}
      />
    ))}

    {/* Render flows as animated lines */}
    {flowData.map(flow => (
      <AnimatedFlow
        key={flow.id}
        from={flow.source_position}
        to={flow.target_position}
        volume={flow.quantity}
      />
    ))}
  </Canvas>
)
```

**Geospatial Features**:
```javascript
// Map with supply chain overlay
import mapboxgl from 'mapbox-gl'

const SupplyChainMap = ({ nodes, flows }) => {
  useEffect(() => {
    const map = new mapboxgl.Map({
      container: 'map',
      style: 'mapbox://styles/mapbox/dark-v10',
      center: [0, 0],
      zoom: 2
    })

    // Add nodes as markers
    nodes.forEach(node => {
      new mapboxgl.Marker()
        .setLngLat([node.lon, node.lat])
        .setPopup(new mapboxgl.Popup().setHTML(`
          <h3>${node.name}</h3>
          <p>Inventory: ${node.inventory}</p>
        `))
        .addTo(map)
    })

    // Add flows as arcs
    map.on('load', () => {
      map.addSource('flows', {
        type: 'geojson',
        data: generateFlowLineStrings(flows)
      })

      map.addLayer({
        id: 'flows',
        type: 'line',
        source: 'flows',
        paint: {
          'line-width': ['get', 'volume'],
          'line-color': '#00ffff',
          'line-opacity': 0.8
        }
      })
    })
  }, [nodes, flows])

  return <div id="map" style={{ width: '100%', height: '600px' }} />
}
```

**Success Metrics**:
- 60 FPS for 3D rendering
- Support 1000+ nodes in 3D view
- Map loads <2s
- Smooth animations
- Mobile-friendly 3D controls

---

### Sprint 6: SAP Integration (7-10 days)

**Objective**: Integrate with SAP S/4HANA and SAP APO

**Deliverables**:

1. **SAP S/4HANA Integration**
   - RFC connection (pyrfc)
   - OData v4 API integration
   - Material master data sync
   - Plant and storage location data
   - Purchase order integration
   - Sales order integration
   - Inventory levels sync

2. **SAP APO Integration**
   - Demand planning data extraction
   - Supply network planning
   - Production planning integration
   - SNP optimizer results import
   - Alert and exception handling

3. **Data Mapping**
   - SAP Material → Beer Game Item
   - SAP Plant → Beer Game Node
   - SAP PO/SO → Beer Game Orders
   - SAP Stock → Beer Game Inventory
   - SAP Location → Lat/Lon mapping

4. **Real-time Sync**
   - Change data capture (CDC)
   - Webhook/IDoc listeners
   - Incremental sync
   - Conflict resolution
   - Data validation

5. **SAP Connector Service**
   - Connection pool management
   - Authentication (SSO, basic)
   - Error handling and retry
   - Rate limiting
   - Audit logging

**SAP S/4HANA Connection**:
```python
# backend/app/integrations/sap_s4hana.py
from pyrfc import Connection

class SAPS4HANAConnector:
    def __init__(self, config: SAPConfig):
        self.conn = Connection(
            ashost=config.host,
            sysnr=config.system_number,
            client=config.client,
            user=config.username,
            passwd=config.password
        )

    def get_material_master(self, material_number: str):
        """Get material master data via BAPI"""
        result = self.conn.call(
            'BAPI_MATERIAL_GET_DETAIL',
            MATERIAL=material_number
        )
        return result['MATERIAL_GENERAL_DATA']

    def get_stock_overview(self, plant: str, material: str):
        """Get current stock levels"""
        result = self.conn.call(
            'BAPI_MATERIAL_STOCK_REQ_LIST',
            PLANT=plant,
            MATERIAL=material
        )
        return result['STOCK_OVERVIEW']

    def create_purchase_order(self, po_data: Dict):
        """Create PO via BAPI"""
        result = self.conn.call(
            'BAPI_PO_CREATE1',
            PO_HEADER=po_data['header'],
            PO_ITEMS=po_data['items']
        )
        if result['RETURN']['TYPE'] == 'S':
            self.conn.call('BAPI_TRANSACTION_COMMIT')
        return result
```

**SAP OData Integration**:
```python
# Using OData v4
class SAPODataClient:
    def __init__(self, base_url: str, auth: tuple):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.auth = auth
        self.session.headers.update({
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        })

    def get_materials(self, filters: Dict = None):
        """Get materials via OData"""
        url = f"{self.base_url}/API_PRODUCT_SRV/A_Product"
        params = {'$format': 'json'}
        if filters:
            params['$filter'] = self._build_filter(filters)

        response = self.session.get(url, params=params)
        return response.json()['d']['results']

    def get_stock_by_plant(self, plant: str):
        """Get stock levels by plant"""
        url = f"{self.base_url}/API_MATERIAL_STOCK_SRV/A_MatlStkInAcctMod"
        params = {
            '$format': 'json',
            '$filter': f"Plant eq '{plant}'"
        }
        response = self.session.get(url, params=params)
        return response.json()['d']['results']
```

**SAP APO Integration**:
```python
class SAPAPOConnector:
    def get_demand_plan(self, planning_version: str):
        """Extract demand plan from APO"""
        result = self.conn.call(
            '/SAPAPO/TS_DB_READ',
            I_PLVAR=planning_version,
            I_KEYFIG='DEMAND'
        )
        return self._parse_timeseries(result)

    def get_supply_network(self):
        """Get supply network structure"""
        result = self.conn.call('/SAPAPO/SDP_NET_GET_STRUCTURE')
        return self._build_network_graph(result)

    def create_alert(self, alert_data: Dict):
        """Create APO alert for exceptions"""
        result = self.conn.call(
            '/SAPAPO/ALERT_CREATE',
            ALERT_DATA=alert_data
        )
        return result
```

**Data Sync Workflow**:
```python
class SAPSyncService:
    async def sync_master_data(self):
        """Sync master data from SAP"""
        # 1. Get materials from SAP
        materials = await self.sap.get_materials()

        # 2. Map to Beer Game items
        items = [self._map_material_to_item(m) for m in materials]

        # 3. Upsert to database
        for item in items:
            await self.db.upsert_item(item)

        return len(items)

    async def sync_inventory_levels(self):
        """Sync current inventory from SAP"""
        plants = await self.db.get_all_plants()

        for plant in plants:
            # Get SAP stock
            stock = await self.sap.get_stock_by_plant(plant.sap_plant_id)

            # Update game node inventory
            await self.update_node_inventory(plant.node_id, stock)

    async def export_orders_to_sap(self, game_id: int):
        """Export game orders back to SAP"""
        orders = await self.db.get_game_orders(game_id)

        for order in orders:
            if order.should_sync_to_sap:
                po_data = self._map_order_to_po(order)
                result = await self.sap.create_purchase_order(po_data)
                await self.db.update_order_sap_sync_status(
                    order.id,
                    result['PO_NUMBER']
                )
```

**Success Metrics**:
- SAP connection: <1s
- Master data sync: <5 minutes for 10k materials
- Real-time sync latency: <10s
- Data accuracy: >99.9%
- Zero duplicate POs

---

## Architecture Overview

### System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Mobile Apps (iOS/Android)                │
│                      React Native + Redux                    │
└────────────┬────────────────────────────────────┬───────────┘
             │                                    │
             │ REST API                           │ WebSocket
             │                                    │
┌────────────▼────────────────────────────────────▼───────────┐
│                   API Gateway (FastAPI)                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │   REST API   │  │  WebSocket   │  │     SSO      │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└────────────┬────────────────────────────────────┬───────────┘
             │                                    │
    ┌────────▼─────────┐                 ┌──────▼────────┐
    │  Business Logic  │                 │  Redis Pub/Sub │
    │   - Multi-tenant │                 │   (A2A msgs)   │
    │   - RBAC         │                 └────────────────┘
    │   - RL Training  │
    └────────┬─────────┘
             │
    ┌────────▼─────────────────────────────────────────┐
    │              Database (MariaDB)                   │
    │  ┌──────────────┐  ┌──────────────┐             │
    │  │  Tenant Data │  │   Geo Data   │             │
    │  └──────────────┘  └──────────────┘             │
    └──────────────────────────────────────────────────┘
             │
    ┌────────▼─────────┐
    │  External Systems │
    │  - SAP S/4HANA   │
    │  - SAP APO       │
    │  - LDAP/AD       │
    │  - SSO Providers │
    └──────────────────┘
```

### Data Flow - Real-time A2A Collaboration

```
1. Agent Decision Request
   Agent → WebSocket → Redis Pub/Sub → All Agents

2. Negotiation Round
   Agent A: "I need 100 units"
   Agent B: "I can supply 80 units"
   Agent C: "I have 20 units available"
   → Consensus: 80 from B, 20 from C

3. Human Oversight
   System → Human: "Agents agreed on plan X, approve?"
   Human → System: "Approved" or "Modified: Y"

4. Execution
   System → Agents: "Execute approved plan"
   Agents → Game Engine: Update orders
   Game Engine → Database: Persist state
   Database → WebSocket → All Clients: Broadcast update
```

---

## Technology Stack

### Mobile
- **Framework**: React Native 0.73+
- **Navigation**: React Navigation 6
- **State**: Redux Toolkit
- **UI**: React Native Paper
- **Notifications**: Firebase Cloud Messaging

### Real-time
- **WebSocket**: FastAPI WebSocket
- **Message Broker**: Redis Pub/Sub
- **Scaling**: Redis Sentinel/Cluster
- **Protocol**: Custom A2A JSON protocol

### AI/ML
- **GNN**: PyTorch Geometric
- **RL**: Stable-Baselines3, RLlib
- **Training**: PyTorch Distributed
- **Tracking**: MLflow, Weights & Biases
- **Optimization**: Optuna

### Enterprise
- **SSO**: python-saml3, Authlib
- **LDAP**: python-ldap
- **Multi-tenancy**: Custom middleware
- **RBAC**: Casbin or custom

### Visualization
- **3D**: Three.js, React Three Fiber
- **Maps**: Mapbox GL JS
- **Geospatial**: Turf.js, Leaflet
- **Animation**: GSAP

### Integration
- **SAP RFC**: pyrfc (SAP NW RFC SDK)
- **SAP OData**: requests + OData client
- **Sync**: Celery for background jobs
- **CDC**: Custom webhook listeners

---

## Implementation Phases

### Phase 7A: Foundation (Weeks 1-2)
- Sprint 1: Mobile app
- Sprint 2: Real-time infrastructure

### Phase 7B: Intelligence (Weeks 3-4)
- Sprint 3: Advanced AI/ML

### Phase 7C: Enterprise (Weeks 5-6)
- Sprint 4: SSO, LDAP, multi-tenancy
- Sprint 5: 3D visualization

### Phase 7D: Integration (Weeks 6-7)
- Sprint 6: SAP integration

---

## Success Metrics

### Mobile
- [ ] App store ready (iOS + Android)
- [ ] <2s app launch time
- [ ] Offline mode functional
- [ ] Push notifications: 99% delivery

### Real-time
- [ ] <100ms WebSocket latency
- [ ] 100+ concurrent connections
- [ ] 99.9% message delivery
- [ ] Agent consensus in <10 rounds

### AI/ML
- [ ] GNN accuracy: >85%
- [ ] RL convergence: <500 episodes
- [ ] Inference: <50ms
- [ ] Multi-agent coordination: >80% optimal

### Enterprise
- [ ] SSO login: <2s
- [ ] 100% tenant isolation
- [ ] LDAP sync: <1 min for 1k users
- [ ] Zero cross-tenant leaks

### Visualization
- [ ] 60 FPS in 3D
- [ ] Support 1000+ nodes
- [ ] Map load: <2s
- [ ] Mobile 3D functional

### SAP Integration
- [ ] Connection: <1s
- [ ] Sync: <5 min for 10k materials
- [ ] Real-time latency: <10s
- [ ] Data accuracy: >99.9%

---

## Risk Assessment

### High Priority Risks

1. **SAP Integration Complexity**
   - Risk: SAP APIs complex, documentation limited
   - Mitigation: Dedicated SAP consultant, sandbox environment

2. **Real-time Scalability**
   - Risk: WebSocket connections don't scale
   - Mitigation: Redis Pub/Sub, horizontal scaling, load testing

3. **RL Training Time**
   - Risk: RL convergence takes too long
   - Mitigation: Distributed training, transfer learning, PPO algorithm

### Medium Priority Risks

1. **Mobile Performance**
   - Risk: React Native performance on low-end devices
   - Mitigation: Performance profiling, native modules for critical paths

2. **Multi-tenancy Data Leaks**
   - Risk: Cross-tenant data exposure
   - Mitigation: Comprehensive testing, automated security scans

3. **3D Performance on Mobile**
   - Risk: Complex 3D scenes slow on mobile
   - Mitigation: LOD, simplified mobile scenes, WebGL optimizations

---

## Dependencies

### External Services
- Firebase (push notifications)
- Mapbox (mapping)
- SAP S/4HANA instance (integration testing)
- LDAP/AD server (authentication testing)
- SSO provider (Azure AD, Okta)

### Libraries
**Python**:
- `pyrfc` (SAP RFC)
- `python-ldap` (LDAP)
- `python-saml3` (SAML SSO)
- `stable-baselines3` (RL)
- `mlflow` (experiment tracking)

**JavaScript**:
- `react-native` (mobile)
- `three` / `@react-three/fiber` (3D)
- `mapbox-gl` (maps)
- `socket.io-client` (WebSocket)

---

## Next Steps

### Immediate Actions (Sprint 1)

1. **Mobile App Setup**
   - Initialize React Native project
   - Setup navigation structure
   - Integrate API client
   - Build authentication flow

2. **Real-time Planning**
   - Design A2A protocol
   - Setup Redis infrastructure
   - Implement WebSocket endpoints
   - Build message routing

3. **SAP Discovery**
   - Get SAP sandbox access
   - Document available APIs
   - Design data mapping
   - Create sync strategy

---

**Document Version**: 1.0
**Created**: 2026-01-14
**Status**: Ready to Start
**Phase 6 Prerequisite**: ✅ Complete (100%)
