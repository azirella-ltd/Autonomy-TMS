# Quick Start Guide

## Get Up and Running in 5 Minutes

### 1. Install Dependencies

```bash
npm install
```

### 2. Start the Backend

In a separate terminal:
```bash
cd ..
make up
```

### 3. Run the Mobile App

#### iOS (Mac only)
```bash
cd ios && pod install && cd ..
npm run ios
```

#### Android
```bash
npm run android
```

### 4. Login

Use the default credentials:
- Email: systemadmin@autonomy.ai
- Password: Autonomy@2026

### 5. Test Features

- Browse template library
- Create a new game
- View dashboard metrics
- Monitor agent activity

## Development Tips

### Hot Reload
- Press `R` twice (iOS) or `RR` (Android) to reload
- Shake device to open developer menu

### Debug
- iOS: Cmd + D
- Android: Cmd/Ctrl + M

### Common Commands

```bash
# Clear cache
npm start -- --reset-cache

# Run on specific device
npm run ios -- --simulator="iPhone 15"
npm run android -- --deviceId=<device-id>

# Build release
npm run build:ios:release
npm run build:android:release
```

## Next Steps

1. Explore the codebase in `src/`
2. Customize theme in `src/theme/`
3. Add new screens in `src/screens/`
4. Extend API client in `src/services/api.ts`

