# The Continuous Autonomous Planning Platform - Mobile Application

**Complete Documentation for iOS and Android Native Applications**

**Version**: 1.0.0
**Date**: January 22, 2026
**React Native**: 0.73.2
**Status**: Production Ready

---

## Executive Summary

The Beer Game Mobile Application extends the platform's capabilities to iOS and Android devices, enabling planners, managers, and players to participate in supply chain gaming, monitor AI agents, and access real-time analytics from anywhere. Built with React Native 0.73.2, the mobile app provides a native experience with offline mode, push notifications, and seamless WebSocket synchronization with the backend platform.

### Key Capabilities

- **Native iOS & Android**: Single codebase for both platforms using React Native
- **Full Feature Parity**: All core features from web platform available on mobile
- **Offline Mode**: Queue actions and sync when connectivity resumes
- **Push Notifications**: Real-time alerts for game events, agent decisions, and system updates
- **WebSocket Integration**: Live game state updates via Socket.IO
- **Material Design UI**: Consistent, professional interface using React Native Paper
- **Biometric Authentication**: Face ID/Touch ID support for secure, fast login
- **Real-Time Analytics**: Mobile-optimized charts and dashboards
- **Agent-to-Agent (A2A) Collaboration**: Monitor and intervene in AI agent conversations on the go

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
│  │  Login, Dashboard, Games, Templates, Analytics   │  │
│  └──────────────────────────────────────────────────┘  │
│                         ↕                                │
│  ┌──────────────────────────────────────────────────┐  │
│  │      State Management (Redux Toolkit)             │  │
│  │  Auth, Games, Templates, Analytics, UI Slices    │  │
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

**Game State Synchronization Flow**:
1. Backend game state changes → FastAPI emits WebSocket event
2. Mobile WebSocket client receives event → Dispatch to gamesSlice
3. Redux state updates → React components re-render
4. UI reflects latest game state in real-time

**Offline Mode Flow**:
1. User makes decision (e.g., place order) → Offline queue
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
  - Stack Navigator: For screen hierarchies (e.g., Game Detail stack)
  - Bottom Tab Navigator: Main app navigation (Dashboard, Games, Templates, Analytics, Profile)

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
cd /home/trevor/Projects/The_Beer_Game
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
FIREBASE_PROJECT_ID=beer-game-mobile
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
cd /home/trevor/Projects/The_Beer_Game
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

**Available Simulators**:
```bash
xcrun simctl list devices available
```

### iOS (Physical Device)

