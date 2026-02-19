# Mobile App Quick Reference

Fast reference guide for common tasks and commands.

---

## 🚀 Quick Start

```bash
# Install dependencies
cd mobile && npm install

# iOS
cd ios && pod install && cd ..
npm run ios

# Android
npm run android
```

---

## 📁 Project Structure

```
mobile/
├── src/
│   ├── navigation/      # Navigation setup
│   ├── screens/         # Screen components
│   │   ├── Auth/        # Login, Register
│   │   ├── Dashboard/   # Main dashboard
│   │   ├── Games/       # Games management
│   │   ├── Templates/   # Template library
│   │   ├── Analytics/   # Analytics views
│   │   └── Profile/     # User profile
│   ├── components/      # Reusable components
│   │   └── common/      # LoadingSpinner, ErrorBoundary, etc.
│   ├── store/           # Redux state
│   │   └── slices/      # Redux slices
│   ├── services/        # API, WebSocket, etc.
│   ├── theme/           # Theme configuration
│   └── App.tsx          # Root component
├── ios/                 # iOS native code
├── android/             # Android native code
└── __tests__/          # Tests
```

---

## 🔧 Common Commands

### Development
```bash
# Start Metro bundler
npm start

# Clear cache
npm start -- --reset-cache

# Run on specific device
npm run ios -- --simulator="iPhone 15 Pro"
npm run android -- --deviceId=<device-id>

# List devices
xcrun simctl list devices  # iOS
adb devices                # Android
```

### Building
```bash
# iOS release
cd ios
xcodebuild -workspace Autonomy.xcworkspace \
  -scheme Autonomy -configuration Release

# Android release
cd android
./gradlew assembleRelease  # APK
./gradlew bundleRelease    # AAB
```

### Debugging
```bash
# React Native Debugger
npm install -g react-native-debugger

# Flipper (built-in)
# iOS: Cmd + D → "Open Debugger"
# Android: Cmd + M → "Open Debugger"

# Logs
npm run ios -- --verbose
npm run android -- --verbose

# Clear data
# iOS: Device → Erase All Content and Settings
# Android: adb shell pm clear com.autonomy.app
```

---

## 📱 Platform Differences

### URLs
```typescript
// iOS Simulator
http://localhost:8000

// Android Emulator
http://10.0.2.2:8000

// Physical Device
http://192.168.1.xxx:8000  // Your computer's IP
```

### Permissions

**iOS (Info.plist)**:
```xml
<key>NSCameraUsageDescription</key>
<string>To scan QR codes</string>
```

**Android (AndroidManifest.xml)**:
```xml
<uses-permission android:name="android.permission.CAMERA" />
```

---

## 🎨 Styling

### Theme Colors
```typescript
primary: '#1976d2'
secondary: '#424242'
success: '#388e3c'
error: '#d32f2f'
warning: '#f57c00'
info: '#0288d1'
```

### Spacing
```typescript
xs: 4px
sm: 8px
md: 16px
lg: 24px
xl: 32px
```

### Common Patterns
```typescript
// Container
<View style={styles.container}>
  {/* Content */}
</View>

const styles = StyleSheet.create({
  container: {
    flex: 1,
    padding: theme.spacing.md,
  },
});
```

---

## 🔌 API Usage

### Making API Calls
```typescript
import { apiClient } from '@services/api';

// GET
const games = await apiClient.getGames({ page: 1 });

// POST
const game = await apiClient.createGame({ name: 'Test Game' });

// With Redux
import { fetchGames } from '@store/slices/gamesSlice';
dispatch(fetchGames({ page: 1 }));
```

### WebSocket
```typescript
import { websocketService } from '@services/websocket';

// Connect
await websocketService.connect();

// Join room
websocketService.joinGame(gameId);

// Listen for events
websocketService.on('round_completed', (data) => {
  console.log('Round completed:', data);
});

// Disconnect
websocketService.disconnect();
```

---

## 📦 Redux Patterns

### Using Redux State
```typescript
import { useAppSelector, useAppDispatch } from '@store';

function MyComponent() {
  const dispatch = useAppDispatch();
  const { games, loading } = useAppSelector((state) => state.games);

  useEffect(() => {
    dispatch(fetchGames());
  }, []);

  return <View>{/* Render games */}</View>;
}
```

