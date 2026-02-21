# Autonomy Platform - Mobile Application

**Complete Documentation for iOS and Android Native Applications**

**Version**: 2.0.0
**Date**: February 21, 2026
**React Native**: 0.73.2
**Status**: In Development

---

## Executive Summary

The Autonomy Mobile Application extends the platform's capabilities to iOS and Android devices, enabling planners, managers, and users to monitor AI agents, manage forecasts, review supply plans, participate in supply chain simulations, and access real-time analytics from anywhere. Built with React Native 0.73.2, the mobile app provides a native experience with offline mode, push notifications, and seamless WebSocket synchronization with the backend platform.

### Key Capabilities

- **Native iOS & Android**: Single codebase for both platforms using React Native
- **Planning on the Go**: Forecasting, supply plans, inventory optimization from mobile
- **AI Agent Monitoring**: Track TRM/GNN agent decisions, approve/override from worklist
- **Offline Mode**: Queue actions and sync when connectivity resumes
- **Push Notifications**: Real-time alerts for planning events, agent decisions, scenario updates
- **WebSocket Integration**: Live state updates via Socket.IO
- **Material Design UI**: Consistent, professional interface using React Native Paper
- **Biometric Authentication**: Face ID/Touch ID support for secure, fast login
- **Real-Time Analytics**: Mobile-optimized charts and dashboards
- **Simulation Support**: Monitor and participate in supply chain scenarios

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Technology Stack](#technology-stack)
3. [Setup & Installation](#setup--installation)
4. [Project Structure](#project-structure)
5. [Core Features](#core-features)
6. [State Management](#state-management)
7. [API Integration](#api-integration)
8. [Offline Mode](#offline-mode)
9. [Push Notifications](#push-notifications)
10. [WebSocket Real-Time Updates](#websocket-real-time-updates)
11. [Screens & Navigation](#screens--navigation)
12. [Testing](#testing)
13. [Performance Optimization](#performance-optimization)
14. [Build & Deployment](#build--deployment)
15. [Troubleshooting](#troubleshooting)

---

## Architecture Overview

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   Mobile Application                     │
│                   (React Native 0.73.2)                  │
│                                                          │
│  ┌──────────────────────────────────────────────────┐  │
│  │         Presentation Layer (Screens)              │  │
│  │  Login, Dashboard, Planning, AI Agents,          │  │
│  │  Simulation, Analytics, Profile                   │  │
│  └──────────────────────────────────────────────────┘  │
│                         ↕                                │
│  ┌──────────────────────────────────────────────────┐  │
│  │      State Management (Redux Toolkit)             │  │
│  │  Auth, Planning, Scenarios, Agents, UI Slices    │  │
│  └──────────────────────────────────────────────────┘  │
│                         ↕                                │
│  ┌──────────────────────────────────────────────────┐  │
│  │           Services Layer                          │  │
│  │  API (Axios) | WebSocket (Socket.IO)             │  │
│  │  Notifications (FCM) | Offline Queue              │  │
│  └──────────────────────────────────────────────────┘  │
│                                                          │
└─────────────────────────────────────────────────────────┘
                         ↕
              ┌─────────────────────┐
              │   Backend Platform   │
              │   (FastAPI/Python)   │
              │  PostgreSQL Database │
              └─────────────────────┘
                         ↕
              ┌─────────────────────┐
              │ Firebase Cloud       │
              │ Messaging (FCM)      │
              └─────────────────────┘
```

### Data Flow

**Authentication Flow**:
1. User enters credentials → LoginScreen
2. authSlice.login() dispatches → API call to `/auth/login`
3. Backend returns JWT token → Store in AsyncStorage + Redux state
4. Navigate to Dashboard → Enable WebSocket connection

**Planning Data Flow**:
1. User opens Planning screen → Fetch pipeline configs, supply plans, forecasts
2. User triggers action (e.g., Start Forecast Run) → API call to backend
3. Backend processes asynchronously → WebSocket pushes progress updates
4. Mobile receives update → Redux state refreshes → UI re-renders

**Scenario State Synchronization Flow**:
1. Backend scenario state changes → FastAPI emits WebSocket event
2. Mobile WebSocket client receives event → Dispatch to scenariosSlice
3. Redux state updates → React components re-render
4. UI reflects latest scenario state in real-time

**Offline Mode Flow**:
1. User makes decision (e.g., approve supply plan) → Offline queue
2. Action saved to AsyncStorage with timestamp
3. When connectivity resumes → Offline service processes queue
4. Actions replayed to backend → Sync state

---

## Technology Stack

### Core Framework
- **React Native 0.73.2**: Cross-platform mobile framework
- **React 18.2.0**: UI library with hooks and functional components
- **TypeScript 5.3.3**: Type-safe JavaScript

### Navigation
- **React Navigation 6.x**: Native-like navigation
  - Stack Navigator: For screen hierarchies (e.g., Planning Detail stack)
  - Bottom Tab Navigator: Main app navigation (Dashboard, Planning, Agents, Simulation, Profile)

### State Management
- **Redux Toolkit 2.0.1**: Modern Redux with reduced boilerplate
- **React Redux 9.0.4**: React bindings for Redux
- **Redux Thunk**: Async action handling (included in RTK)

### API & Data
- **Axios 1.6.5**: HTTP client with interceptors for JWT
- **Socket.IO Client 4.6.1**: WebSocket client for real-time updates
- **AsyncStorage 1.21.0**: Local storage for offline data

### UI Components
- **React Native Paper 5.11.6**: Material Design components
- **React Native Vector Icons 10.0.3**: Icon library
- **React Native Safe Area Context 4.8.2**: Safe area management for notches/insets

### Animations & Gestures
- **React Native Reanimated 3.6.1**: High-performance animations
- **React Native Gesture Handler 2.14.1**: Native gesture handling

### Charts & Visualization
- **Victory Native 36.9.2**: Mobile-optimized charts (line, bar, pie)
- **React Native SVG 14.1.0**: SVG rendering for custom visualizations

### Push Notifications
- **Firebase Cloud Messaging (FCM) 19.0.1**: Push notifications for iOS and Android

### Testing
- **Jest 29.7.0**: Unit testing framework
- **React Native Testing Library 12.4.3**: Component testing
- **Redux Mock Store 1.5.4**: Mock Redux store for testing

### Development Tools
- **Metro Bundler 0.77.0**: JavaScript bundler
- **Babel 7.23.7**: JavaScript transpiler
- **ESLint 8.56.0**: Linting
- **Prettier 3.1.1**: Code formatting

---

## Setup & Installation

### Prerequisites

#### Required
- **Node.js 18+**: JavaScript runtime
- **npm or yarn**: Package manager
- **React Native CLI**: `npm install -g react-native-cli`
- **Git**: Version control

#### iOS Development (macOS only)
- **Xcode 14+**: iOS development environment
- **CocoaPods 1.15+**: Dependency manager for iOS
- **iOS Simulator or physical device**

#### Android Development
- **Android Studio**: Android development environment
- **Android SDK Platform 33+** (via Android Studio SDK Manager)
- **Android Emulator or physical device**
- **Java Development Kit (JDK) 17**

### Installation Steps

#### 1. Clone Repository and Navigate to Mobile Directory

```bash
cd /home/trevor/Documents/Autonomy/Autonomy
cd mobile
```

#### 2. Install JavaScript Dependencies

```bash
npm install
```

This installs all packages listed in `package.json` (~300MB).

#### 3. iOS Setup (macOS only)

```bash
cd ios
pod install
cd ..
```

This installs native iOS dependencies via CocoaPods (~200MB).

**Troubleshooting iOS Pod Install**:
```bash
# If pod install fails, try:
cd ios
rm -rf Pods Podfile.lock
pod install --repo-update
cd ..
```

#### 4. Android Setup

No additional steps required. Gradle dependencies will download on first build.

**Verify Android SDK**:
```bash
# Check ANDROID_HOME is set
echo $ANDROID_HOME
# Should output: /Users/<username>/Library/Android/sdk (macOS)
# Or: ~/Android/Sdk (Linux)
```

#### 5. Environment Configuration

Create `.env` file in `mobile/` directory:

```bash
cp .env.example .env
```

Edit `.env`:

```env
# Backend API
API_BASE_URL=http://172.29.20.187:8000
WS_URL=ws://172.29.20.187:8000/ws

# Firebase (for push notifications)
FIREBASE_PROJECT_ID=autonomy-mobile
FIREBASE_APP_ID=1:123456789012:ios:abcdef1234567890
FIREBASE_API_KEY=AIzaSyC...

# Environment
ENVIRONMENT=development
```

**For Local Development** (localhost on simulator):
```env
API_BASE_URL=http://localhost:8000
WS_URL=ws://localhost:8000/ws
```

**For Physical Devices** (use host machine IP):
```env
API_BASE_URL=http://172.29.20.187:8000
WS_URL=ws://172.29.20.187:8000/ws
```

#### 6. Start Backend Platform

In a separate terminal:

```bash
cd /home/trevor/Documents/Autonomy/Autonomy
make up
```

Wait for backend to be healthy:
```bash
docker compose ps
# All services should show "healthy" status
```

---

## Running the Application

### iOS (Simulator)

```bash
npm run ios
```

Or specify simulator:
```bash
npm run ios -- --simulator="iPhone 15"
```

### iOS (Physical Device)

1. Open `ios/Autonomy.xcworkspace` in Xcode
2. Select your device from device list
3. Click Run button
4. Xcode will handle code signing automatically

### Android (Emulator)

1. Start Android emulator from Android Studio:
   - Tools → AVD Manager → Select device → Play button

2. Run app:
```bash
npm run android
```

### Android (Physical Device)

1. Enable USB Debugging on device:
   - Settings → About Phone → Tap "Build Number" 7 times
   - Settings → Developer Options → Enable "USB Debugging"

2. Connect device via USB

3. Verify device is detected:
```bash
adb devices
```

4. Run app:
```bash
npm run android
```

### Start Metro Bundler Separately

```bash
npm start
```

**Reset Cache**:
```bash
npm start -- --reset-cache
```

---

## Project Structure

```
mobile/
├── iOS Native Code
│   ├── Autonomy.xcworkspace          # Xcode workspace
│   ├── Autonomy/
│   │   ├── AppDelegate.mm            # iOS app lifecycle
│   │   ├── Info.plist                 # iOS configuration
│   │   └── GoogleService-Info.plist   # Firebase config (add this)
│   └── Podfile                        # CocoaPods dependencies
│
├── Android Native Code
│   ├── app/
│   │   ├── build.gradle               # App-level Gradle
│   │   ├── src/main/
│   │   │   ├── AndroidManifest.xml
│   │   │   └── java/com/autonomy/     # Native Java/Kotlin code
│   │   └── google-services.json       # Firebase config (add this)
│   └── build.gradle                   # Project-level Gradle
│
├── Source Code (src/)
│   ├── App.tsx                        # Root component
│   │
│   ├── navigation/
│   │   └── AppNavigator.tsx           # Navigation structure
│   │
│   ├── screens/                       # Screen components
│   │   ├── Auth/
│   │   │   ├── LoginScreen.tsx
│   │   │   └── RegisterScreen.tsx
│   │   ├── Dashboard/
│   │   │   └── DashboardScreen.tsx
│   │   ├── Planning/
│   │   │   ├── ForecastingScreen.tsx
│   │   │   ├── ForecastPipelineDetailScreen.tsx
│   │   │   ├── SupplyPlanScreen.tsx
│   │   │   ├── InventoryScreen.tsx
│   │   │   └── MPSScreen.tsx
│   │   ├── Agents/
│   │   │   ├── AgentDashboardScreen.tsx
│   │   │   ├── WorklistScreen.tsx
│   │   │   └── AgentDetailScreen.tsx
│   │   ├── Scenarios/
│   │   │   ├── ScenariosListScreen.tsx
│   │   │   ├── ScenarioDetailScreen.tsx
│   │   │   ├── ScenarioDetailWithChatScreen.tsx
│   │   │   └── CreateScenarioScreen.tsx
│   │   ├── Analytics/
│   │   │   └── AnalyticsScreen.tsx
│   │   └── Profile/
│   │       └── ProfileScreen.tsx
│   │
│   ├── components/                    # Reusable components
│   │   ├── common/
│   │   │   ├── LoadingSpinner.tsx
│   │   │   ├── ErrorBoundary.tsx
│   │   │   ├── EmptyState.tsx
│   │   │   ├── Toast.tsx
│   │   │   └── OfflineBanner.tsx
│   │   ├── planning/
│   │   │   ├── PipelineConfigCard.tsx
│   │   │   ├── RunStatusBadge.tsx
│   │   │   ├── ForecastChart.tsx
│   │   │   └── SupplyPlanSummary.tsx
│   │   ├── charts/
│   │   │   ├── LineChart.tsx
│   │   │   ├── BarChart.tsx
│   │   │   └── PieChart.tsx
│   │   └── chat/                      # Agent chat components
│   │       ├── ChatMessage.tsx
│   │       ├── ChatInput.tsx
│   │       ├── ChatMessageList.tsx
│   │       ├── TypingIndicator.tsx
│   │       ├── AgentSuggestionCard.tsx
│   │       └── ChatContainer.tsx
│   │
│   ├── store/                         # Redux state management
│   │   ├── index.ts                   # Store configuration
│   │   └── slices/
│   │       ├── authSlice.ts           # Authentication state
│   │       ├── planningSlice.ts       # Planning state (forecasts, supply plans)
│   │       ├── scenariosSlice.ts      # Simulation scenarios state
│   │       ├── agentsSlice.ts         # AI agent monitoring state
│   │       ├── analyticsSlice.ts      # Analytics state
│   │       ├── chatSlice.ts           # Agent chat state
│   │       └── uiSlice.ts            # UI state (toasts, modals, theme)
│   │
│   ├── services/                      # API & external services
│   │   ├── api.ts                     # Axios HTTP client
│   │   ├── websocket.ts              # Socket.IO WebSocket client
│   │   ├── notifications.ts          # Firebase Cloud Messaging
│   │   ├── offline.ts                # Offline mode queue
│   │   └── chat.ts                    # Agent chat service
│   │
│   ├── theme/
│   │   └── index.ts                   # Material Design theme
│   │
│   ├── utils/                         # Utility functions
│   ├── constants/                     # Constants
│   └── types/                         # TypeScript types
│
├── Assets
│   ├── images/                        # Images
│   ├── fonts/                         # Custom fonts
│   └── icons/                         # App icons
│
├── Tests
│   ├── __tests__/
│   │   ├── screens/                   # Screen tests
│   │   ├── store/slices/              # Redux slice tests
│   │   └── services/                  # Service tests
│   ├── jest.config.js                 # Jest configuration
│   └── jest.setup.js                  # Test setup
│
└── Configuration
    ├── package.json                   # Dependencies
    ├── tsconfig.json                  # TypeScript config
    ├── babel.config.js                # Babel config
    ├── metro.config.js                # Metro bundler config
    ├── app.json                       # App metadata
    └── .env.example                   # Environment template
```

---

## Core Features

### 1. Authentication & Security

**Features**:
- Email/password login
- User registration
- Biometric authentication (Face ID/Touch ID)
- "Remember Me" functionality
- Password reset
- JWT token management
- Auto-refresh token before expiry

**Implementation** (`src/screens/Auth/LoginScreen.tsx`):
```typescript
import { useDispatch } from 'react-redux';
import { login } from '../../store/slices/authSlice';
import ReactNativeBiometrics from 'react-native-biometrics';

const LoginScreen = () => {
  const dispatch = useDispatch();

  const handleLogin = async (email: string, password: string) => {
    await dispatch(login({ email, password })).unwrap();
    // Navigate to dashboard on success
  };

  const handleBiometricAuth = async () => {
    const rnBiometrics = new ReactNativeBiometrics();
    const { success } = await rnBiometrics.simplePrompt({
      promptMessage: 'Authenticate'
    });

    if (success) {
      // Retrieve stored credentials from secure storage
      // Login automatically
    }
  };

  return (
    <View>
      <TextInput placeholder="Email" />
      <TextInput placeholder="Password" secureTextEntry />
      <Button onPress={handleLogin}>Login</Button>
      <Button onPress={handleBiometricAuth}>Login with Face ID</Button>
    </View>
  );
};
```

**Security Features**:
- JWT token stored in AsyncStorage (HTTP-only equivalent for mobile)
- Automatic token refresh 5 minutes before expiry
- Biometric credentials stored in iOS Keychain / Android Keystore
- HTTPS/TLS for all API calls (enforced in production)

---

### 2. Dashboard

**Features**:
- Overview metrics (active scenarios, active forecast pipelines, pending approvals)
- Planning status cards (latest forecast run, supply plan status, inventory alerts)
- AI agent health summary (agent score, touchless rate, override rate)
- Quick actions (View Worklist, Start Forecast Run, Browse Scenarios)
- Recent activity feed
- Notifications badge

**Key Metrics Displayed**:
- Active Forecast Pipelines
- Pending Supply Plan Approvals
- Agent Touchless Rate (%)
- Open Worklist Items
- Active Scenarios Count

**Implementation** (`src/screens/Dashboard/DashboardScreen.tsx`):
```typescript
const DashboardScreen = () => {
  const { user } = useSelector((state: RootState) => state.auth);
  const { pipelineConfigs, latestRun } = useSelector((state: RootState) => state.planning);
  const { worklistCount, agentScore } = useSelector((state: RootState) => state.agents);

  return (
    <ScrollView>
      <Card>
        <Title>Welcome, {user?.name}</Title>
        <Paragraph>You have {worklistCount} worklist items pending</Paragraph>
      </Card>

      <Card>
        <Title>Planning Overview</Title>
        <View>
          <Text>Forecast Pipelines: {pipelineConfigs.length}</Text>
          <Text>Latest Run: {latestRun?.status || 'None'}</Text>
          <Text>Agent Score: {agentScore}</Text>
        </View>
      </Card>

      <Card>
        <Title>Quick Actions</Title>
        <Button onPress={() => nav.navigate('Worklist')}>View Worklist</Button>
        <Button onPress={() => nav.navigate('Forecasting')}>Forecasting</Button>
        <Button onPress={() => nav.navigate('ScenariosList')}>Scenarios</Button>
      </Card>
    </ScrollView>
  );
};
```

---

### 3. Planning

The Planning module is the primary focus of the mobile app, providing on-the-go access to key planning workflows.

#### 3.1 Forecasting

**Features**:
- View forecast pipeline configs for the selected supply chain configuration
- Overview cards showing pipeline model type, clustering method, cadence, and metric
- Start new forecast pipeline runs
- Monitor run progress (pending → running → completed → published)
- View run results (records processed, error messages, run log)
- Publish completed runs to the core Forecast table
- Create and edit pipeline configurations with all AWS SC parameters

**Pipeline Configuration Parameters** (24+ fields organized in 5 sections):

| Section | Parameters |
|---------|-----------|
| Dataset & Column Mapping | demand_item, demand_point, target_column, date_column |
| Forecast Settings | time_bucket (D/W/M), forecast_horizon, number_of_items_analyzed, forecast_metric (WAPE/MAE/RMSE) |
| Data Quality Thresholds | min_observations, cv_sq_threshold, adi_threshold, ignore_numeric_columns |
| Clustering | cluster_selection_method (9 algorithms), min/max_clusters, min_cluster_size, min_cluster_size_uom |
| Feature Engineering | characteristics_creation_method, feature_correlation_threshold, feature_importance_method, feature_importance_threshold, pca_variance_threshold, pca_importance_threshold |

**Implementation** (`src/screens/Planning/ForecastingScreen.tsx`):
```typescript
const ForecastingScreen = () => {
  const dispatch = useDispatch();
  const { pipelineConfigs, runs, loading } = useSelector((state: RootState) => state.planning);
  const [selectedConfigId, setSelectedConfigId] = useState<number | null>(null);

  useEffect(() => {
    dispatch(fetchPipelineConfigs({ configId: scConfigId }));
  }, [scConfigId]);

  const activePipeline = pipelineConfigs.find(c => c.is_active) || pipelineConfigs[0];

  const handleStartRun = async () => {
    if (!selectedConfigId) return;
    await dispatch(startPipelineRun({ pipeline_config_id: selectedConfigId }));
    dispatch(fetchPipelineRuns({ pipeline_config_id: selectedConfigId }));
  };

  return (
    <ScrollView>
      {/* Overview Cards */}
      <View style={styles.cardsRow}>
        <MetricCard label="Pipeline" value={activePipeline?.model_type || 'Not Configured'} />
        <MetricCard label="Clustering" value={activePipeline?.cluster_selection_method || '—'} />
        <MetricCard label="Cadence" value={bucketLabel(activePipeline?.time_bucket)} />
        <MetricCard label="Metric" value={(activePipeline?.forecast_metric || '—').toUpperCase()} />
      </View>

      {/* Pipeline Config Selector */}
      <Card>
        <Title>Pipeline Controls</Title>
        <Picker selectedValue={selectedConfigId} onValueChange={setSelectedConfigId}>
          {pipelineConfigs.map(c => (
            <Picker.Item key={c.id} label={c.name} value={c.id} />
          ))}
        </Picker>
        <Button onPress={handleStartRun} disabled={loading}>Start Run</Button>
        <Button onPress={() => nav.navigate('PipelineDetail', { configId: selectedConfigId })}>
          Edit Config
        </Button>
      </Card>

      {/* Run History */}
      <Card>
        <Title>Run History</Title>
        <FlatList
          data={runs}
          renderItem={({ item }) => (
            <RunRow
              run={item}
              onPublish={() => dispatch(publishRun(item.id))}
              onRerun={() => dispatch(reExecuteRun(item.id))}
            />
          )}
        />
      </Card>
    </ScrollView>
  );
};
```

#### 3.2 Supply Planning

**Features**:
- View generated supply plans (PO/TO/MO requests)
- Supply plan approval workflow (approve/reject with notes)
- Monitor supply plan generation progress
- View probabilistic balanced scorecard results
- Filter by product, site, date range

**Implementation** (`src/screens/Planning/SupplyPlanScreen.tsx`):
```typescript
const SupplyPlanScreen = () => {
  const { supplyPlans, loading } = useSelector((state: RootState) => state.planning);

  return (
    <ScrollView>
      <Card>
        <Title>Supply Plans</Title>
        <FlatList
          data={supplyPlans}
          renderItem={({ item }) => (
            <SupplyPlanCard
              plan={item}
              onApprove={() => dispatch(approvePlan(item.id))}
              onReject={() => dispatch(rejectPlan(item.id))}
            />
          )}
        />
      </Card>
    </ScrollView>
  );
};
```

#### 3.3 Inventory Optimization

**Features**:
- View current inventory levels across sites
- Safety stock policy overview (4 policy types: abs_level, doc_dem, doc_fcst, sl)
- Inventory alerts (stockouts, overstock)
- Inventory projection charts

#### 3.4 Master Production Scheduling (MPS)

**Features**:
- View MPS plan items
- Capacity check summaries
- Key material requirements

---

### 4. AI Agent Monitoring

**Features**:
- Agent dashboard with performance metrics (agent score, touchless rate, override rate)
- Worklist for exception triage (Ask Why, Accept, Override with reason)
- TRM agent decision history (ATP, Rebalancing, PO Creation, Order Tracking)
- CDC trigger log and retraining status
- Agent-to-agent conversation monitoring
- Human intervention controls

**Worklist Implementation** (`src/screens/Agents/WorklistScreen.tsx`):
```typescript
const WorklistScreen = () => {
  const { worklistItems, loading } = useSelector((state: RootState) => state.agents);

  const handleAccept = (itemId: number) => {
    dispatch(resolveWorklistItem({ id: itemId, action: 'accept' }));
  };

  const handleOverride = (itemId: number, reason: string, newValue: any) => {
    dispatch(resolveWorklistItem({
      id: itemId,
      action: 'override',
      override_reason: reason,
      override_value: newValue,
    }));
  };

  return (
    <FlatList
      data={worklistItems}
      renderItem={({ item }) => (
        <WorklistCard
          item={item}
          onAccept={() => handleAccept(item.id)}
          onAskWhy={() => nav.navigate('AgentDetail', { itemId: item.id })}
          onOverride={(reason, val) => handleOverride(item.id, reason, val)}
        />
      )}
      refreshControl={
        <RefreshControl refreshing={loading} onRefresh={() => dispatch(fetchWorklist())} />
      }
    />
  );
};
```

**Key Metrics**:
- **Agent Score**: -100 to +100 measuring decision quality vs baseline
- **Touchless Rate**: % of decisions executed without human intervention
- **Human Override Rate**: % of decisions overridden by humans
- **Override Dependency Ratio**: Frequency of overrides by decision type

---

### 5. Simulation (Scenarios)

Supply chain simulation for learning, validation, and agent confidence building.

#### 5.1 Scenarios List

**Features**:
- Browse all scenarios (active, completed, pending)
- Filter by status, configuration, date
- Search by scenario name
- Quick join button for active scenarios
- Pull-to-refresh

**Implementation** (`src/screens/Scenarios/ScenariosListScreen.tsx`):
```typescript
const ScenariosListScreen = () => {
  const dispatch = useDispatch();
  const { scenarios, loading } = useSelector((state: RootState) => state.scenarios);
  const [filter, setFilter] = useState('active');

  useEffect(() => {
    dispatch(fetchScenarios());
  }, []);

  const filteredScenarios = scenarios.filter(s => s.status === filter);

  return (
    <View>
      <Searchbar placeholder="Search scenarios..." />
      <SegmentedButtons
        value={filter}
        onValueChange={setFilter}
        buttons={[
          { value: 'active', label: 'Active' },
          { value: 'completed', label: 'Completed' },
          { value: 'pending', label: 'Pending' },
        ]}
      />
      <FlatList
        data={filteredScenarios}
        renderItem={({ item }) => <ScenarioListItem scenario={item} />}
        refreshControl={
          <RefreshControl refreshing={loading} onRefresh={() => dispatch(fetchScenarios())} />
        }
      />
    </View>
  );
};
```

#### 5.2 Scenario Detail

**Features**:
- Scenario overview (status, participants, periods)
- Participant list with roles and stats
- Period history with metrics
- Real-time updates via WebSocket
- Place orders / make decisions
- Period progression controls (for admins)

**Real-Time Updates**:
```typescript
const ScenarioDetailScreen = ({ route }: { route: any }) => {
  const { scenarioId } = route.params;
  const dispatch = useDispatch();
  const scenario = useSelector((state: RootState) => state.scenarios.currentScenario);

  useEffect(() => {
    dispatch(fetchScenarioById(scenarioId));

    // Subscribe to WebSocket updates
    socket.emit('join_scenario', { scenarioId });
    socket.on('scenario_update', (data) => {
      dispatch(updateScenarioState(data));
    });

    return () => {
      socket.emit('leave_scenario', { scenarioId });
      socket.off('scenario_update');
    };
  }, [scenarioId]);

  const handlePlaceOrder = (quantity: number) => {
    if (offlineService.isOffline()) {
      offlineService.queueAction({
        type: 'PLACE_ORDER',
        payload: { scenarioId, quantity },
        timestamp: Date.now(),
      });
      showToast('Order queued for sync');
    } else {
      dispatch(placeOrder({ scenarioId, quantity }));
    }
  };

  return (
    <ScrollView>
      <Card>
        <Title>{scenario?.name}</Title>
        <Paragraph>Period {scenario?.currentPeriod} of {scenario?.maxPeriods}</Paragraph>
      </Card>

      <Card>
        <Title>Your Role: {scenario?.myRole}</Title>
        <Text>Inventory: {scenario?.myInventory}</Text>
        <Text>Backlog: {scenario?.myBacklog}</Text>
        <TextInput label="Order Quantity" keyboardType="numeric" />
        <Button onPress={() => handlePlaceOrder(orderQty)}>Place Order</Button>
      </Card>

      <Card>
        <Title>Participants</Title>
        <FlatList
          data={scenario?.participants}
          renderItem={({ item }) => <ParticipantItem participant={item} />}
        />
      </Card>
    </ScrollView>
  );
};
```

#### 5.3 Scenario Detail with Agent Chat

**Features**:
- All features from Scenario Detail
- Real-time agent-to-agent conversation stream
- Human intervention controls
- Agent suggestion cards
- Typing indicators
- Message history with timestamps

#### 5.4 Create Scenario

**Features**:
- Quick Start Wizard (guided flow)
- Manual configuration
- Select supply chain configuration
- Add participants (human or AI agents)
- Configure scenario parameters (periods, lead times, costs)
- Template selection

---

### 6. Analytics Dashboard

**Features**:
- Real-time metrics (cost, service level, inventory)
- Mobile-optimized charts (line, bar, pie)
- Bullwhip effect analysis (for simulation scenarios)
- Forecast accuracy metrics (WAPE, MAE, RMSE)
- Cost breakdown by role/echelon
- Export data (CSV, JSON)
- Filter by date range

**Charts Available**:
- **Line Chart**: Inventory/backlog over time, forecast vs actual
- **Bar Chart**: Cost comparison by participant/period, forecast accuracy by cluster
- **Pie Chart**: Cost breakdown (holding vs. backlog), demand classification
- **Bullwhip Chart**: Demand variance by echelon

**Implementation** (`src/screens/Analytics/AnalyticsScreen.tsx`):
```typescript
import { VictoryLine, VictoryChart, VictoryTheme } from 'victory-native';

const AnalyticsScreen = () => {
  const { analyticsData } = useSelector((state: RootState) => state.analytics);

  return (
    <ScrollView>
      <Card>
        <Title>Forecast Accuracy</Title>
        <VictoryChart theme={VictoryTheme.material}>
          <VictoryLine
            data={analyticsData.forecastAccuracy}
            x="period"
            y="wape"
          />
        </VictoryChart>
      </Card>

      <Card>
        <Title>Inventory Over Time</Title>
        <VictoryChart theme={VictoryTheme.material}>
          <VictoryLine
            data={analyticsData.inventoryHistory}
            x="period"
            y="inventory"
          />
        </VictoryChart>
      </Card>

      <Card>
        <Title>Cost Breakdown</Title>
        <VictoryPie
          data={analyticsData.costBreakdown}
          x="category"
          y="cost"
        />
      </Card>
    </ScrollView>
  );
};
```

---

### 7. Profile & Settings

**Features**:
- User profile information
- Change password
- Notification preferences
- Theme selection (light/dark)
- Language selection
- Group and role display
- Logout

---

## State Management

### Redux Store Architecture

The app uses Redux Toolkit for centralized state management with 7 slices:

```typescript
// src/store/index.ts
import { configureStore } from '@reduxjs/toolkit';
import authReducer from './slices/authSlice';
import planningReducer from './slices/planningSlice';
import scenariosReducer from './slices/scenariosSlice';
import agentsReducer from './slices/agentsSlice';
import analyticsReducer from './slices/analyticsSlice';
import chatReducer from './slices/chatSlice';
import uiReducer from './slices/uiSlice';

export const store = configureStore({
  reducer: {
    auth: authReducer,
    planning: planningReducer,
    scenarios: scenariosReducer,
    agents: agentsReducer,
    analytics: analyticsReducer,
    chat: chatReducer,
    ui: uiReducer,
  },
  middleware: (getDefaultMiddleware) =>
    getDefaultMiddleware({
      serializableCheck: false, // For Date objects in state
    }),
});

export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;
```

### Redux Slices

#### 1. authSlice (`src/store/slices/authSlice.ts`)

**State**:
```typescript
interface AuthState {
  user: User | null;
  token: string | null;
  loading: boolean;
  error: string | null;
  isAuthenticated: boolean;
}
```

**Actions**: `login()`, `logout()`, `register()`, `refreshToken()`, `updateProfile()`

#### 2. planningSlice (`src/store/slices/planningSlice.ts`)

**State**:
```typescript
interface PlanningState {
  // Supply chain configs
  scConfigs: SupplyChainConfig[];
  selectedScConfigId: number | null;

  // Forecast pipeline
  pipelineConfigs: ForecastPipelineConfig[];
  pipelineRuns: ForecastPipelineRun[];
  selectedPipelineConfigId: number | null;

  // Supply plans
  supplyPlans: SupplyPlan[];

  // Inventory
  inventoryLevels: InventoryLevel[];
  inventoryPolicies: InventoryPolicy[];

  loading: boolean;
  error: string | null;
}
```

**Actions**:
- `fetchScConfigs()`: Load supply chain configurations (auto-select root baseline)
- `fetchPipelineConfigs()`: Load forecast pipeline configs for selected SC config
- `fetchPipelineRuns()`: Load runs for selected pipeline config
- `startPipelineRun()`: Create and start a new run
- `reExecuteRun()`: Re-execute an existing run
- `publishRun()`: Publish completed run to Forecast table
- `createPipelineConfig()`: Create new pipeline configuration
- `updatePipelineConfig()`: Update existing pipeline configuration
- `fetchSupplyPlans()`: Load supply plans
- `approvePlan()`: Approve a supply plan
- `fetchInventoryLevels()`: Load inventory data

#### 3. scenariosSlice (`src/store/slices/scenariosSlice.ts`)

**State**:
```typescript
interface ScenariosState {
  scenarios: Scenario[];
  currentScenario: Scenario | null;
  activeScenarios: Scenario[];
  completedScenarios: Scenario[];
  loading: boolean;
  error: string | null;
}
```

**Actions**:
- `fetchScenarios()`: Load all scenarios for user
- `fetchScenarioById()`: Load single scenario details
- `createScenario()`: Create new scenario
- `joinScenario()`: Join existing scenario
- `placeOrder()`: Submit order decision
- `updateScenarioState()`: Update from WebSocket event

#### 4. agentsSlice (`src/store/slices/agentsSlice.ts`)

**State**:
```typescript
interface AgentsState {
  worklistItems: WorklistItem[];
  worklistCount: number;
  agentScore: number;
  touchlessRate: number;
  overrideRate: number;
  cdcTriggers: CDCTrigger[];
  retrainingStatus: RetrainingStatus | null;
  loading: boolean;
}
```

**Actions**:
- `fetchWorklist()`: Load worklist items
- `resolveWorklistItem()`: Accept or override a worklist item
- `fetchAgentMetrics()`: Load agent performance metrics
- `fetchCDCTriggers()`: Load CDC trigger history
- `triggerRetraining()`: Manually trigger agent retraining

#### 5. analyticsSlice (`src/store/slices/analyticsSlice.ts`)

**State**:
```typescript
interface AnalyticsState {
  analyticsData: {
    forecastAccuracy: DataPoint[];
    inventoryHistory: DataPoint[];
    costBreakdown: CostCategory[];
    bullwhipRatio: number;
    demandVariance: DataPoint[];
  };
  loading: boolean;
}
```

#### 6. chatSlice (`src/store/slices/chatSlice.ts`)

**State**:
```typescript
interface ChatState {
  conversations: { [scenarioId: string]: Message[] };
  typingAgents: { [scenarioId: string]: string[] };
  unreadCounts: { [scenarioId: string]: number };
}
```

#### 7. uiSlice (`src/store/slices/uiSlice.ts`)

**State**:
```typescript
interface UIState {
  theme: 'light' | 'dark';
  toasts: Toast[];
  modals: { [key: string]: boolean };
  offlineBannerVisible: boolean;
}
```

---

## API Integration

### Axios Client Configuration

**File**: `src/services/api.ts`

```typescript
import axios from 'axios';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { API_BASE_URL } from '../constants';

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor: Add JWT token to every request
api.interceptors.request.use(
  async (config) => {
    const token = await AsyncStorage.getItem('auth_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Response interceptor: Handle token expiry
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (error.response?.status === 401) {
      await AsyncStorage.removeItem('auth_token');
      store.dispatch(logout());
    }
    return Promise.reject(error);
  }
);

export default api;
```

### API Endpoints Used

**Authentication**:
- `POST /api/v1/auth/login` — User login
- `POST /api/v1/auth/register` — User registration
- `POST /api/v1/auth/logout` — User logout
- `POST /api/v1/auth/refresh` — Refresh JWT token

**Supply Chain Configuration**:
- `GET /api/v1/supply-chain-config/` — List configurations
- `GET /api/v1/supply-chain-config/{id}` — Get config details

**Forecast Pipeline**:
- `GET /api/v1/forecast-pipeline/configs` — List pipeline configs
- `POST /api/v1/forecast-pipeline/configs` — Create pipeline config
- `PUT /api/v1/forecast-pipeline/configs/{id}` — Update pipeline config
- `GET /api/v1/forecast-pipeline/runs` — List runs
- `POST /api/v1/forecast-pipeline/runs` — Create and start run
- `GET /api/v1/forecast-pipeline/runs/{id}` — Get run details
- `POST /api/v1/forecast-pipeline/runs/{id}/execute` — Re-execute run
- `POST /api/v1/forecast-pipeline/runs/{id}/publish` — Publish run results
- `GET /api/v1/forecast-pipeline/runs/{id}/publish-log` — Get publish history

**Supply Planning**:
- `POST /api/v1/supply-plan/generate` — Generate supply plan
- `GET /api/v1/supply-plan/status/{task_id}` — Check progress
- `GET /api/v1/supply-plan/result/{task_id}` — Get results
- `POST /api/v1/supply-plan/approve/{task_id}` — Approve plan

**Inventory**:
- `GET /api/v1/inventory-visibility/levels` — Inventory levels
- `GET /api/v1/inventory-projection/` — Inventory projections

**MPS**:
- `GET /api/v1/mps/plans` — List MPS plans
- `GET /api/v1/mps/plans/{id}` — Get MPS plan details

**AI Agents & Powell Framework**:
- `GET /api/v1/powell/allocations` — Get current allocations
- `GET /api/v1/site-agent/cdc/triggers/{site_key}` — CDC trigger history
- `GET /api/v1/site-agent/retraining/status/{site_key}` — Retraining status
- `POST /api/v1/site-agent/retraining/trigger/{site_key}` — Manual retraining
- `GET /api/v1/decision-metrics/` — Agent decision metrics

**Scenarios (Simulation)**:
- `GET /api/v1/mixed-scenarios/` — List scenarios
- `POST /api/v1/mixed-scenarios/` — Create scenario
- `GET /api/v1/mixed-scenarios/{id}` — Get scenario details
- `POST /api/v1/mixed-scenarios/{id}/start` — Start scenario
- `POST /api/v1/mixed-scenarios/{id}/execute-period` — Submit period decisions
- `GET /api/v1/mixed-scenarios/{id}/state` — Get current state
- `GET /api/v1/mixed-scenarios/{id}/history` — Get scenario history

**Analytics**:
- `GET /api/v1/analytics/kpi` — KPI metrics
- `GET /api/v1/predictive-analytics/` — Predictive analytics

**Notifications**:
- `POST /api/v1/notifications/push-token` — Register FCM token
- `GET /api/v1/notifications/` — List notifications

---

## Offline Mode

### Architecture

The offline mode uses a queue-based system to store actions when connectivity is lost and replay them when connectivity resumes.

**File**: `src/services/offline.ts`

```typescript
import AsyncStorage from '@react-native-async-storage/async-storage';
import NetInfo from '@react-native-community/netinfo';
import api from './api';

interface QueuedAction {
  id: string;
  type: string;
  payload: any;
  timestamp: number;
  retryCount: number;
}

class OfflineService {
  private queue: QueuedAction[] = [];
  private isOnline: boolean = true;

  constructor() {
    this.initialize();
  }

  async initialize() {
    const stored = await AsyncStorage.getItem('offline_queue');
    if (stored) {
      this.queue = JSON.parse(stored);
    }

    NetInfo.addEventListener(state => {
      const wasOffline = !this.isOnline;
      this.isOnline = state.isConnected ?? false;

      if (wasOffline && this.isOnline) {
        this.processQueue();
      }
    });
  }

  async queueAction(action: Omit<QueuedAction, 'id' | 'retryCount'>) {
    const queuedAction: QueuedAction = {
      id: Date.now().toString(),
      retryCount: 0,
      ...action,
    };

    this.queue.push(queuedAction);
    await this.saveQueue();
  }

  async processQueue() {
    while (this.queue.length > 0 && this.isOnline) {
      const action = this.queue[0];

      try {
        await this.executeAction(action);
        this.queue.shift();
      } catch (error) {
        action.retryCount++;
        if (action.retryCount >= 3) {
          this.queue.shift();
        } else {
          break;
        }
      }

      await this.saveQueue();
    }
  }

  async executeAction(action: QueuedAction) {
    switch (action.type) {
      case 'PLACE_ORDER':
        await api.post(`/mixed-scenarios/${action.payload.scenarioId}/execute-period`, {
          order_quantity: action.payload.quantity,
        });
        break;
      case 'START_PIPELINE_RUN':
        await api.post('/forecast-pipeline/runs', {
          pipeline_config_id: action.payload.pipelineConfigId,
          auto_start: true,
        });
        break;
      case 'PUBLISH_RUN':
        await api.post(`/forecast-pipeline/runs/${action.payload.runId}/publish`, {});
        break;
      case 'APPROVE_SUPPLY_PLAN':
        await api.post(`/supply-plan/approve/${action.payload.taskId}`, {});
        break;
      case 'RESOLVE_WORKLIST':
        await api.post(`/powell/worklist/${action.payload.itemId}/resolve`, action.payload.resolution);
        break;
    }
  }

  async saveQueue() {
    await AsyncStorage.setItem('offline_queue', JSON.stringify(this.queue));
  }

  isOffline() {
    return !this.isOnline;
  }
}

export const offlineService = new OfflineService();
```

### Offline Banner

**Component**: `src/components/common/OfflineBanner.tsx`

Displays a banner at the top of the screen when offline.

```typescript
const OfflineBanner = () => {
  const isOffline = useSelector((state: RootState) => state.ui.offlineBannerVisible);

  if (!isOffline) return null;

  return (
    <Banner visible={isOffline} icon="wifi-off">
      You are offline. Actions will sync when connection resumes.
    </Banner>
  );
};
```

---

## Push Notifications

### Firebase Cloud Messaging Setup

**See**: `mobile/firebase-setup.md` for detailed setup instructions.

### Implementation

**File**: `src/services/notifications.ts`

```typescript
import messaging from '@react-native-firebase/messaging';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { Alert } from 'react-native';

class NotificationService {
  async requestPermission(): Promise<boolean> {
    const authStatus = await messaging().requestPermission();
    const enabled =
      authStatus === messaging.AuthorizationStatus.AUTHORIZED ||
      authStatus === messaging.AuthorizationStatus.PROVISIONAL;

    if (enabled) {
      await this.registerDevice();
    }

    return enabled;
  }

  async registerDevice() {
    const token = await messaging().getToken();
    await AsyncStorage.setItem('fcm_token', token);
    await api.post('/notifications/push-token', { token });
  }

  setupForegroundHandler() {
    messaging().onMessage(async (remoteMessage) => {
      Alert.alert(
        remoteMessage.notification?.title ?? 'Notification',
        remoteMessage.notification?.body ?? ''
      );
    });
  }

  setupBackgroundHandler() {
    messaging().setBackgroundMessageHandler(async (remoteMessage) => {
      console.log('Background message:', remoteMessage);
    });
  }

  async getToken(): Promise<string> {
    return await messaging().getToken();
  }
}

export const notificationService = new NotificationService();
```

### Notification Types

**Planning Events**:
- `forecast_run_completed`: "Forecast pipeline run completed — 1,240 records"
- `forecast_run_failed`: "Forecast pipeline run failed — insufficient data"
- `supply_plan_ready`: "Supply plan ready for review"
- `supply_plan_approved`: "Supply plan approved and released"
- `inventory_alert`: "Stockout risk detected at Site DC-East for SKU-1234"

**Agent Events**:
- `agent_suggestion`: "AI agent suggests ordering [X] units"
- `agent_decision`: "Agent [name] made a decision"
- `worklist_item`: "New worklist item requires your attention"
- `cdc_trigger`: "CDC trigger detected — agent retraining initiated"

**Scenario Events**:
- `scenario_started`: "Scenario [name] has started!"
- `period_completed`: "Period [X] completed in [scenario name]"
- `your_turn`: "It's your turn in [scenario name]"
- `scenario_completed`: "Scenario [name] has finished!"

**System Events**:
- `system_update`: "Platform maintenance scheduled"

### Handling Notification Taps

```typescript
messaging().onNotificationOpenedApp((remoteMessage) => {
  const { type, scenarioId, runId } = remoteMessage.data;

  if (type === 'your_turn' || type === 'scenario_started') {
    navigation.navigate('ScenarioDetail', { scenarioId });
  } else if (type === 'forecast_run_completed') {
    navigation.navigate('Forecasting');
  } else if (type === 'worklist_item') {
    navigation.navigate('Worklist');
  }
});
```

---

## WebSocket Real-Time Updates

### Socket.IO Client Configuration

**File**: `src/services/websocket.ts`

```typescript
import io, { Socket } from 'socket.io-client';
import { WS_URL } from '../constants';
import { store } from '../store';
import { updateScenarioState } from '../store/slices/scenariosSlice';
import { addChatMessage } from '../store/slices/chatSlice';
import { updatePipelineRunStatus } from '../store/slices/planningSlice';

class WebSocketService {
  private socket: Socket | null = null;

  connect(token: string) {
    this.socket = io(WS_URL, {
      auth: { token },
      transports: ['websocket'],
      reconnection: true,
      reconnectionDelay: 1000,
      reconnectionDelayMax: 5000,
      reconnectionAttempts: 5,
    });

    this.setupListeners();
  }

  setupListeners() {
    if (!this.socket) return;

    this.socket.on('connect', () => {
      console.log('WebSocket connected');
    });

    this.socket.on('disconnect', () => {
      console.log('WebSocket disconnected');
    });

    // Scenario events
    this.socket.on('scenario_update', (data) => {
      store.dispatch(updateScenarioState(data));
    });

    this.socket.on('period_completed', (data) => {
      // Show notification or update UI
    });

    // Agent chat events
    this.socket.on('a2a_message', (data) => {
      store.dispatch(addChatMessage(data));
    });

    // Planning events
    this.socket.on('pipeline_run_update', (data) => {
      store.dispatch(updatePipelineRunStatus(data));
    });
  }

  joinScenario(scenarioId: string) {
    this.socket?.emit('join_scenario', { scenarioId });
  }

  leaveScenario(scenarioId: string) {
    this.socket?.emit('leave_scenario', { scenarioId });
  }

  disconnect() {
    this.socket?.disconnect();
    this.socket = null;
  }
}

export const websocketService = new WebSocketService();
```

### WebSocket Events

**Client → Server**:
- `join_scenario`: Subscribe to scenario updates
- `leave_scenario`: Unsubscribe from scenario updates
- `place_order`: Submit order decision (alternative to REST API)

**Server → Client**:
- `scenario_update`: Full scenario state update
- `period_completed`: Period finished, new period started
- `participant_joined`: New participant joined scenario
- `participant_left`: Participant left scenario
- `a2a_message`: Agent-to-agent conversation message
- `pipeline_run_update`: Forecast pipeline run status change

---

## Screens & Navigation

### Navigation Structure

**File**: `src/navigation/AppNavigator.tsx`

```
AppNavigator
├── AuthNavigator (when not authenticated)
│   ├── LoginScreen
│   └── RegisterScreen
└── MainNavigator (when authenticated)
    └── BottomTabNavigator
        ├── DashboardTab
        │   └── DashboardScreen
        ├── PlanningTab (Stack)
        │   ├── PlanningHubScreen (tab selector: Forecasting / Supply / Inventory / MPS)
        │   ├── ForecastingScreen
        │   ├── ForecastPipelineDetailScreen
        │   ├── SupplyPlanScreen
        │   ├── InventoryScreen
        │   └── MPSScreen
        ├── AgentsTab (Stack)
        │   ├── AgentDashboardScreen
        │   ├── WorklistScreen
        │   └── AgentDetailScreen
        ├── SimulationTab (Stack)
        │   ├── ScenariosListScreen
        │   ├── ScenarioDetailScreen
        │   ├── ScenarioDetailWithChatScreen
        │   └── CreateScenarioScreen
        ├── AnalyticsTab
        │   └── AnalyticsScreen
        └── ProfileTab
            └── ProfileScreen
```

### Navigation Implementation

```typescript
import { NavigationContainer } from '@react-navigation/native';
import { createStackNavigator } from '@react-navigation/stack';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';

const Stack = createStackNavigator();
const Tab = createBottomTabNavigator();

const AuthNavigator = () => (
  <Stack.Navigator screenOptions={{ headerShown: false }}>
    <Stack.Screen name="Login" component={LoginScreen} />
    <Stack.Screen name="Register" component={RegisterScreen} />
  </Stack.Navigator>
);

const PlanningStack = () => (
  <Stack.Navigator>
    <Stack.Screen name="PlanningHub" component={PlanningHubScreen} />
    <Stack.Screen name="Forecasting" component={ForecastingScreen} />
    <Stack.Screen name="PipelineDetail" component={ForecastPipelineDetailScreen} />
    <Stack.Screen name="SupplyPlan" component={SupplyPlanScreen} />
    <Stack.Screen name="Inventory" component={InventoryScreen} />
    <Stack.Screen name="MPS" component={MPSScreen} />
  </Stack.Navigator>
);

const AgentsStack = () => (
  <Stack.Navigator>
    <Stack.Screen name="AgentDashboard" component={AgentDashboardScreen} />
    <Stack.Screen name="Worklist" component={WorklistScreen} />
    <Stack.Screen name="AgentDetail" component={AgentDetailScreen} />
  </Stack.Navigator>
);

const SimulationStack = () => (
  <Stack.Navigator>
    <Stack.Screen name="ScenariosList" component={ScenariosListScreen} />
    <Stack.Screen name="ScenarioDetail" component={ScenarioDetailScreen} />
    <Stack.Screen name="ScenarioDetailWithChat" component={ScenarioDetailWithChatScreen} />
    <Stack.Screen name="CreateScenario" component={CreateScenarioScreen} />
  </Stack.Navigator>
);

const MainNavigator = () => (
  <Tab.Navigator>
    <Tab.Screen name="Dashboard" component={DashboardScreen}
      options={{ tabBarIcon: ({ color }) => <Icon name="view-dashboard" color={color} /> }} />
    <Tab.Screen name="Planning" component={PlanningStack}
      options={{ tabBarIcon: ({ color }) => <Icon name="chart-timeline" color={color} /> }} />
    <Tab.Screen name="Agents" component={AgentsStack}
      options={{ tabBarIcon: ({ color }) => <Icon name="robot" color={color} /> }} />
    <Tab.Screen name="Simulation" component={SimulationStack}
      options={{ tabBarIcon: ({ color }) => <Icon name="gamepad-variant" color={color} /> }} />
    <Tab.Screen name="Profile" component={ProfileScreen}
      options={{ tabBarIcon: ({ color }) => <Icon name="account" color={color} /> }} />
  </Tab.Navigator>
);

const AppNavigator = () => {
  const isAuthenticated = useSelector((state: RootState) => state.auth.isAuthenticated);

  return (
    <NavigationContainer>
      {isAuthenticated ? <MainNavigator /> : <AuthNavigator />}
    </NavigationContainer>
  );
};
```

---

## Testing

### Test Structure

```
__tests__/
├── screens/
│   ├── LoginScreen.test.tsx
│   ├── DashboardScreen.test.tsx
│   └── ForecastingScreen.test.tsx
├── store/slices/
│   ├── authSlice.test.ts
│   ├── planningSlice.test.ts
│   ├── scenariosSlice.test.ts
│   └── agentsSlice.test.ts
└── services/
    ├── notifications.test.ts
    └── offline.test.ts
```

### Running Tests

```bash
# Run all tests
npm test

# Run with coverage
npm test -- --coverage

# Run specific test file
npm test -- LoginScreen.test.tsx

# Watch mode
npm test -- --watch
```

---

## Performance Optimization

### React.memo for Expensive Components

```typescript
const PipelineConfigCard = React.memo(({ config }: { config: PipelineConfig }) => {
  return (
    <Card>
      <Card.Title title={config.name} />
      <Card.Content>
        <Text>Method: {config.cluster_selection_method}</Text>
        <Text>Metric: {config.forecast_metric?.toUpperCase()}</Text>
      </Card.Content>
    </Card>
  );
});
```

### FlatList Optimization

```typescript
<FlatList
  data={runs}
  renderItem={({ item }) => <RunCard run={item} />}
  keyExtractor={(item) => item.id.toString()}
  initialNumToRender={10}
  maxToRenderPerBatch={10}
  windowSize={5}
  removeClippedSubviews={true}
  getItemLayout={(data, index) => ({
    length: ITEM_HEIGHT,
    offset: ITEM_HEIGHT * index,
    index,
  })}
/>
```

### Hermes JavaScript Engine

**Android** (`android/app/build.gradle`):
```groovy
project.ext.react = [
    enableHermes: true,
]
```

**iOS**: Hermes enabled by default in React Native 0.70+

---

## Build & Deployment

### iOS Build & Release

**Debug Build**:
```bash
npm run ios
```

**Release Build**:
1. Open Xcode:
```bash
open ios/Autonomy.xcworkspace
```

2. Select "Any iOS Device (arm64)" target
3. Product → Archive
4. Distribute App → App Store Connect

### Android Build & Release

**Debug Build**:
```bash
npm run android
```

**Release APK**:
```bash
cd android
./gradlew assembleRelease
# APK: android/app/build/outputs/apk/release/app-release.apk
```

**Release Bundle (for Play Store)**:
```bash
cd android
./gradlew bundleRelease
# AAB: android/app/build/outputs/bundle/release/app-release.aab
```

### Environment Configuration

**Development**:
```env
API_BASE_URL=http://localhost:8000
WS_URL=ws://localhost:8000/ws
ENVIRONMENT=development
```

**Staging**:
```env
API_BASE_URL=https://staging-api.autonomy.ai
WS_URL=wss://staging-api.autonomy.ai/ws
ENVIRONMENT=staging
```

**Production**:
```env
API_BASE_URL=https://api.autonomy.ai
WS_URL=wss://api.autonomy.ai/ws
ENVIRONMENT=production
```

---

## Troubleshooting

### iOS Pod Install Issues

```bash
cd ios
rm -rf Pods Podfile.lock
pod deintegrate
pod install --repo-update
cd ..
```

### Android Build Issues

```bash
cd android
./gradlew clean
./gradlew assembleDebug --info
cd ..
```

### Metro Bundler Issues

```bash
npm start -- --reset-cache
```

### WebSocket Connection Issues

1. Check backend is running: `docker compose ps`
2. Verify WebSocket URL in `.env` is correct
3. Check firewall allows WebSocket connections
4. For physical devices, use host machine IP (not localhost)

### Push Notifications Not Working

1. Verify Firebase setup: `mobile/firebase-setup.md`
2. Check `google-services.json` (Android) and `GoogleService-Info.plist` (iOS) are present
3. Request notification permissions in app
4. Test with Firebase Console Test Message

---

## Deployment Checklist

See `mobile/INTEGRATION_CHECKLIST.md` for complete pre-launch checklist.

**Quick Checklist**:
- [ ] Environment variables configured
- [ ] Firebase Cloud Messaging setup
- [ ] App icons and splash screens
- [ ] Code signing certificates (iOS)
- [ ] Keystore configured (Android)
- [ ] API endpoints point to production
- [ ] Analytics tracking enabled
- [ ] Crash reporting enabled
- [ ] All tests passing
- [ ] Performance profiled
- [ ] Accessibility verified
- [ ] Privacy policy and terms of service linked

---

## Additional Resources

### Documentation
- `mobile/README.md` — Project overview
- `mobile/INSTALL.md` — Installation instructions
- `mobile/QUICKSTART.md` — 5-minute quick start
- `mobile/QUICK_REFERENCE.md` — Command reference
- `mobile/firebase-setup.md` — Firebase setup
- `mobile/DEPLOYMENT.md` — Deployment guide
- `mobile/TESTING_GUIDE.md` — Testing procedures
- `mobile/ACCESSIBILITY.md` — Accessibility guidelines
- `mobile/A2A_COLLABORATION_GUIDE.md` — Agent-to-Agent feature guide

### External Links
- [React Native Documentation](https://reactnative.dev/docs/getting-started)
- [React Navigation](https://reactnavigation.org/docs/getting-started)
- [Redux Toolkit](https://redux-toolkit.js.org/introduction/getting-started)
- [Firebase Cloud Messaging](https://firebase.google.com/docs/cloud-messaging)
- [Socket.IO Client](https://socket.io/docs/v4/client-api/)

---

## Support & Contact

For issues, questions, or feature requests:
- GitHub Issues: [Project Repository](https://github.com/anthropics/claude-code/issues)
- Email: support@autonomy.ai

---

**Document Version**: 2.0.0
**Last Updated**: February 21, 2026
**Status**: In Development