1. Open `ios/BeerGame.xcworkspace` in Xcode
2. Select your device from device list
3. Click Run (▶) button
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
# Should show your device ID
```

4. Run app:
```bash
npm run android
```

### Start Metro Bundler Separately

```bash
npm start
```

This starts the JavaScript bundler. Keep it running in a separate terminal.

**Reset Cache**:
```bash
npm start -- --reset-cache
```

---

## Project Structure

```
mobile/
├── 📱 iOS Native Code
│   ├── BeerGame.xcworkspace        # Xcode workspace
│   ├── BeerGame/
│   │   ├── AppDelegate.mm          # iOS app lifecycle
│   │   ├── Info.plist             # iOS configuration
│   │   └── GoogleService-Info.plist # Firebase config (add this)
│   └── Podfile                    # CocoaPods dependencies
│
├── 🤖 Android Native Code
│   ├── app/
│   │   ├── build.gradle           # App-level Gradle
│   │   ├── src/main/
│   │   │   ├── AndroidManifest.xml
│   │   │   └── java/com/beergame/ # Native Java/Kotlin code
│   │   └── google-services.json   # Firebase config (add this)
│   └── build.gradle               # Project-level Gradle
│
├── 📂 Source Code (src/)
│   ├── App.tsx                    # Root component
│   │
│   ├── navigation/
│   │   └── AppNavigator.tsx       # Navigation structure
│   │
│   ├── screens/                   # Screen components
│   │   ├── Auth/
│   │   │   ├── LoginScreen.tsx
│   │   │   └── RegisterScreen.tsx
│   │   ├── Dashboard/
│   │   │   └── DashboardScreen.tsx
│   │   ├── Games/
│   │   │   ├── GamesListScreen.tsx
│   │   │   ├── GameDetailScreen.tsx
│   │   │   ├── GameDetailWithChatScreen.tsx  # A2A integration
│   │   │   └── CreateGameScreen.tsx
│   │   ├── Templates/
│   │   │   └── TemplateLibraryScreen.tsx
│   │   ├── Analytics/
│   │   │   └── AnalyticsScreen.tsx
│   │   └── Profile/
│   │       └── ProfileScreen.tsx
│   │
│   ├── components/                # Reusable components
│   │   ├── common/
│   │   │   ├── LoadingSpinner.tsx
│   │   │   ├── ErrorBoundary.tsx
│   │   │   ├── EmptyState.tsx
│   │   │   ├── Toast.tsx
│   │   │   └── OfflineBanner.tsx
│   │   ├── charts/
│   │   │   ├── LineChart.tsx
│   │   │   ├── BarChart.tsx
│   │   │   └── PieChart.tsx
│   │   └── chat/                  # A2A chat components
│   │       ├── ChatMessage.tsx
│   │       ├── ChatInput.tsx
│   │       ├── ChatMessageList.tsx
│   │       ├── TypingIndicator.tsx
│   │       ├── AgentSuggestionCard.tsx
│   │       └── ChatContainer.tsx
│   │
│   ├── store/                     # Redux state management
│   │   ├── index.ts               # Store configuration
│   │   └── slices/
│   │       ├── authSlice.ts       # Authentication state
│   │       ├── gamesSlice.ts      # Games state
│   │       ├── templatesSlice.ts  # Templates state
│   │       ├── analyticsSlice.ts  # Analytics state
│   │       ├── chatSlice.ts       # A2A chat state
│   │       └── uiSlice.ts         # UI state (toasts, modals, theme)
│   │
│   ├── services/                  # API & external services
│   │   ├── api.ts                 # Axios HTTP client
│   │   ├── websocket.ts           # Socket.IO WebSocket client
│   │   ├── notifications.ts       # Firebase Cloud Messaging
│   │   ├── offline.ts             # Offline mode queue
│   │   └── chat.ts                # A2A chat service
│   │
│   ├── theme/
│   │   └── index.ts               # Material Design theme
│   │
│   ├── utils/                     # Utility functions
│   ├── constants/                 # Constants
│   └── types/                     # TypeScript types
│
├── 📦 Assets
│   ├── images/                    # Images
│   ├── fonts/                     # Custom fonts
│   └── icons/                     # App icons
│
├── 🧪 Tests
│   ├── __tests__/
│   │   ├── screens/               # Screen tests
│   │   ├── store/slices/          # Redux slice tests
│   │   └── services/              # Service tests
│   ├── jest.config.js             # Jest configuration
│   └── jest.setup.js              # Test setup
│
└── 📄 Configuration
    ├── package.json               # Dependencies
    ├── tsconfig.json              # TypeScript config
    ├── babel.config.js            # Babel config
    ├── metro.config.js            # Metro bundler config
    ├── app.json                   # App metadata
    └── .env.example               # Environment template
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

**Implementation** ([src/screens/Auth/LoginScreen.tsx](../mobile/src/screens/Auth/LoginScreen.tsx)):
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
- Overview metrics (active games, win rate, total cost)
- Active games list with quick join
- Quick actions (Create Game, Browse Templates, View Analytics)
- Recent activity feed
- Notifications badge

**Key Metrics Displayed**:
- Active Games Count
- Completed Games Count
- Win Rate (%)
- Average Cost per Game
- Recent Achievements

**Implementation** ([src/screens/Dashboard/DashboardScreen.tsx](../mobile/src/screens/Dashboard/DashboardScreen.tsx)):
```typescript
const DashboardScreen = () => {
  const { user } = useSelector((state: RootState) => state.auth);
  const { activeGames, stats } = useSelector((state: RootState) => state.games);

  return (
    <ScrollView>
      <Card>
        <Title>Welcome, {user?.name}</Title>
        <Paragraph>You have {activeGames.length} active games</Paragraph>
      </Card>

      <Card>
        <Title>Quick Stats</Title>
        <View>
          <Text>Win Rate: {stats.winRate}%</Text>
          <Text>Avg Cost: ${stats.avgCost}</Text>
        </View>
      </Card>

      <FlatList
        data={activeGames}
        renderItem={({ item }) => <GameCard game={item} />}
      />
    </ScrollView>
  );
};
```

---

### 3. Game Management

#### 3.1 Games List

**Features**:
- Browse all games (active, completed, pending)
- Filter by status, configuration, date
- Search by game name
- Quick join button for active games
- Pull-to-refresh

