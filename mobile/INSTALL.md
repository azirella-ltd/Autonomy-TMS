# Installation Instructions

## 1. Prerequisites

Install the following:
- Node.js 18+ (https://nodejs.org/)
- React Native CLI: `npm install -g react-native-cli`
- Watchman (Mac): `brew install watchman`

### For iOS Development:
- Xcode 14+ (Mac only)
- CocoaPods: `sudo gem install cocoapods`

### For Android Development:
- Android Studio
- Android SDK
- Set ANDROID_HOME environment variable

## 2. Install Dependencies

```bash
cd mobile
npm install
```

## 3. iOS Setup (Mac only)

```bash
cd ios
pod install
cd ..
```

## 4. Run the App

### iOS
```bash
npm run ios
```

### Android
```bash
npm run android
```

### Start Metro Bundler (in separate terminal)
```bash
npm start
```

## 5. Configure Environment

Create `.env` file:
```env
API_BASE_URL=http://localhost:8000
WS_URL=ws://localhost:8000/ws
```

For iOS simulator to access localhost:
- Use `http://localhost:8000`

For Android emulator to access localhost:
- Use `http://10.0.2.2:8000`

For physical devices:
- Use your computer's IP address

## Troubleshooting

### Metro Bundler Issues
```bash
npm start -- --reset-cache
```

### iOS Build Issues
```bash
cd ios
rm -rf Pods Podfile.lock
pod install
cd ..
```

### Android Build Issues
```bash
cd android
./gradlew clean
./gradlew assembleDebug
```

### Common Errors

**Error: Unable to resolve module**
```bash
npm start -- --reset-cache
npm install
```

**Error: CocoaPods**
```bash
cd ios
pod deintegrate
pod install
```

**Error: SDK location not found (Android)**
- Set ANDROID_HOME in ~/.bash_profile or ~/.zshrc
- `export ANDROID_HOME=$HOME/Library/Android/sdk`

## Next Steps

1. Configure Firebase for push notifications
2. Setup code signing (iOS)
3. Configure app icons and splash screens
4. Test on physical devices
