# Mobile App Deployment Guide

Complete guide for building and deploying Autonomy mobile app to iOS App Store and Google Play Store.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Environment Setup](#environment-setup)
3. [iOS Deployment](#ios-deployment)
4. [Android Deployment](#android-deployment)
5. [CI/CD Setup](#cicd-setup)
6. [App Store Submission](#app-store-submission)
7. [Play Store Submission](#play-store-submission)
8. [Post-Launch](#post-launch)

---

## Prerequisites

### Required Tools

- **Node.js**: 18+ LTS
- **React Native CLI**: `npm install -g react-native-cli`
- **CocoaPods**: (iOS) `sudo gem install cocoapods`
- **Xcode**: 14+ (iOS - Mac only)
- **Android Studio**: Latest (Android)
- **Fastlane**: (Optional) `sudo gem install fastlane`

### Required Accounts

- **Apple Developer Account**: $99/year
- **Google Play Developer Account**: $25 one-time
- **Firebase Account**: Free

### Code Signing

- **iOS**: Apple Developer certificates and provisioning profiles
- **Android**: Keystore file for app signing

---

## Environment Setup

### 1. Clone and Install

```bash
# Clone repository
git clone <repo-url>
cd The_Beer_Game/mobile

# Install dependencies
npm install

# iOS: Install pods
cd ios && pod install && cd ..
```

### 2. Environment Configuration

Create `.env` file:

```env
# API Configuration
API_BASE_URL=https://api.autonomy.com
WS_URL=wss://api.autonomy.com/ws

# Firebase Configuration
FIREBASE_PROJECT_ID=your-project-id
FIREBASE_API_KEY=your-api-key
FIREBASE_APP_ID=your-app-id

# Feature Flags
ENABLE_PUSH_NOTIFICATIONS=true
ENABLE_OFFLINE_MODE=true
ENABLE_BIOMETRIC_AUTH=true
```

### 3. Firebase Setup

Follow [firebase-setup.md](./firebase-setup.md) to configure push notifications.

---

## iOS Deployment

### Step 1: Update App Configuration

**Update `ios/Autonomy/Info.plist`:**

```xml
<key>CFBundleDisplayName</key>
<string>Autonomy</string>
<key>CFBundleShortVersionString</key>
<string>1.0.0</string>
<key>CFBundleVersion</key>
<string>1</string>
```

### Step 2: App Icon and Launch Screen

1. **App Icon**:
   - Create 1024x1024 px icon
   - Use [App Icon Generator](https://appicon.co/)
   - Place generated assets in `ios/Autonomy/Images.xcassets/AppIcon.appiconset/`

2. **Launch Screen**:
   - Edit `ios/Autonomy/LaunchScreen.storyboard` in Xcode
   - Or use `react-native-splash-screen` package

### Step 3: Code Signing

1. Open `ios/Autonomy.xcworkspace` in Xcode
2. Select project → Target → "Signing & Capabilities"
3. Select your team
4. Xcode will automatically create certificates and provisioning profiles

### Step 4: Build Release

**Option A: Xcode UI**

1. Product → Scheme → Edit Scheme
2. Set Build Configuration to "Release"
3. Product → Archive
4. Window → Organizer → Distribute App

**Option B: Command Line**

```bash
cd ios

# Build release
xcodebuild -workspace Autonomy.xcworkspace \
  -scheme Autonomy \
  -configuration Release \
  -archivePath build/Autonomy.xcarchive \
  archive

# Export IPA
xcodebuild -exportArchive \
  -archivePath build/Autonomy.xcarchive \
  -exportPath build \
  -exportOptionsPlist ExportOptions.plist
```

**Option C: Fastlane**

```bash
# Install fastlane
cd ios
fastlane init

# Configure Fastfile
fastlane ios release
```

### Step 5: TestFlight

1. Xcode Organizer → Distribute App → TestFlight
2. Upload build
3. Wait for processing (10-30 minutes)
4. Add internal testers
5. Submit for external testing (requires review)

### Step 6: Version Bump

```bash
# Increment build number
cd ios
agvtool next-version -all

# Or manually edit Info.plist
```

---

## Android Deployment

### Step 1: Generate Keystore

```bash
cd android/app

# Generate keystore
keytool -genkeypair -v \
  -storetype PKCS12 \
  -keystore autonomy-release.keystore \
  -alias autonomy \
  -keyalg RSA \
  -keysize 2048 \
  -validity 10000
```

**Save keystore credentials securely!**

### Step 2: Configure Signing

**Create `android/gradle.properties`:**

```properties
BEERGAME_RELEASE_STORE_FILE=autonomy-release.keystore
BEERGAME_RELEASE_KEY_ALIAS=autonomy
BEERGAME_RELEASE_STORE_PASSWORD=****
BEERGAME_RELEASE_KEY_PASSWORD=****
```

**Update `android/app/build.gradle`:**

```gradle
android {
    signingConfigs {
        release {
            if (project.hasProperty('BEERGAME_RELEASE_STORE_FILE')) {
                storeFile file(BEERGAME_RELEASE_STORE_FILE)
                storePassword BEERGAME_RELEASE_STORE_PASSWORD
                keyAlias BEERGAME_RELEASE_KEY_ALIAS
                keyPassword BEERGAME_RELEASE_KEY_PASSWORD
            }
        }
    }
    buildTypes {
        release {
            signingConfig signingConfigs.release
            minifyEnabled true
            proguardFiles getDefaultProguardFile("proguard-android.txt"), "proguard-rules.pro"
        }
    }
}
```

### Step 3: App Icon and Splash Screen

1. **App Icon**:
   - Create icons for all densities (mdpi, hdpi, xhdpi, xxhdpi, xxxhdpi)
   - Place in `android/app/src/main/res/mipmap-*/`
   - Or use [Android Asset Studio](https://romannurik.github.io/AndroidAssetStudio/)

2. **Splash Screen**:
   - Use `react-native-splash-screen` package
   - Or configure in `android/app/src/main/res/values/styles.xml`

### Step 4: Build Release APK/AAB

**APK (for testing):**

```bash
cd android
./gradlew assembleRelease

# Output: android/app/build/outputs/apk/release/app-release.apk
```

**AAB (for Play Store):**

```bash
cd android
./gradlew bundleRelease

# Output: android/app/build/outputs/bundle/release/app-release.aab
```

### Step 5: Test APK

```bash
# Install on device
adb install android/app/build/outputs/apk/release/app-release.apk

# Or drag and drop APK to emulator
```

### Step 6: Version Bump

**Update `android/app/build.gradle`:**

```gradle
android {
    defaultConfig {
        versionCode 2  // Increment for each release
        versionName "1.0.1"  // User-facing version
    }
}
```

---

## CI/CD Setup

### GitHub Actions Example

**`.github/workflows/build-ios.yml`:**

```yaml
name: Build iOS

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  build:
    runs-on: macos-latest
    steps:
      - uses: actions/checkout@v3

      - name: Setup Node.js
        uses: actions/setup-node@v3
        with:
          node-version: '18'

      - name: Install dependencies
        working-directory: mobile
        run: npm install

      - name: Install pods
        working-directory: mobile/ios
        run: pod install

      - name: Build iOS
        working-directory: mobile/ios
        run: |
          xcodebuild -workspace Autonomy.xcworkspace \
            -scheme Autonomy \
            -configuration Release \
            -sdk iphoneos \
            -archivePath build/Autonomy.xcarchive \
            archive
```

**`.github/workflows/build-android.yml`:**

```yaml
name: Build Android

on:
  push:
    branches: [main]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Setup Node.js
        uses: actions/setup-node@v3
        with:
          node-version: '18'

      - name: Setup Java
        uses: actions/setup-java@v3
        with:
          distribution: 'zulu'
          java-version: '11'

      - name: Install dependencies
        working-directory: mobile
        run: npm install

      - name: Build Android AAB
        working-directory: mobile/android
        run: ./gradlew bundleRelease

      - name: Upload AAB
        uses: actions/upload-artifact@v3
        with:
          name: app-release.aab
          path: mobile/android/app/build/outputs/bundle/release/app-release.aab
```

---

## App Store Submission

### 1. App Store Connect Setup

1. Go to [App Store Connect](https://appstoreconnect.apple.com)
2. My Apps → "+" → New App
3. Fill in app information:
   - **Name**: Autonomy
   - **Primary Language**: English
   - **Bundle ID**: com.autonomy.app
   - **SKU**: autonomy
   - **User Access**: Full Access

### 2. App Information

- **Category**: Education or Business
- **Content Rights**: Check if you own rights
- **Age Rating**: 4+

### 3. Pricing and Availability

- **Price**: Free (or set price)
- **Availability**: All countries

### 4. Prepare for Submission

1. **Screenshots** (required for each device size):
   - iPhone 6.7" (1290 x 2796 px) - 3 required
   - iPhone 6.5" (1284 x 2778 px)
   - iPhone 5.5" (1242 x 2208 px)
   - iPad Pro 12.9" (2048 x 2732 px)

2. **App Preview** (optional):
   - 15-30 second videos

3. **Description**:
   ```
   Autonomy - Supply Chain Simulation Platform

   Master supply chain management through interactive gameplay.
   Experience the bullwhip effect firsthand and learn optimal
   inventory strategies.

   Features:
   - AI-powered agents
   - Real-time collaboration
   - Advanced analytics
   - Multiple supply chain configurations
   ```

4. **Keywords**: supply chain, simulation, business, education, logistics

5. **Support URL**: https://autonomy.com/support
6. **Privacy Policy URL**: https://autonomy.com/privacy

### 5. Submit for Review

1. Upload build from TestFlight
2. Fill in "What's New in This Version"
3. Submit for review
4. Wait 24-48 hours for approval

---

## Play Store Submission

### 1. Google Play Console Setup

1. Go to [Google Play Console](https://play.google.com/console)
2. Create app
3. Fill in app details:
   - **App name**: Autonomy
   - **Default language**: English
   - **App or game**: App
   - **Free or paid**: Free

### 2. Store Listing

1. **Short description** (80 chars):
   ```
   Master supply chain management through interactive gameplay simulation
   ```

2. **Full description** (4000 chars):
   ```
   Autonomy - Supply Chain Simulation Platform

   [Full description here]
   ```

3. **App icon**: 512 x 512 px PNG
4. **Feature graphic**: 1024 x 500 px JPG
5. **Screenshots**:
   - Phone: 320-3840 px (min 2, max 8)
   - 7-inch tablet: 1024-3840 px (optional)
   - 10-inch tablet: 1024-3840 px (optional)

6. **Category**: Business or Education
7. **Content rating**: Complete questionnaire
8. **Target audience**: 13+

### 3. App Content

1. **Privacy policy**: https://autonomy.com/privacy
2. **App access**: Not restricted
3. **Content ratings**: Complete IARC questionnaire
4. **Target audience**: Select age groups
5. **News apps**: No
6. **COVID-19 contact tracing**: No
7. **Data safety**: Complete data collection form

### 4. Create Release

1. **Production** → Create new release
2. Upload AAB
3. Add release notes
4. Set rollout percentage (optional)
5. Review and rollout

### 5. Submit for Review

Review typically takes 1-3 days.

---

## Post-Launch

### Monitoring

1. **Crashlytics** (Firebase):
   - Monitor crash-free users
   - Track ANR (Android Not Responding)

2. **Analytics** (Firebase):
   - Track active users
   - Monitor retention
   - Track key events

3. **App Store/Play Console**:
   - Monitor ratings and reviews
   - Track downloads and installs

### Updates

1. Fix critical bugs quickly
2. Regular feature updates every 2-4 weeks
3. Version increments:
   - Major: 1.0.0 → 2.0.0 (breaking changes)
   - Minor: 1.0.0 → 1.1.0 (new features)
   - Patch: 1.0.0 → 1.0.1 (bug fixes)

### User Feedback

1. Respond to reviews (App Store/Play Store)
2. Monitor support channels
3. Collect feature requests
4. Track NPS (Net Promoter Score)

---

## Troubleshooting

### iOS Build Issues

**Issue**: "Provisioning profile doesn't include signing certificate"
- **Fix**: Xcode → Preferences → Accounts → Download Manual Profiles

**Issue**: "Code signing failed"
- **Fix**: Ensure correct team and certificates are selected

### Android Build Issues

**Issue**: "Task :app:lintVitalRelease FAILED"
- **Fix**: Add to `android/app/build.gradle`:
  ```gradle
  lintOptions {
      checkReleaseBuilds false
  }
  ```

**Issue**: "Keystore file not found"
- **Fix**: Check path in `gradle.properties`

---

## Checklists

### Pre-Launch Checklist

- [ ] All features tested on physical devices
- [ ] Crash-free rate >99%
- [ ] App size <100MB
- [ ] Loading time <3 seconds
- [ ] API endpoints configured
- [ ] Push notifications working
- [ ] Deep links tested
- [ ] App icons added (all sizes)
- [ ] Screenshots captured
- [ ] App Store descriptions written
- [ ] Privacy policy published
- [ ] Terms of service published

### Launch Day Checklist

- [ ] Monitor crash reports
- [ ] Check server load
- [ ] Monitor user reviews
- [ ] Track downloads
- [ ] Prepare hotfix if needed
- [ ] Social media announcements
- [ ] Email existing users

---

**Deployment Complete!** 🚀

Your mobile app is now live in production.