**Implementation** ([src/screens/Games/GamesListScreen.tsx](../mobile/src/screens/Games/GamesListScreen.tsx)):
```typescript
const GamesListScreen = () => {
  const dispatch = useDispatch();
  const { games, loading } = useSelector((state: RootState) => state.games);
  const [filter, setFilter] = useState('active');

  useEffect(() => {
    dispatch(fetchGames());
  }, []);

  const filteredGames = games.filter(g => g.status === filter);

  return (
    <View>
      <Searchbar placeholder="Search games..." />
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
        data={filteredGames}
        renderItem={({ item }) => <GameListItem game={item} />}
        refreshControl={
          <RefreshControl refreshing={loading} onRefresh={() => dispatch(fetchGames())} />
        }
      />
    </View>
  );
};
```

#### 3.2 Game Detail

**Features**:
- Game overview (status, players, rounds)
- Player list with roles and stats
- Round history with metrics
- Real-time updates via WebSocket
- Place orders / make decisions
- Round progression controls (for admins)
- Export game data

**Real-Time Updates**:
```typescript
const GameDetailScreen = ({ route }: { route: any }) => {
  const { gameId } = route.params;
  const dispatch = useDispatch();
  const game = useSelector((state: RootState) => state.games.currentGame);

  useEffect(() => {
    // Fetch game initially
    dispatch(fetchGameById(gameId));

    // Subscribe to WebSocket updates
    socket.emit('join_game', { gameId });
    socket.on('game_update', (data) => {
      dispatch(updateGameState(data));
    });

    return () => {
      socket.emit('leave_game', { gameId });
      socket.off('game_update');
    };
  }, [gameId]);

  const handlePlaceOrder = (quantity: number) => {
    if (offlineService.isOffline()) {
      // Queue action for later sync
      offlineService.queueAction({
        type: 'PLACE_ORDER',
        payload: { gameId, quantity },
        timestamp: Date.now(),
      });
      showToast('Order queued for sync');
    } else {
      dispatch(placeOrder({ gameId, quantity }));
    }
  };

  return (
    <ScrollView>
      <Card>
        <Title>{game?.name}</Title>
        <Paragraph>Round {game?.currentRound} of {game?.maxRounds}</Paragraph>
      </Card>

      <Card>
        <Title>Your Role: {game?.myRole}</Title>
        <Text>Inventory: {game?.myInventory}</Text>
        <Text>Backlog: {game?.myBacklog}</Text>
        <TextInput label="Order Quantity" keyboardType="numeric" />
        <Button onPress={() => handlePlaceOrder(orderQty)}>Place Order</Button>
      </Card>

      <Card>
        <Title>Players</Title>
        <FlatList data={game?.players} renderItem={({ item }) => <PlayerItem player={item} />} />
      </Card>
    </ScrollView>
  );
};
```

#### 3.3 Game Detail with A2A Chat

**Features**:
- All features from Game Detail
- Real-time agent-to-agent conversation stream
- Human intervention controls
- Agent suggestion cards
- Typing indicators
- Message history with timestamps

**Implementation** ([src/screens/Games/GameDetailWithChatScreen.tsx](../mobile/src/screens/Games/GameDetailWithChatScreen.tsx)):
Integrates chat components from `src/components/chat/` to display agent conversations.

#### 3.4 Create Game

**Features**:
- Quick Start Wizard (guided flow)
- Manual configuration
- Select supply chain configuration
- Add players (human or AI agents)
- Configure game parameters (rounds, lead times, costs)
- Template selection

**Quick Start Wizard Flow**:
```typescript
const CreateGameScreen = () => {
  const [step, setStep] = useState(1);
  const [gameConfig, setGameConfig] = useState({});

  const steps = [
    { label: 'Choose Configuration', component: <ConfigSelector /> },
    { label: 'Add Players', component: <PlayerSelector /> },
    { label: 'Set Parameters', component: <ParameterForm /> },
    { label: 'Review & Create', component: <ReviewStep /> },
  ];

  const handleNext = () => setStep(step + 1);
  const handleBack = () => setStep(step - 1);

  return (
    <View>
      <ProgressBar progress={step / steps.length} />
      {steps[step - 1].component}
      <Button onPress={handleBack} disabled={step === 1}>Back</Button>
      <Button onPress={handleNext} disabled={step === steps.length}>Next</Button>
      {step === steps.length && <Button onPress={handleCreateGame}>Create Game</Button>}
    </View>
  );
};
```

