# The Beer Game - Mobile Application

React Native mobile application for iOS and Android.

## Features

- 📱 Native iOS and Android support
- 🔐 Secure authentication with JWT
- 🎮 Full game management
- 📊 Real-time analytics dashboard
- 🤖 AI agent monitoring
- 🔔 Push notifications for game events
- 📡 Real-time WebSocket updates
- 💾 Offline mode support
- 🎨 Material Design UI

## Prerequisites

- Node.js 18+
- React Native CLI
- Xcode 14+ (for iOS)
- Android Studio (for Android)
- CocoaPods (for iOS)

## Setup

### 1. Install Dependencies

```bash
cd mobile
npm install

# iOS only
cd ios && pod install && cd ..
```

### 2. Configuration

Create `.env` file:

```env
API_BASE_URL=http://localhost:8000
WS_URL=ws://localhost:8000/ws
FIREBASE_PROJECT_ID=your-project-id
```

### 3. Run

```bash
# iOS
npm run ios

# Android
npm run android

# Start Metro bundler
npm start
```

## Project Structure

```
mobile/
├── src/
│   ├── navigation/        # Navigation configuration
│   ├── screens/          # Screen components
│   │   ├── Auth/        # Authentication screens
│   │   ├── Dashboard/   # Dashboard screen
│   │   ├── Games/       # Game management
│   │   ├── Templates/   # Template browser
│   │   └── Analytics/   # Analytics views
│   ├── components/       # Reusable components
│   ├── store/           # Redux store
│   │   ├── slices/     # Redux slices
│   │   └── api/        # API integration
│   ├── services/        # API services
│   │   ├── api.ts      # API client
│   │   ├── auth.ts     # Authentication
│   │   └── websocket.ts # WebSocket client
│   ├── utils/           # Utility functions
│   ├── constants/       # Constants
│   ├── types/           # TypeScript types
│   └── theme/           # Theme configuration
├── android/             # Android native code
├── ios/                 # iOS native code
├── __tests__/          # Tests
└── assets/             # Images, fonts
```

## Features by Screen

### Authentication
- Login with email/password
- Registration
- Biometric authentication (Face ID/Touch ID)
- Remember me
- Password reset

### Dashboard
- Overview metrics
- Active games list
- Quick actions
- Recent activity
- Notifications

### Game Management
- Browse games
- Create new game
- Quick Start Wizard
- Game details
- Player management
- Round progression

### Templates
- Browse template library
- Search and filter
- Template preview
- Use template
- Favorite templates

### Analytics
- Real-time metrics
- Charts and graphs
- Bullwhip effect analysis
- Cost breakdown
- Export data

### Agent Monitoring
- Agent activity feed
- Agent decisions
- Performance metrics
- A2A conversations
- Intervention controls

## API Integration

### REST API

```typescript
// src/services/api.ts
import axios from 'axios';

const api = axios.create({
  baseURL: process.env.API_BASE_URL,
  timeout: 10000,
});

// Request interceptor
api.interceptors.request.use(async (config) => {
  const token = await AsyncStorage.getItem('auth_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export default api;
```

### WebSocket

```typescript
// src/services/websocket.ts
import io from 'socket.io-client';

const socket = io(process.env.WS_URL, {
  transports: ['websocket'],
  autoConnect: false,
});

socket.on('connect', () => {
  console.log('WebSocket connected');
});

socket.on('game_update', (data) => {
  store.dispatch(updateGameState(data));
});

export default socket;
```

## State Management

Redux Toolkit for state management:

```typescript
// src/store/slices/authSlice.ts
import { createSlice, createAsyncThunk } from '@reduxjs/toolkit';

export const login = createAsyncThunk(
  'auth/login',
  async ({ email, password }) => {
    const response = await api.post('/auth/login', { email, password });
    return response.data;
  }
);

const authSlice = createSlice({
  name: 'auth',
  initialState: { user: null, token: null, loading: false },
  reducers: {
    logout: (state) => {
      state.user = null;
      state.token = null;
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(login.pending, (state) => {
        state.loading = true;
      })
      .addCase(login.fulfilled, (state, action) => {
        state.user = action.payload.user;
        state.token = action.payload.token;
        state.loading = false;
      });
  },
});

export default authSlice.reducer;
```

## Push Notifications

### Setup Firebase

1. Add `google-services.json` (Android) to `android/app/`
2. Add `GoogleService-Info.plist` (iOS) to `ios/`

### Request Permission

```typescript
// src/services/notifications.ts
import messaging from '@react-native-firebase/messaging';

export async function requestNotificationPermission() {
  const authStatus = await messaging().requestPermission();
  return authStatus === messaging.AuthorizationStatus.AUTHORIZED;
}

export async function getDeviceToken() {
  return await messaging().getToken();
}

// Handle foreground notifications
messaging().onMessage(async (remoteMessage) => {
  Alert.alert(
    remoteMessage.notification?.title,
    remoteMessage.notification?.body
  );
});
```

## Offline Mode

Uses AsyncStorage for offline data caching:

```typescript
// src/utils/offlineStorage.ts
import AsyncStorage from '@react-native-async-storage/async-storage';

export async function cacheGameData(gameId: string, data: any) {
  await AsyncStorage.setItem(`game_${gameId}`, JSON.stringify(data));
}

export async function getCachedGameData(gameId: string) {
  const data = await AsyncStorage.getItem(`game_${gameId}`);
  return data ? JSON.parse(data) : null;
}
```

## Testing

```bash
# Run tests
npm test

# Run tests with coverage
npm test -- --coverage

# Run E2E tests (Detox)
npm run test:e2e
```

## Build & Release

### Android

```bash
# Debug build
npm run android

# Release build
cd android
./gradlew assembleRelease

# APK location
android/app/build/outputs/apk/release/app-release.apk
```

### iOS

```bash
# Debug build
npm run ios

# Release build
# Open Xcode and archive
open ios/BeerGame.xcworkspace
```

## Performance Optimization

### Tips
- Use React.memo for expensive components
- Implement FlatList with proper optimization
- Use native driver for animations
- Lazy load screens
- Optimize images (WebP format)
- Enable Hermes engine
- Use Flipper for debugging

### Hermes Configuration

```javascript
// android/app/build.gradle
project.ext.react = [
    enableHermes: true,
]
```

## Troubleshooting

### iOS Pod Install Issues
```bash
cd ios
rm -rf Pods Podfile.lock
pod install --repo-update
```

### Android Build Issues
```bash
cd android
./gradlew clean
./gradlew assembleDebug
```

### Metro Bundler Issues
```bash
npm start -- --reset-cache
```

## Environment Configuration

### Development
```env
API_BASE_URL=http://localhost:8000
WS_URL=ws://localhost:8000/ws
```

### Staging
```env
API_BASE_URL=https://staging-api.beergame.com
WS_URL=wss://staging-api.beergame.com/ws
```

### Production
```env
API_BASE_URL=https://api.beergame.com
WS_URL=wss://api.beergame.com/ws
```

## Contributing

1. Create feature branch
2. Make changes
3. Add tests
4. Submit PR

## License

(Specify license)

---

**Version**: 1.0.0
**Last Updated**: 2026-01-14
**React Native**: 0.73.2
