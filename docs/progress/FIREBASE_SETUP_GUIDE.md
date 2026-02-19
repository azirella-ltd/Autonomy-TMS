# Firebase Setup Guide - Step-by-Step

**Task**: Option 2, Task 2 - Firebase Configuration
**Estimated Time**: 4-6 hours
**Difficulty**: Easy (configuration only, no coding)

---

## Overview

This guide will walk you through setting up Firebase Cloud Messaging (FCM) for The Beer Game mobile application. You'll configure:

1. Firebase project
2. iOS app registration
3. Android app registration
4. APNs authentication (iOS)
5. Service account credentials (backend)
6. Testing notification delivery

---

## Prerequisites

### Required Accounts
- [ ] Google Account (for Firebase Console)
- [ ] Apple Developer Account ($99/year) - **Required for iOS push notifications**
- [ ] Access to macOS (for iOS APNs key generation)

### Tools Needed
- [ ] Web browser
- [ ] Text editor
- [ ] Terminal/command line access
- [ ] Physical iOS device (iPhone 12+ with iOS 16+) for testing
- [ ] Physical Android device (Pixel 6+ with Android API 30+) for testing

---

## Part 1: Create Firebase Project (15 minutes)

### Step 1.1: Access Firebase Console

1. Open your web browser
2. Go to https://console.firebase.google.com
3. Sign in with your Google account

### Step 1.2: Create New Project

1. Click **"Add project"** or **"Create a project"**
2. Enter project details:
   - **Project name**: `Beer Game Mobile`
   - Click **"Continue"**

3. Google Analytics (Optional):
   - Toggle **"Enable Google Analytics for this project"**
   - Recommended: **Enable** (useful for tracking app usage)
   - Click **"Continue"**

4. Configure Google Analytics (if enabled):
   - **Analytics account**: Select existing or create new
   - **Analytics location**: Select your region
   - Accept terms and conditions
   - Click **"Create project"**

5. Wait for project creation (30-60 seconds)
6. Click **"Continue"** when done

### Step 1.3: Enable Cloud Messaging