---

### 4. Template Library

**Features**:
- Browse supply chain configuration templates
- Search and filter templates
- Template preview with Sankey diagram
- Favorite templates
- Use template to create new game
- Template details (nodes, lanes, items, BOMs)

**Template Categories**:
- **Classic Beer Game**: Standard 4-echelon supply chain
- **Multi-Product**: Multiple finished goods with shared components
- **Complex Networks**: Convergent/divergent topologies
- **Custom**: User-created configurations

**Implementation** ([src/screens/Templates/TemplateLibraryScreen.tsx](../mobile/src/screens/Templates/TemplateLibraryScreen.tsx)):
```typescript
const TemplateLibraryScreen = () => {
  const dispatch = useDispatch();
  const { templates, loading } = useSelector((state: RootState) => state.templates);

  useEffect(() => {
    dispatch(fetchTemplates());
  }, []);

  const handleUseTemplate = (templateId: string) => {
    navigation.navigate('CreateGame', { templateId });
  };

  return (
    <View>
      <Searchbar placeholder="Search templates..." />
      <FlatList
        data={templates}
        renderItem={({ item }) => (
          <Card>
            <Card.Cover source={{ uri: item.thumbnailUrl }} />
            <Card.Title title={item.name} subtitle={item.description} />
            <Card.Actions>
              <Button onPress={() => handleUseTemplate(item.id)}>Use Template</Button>
            </Card.Actions>
          </Card>
        )}
      />
    </View>
  );
};
```

---

### 5. Analytics Dashboard

**Features**:
- Real-time metrics (cost, service level, inventory)
- Mobile-optimized charts (line, bar, pie)
- Bullwhip effect analysis
- Cost breakdown by role/echelon
- Demand amplification visualization
- Export data (CSV, JSON)
- Compare multiple games
- Filter by date range

**Charts Available**:
- **Line Chart**: Inventory/backlog over time
- **Bar Chart**: Cost comparison by player/round
- **Pie Chart**: Cost breakdown (holding vs. backlog)
- **Bullwhip Chart**: Demand variance by echelon

**Implementation** ([src/screens/Analytics/AnalyticsScreen.tsx](../mobile/src/screens/Analytics/AnalyticsScreen.tsx)):
```typescript
import { VictoryLine, VictoryChart, VictoryTheme } from 'victory-native';

const AnalyticsScreen = () => {
  const { analyticsData } = useSelector((state: RootState) => state.analytics);

  return (
    <ScrollView>
      <Card>
        <Title>Inventory Over Time</Title>
        <VictoryChart theme={VictoryTheme.material}>
          <VictoryLine
            data={analyticsData.inventoryHistory}
            x="round"
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

      <Card>
        <Title>Bullwhip Effect</Title>
        <Text>Demand Amplification: {analyticsData.bullwhipRatio}x</Text>
        <VictoryChart>
          <VictoryLine data={analyticsData.demandVariance} />
        </VictoryChart>
      </Card>
    </ScrollView>
  );
};
```

**Mobile-Optimized Charts**:
- Victory Native for performant native charts
- Responsive sizing for different screen sizes
- Touch interactions (zoom, pan, tooltip)
- Lazy loading for large datasets

---

### 6. Profile & Settings

**Features**:
- User profile information
- Change password
- Notification preferences
- Theme selection (light/dark)
- Language selection
- Logout

---

### 7. Agent-to-Agent (A2A) Collaboration

**Features**:
- Real-time agent conversation monitoring
- Human intervention controls
- Agent suggestion cards
- Message history
- Typing indicators
- Configurable notification preferences

**Components** ([src/components/chat/](../mobile/src/components/chat/)):
- **ChatMessage.tsx**: Individual message bubble
- **ChatInput.tsx**: Message input field (for human intervention)
- **ChatMessageList.tsx**: Scrollable message list
- **TypingIndicator.tsx**: Shows when agent is "thinking"
- **AgentSuggestionCard.tsx**: Displays agent recommendations
- **ChatContainer.tsx**: Full chat interface

**Service** ([src/services/chat.ts](../mobile/src/services/chat.ts)):
Handles WebSocket events for agent messages and manages chat state.

---

## State Management

### Redux Store Architecture

The app uses Redux Toolkit for centralized state management with 6 slices:

