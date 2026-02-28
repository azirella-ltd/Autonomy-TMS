#!/bin/bash
#
# Mobile App Setup Script
# Phase 7 Sprint 1: Mobile Application Foundation
#
# This script sets up the complete React Native project structure
#

set -e

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${BLUE}=================================="
echo "Mobile App Setup"
echo "==================================${NC}"
echo ""

MOBILE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Setting up React Native project structure..."

# Create directory structure
echo "Creating directories..."
mkdir -p "${MOBILE_DIR}/src"/{navigation,screens,components,store,services,utils,constants,types,theme}
mkdir -p "${MOBILE_DIR}/src/screens"/{Auth,Dashboard,Games,Templates,Analytics,Profile}
mkdir -p "${MOBILE_DIR}/src/store"/{slices,api}
mkdir -p "${MOBILE_DIR}/src/components"/{common,game,template,analytics}
mkdir -p "${MOBILE_DIR}/__tests__"
mkdir -p "${MOBILE_DIR}/assets"/{images,fonts}
mkdir -p "${MOBILE_DIR}/android/app/src/main"
mkdir -p "${MOBILE_DIR}/ios"

echo -e "${GREEN}✓ Directories created${NC}"

# Installation instructions
cat > "${MOBILE_DIR}/INSTALL.md" << 'EOF'
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
EOF

# Create TypeScript configuration
cat > "${MOBILE_DIR}/tsconfig.json" << 'EOF'
{
  "compilerOptions": {
    "allowJs": true,
    "allowSyntheticDefaultImports": true,
    "esModuleInterop": true,
    "isolatedModules": true,
    "jsx": "react-native",
    "lib": ["es2017"],
    "moduleResolution": "node",
    "noEmit": true,
    "strict": true,
    "target": "esnext",
    "resolveJsonModule": true,
    "skipLibCheck": true,
    "baseUrl": ".",
    "paths": {
      "@/*": ["src/*"],
      "@components/*": ["src/components/*"],
      "@screens/*": ["src/screens/*"],
      "@navigation/*": ["src/navigation/*"],
      "@store/*": ["src/store/*"],
      "@services/*": ["src/services/*"],
      "@utils/*": ["src/utils/*"],
      "@constants/*": ["src/constants/*"],
      "@types/*": ["src/types/*"],
      "@theme/*": ["src/theme/*"]
    }
  },
  "exclude": [
    "node_modules",
    "babel.config.js",
    "metro.config.js",
    "jest.config.js"
  ]
}
EOF

# Create babel configuration
cat > "${MOBILE_DIR}/babel.config.js" << 'EOF'
module.exports = {
  presets: ['module:@react-native/babel-preset'],
  plugins: [
    [
      'module-resolver',
      {
        root: ['./src'],
        extensions: ['.ios.js', '.android.js', '.js', '.ts', '.tsx', '.json'],
        alias: {
          '@': './src',
          '@components': './src/components',
          '@screens': './src/screens',
          '@navigation': './src/navigation',
          '@store': './src/store',
          '@services': './src/services',
          '@utils': './src/utils',
          '@constants': './src/constants',
          '@types': './src/types',
          '@theme': './src/theme',
        },
      },
    ],
    'react-native-reanimated/plugin',
  ],
};
EOF

# Create metro configuration
cat > "${MOBILE_DIR}/metro.config.js" << 'EOF'
const {getDefaultConfig, mergeConfig} = require('@react-native/metro-config');

const defaultConfig = getDefaultConfig(__dirname);

const config = {
  transformer: {
    getTransformOptions: async () => ({
      transform: {
        experimentalImportSupport: false,
        inlineRequires: true,
      },
    }),
  },
};

module.exports = mergeConfig(defaultConfig, config);
EOF

# Create app entry point
cat > "${MOBILE_DIR}/index.js" << 'EOF'
/**
 * @format
 */

import {AppRegistry} from 'react-native';
import App from './src/App';
import {name as appName} from './app.json';

AppRegistry.registerComponent(appName, () => App);
EOF

# Create app.json
cat > "${MOBILE_DIR}/app.json" << 'EOF'
{
  "name": "Autonomy",
  "displayName": "Autonomy",
  "expo": {
    "name": "Autonomy",
    "slug": "autonomy",
    "version": "1.0.0",
    "orientation": "portrait",
    "icon": "./assets/icon.png",
    "splash": {
      "image": "./assets/splash.png",
      "resizeMode": "contain",
      "backgroundColor": "#1976d2"
    },
    "updates": {
      "fallbackToCacheTimeout": 0
    },
    "assetBundlePatterns": [
      "**/*"
    ],
    "ios": {
      "supportsTablet": true,
      "bundleIdentifier": "com.autonomy.app"
    },
    "android": {
      "adaptiveIcon": {
        "foregroundImage": "./assets/adaptive-icon.png",
        "backgroundColor": "#FFFFFF"
      },
      "package": "com.autonomy.app"
    }
  }
}
EOF

# Create .env template
cat > "${MOBILE_DIR}/.env.example" << 'EOF'
# API Configuration
API_BASE_URL=http://localhost:8000
WS_URL=ws://localhost:8000/ws

# Firebase Configuration (optional)
FIREBASE_PROJECT_ID=
FIREBASE_API_KEY=
FIREBASE_APP_ID=

# Feature Flags
ENABLE_PUSH_NOTIFICATIONS=true
ENABLE_OFFLINE_MODE=true
ENABLE_BIOMETRIC_AUTH=true
EOF

echo -e "${GREEN}✓ Configuration files created${NC}"

# Create quick start guide
cat > "${MOBILE_DIR}/QUICKSTART.md" << 'EOF'
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

EOF

echo ""
echo -e "${GREEN}✓✓✓ Mobile app setup complete! ✓✓✓${NC}"
echo ""
echo "Next steps:"
echo "  1. cd mobile"
echo "  2. npm install"
echo "  3. Read INSTALL.md for platform-specific setup"
echo "  4. npm run ios    (or npm run android)"
echo ""
echo "Documentation:"
echo "  - README.md       - Complete documentation"
echo "  - INSTALL.md      - Installation instructions"
echo "  - QUICKSTART.md   - 5-minute quick start"
echo ""