1. In Firebase Console, your project should now be open
2. Note your **Project ID** (you'll need this later)
   - Format: `beer-game-mobile-xxxxx`
   - Location: Project Settings → General

---

## Part 2: Register iOS App (30 minutes)

### Step 2.1: Add iOS App to Firebase

1. In Firebase Console, click the **iOS icon** (⊕ iOS)
2. Fill in iOS app details:

   **iOS bundle ID**: `com.autonomy.app`
   - ⚠️ **CRITICAL**: This must match exactly
   - Check your iOS app's Bundle ID in Xcode: `mobile/ios/BeerGame.xcodeproj` → Signing & Capabilities

   **App nickname** (optional): `Beer Game iOS`

   **App Store ID** (optional): Leave blank (only needed if app is published)

3. Click **"Register app"**

### Step 2.2: Download iOS Configuration File

1. Click **"Download GoogleService-Info.plist"**
2. Save the file to your computer
3. **IMPORTANT**: This file contains sensitive credentials
4. Click **"Next"**

### Step 2.3: Add Config File to iOS Project

**Using Terminal**:
```bash
# Navigate to project root
cd /home/trevor/Projects/The_Beer_Game

# Copy the downloaded file to iOS directory
cp ~/Downloads/GoogleService-Info.plist mobile/ios/

# Verify it's there
ls -la mobile/ios/GoogleService-Info.plist
```

**Using File Manager**:
1. Locate downloaded `GoogleService-Info.plist`
2. Move to: `/home/trevor/Projects/The_Beer_Game/mobile/ios/`
3. Verify the file is in the correct location

### Step 2.4: Firebase SDK Setup (Skip - Already Done)

The Firebase SDK is already integrated in the mobile app. Click **"Next"** through these steps.

### Step 2.5: Complete iOS Setup

Click **"Continue to console"**

---

## Part 3: Configure APNs (Apple Push Notification Service) (45-60 minutes)

### Step 3.1: Generate APNs Authentication Key

⚠️ **REQUIRES**: Apple Developer Account ($99/year)

1. Go to https://developer.apple.com
2. Sign in with your Apple ID
3. Navigate to: **Certificates, Identifiers & Profiles**
4. Click **"Keys"** in the sidebar

5. Create new key:
   - Click the **"+"** button
   - **Key Name**: `Beer Game APNs Key`
   - Check **"Apple Push Notifications service (APNs)"**
   - Click **"Continue"**

6. Review and confirm:
   - Click **"Register"**

7. Download the key:
   - Click **"Download"**
   - File format: `AuthKey_XXXXXXXXXX.p8`
   - ⚠️ **IMPORTANT**: You can only download this once!
   - Save to a secure location
   - Note the **Key ID** (10-character string)
   - Note your **Team ID** (found in top-right of Apple Developer portal)

### Step 3.2: Upload APNs Key to Firebase

1. Return to Firebase Console
2. Go to: **Project Settings** (⚙️ icon) → **Cloud Messaging** tab
3. Scroll to **"Apple app configuration"** section

4. Upload APNs Authentication Key:
   - Click **"Upload"** under APNs Authentication Key
   - Select your downloaded `.p8` file
   - Enter **Key ID** (from Step 3.1)
   - Enter **Team ID** (from Step 3.1)
   - Click **"Upload"**

5. Verify:
   - You should see "APNs Authentication Key" with a green checkmark
   - Status: **"Configured"**

### Step 3.3: Register App ID with Push Notifications

1. Go to https://developer.apple.com
2. Navigate to: **Certificates, Identifiers & Profiles** → **Identifiers**
3. Find or create App ID:
   - **Bundle ID**: `com.autonomy.app`
   - If it doesn't exist, click **"+"** to create

4. Enable Push Notifications:
   - Select the App ID
   - Under **Capabilities**, check **"Push Notifications"**
   - Click **"Save"**

---

## Part 4: Register Android App (15 minutes)

### Step 4.1: Add Android App to Firebase

1. In Firebase Console, click the **Android icon** (⊕ Android)
2. Fill in Android app details:

   **Android package name**: `com.autonomy.app`
   - ⚠️ **CRITICAL**: This must match exactly
   - Check your Android app's package name in: `mobile/android/app/build.gradle`
   - Look for: `applicationId "com.autonomy.app"`

   **App nickname** (optional): `Beer Game Android`

   **Debug signing certificate SHA-1** (optional): Leave blank for now
   - Only needed for Google Sign-In (not used in this app)

3. Click **"Register app"**

### Step 4.2: Download Android Configuration File

1. Click **"Download google-services.json"**
2. Save the file to your computer
3. **IMPORTANT**: This file contains sensitive credentials
4. Click **"Next"**

### Step 4.3: Add Config File to Android Project

**Using Terminal**:
```bash
# Navigate to project root
cd /home/trevor/Projects/The_Beer_Game

# Copy the downloaded file to Android directory
cp ~/Downloads/google-services.json mobile/android/app/

# Verify it's there
ls -la mobile/android/app/google-services.json
```

**Using File Manager**:
1. Locate downloaded `google-services.json`
2. Move to: `/home/trevor/Projects/The_Beer_Game/mobile/android/app/`
3. Verify the file is in the correct location

### Step 4.4: Firebase SDK Setup (Skip - Already Done)

The Firebase SDK is already integrated. Click **"Next"** through these steps.

### Step 4.5: Complete Android Setup

Click **"Continue to console"**

---

## Part 5: Backend Service Account Setup (30 minutes)

### Step 5.1: Create Service Account

1. In Firebase Console, go to: **Project Settings** (⚙️ icon)
2. Click **"Service accounts"** tab
3. Click **"Generate new private key"**

4. Confirmation dialog:
   - Warning: "This key provides full access to your project"
   - Click **"Generate key"**

5. Download JSON file:
   - File format: `beer-game-mobile-xxxxx-firebase-adminsdk-xxxxx-xxxxxxxxxx.json`
   - ⚠️ **CRITICAL**: This is a sensitive credential file
   - Save to a secure location

### Step 5.2: Rename and Move Service Account File

**Using Terminal**:
```bash
# Navigate to backend directory
cd /home/trevor/Projects/The_Beer_Game/backend

# Copy the downloaded file and rename it
cp ~/Downloads/beer-game-mobile-*-firebase-adminsdk-*.json firebase-credentials.json

# Verify it's there
ls -la firebase-credentials.json

# Set proper permissions (important for security)
chmod 600 firebase-credentials.json
```

**File Location**: `/home/trevor/Projects/The_Beer_Game/backend/firebase-credentials.json`

### Step 5.3: Add to .gitignore

⚠️ **CRITICAL SECURITY STEP**

1. Open `.gitignore` in the backend directory:
```bash
cd /home/trevor/Projects/The_Beer_Game/backend
nano .gitignore
# or use your preferred editor
```

2. Add this line:
```
firebase-credentials.json
```

3. Save and close

4. Verify it won't be committed:
```bash
git status
# firebase-credentials.json should NOT appear in the list
```

### Step 5.4: Verify Backend Integration

The backend service is already configured to use this file. Verify:

```bash
cd /home/trevor/Projects/The_Beer_Game/backend

# Check if file exists
ls -la firebase-credentials.json

# Restart backend to load credentials
cd ..
docker compose restart backend

# Check logs for Firebase initialization
docker compose logs backend | grep -i firebase
```

Expected output:
```
INFO: Firebase Admin SDK initialized successfully
```

or (if file not found):
```
WARNING: Failed to initialize Firebase: [Errno 2] No such file or directory: 'firebase-credentials.json'
```

---

## Part 6: Install Firebase Dependencies (10 minutes)

### Step 6.1: Install Firebase Admin SDK (Backend)

```bash
cd /home/trevor/Projects/The_Beer_Game/backend

# Install Firebase Admin SDK
pip install firebase-admin>=6.4.0

# Verify installation
pip show firebase-admin
```

Expected output:
```
Name: firebase-admin
Version: 6.4.0
...
```

### Step 6.2: Restart Backend

```bash
cd /home/trevor/Projects/The_Beer_Game
docker compose restart backend

# Wait for backend to start (about 10 seconds)
sleep 10

# Check health
curl http://localhost:8000/api/health
```

Expected output:
```json
{"status":"ok","time":"2026-01-16T..."}
```

---

## Part 7: Testing Notification Delivery (30 minutes)

### Step 7.1: Prepare Test Environment

**Requirements**:
- Physical iOS device (iPhone 12+ with iOS 16+)
- Physical Android device (Pixel 6+ with Android API 30+)
- Both devices connected to the internet
- Beer Game mobile app installed on both devices

⚠️ **IMPORTANT**: Push notifications do NOT work on simulators/emulators. You MUST use physical devices.

### Step 7.2: Get User Authentication Token

1. Open Beer Game mobile app on your device
2. Log in with test account:
   - Email: `systemadmin@autonomy.ai`
   - Password: `Autonomy@2025`

3. **Option A: Use App Debug Mode**
   - If the app has debug mode, it may display the JWT token
   - Copy the token

4. **Option B: Extract from Network Traffic**
   - Use Chrome DevTools or similar
   - Find the Authorization header from any API request
   - Format: `Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...`
   - Copy everything after "Bearer "

### Step 7.3: Register Device Token (iOS)

The mobile app should automatically register the FCM token when it launches. Verify:

**Using Mobile App**:
1. Open the app
2. Go to Settings/Profile
3. Navigate to Notification Settings
4. You should see: "Notifications: Enabled"

**Using API (Manual Verification)**:
```bash
# Check notification status
curl -X GET http://localhost:8000/api/v1/notifications/status \
  -H "Authorization: Bearer YOUR_JWT_TOKEN_HERE"
```

Expected response:
```json
{
  "user_id": 1,
  "notifications_enabled": true,
  "active_tokens": 1,
  "platforms": ["ios"],
  "preferences_configured": true,
  "firebase_available": true
}
```

### Step 7.4: Send Test Notification (iOS)

**Using Mobile App**:
1. In the app, go to Settings → Notifications
2. Tap "Send Test Notification" button
3. You should receive a notification within 5 seconds

**Using API (Manual Test)**:
```bash
# Send test notification
curl -X POST http://localhost:8000/api/v1/notifications/test \
  -H "Authorization: Bearer YOUR_JWT_TOKEN_HERE" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Test Notification",
    "body": "This is a test from The Beer Game"
  }'
```

Expected response:
```json
{
  "success": true,
  "message": "Test notification sent",
  "sent_count": 1,
  "total_tokens": 1,
  "results": [
    {
      "token_id": 1,
      "platform": "ios",
      "status": "sent",
      "message_id": "projects/beer-game-mobile/messages/..."
    }
  ]
}
```

**Verify on Device**:
- Within 5 seconds, you should see a notification
- Title: "Test Notification"
- Body: "This is a test from The Beer Game"
- Sound: Default notification sound
- Badge: App icon should show a badge

### Step 7.5: Repeat for Android

Follow the same steps (7.3 and 7.4) using an Android device.

### Step 7.6: Test Notification Types

Test all notification types to ensure they work:

**Game Started**:
1. Create a new game in the web app
2. Start the game
3. Players should receive "Game Started" notification

**Your Turn**:
1. In an active game, wait for your turn
2. You should receive "Your Turn!" notification
3. Tap the notification → app should open to game screen

**Game Completed**:
1. Complete a game
2. All players should receive "Game Completed" notification

**Team Message**:
1. Send a message in team chat
2. Team members should receive notification

### Step 7.7: Test Quiet Hours

1. In mobile app, go to Settings → Notifications
2. Enable "Quiet Hours"
3. Set hours: `22:00` to `08:00`
4. Set device time to 23:00 (within quiet hours)
5. Send test notification
6. Verify: Notification is blocked and logged but not delivered

7. Set device time to 12:00 (outside quiet hours)
8. Send test notification
9. Verify: Notification is delivered

---

## Part 8: Troubleshooting

### Issue: "Firebase Admin SDK initialization failed"

**Symptoms**:
- Backend logs show: "Failed to initialize Firebase"
- Notifications not sending

**Solutions**:
1. Check file location:
   ```bash
   ls -la /home/trevor/Projects/The_Beer_Game/backend/firebase-credentials.json
   ```

2. Verify file permissions:
   ```bash
   chmod 600 /home/trevor/Projects/The_Beer_Game/backend/firebase-credentials.json
   ```

3. Check file contents (first few lines):
   ```bash
   head -5 /home/trevor/Projects/The_Beer_Game/backend/firebase-credentials.json
   ```
   Should look like:
   ```json
   {
     "type": "service_account",
     "project_id": "beer-game-mobile-xxxxx",
     "private_key_id": "...",
     "private_key": "-----BEGIN PRIVATE KEY-----\n..."
   ```

4. Restart backend:
   ```bash
   docker compose restart backend
   ```

### Issue: "Invalid APNs credentials" (iOS)

**Symptoms**:
- iOS notifications not delivering
- Firebase Console shows "APNs error"

**Solutions**:
1. Verify APNs key is uploaded:
   - Firebase Console → Project Settings → Cloud Messaging
   - Check "APNs Authentication Key" status

2. Verify Key ID and Team ID are correct:
   - Re-check in Apple Developer portal

3. Re-upload APNs key if needed

### Issue: "Token registration failed"

**Symptoms**:
- Mobile app shows "Failed to register for notifications"
- API returns 500 error

**Solutions**:
1. Check mobile app has correct config files:
   ```bash
   # iOS
   ls -la mobile/ios/GoogleService-Info.plist

   # Android
   ls -la mobile/android/app/google-services.json
   ```

2. Rebuild mobile app:
   ```bash
   cd mobile

   # iOS
   cd ios && pod install && cd ..
   npx react-native run-ios

   # Android
   npx react-native run-android
   ```

3. Check device has internet connection

4. Verify Bundle ID / Package Name matches exactly

### Issue: "Notifications not appearing on device"

**Symptoms**:
- API returns success
- No notification appears on device

**Solutions**:
1. Check device notification settings:
   - iOS: Settings → Notifications → Beer Game → Allow Notifications (ON)
   - Android: Settings → Apps → Beer Game → Notifications (ON)

2. Verify app is not in Do Not Disturb mode

3. Check battery optimization settings (Android):
   - Settings → Battery → Battery Optimization → Beer Game → Don't optimize

4. Ensure using physical device (not simulator)

5. Check Firebase Console for delivery errors:
   - Cloud Messaging → Reports

### Issue: "Rate limit exceeded"

**Symptoms**:
- API returns: "Too many requests"
- Firebase Console shows quota exceeded

**Solutions**:
1. Check Firebase quota:
   - Firebase Console → Usage and billing

2. Implement client-side rate limiting

3. Upgrade Firebase plan if needed (free tier: 10,000 notifications/month)

---

## Part 9: Verification Checklist

Use this checklist to verify everything is working:

### Backend
- [ ] `firebase-credentials.json` exists in backend directory
- [ ] File is in `.gitignore`
- [ ] Backend starts without Firebase errors
- [ ] `firebase-admin` package installed
- [ ] Health check returns `{"status":"ok"}`

### iOS
- [ ] `GoogleService-Info.plist` in `mobile/ios/`
- [ ] Bundle ID matches: `com.autonomy.app`
- [ ] APNs key uploaded to Firebase
- [ ] APNs status: "Configured" in Firebase Console
- [ ] Test notification received on physical device

### Android
- [ ] `google-services.json` in `mobile/android/app/`
- [ ] Package name matches: `com.autonomy.app`
- [ ] Test notification received on physical device

### API Endpoints
- [ ] `POST /api/v1/notifications/register` returns 200
- [ ] `GET /api/v1/notifications/status` shows Firebase available
- [ ] `POST /api/v1/notifications/test` sends notification successfully
- [ ] `GET /api/v1/notifications/tokens` lists device tokens

### Notification Types
- [ ] Test notification works
- [ ] Game started notification works
- [ ] Your turn notification works
- [ ] Game completed notification works
- [ ] Team message notification works

### Preferences
- [ ] Can get preferences via API
- [ ] Can update preferences via API
- [ ] Quiet hours blocks notifications during configured times
- [ ] Notifications deliver outside quiet hours

---

## Part 10: Security Best Practices

### Credential Management

1. **Never commit credentials to Git**:
   ```bash
   # Verify .gitignore
   grep -r "firebase-credentials.json" .gitignore
   grep -r "GoogleService-Info.plist" .gitignore
   grep -r "google-services.json" .gitignore
   ```

2. **Secure file permissions**:
   ```bash
   chmod 600 backend/firebase-credentials.json
   ```

3. **Use environment variables in production**:
   ```bash
   # Instead of file, use base64-encoded credential
   export FIREBASE_CREDENTIALS_BASE64="$(cat firebase-credentials.json | base64)"
   ```

4. **Rotate credentials regularly**:
   - Generate new service account key every 90 days
   - Revoke old keys in Firebase Console

### Network Security

1. **Use HTTPS in production**:
   - Never send credentials over HTTP
   - Use SSL/TLS for all API communication

2. **Implement rate limiting**:
   - Prevent abuse of notification endpoints
   - Use Firebase App Check for mobile apps

3. **Validate tokens**:
   - Always verify JWT tokens
   - Implement token refresh logic

---

## Summary

**Time Invested**: ~4-6 hours
**Result**: Firebase Cloud Messaging fully configured

**What You Accomplished**:
1. ✅ Created Firebase project
2. ✅ Registered iOS app with APNs
3. ✅ Registered Android app
4. ✅ Set up backend service account
5. ✅ Tested notification delivery
6. ✅ Verified all notification types work

**Next Step**: Task 3 - Mobile Testing & Polish (1 day)

---

## Need Help?

If you encounter issues:

1. **Check Firebase Console Logs**:
   - Cloud Messaging → Reports
   - Look for delivery errors

2. **Check Backend Logs**:
   ```bash
   docker compose logs backend | grep -i firebase
   docker compose logs backend | grep -i notification
   ```

3. **Check Mobile App Logs**:
   - iOS: Xcode → Console
   - Android: Android Studio → Logcat

4. **Firebase Documentation**:
   - https://firebase.google.com/docs/cloud-messaging
   - https://firebase.google.com/docs/admin/setup

5. **Community Support**:
   - Stack Overflow: `[firebase-cloud-messaging]` tag
   - Firebase Community: https://firebase.google.com/community

---

**Date**: 2026-01-16
**Status**: Ready for Implementation
**Estimated Completion**: 4-6 hours