```typescript
// src/store/index.ts
import { configureStore } from '@reduxjs/toolkit';
import authReducer from './slices/authSlice';
import gamesReducer from './slices/gamesSlice';
import templatesReducer from './slices/templatesSlice';
import analyticsReducer from './slices/analyticsSlice';
import chatReducer from './slices/chatSlice';
import uiReducer from './slices/uiSlice';

export const store = configureStore({
  reducer: {
    auth: authReducer,
    games: gamesReducer,
    templates: templatesReducer,
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

#### 1. authSlice ([src/store/slices/authSlice.ts](../mobile/src/store/slices/authSlice.ts))

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

**Actions**:
- `login()`: Authenticate user, store token
- `logout()`: Clear token, navigate to login
- `register()`: Create new user account
- `refreshToken()`: Refresh JWT before expiry
- `updateProfile()`: Update user info

**Thunks**:
```typescript
export const login = createAsyncThunk(
  'auth/login',
  async ({ email, password }: LoginCredentials, { rejectWithValue }) => {
    try {
      const response = await api.post('/auth/login', { email, password });
      await AsyncStorage.setItem('auth_token', response.data.token);
      return response.data;
    } catch (error) {
      return rejectWithValue(error.response.data);
    }
  }
);
```

#### 2. gamesSlice ([src/store/slices/gamesSlice.ts](../mobile/src/store/slices/gamesSlice.ts))

**State**:
```typescript
interface GamesState {
  games: Game[];
  currentGame: Game | null;
  activeGames: Game[];
  completedGames: Game[];
  loading: boolean;
  error: string | null;
  stats: {
    winRate: number;
    avgCost: number;
    totalGames: number;
  };
}
```

**Actions**:
- `fetchGames()`: Load all games for user
- `fetchGameById()`: Load single game details
- `createGame()`: Create new game
- `joinGame()`: Join existing game
- `placeOrder()`: Submit order decision
- `updateGameState()`: Update from WebSocket event

#### 3. templatesSlice ([src/store/slices/templatesSlice.ts](../mobile/src/store/slices/templatesSlice.ts))

**State**:
```typescript
interface TemplatesState {
  templates: Template[];
  favorites: string[];
  loading: boolean;
}
```

#### 4. analyticsSlice ([src/store/slices/analyticsSlice.ts](../mobile/src/store/slices/analyticsSlice.ts))

**State**:
```typescript
interface AnalyticsState {
  analyticsData: {
    inventoryHistory: DataPoint[];
    costBreakdown: CostCategory[];
    bullwhipRatio: number;
    demandVariance: DataPoint[];
  };
  loading: boolean;
}
```

#### 5. chatSlice ([src/store/slices/chatSlice.ts](../mobile/src/store/slices/chatSlice.ts))

**State**:
```typescript
interface ChatState {
  conversations: { [gameId: string]: Message[] };
  typingAgents: { [gameId: string]: string[] };
  unreadCounts: { [gameId: string]: number };
}
```

#### 6. uiSlice ([src/store/slices/uiSlice.ts](../mobile/src/store/slices/uiSlice.ts))

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

**File**: [src/services/api.ts](../mobile/src/services/api.ts)

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
      // Token expired, logout user
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
- `POST /api/v1/auth/login` - User login
- `POST /api/v1/auth/register` - User registration
- `POST /api/v1/auth/logout` - User logout
- `POST /api/v1/auth/refresh` - Refresh JWT token

**Games**:
- `GET /api/v1/mixed-games` - List games
- `POST /api/v1/mixed-games` - Create game
- `GET /api/v1/mixed-games/{id}` - Get game details
- `POST /api/v1/mixed-games/{id}/start` - Start game
- `POST /api/v1/mixed-games/{id}/play-round` - Submit round decisions
- `GET /api/v1/mixed-games/{id}/state` - Get current state
- `GET /api/v1/mixed-games/{id}/history` - Get game history

**Templates**:
- `GET /api/v1/supply-chain-configs` - List templates
- `GET /api/v1/supply-chain-configs/{id}` - Get template details

**Analytics**:
- `GET /api/v1/analytics/bullwhip` - Bullwhip metrics
- `GET /api/v1/analytics/performance` - Performance report
- `POST /api/v1/reports/generate` - Generate report

**Agents**:
- `POST /api/v1/agents/suggest` - Get AI suggestion
- `GET /api/v1/agents/strategies` - List agent strategies

---

## Offline Mode

### Architecture

The offline mode uses a queue-based system to store actions when connectivity is lost and replay them when connectivity resumes.

**File**: [src/services/offline.ts](../mobile/src/services/offline.ts)

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
    // Load queue from storage
    const stored = await AsyncStorage.getItem('offline_queue');
    if (stored) {
      this.queue = JSON.parse(stored);
    }

    // Monitor connectivity
    NetInfo.addEventListener(state => {
      const wasOffline = !this.isOnline;
      this.isOnline = state.isConnected ?? false;

      if (wasOffline && this.isOnline) {
        // Came back online, process queue
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
        this.queue.shift(); // Remove from queue on success
      } catch (error) {
        action.retryCount++;
        if (action.retryCount >= 3) {
          // Max retries reached, discard
          this.queue.shift();
        } else {
          // Retry later
          break;
        }
      }

      await this.saveQueue();
    }
  }

  async executeAction(action: QueuedAction) {
    switch (action.type) {
      case 'PLACE_ORDER':
        await api.post(`/mixed-games/${action.payload.gameId}/play-round`, {
          order_quantity: action.payload.quantity,
        });
        break;
      // Add more action types as needed
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

### Usage in Components

```typescript
const GameDetailScreen = () => {
  const handlePlaceOrder = async (quantity: number) => {
    if (offlineService.isOffline()) {
      // Queue action for later
      await offlineService.queueAction({
        type: 'PLACE_ORDER',
        payload: { gameId, quantity },
        timestamp: Date.now(),
      });
      showToast('Offline: Order queued for sync', 'warning');
    } else {
      // Online: Execute immediately
      await dispatch(placeOrder({ gameId, quantity }));
    }
  };
};
```

### Offline Banner

**Component**: [src/components/common/OfflineBanner.tsx](../mobile/src/components/common/OfflineBanner.tsx)

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

**See**: [mobile/firebase-setup.md](../mobile/firebase-setup.md) for detailed setup instructions.

### Implementation

**File**: [src/services/notifications.ts](../mobile/src/services/notifications.ts)

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

    // Send token to backend
    await api.post('/users/me/fcm-token', { token });
  }

  setupForegroundHandler() {
    // Handle notifications when app is in foreground
    messaging().onMessage(async (remoteMessage) => {
      Alert.alert(
        remoteMessage.notification?.title ?? 'Notification',
        remoteMessage.notification?.body ?? ''
      );
    });
  }

  setupBackgroundHandler() {
    // Handle notifications when app is in background
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

**Game Events**:
- `game_started`: "Game [name] has started!"
- `round_completed`: "Round [X] completed in [game name]"
- `your_turn`: "It's your turn in [game name]"
- `game_completed`: "Game [name] has finished!"

**Agent Events**:
- `agent_suggestion`: "AI agent suggests ordering [X] units"
- `agent_decision`: "Agent [name] placed an order"
- `a2a_message`: "New agent conversation in [game name]"

**System Events**:
- `system_update`: "Platform maintenance scheduled"
- `achievement_unlocked`: "You unlocked [achievement]!"

### Notification Payload

```json
{
  "notification": {
    "title": "Your Turn!",
    "body": "It's your turn in Classic Beer Game"
  },
  "data": {
    "type": "your_turn",
    "gameId": "123",
    "roundNumber": "5"
  }
}
```

### Handling Notification Taps

```typescript
// Open app from notification
messaging().onNotificationOpenedApp((remoteMessage) => {
  const { type, gameId } = remoteMessage.data;

  if (type === 'your_turn' || type === 'game_started') {
    navigation.navigate('GameDetail', { gameId });
  }
});