### Creating New Slice
```typescript
import { createSlice, createAsyncThunk } from '@reduxjs/toolkit';

export const fetchData = createAsyncThunk(
  'slice/fetchData',
  async () => {
    const response = await apiClient.getData();
    return response.data;
  }
);

const slice = createSlice({
  name: 'slice',
  initialState: { data: null, loading: false },
  reducers: {},
  extraReducers: (builder) => {
    builder
      .addCase(fetchData.pending, (state) => {
        state.loading = true;
      })
      .addCase(fetchData.fulfilled, (state, action) => {
        state.data = action.payload;
        state.loading = false;
      });
  },
});

export default slice.reducer;
```

---

## 🧪 Testing

### Running Tests
```bash
# Run all tests
npm test

# Run in watch mode
npm test -- --watch

# Coverage
npm test -- --coverage
```

### Writing Tests
```typescript
import { render, fireEvent } from '@testing-library/react-native';
import LoginScreen from '@screens/Auth/LoginScreen';

test('login button disabled when fields empty', () => {
  const { getByText } = render(<LoginScreen />);
  const button = getByText('Sign In');
  expect(button).toBeDisabled();
});
```

---

## 🔔 Push Notifications

### Send Test Notification (cURL)
```bash
curl -X POST https://fcm.googleapis.com/fcm/send \
  -H "Authorization: key=YOUR_SERVER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "to": "FCM_TOKEN",
    "notification": {
      "title": "Test",
      "body": "Test notification"
    },
    "data": {
      "type": "game_started",
      "game_id": "123"
    }
  }'
```

### Handle Notification
```typescript
import { notificationsService } from '@services/notifications';

// Initialize
await notificationsService.initialize();

// Get token
const token = await notificationsService.getToken();
console.log('FCM Token:', token);
```

---

## 📂 File Naming Conventions

- **Screens**: `PascalCase.tsx` (LoginScreen.tsx)
- **Components**: `PascalCase.tsx` (GameCard.tsx)
- **Services**: `camelCase.ts` (api.ts)
- **Styles**: inline StyleSheet
- **Types**: `types.ts` or inline interfaces

---

## 🐛 Common Issues

### Metro Bundler
```bash
# Issue: Module not found
# Fix:
npm start -- --reset-cache
rm -rf node_modules && npm install

# Issue: Port already in use
# Fix:
lsof -ti:8081 | xargs kill -9
```

### iOS Build
```bash
# Issue: Pod install fails
# Fix:
cd ios
rm -rf Pods Podfile.lock
pod deintegrate
pod install

# Issue: Xcode build fails
# Fix: Clean build folder
# Xcode → Product → Clean Build Folder (Cmd + Shift + K)
```

### Android Build
```bash
# Issue: Gradle build fails
# Fix:
cd android
./gradlew clean
./gradlew assembleDebug

# Issue: SDK not found
# Fix: Set ANDROID_HOME in ~/.bash_profile or ~/.zshrc
export ANDROID_HOME=$HOME/Library/Android/sdk
export PATH=$PATH:$ANDROID_HOME/emulator
export PATH=$PATH:$ANDROID_HOME/tools
export PATH=$PATH:$ANDROID_HOME/platform-tools
```

---

## 🔑 Environment Variables

```env
# .env file
API_BASE_URL=http://localhost:8000
WS_URL=ws://localhost:8000/ws
FIREBASE_PROJECT_ID=your-project-id
FIREBASE_API_KEY=your-api-key
ENABLE_PUSH_NOTIFICATIONS=true
```

Access in code:
```typescript
import Config from 'react-native-config';
const apiUrl = Config.API_BASE_URL;
```

---

## 📊 Performance Tips

### Optimize FlatList
```typescript
<FlatList
  data={items}
  keyExtractor={(item) => item.id.toString()}
  getItemLayout={(data, index) => ({
    length: ITEM_HEIGHT,
    offset: ITEM_HEIGHT * index,
    index,
  })}
  removeClippedSubviews={true}
  maxToRenderPerBatch={10}
  windowSize={10}
/>
```

### Memoize Components
```typescript
import React, { memo } from 'react';

const GameCard = memo(({ game }) => {
  return <Card>{/* ... */}</Card>;
});
```

### Use React.useCallback
```typescript
const handlePress = useCallback(() => {
  dispatch(action());
}, [dispatch]);
```

---

## 🔗 Useful Links

- **React Native Docs**: https://reactnative.dev
- **React Navigation**: https://reactnavigation.org
- **Redux Toolkit**: https://redux-toolkit.js.org
- **React Native Paper**: https://callstack.github.io/react-native-paper
- **Firebase**: https://firebase.google.com/docs

---

## 📞 Support

- **Issues**: GitHub Issues
- **Docs**: See README.md
- **Slack**: #mobile-dev channel

---

**Last Updated**: 2026-01-14
