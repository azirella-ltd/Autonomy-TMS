# Firebase Cloud Messaging Setup Guide

This guide walks you through setting up Firebase Cloud Messaging (FCM) for push notifications in The Beer Game mobile app.

---

## Prerequisites

1. Firebase account (https://console.firebase.google.com)
2. Xcode 14+ (for iOS)
3. Android Studio (for Android)
4. CocoaPods installed (for iOS)

---

## Step 1: Create Firebase Project

1. Go to [Firebase Console](https://console.firebase.google.com)
2. Click "Add project"
3. Enter project name: "The Beer Game"
4. Enable Google Analytics (optional)
5. Click "Create project"

---

## Step 2: iOS Setup

### 2.1 Register iOS App

1. In Firebase Console, click "Add app" → iOS
2. Enter iOS bundle ID: `com.autonomy.app`
3. Enter App nickname: "Autonomy iOS"
4. Click "Register app"
5. Download `GoogleService-Info.plist`

### 2.2 Add Configuration File

```bash
# Copy GoogleService-Info.plist to iOS project
cp ~/Downloads/GoogleService-Info.plist mobile/ios/GoogleService-Info.plist
```

### 2.3 Update Xcode Project

1. Open `mobile/ios/Autonomy.xcworkspace` in Xcode
2. Right-click on project root → "Add Files to Autonomy"
3. Select `GoogleService-Info.plist`
4. **Important**: Check "Copy items if needed"

### 2.4 Enable Push Notifications Capability

1. In Xcode, select project → Target → "Signing & Capabilities"
2. Click "+ Capability"
3. Add "Push Notifications"
4. Add "Background Modes"
5. Check "Remote notifications" in Background Modes

### 2.5 APNs Authentication Key

1. Go to [Apple Developer Portal](https://developer.apple.com/account)
2. Certificates, Identifiers & Profiles → Keys
3. Click "+" to create new key
4. Enable "Apple Push Notifications service (APNs)"
5. Download `.p8` file
6. Note the Key ID

### 2.6 Upload APNs Key to Firebase

1. Firebase Console → Project Settings → Cloud Messaging
2. iOS app configuration → APNs Authentication Key
3. Upload `.p8` file
4. Enter Key ID and Team ID

---

## Step 3: Android Setup

### 3.1 Register Android App

1. In Firebase Console, click "Add app" → Android
2. Enter Android package name: `com.autonomy.app`
3. Enter App nickname: "Autonomy Android"
4. Click "Register app"
5. Download `google-services.json`

### 3.2 Add Configuration File

```bash
# Copy google-services.json to Android project
cp ~/Downloads/google-services.json mobile/android/app/google-services.json
```

### 3.3 Update build.gradle Files

**Project-level `android/build.gradle`:**
```gradle
buildscript {
  dependencies {
    // Add this line
    classpath 'com.google.gms:google-services:4.4.0'
  }
}
```

**App-level `android/app/build.gradle`:**
```gradle
// Add at the bottom of the file
apply plugin: 'com.google.gms.google-services'
```

### 3.4 Update AndroidManifest.xml

Add to `android/app/src/main/AndroidManifest.xml`:

```xml
<manifest>
  <application>
    <!-- Firebase Cloud Messaging -->
    <service
      android:name=".MyFirebaseMessagingService"
      android:exported="false">
      <intent-filter>
        <action android:name="com.google.firebase.MESSAGING_EVENT" />
      </intent-filter>
    </service>

    <!-- Default notification channel -->
    <meta-data
      android:name="com.google.firebase.messaging.default_notification_channel_id"
      android:value="@string/default_notification_channel_id" />
  </application>
</manifest>
```

---

## Step 4: Install Dependencies

```bash
cd mobile

# Install Firebase packages
npm install @react-native-firebase/app @react-native-firebase/messaging

# iOS: Install pods
cd ios && pod install && cd ..
```

---

## Step 5: Background Message Handler

Update `mobile/index.js`:

```javascript
import { AppRegistry } from 'react-native';
import messaging from '@react-native-firebase/messaging';
import App from './src/App';
import { name as appName } from './app.json';

// Background message handler
messaging().setBackgroundMessageHandler(async (remoteMessage) => {
  console.log('Background message received:', remoteMessage);
  // Handle background notification
});

AppRegistry.registerComponent(appName, () => App);
```

---

## Step 6: Testing

### Test on iOS Simulator
**Note**: iOS Simulator does NOT support push notifications. You must test on a physical device.

### Test on Android Emulator
Android emulator with Google Play Services supports FCM testing.

### Send Test Notification

1. Firebase Console → Cloud Messaging → Send test message
2. Enter FCM registration token (obtained from app logs)
3. Send notification

### Get FCM Token in App

The token is logged when the app initializes:
```
FCM token obtained: <token>
```

Copy this token to send test notifications from Firebase Console.

---

## Step 7: Backend Integration

Update backend to send push notifications:

```python
# backend/app/services/notifications.py
from firebase_admin import messaging

def send_notification(fcm_token: str, title: str, body: str, data: dict = None):
    message = messaging.Message(
        notification=messaging.Notification(
            title=title,
            body=body,
        ),
        data=data or {},
        token=fcm_token,
    )

    response = messaging.send(message)
    return response
```

---

## Step 8: Notification Types

The app handles these notification types:

### 1. Round Completed
```json
{
  "type": "round_completed",
  "game_id": "123",
  "round": "5"
}
```

### 2. Game Started
```json
{
  "type": "game_started",
  "game_id": "123"
}
```

### 3. Game Ended
```json
{
  "type": "game_ended",
  "game_id": "123"
}
```

### 4. Your Turn
```json
{
  "type": "your_turn",
  "game_id": "123",
  "node_name": "Retailer"
}
```

### 5. New Template
```json
{
  "type": "new_template",
  "template_id": "456"
}
```

---

## Troubleshooting

### iOS Issues

**Issue**: "No valid 'aps-environment' entitlement"
- **Fix**: Enable Push Notifications capability in Xcode

**Issue**: Token registration fails
- **Fix**: Ensure APNs key is uploaded to Firebase Console

**Issue**: Notifications not received in background
- **Fix**: Enable "Remote notifications" in Background Modes

### Android Issues

**Issue**: "Default FirebaseApp is not initialized"
- **Fix**: Ensure `google-services.json` is in `android/app/`
- **Fix**: Check `google-services` plugin is applied

**Issue**: FCM token not generated
- **Fix**: Ensure Google Play Services is installed on device/emulator

**Issue**: Notifications not showing
- **Fix**: Create notification channel for Android 8.0+

---

## Environment Variables

Add to `.env`:

```env
# Firebase Configuration (optional - used by Firebase SDK)
FIREBASE_PROJECT_ID=your-project-id
FIREBASE_API_KEY=your-api-key
FIREBASE_APP_ID=your-app-id
```

---

## Security Considerations

1. **Never commit Firebase config files to public repositories**
   - Add to `.gitignore`:
     ```
     mobile/ios/GoogleService-Info.plist
     mobile/android/app/google-services.json
     ```

2. **Use Firebase App Check** (optional)
   - Protects backend from abuse
   - Verifies requests come from legitimate app instances

3. **Server-side Token Validation**
   - Validate FCM tokens before sending notifications
   - Remove invalid tokens from database

---

## Production Deployment

### iOS

1. Generate production APNs certificate
2. Upload to Firebase Console
3. Update provisioning profiles
4. Archive and submit to App Store

### Android

1. Generate signed APK/AAB
2. Upload to Play Console
3. Firebase automatically works in production

---

## Monitoring

Firebase Console provides:
- Notification delivery metrics
- Conversion tracking
- A/B testing for notifications
- Analytics integration

---

## Cost

Firebase Cloud Messaging is **free** for unlimited notifications.

---

## Additional Resources

- [Firebase Cloud Messaging Docs](https://firebase.google.com/docs/cloud-messaging)
- [React Native Firebase Docs](https://rnfirebase.io)
- [APNs Overview](https://developer.apple.com/notifications/)
- [FCM HTTP v1 API](https://firebase.google.com/docs/reference/fcm/rest/v1/projects.messages)

---

**Setup Complete!** 🎉

Your mobile app is now configured for push notifications.