// App opened from quit state
messaging()
  .getInitialNotification()
  .then((remoteMessage) => {
    if (remoteMessage) {
      const { type, gameId } = remoteMessage.data;
      navigation.navigate('GameDetail', { gameId });
    }
  });
```

---

## WebSocket Real-Time Updates

### Socket.IO Client Configuration

**File**: [src/services/websocket.ts](../mobile/src/services/websocket.ts)

```typescript
import io, { Socket } from 'socket.io-client';
import { WS_URL } from '../constants';
import { store } from '../store';
import { updateGameState } from '../store/slices/gamesSlice';
import { addChatMessage } from '../store/slices/chatSlice';

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

    this.socket.on('game_update', (data) => {
      store.dispatch(updateGameState(data));
    });

    this.socket.on('a2a_message', (data) => {
      store.dispatch(addChatMessage(data));
    });

    this.socket.on('round_completed', (data) => {
      // Show notification or update UI
    });
  }

  joinGame(gameId: string) {
    this.socket?.emit('join_game', { gameId });
  }

  leaveGame(gameId: string) {
    this.socket?.emit('leave_game', { gameId });
  }

  disconnect() {
    this.socket?.disconnect();
    this.socket = null;
  }
}

export const websocketService = new WebSocketService();
```

### Usage in Components

```typescript
const GameDetailScreen = ({ route }: any) => {
  const { gameId } = route.params;

  useEffect(() => {
    // Join game room
    websocketService.joinGame(gameId);

    return () => {
      // Leave game room on unmount
      websocketService.leaveGame(gameId);
    };
  }, [gameId]);

  // Component automatically re-renders when Redux state updates from WebSocket
};
```

### WebSocket Events

**Client → Server**:
- `join_game`: Subscribe to game updates
- `leave_game`: Unsubscribe from game updates
- `place_order`: Submit order decision (alternative to REST API)

**Server → Client**:
- `game_update`: Full game state update
- `round_completed`: Round finished, new round started
- `player_joined`: New player joined game
- `player_left`: Player left game
- `a2a_message`: Agent-to-agent conversation message

---

## Screens & Navigation

### Navigation Structure

**File**: [src/navigation/AppNavigator.tsx](../mobile/src/navigation/AppNavigator.tsx)

```
AppNavigator
├── AuthNavigator (when not authenticated)
│   ├── LoginScreen
│   └── RegisterScreen
└── MainNavigator (when authenticated)
    └── BottomTabNavigator
        ├── DashboardTab
        │   └── DashboardScreen
        ├── GamesTab (Stack)
        │   ├── GamesListScreen
        │   ├── GameDetailScreen
        │   ├── GameDetailWithChatScreen
        │   └── CreateGameScreen
        ├── TemplatesTab
        │   └── TemplateLibraryScreen
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

const GamesStack = () => (
  <Stack.Navigator>
    <Stack.Screen name="GamesList" component={GamesListScreen} />
    <Stack.Screen name="GameDetail" component={GameDetailScreen} />
    <Stack.Screen name="GameDetailWithChat" component={GameDetailWithChatScreen} />
    <Stack.Screen name="CreateGame" component={CreateGameScreen} />
  </Stack.Navigator>
);

const MainNavigator = () => (
  <Tab.Navigator>
    <Tab.Screen name="Dashboard" component={DashboardScreen} />
    <Tab.Screen name="Games" component={GamesStack} />
    <Tab.Screen name="Templates" component={TemplateLibraryScreen} />
    <Tab.Screen name="Analytics" component={AnalyticsScreen} />
    <Tab.Screen name="Profile" component={ProfileScreen} />
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
│   └── DashboardScreen.test.tsx
├── store/slices/
│   ├── authSlice.test.ts
│   ├── gamesSlice.test.ts
│   └── templatesSlice.test.ts
└── services/
    └── notifications.test.ts
```

### Unit Testing Example

**File**: [__tests__/store/slices/authSlice.test.ts](../mobile/__tests__/store/slices/authSlice.test.ts)

```typescript
import { configureStore } from '@reduxjs/toolkit';
import authReducer, { login, logout } from '../../../src/store/slices/authSlice';

describe('authSlice', () => {
  let store;

  beforeEach(() => {
    store = configureStore({ reducer: { auth: authReducer } });
  });

  it('should handle login success', async () => {
    const credentials = { email: 'test@example.com', password: 'password' };
    await store.dispatch(login(credentials));

    const state = store.getState().auth;
    expect(state.isAuthenticated).toBe(true);
    expect(state.token).toBeTruthy();
  });

  it('should handle logout', () => {
    store.dispatch(logout());

    const state = store.getState().auth;
    expect(state.isAuthenticated).toBe(false);
    expect(state.token).toBeNull();
  });
});
```

### Component Testing Example

```typescript
import { render, fireEvent } from '@testing-library/react-native';
import { Provider } from 'react-redux';
import { store } from '../../../src/store';
import LoginScreen from '../../../src/screens/Auth/LoginScreen';

describe('LoginScreen', () => {
  it('should render login form', () => {
    const { getByPlaceholderText, getByText } = render(
      <Provider store={store}>
        <LoginScreen />
      </Provider>
    );

    expect(getByPlaceholderText('Email')).toBeTruthy();
    expect(getByPlaceholderText('Password')).toBeTruthy();
    expect(getByText('Login')).toBeTruthy();
  });

  it('should call login on submit', () => {
    const { getByPlaceholderText, getByText } = render(
      <Provider store={store}>
        <LoginScreen />
      </Provider>
    );

    fireEvent.changeText(getByPlaceholderText('Email'), 'test@example.com');
    fireEvent.changeText(getByPlaceholderText('Password'), 'password');
    fireEvent.press(getByText('Login'));

    // Assert login action was dispatched
  });
});
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
const GameCard = React.memo(({ game }: { game: Game }) => {
  return (
    <Card>
      <Card.Title title={game.name} />
      <Card.Content>
        <Text>Status: {game.status}</Text>
      </Card.Content>
    </Card>
  );
});
```

### FlatList Optimization

```typescript
<FlatList
  data={games}
  renderItem={({ item }) => <GameCard game={item} />}
  keyExtractor={(item) => item.id}
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

### Image Optimization

```typescript
import FastImage from 'react-native-fast-image';

<FastImage
  source={{ uri: imageUrl, priority: FastImage.priority.normal }}
  style={{ width: 200, height: 200 }}
  resizeMode={FastImage.resizeMode.contain}
/>
```

### Hermes JavaScript Engine

**Android** ([android/app/build.gradle](../mobile/android/app/build.gradle)):
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
open ios/BeerGame.xcworkspace
```

2. Select "Any iOS Device (arm64)" target

3. Product → Archive

4. Distribute App → App Store Connect

**Fastlane (Automated)**:
```bash
cd ios
fastlane release
```

### Android Build & Release

**Debug Build**:
```bash
npm run android
```

**Release APK**:
```bash
cd android
./gradlew assembleRelease

# APK location:
# android/app/build/outputs/apk/release/app-release.apk
```

**Release Bundle (for Play Store)**:
```bash
cd android
./gradlew bundleRelease

# AAB location:
# android/app/build/outputs/bundle/release/app-release.aab
```

**Fastlane (Automated)**:
```bash
cd android
fastlane release
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
API_BASE_URL=https://staging-api.beergame.com
WS_URL=wss://staging-api.beergame.com/ws
ENVIRONMENT=staging
```

**Production**:
```env
API_BASE_URL=https://api.beergame.com
WS_URL=wss://api.beergame.com/ws
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

1. Verify Firebase setup: [firebase-setup.md](../mobile/firebase-setup.md)
2. Check `google-services.json` (Android) and `GoogleService-Info.plist` (iOS) are present
3. Request notification permissions in app
4. Test with Firebase Console Test Message

---

## Deployment Checklist

See [mobile/INTEGRATION_CHECKLIST.md](../mobile/INTEGRATION_CHECKLIST.md) for complete pre-launch checklist.

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
- [README.md](../mobile/README.md) - Project overview
- [INSTALL.md](../mobile/INSTALL.md) - Installation instructions
- [QUICKSTART.md](../mobile/QUICKSTART.md) - 5-minute quick start
- [QUICK_REFERENCE.md](../mobile/QUICK_REFERENCE.md) - Command reference
- [firebase-setup.md](../mobile/firebase-setup.md) - Firebase setup
- [DEPLOYMENT.md](../mobile/DEPLOYMENT.md) - Deployment guide
- [TESTING_GUIDE.md](../mobile/TESTING_GUIDE.md) - Testing procedures
- [ACCESSIBILITY.md](../mobile/ACCESSIBILITY.md) - Accessibility guidelines
- [A2A_COLLABORATION_GUIDE.md](../mobile/A2A_COLLABORATION_GUIDE.md) - Agent-to-Agent feature guide

### External Links
- [React Native Documentation](https://reactnative.dev/docs/getting-started)
- [React Navigation](https://reactnavigation.org/docs/getting-started)
- [Redux Toolkit](https://redux-toolkit.js.org/introduction/getting-started)
- [Firebase Cloud Messaging](https://firebase.google.com/docs/cloud-messaging)
- [Socket.IO Client](https://socket.io/docs/v4/client-api/)

---

## Support & Contact

For issues, questions, or feature requests:
- GitHub Issues: [Project Repository]
- Email: support@beergame.com
- Slack: #mobile-app channel

---

**Document Version**: 1.0.0
**Last Updated**: January 22, 2026
**Status**: Complete ✅
