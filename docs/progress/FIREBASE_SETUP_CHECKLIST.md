# Firebase Setup - Quick Checklist

**Status**: Ready to start
**Estimated Time**: 4-6 hours
**Stage**: Configuration (no coding)

---

## 📋 Prerequisites Checklist

Before you begin, verify you have:

- [ ] Google Account (for Firebase Console)
- [ ] Apple Developer Account ($99/year) - https://developer.apple.com
- [ ] Physical iPhone (iOS 16 or later)
- [ ] Physical Android device (Android API 30/Android 11 or later)
- [ ] Mac computer (required for iOS development)
- [ ] Xcode installed (for iOS)
- [ ] Android Studio installed (for Android)

---

## 🚀 Step-by-Step Process

### Part 1: Firebase Console Setup (30 minutes)

#### 1.1 Create Firebase Project
- [ ] Go to https://console.firebase.google.com/
- [ ] Click "Add project" or "Create a project"
- [ ] Project name: `Beer Game Mobile`
- [ ] Disable Google Analytics (optional for testing)
- [ ] Click "Create project"
- [ ] Wait for project creation (1-2 minutes)

#### 1.2 Enable Cloud Messaging
- [ ] In Firebase Console, click on your project
- [ ] Navigate to: Build → Cloud Messaging
- [ ] Note: Cloud Messaging is enabled by default for new projects

---

### Part 2: iOS Configuration (2-3 hours)

#### 2.1 Register iOS App in Firebase
- [ ] In Firebase Console: Project Overview → Add app → iOS
- [ ] Apple bundle ID: `com.autonomy.app`
- [ ] App nickname: `Beer Game iOS`
- [ ] Click "Register app"
- [ ] **Download** `GoogleService-Info.plist`
- [ ] Save to: `mobile/ios/GoogleService-Info.plist`
- [ ] Click "Next" through the setup steps

#### 2.2 Generate APNs Authentication Key (Apple Developer Portal)
- [ ] Go to https://developer.apple.com/account/
- [ ] Navigate to: Certificates, IDs & Profiles → Keys
- [ ] Click the "+" button to create a new key
- [ ] Key Name: `Beer Game APNs Key`
- [ ] Check: "Apple Push Notifications service (APNs)"
- [ ] Click "Continue" → "Register"
- [ ] **Download** the .p8 key file (SAVE THIS - you can only download once!)
- [ ] Note the Key ID (e.g., `ABC123DEFG`)
- [ ] Note your Team ID (top right of page, e.g., `XYZ456HIJK`)

#### 2.3 Upload APNs Key to Firebase
- [ ] Back in Firebase Console: Project Settings → Cloud Messaging → iOS app configuration
- [ ] Click "Upload" under APNs Authentication Key
- [ ] Upload your .p8 file
- [ ] Enter Key ID (from step 2.2)
- [ ] Enter Team ID (from step 2.2)
- [ ] Click "Upload"
- [ ] Verify: Status should show "APNs Authentication Key uploaded"

#### 2.4 Register App ID in Apple Developer Portal
- [ ] Go to https://developer.apple.com/account/
- [ ] Navigate to: Certificates, IDs & Profiles → Identifiers
- [ ] Click "+" to create new App ID
- [ ] Select: "App IDs" → Continue
- [ ] Description: `Beer Game`
- [ ] Bundle ID: Explicit → `com.autonomy.app`
- [ ] Capabilities: Check "Push Notifications"
- [ ] Click "Continue" → "Register"

#### 2.5 Create Provisioning Profile
- [ ] Navigate to: Certificates, IDs & Profiles → Profiles
- [ ] Click "+" to create new profile
- [ ] Select: "iOS App Development" → Continue
- [ ] Select App ID: `Beer Game (com.autonomy.app)`
- [ ] Select your development certificate
- [ ] Select your test devices
- [ ] Profile Name: `Beer Game Development`
- [ ] Click "Generate" → Download
- [ ] Double-click to install in Xcode

---

### Part 3: Android Configuration (30 minutes)

#### 3.1 Register Android App in Firebase
- [ ] In Firebase Console: Project Overview → Add app → Android
- [ ] Android package name: `com.autonomy.app`
- [ ] App nickname: `Beer Game Android`
- [ ] Leave SHA-1 blank for now (can add later)
- [ ] Click "Register app"
- [ ] **Download** `google-services.json`
- [ ] Save to: `mobile/android/app/google-services.json`
- [ ] Click "Next" through the setup steps

#### 3.2 Verify Android Configuration
- [ ] File location: `mobile/android/app/google-services.json`
- [ ] File should contain: `"project_id": "beer-game-mobile"`
- [ ] File should contain: `"package_name": "com.autonomy.app"`

---

### Part 4: Backend Service Account (30 minutes)

#### 4.1 Create Service Account
- [ ] In Firebase Console: Project Settings (gear icon)
- [ ] Navigate to: Service accounts tab
- [ ] Click "Generate new private key"
- [ ] Confirm: "Generate key"
- [ ] **Download** JSON file (e.g., `beer-game-mobile-abc123.json`)
- [ ] **Rename** to: `firebase-credentials.json`
- [ ] **Move** to: `backend/firebase-credentials.json`

#### 4.2 Secure the Credentials File
```bash
# Set proper permissions
chmod 600 backend/firebase-credentials.json

# Verify it's in .gitignore (should already be there)
grep firebase-credentials.json backend/.gitignore

# If not in .gitignore, add it:
echo "firebase-credentials.json" >> backend/.gitignore
```

- [ ] Permissions set to 600
- [ ] File is in .gitignore
- [ ] File exists at: `backend/firebase-credentials.json`

#### 4.3 Verify Backend Can Load Credentials
```bash
docker compose exec backend python -c "
import os
import json

creds_path = '/app/firebase-credentials.json'
if os.path.exists(creds_path):
    with open(creds_path) as f:
        creds = json.load(f)
    print('✓ Credentials file exists')
    print(f'✓ Project ID: {creds.get(\"project_id\")}')
    print(f'✓ Client email: {creds.get(\"client_email\")}')
else:
    print('✗ Credentials file not found at', creds_path)
"
```

- [ ] Credentials file loaded successfully
- [ ] Project ID matches your Firebase project
- [ ] Client email looks correct

---

### Part 5: Backend Configuration (15 minutes)

#### 5.1 Update Environment Variables (Optional)
```bash
# Edit backend/.env if needed
# These are optional - the service uses firebase-credentials.json by default

FIREBASE_PROJECT_ID=beer-game-mobile
FIREBASE_CREDENTIALS_PATH=/app/firebase-credentials.json
```

- [ ] Environment variables set (if needed)
- [ ] Backend will auto-detect firebase-credentials.json

#### 5.2 Restart Backend to Load Firebase
```bash
docker compose restart backend
sleep 10
docker compose ps backend
```

- [ ] Backend restarted successfully
- [ ] Status shows: Up (healthy)

#### 5.3 Check Backend Logs for Firebase
```bash
docker compose logs backend --tail 50 | grep -i firebase
```

Expected output:
- Should NOT see: "Firebase credentials not found"
- Should NOT see: "Firebase initialization failed"

- [ ] No Firebase errors in logs
- [ ] Backend started successfully

---

### Part 6: Test Notification Delivery (1 hour)

#### 6.1 Get FCM Token from Mobile App

**On iOS**:
```swift
// In your AppDelegate or main app file
import FirebaseMessaging

// Get token
Messaging.messaging().token { token, error in
    if let error = error {
        print("Error fetching FCM token: \(error)")
    } else if let token = token {
        print("FCM Token: \(token)")
        // Copy this token for testing
    }
}
```

**On Android**:
```kotlin
// In your MainActivity or Application class
import com.google.firebase.messaging.FirebaseMessaging

// Get token
FirebaseMessaging.getInstance().token.addOnCompleteListener { task ->
    if (task.isSuccessful) {
        val token = task.result
        Log.d("FCM", "Token: $token")
        // Copy this token for testing
    }
}
```

- [ ] iOS app installed on device
- [ ] Android app installed on device
- [ ] FCM token obtained from iOS
- [ ] FCM token obtained from Android

#### 6.2 Register Tokens via API

**Login first**:
```bash
# Get auth token
RESPONSE=$(curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "systemadmin@autonomy.ai",
    "password": "Autonomy@2025"
  }')

TOKEN=$(echo $RESPONSE | jq -r '.access_token')
echo "Token: $TOKEN"
```

**Register iOS token**:
```bash
curl -X POST http://localhost:8000/api/v1/notifications/register \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "token": "YOUR_IOS_FCM_TOKEN_HERE",
    "platform": "ios",
    "device_name": "iPhone 12",
    "app_version": "1.0.0"
  }'
```

**Register Android token**:
```bash
curl -X POST http://localhost:8000/api/v1/notifications/register \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "token": "YOUR_ANDROID_FCM_TOKEN_HERE",
    "platform": "android",
    "device_name": "Pixel 6",
    "app_version": "1.0.0"
  }'
```

- [ ] iOS token registered successfully
- [ ] Android token registered successfully

#### 6.3 Send Test Notifications

**Send to iOS**:
```bash
curl -X POST http://localhost:8000/api/v1/notifications/test \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Test iOS Notification",
    "body": "This is a test notification for iOS!"
  }'
```

**Send to Android**:
```bash
curl -X POST http://localhost:8000/api/v1/notifications/test \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Test Android Notification",
    "body": "This is a test notification for Android!"
  }'
```

- [ ] iOS device received notification
- [ ] Android device received notification
- [ ] Notifications appeared within 5 seconds
- [ ] Notification title and body are correct

#### 6.4 Verify Notification Logs
```bash
curl -X GET http://localhost:8000/api/v1/notifications/status \
  -H "Authorization: Bearer $TOKEN" | jq
```

Expected response:
```json
{
  "user_id": 1,
  "active_tokens": 2,
  "platforms": ["ios", "android"],
  "preferences": { ... },
  "recent_notifications": [ ... ]
}
```

- [ ] Status shows correct number of active tokens
- [ ] Both platforms listed
- [ ] Recent notifications appear in logs

---

### Part 7: Test Notification Types (30 minutes)

#### 7.1 Test Game Notifications
```bash
# Your Turn notification
curl -X POST http://localhost:8000/api/v1/notifications/test \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Your Turn!",
    "body": "It'\''s your turn in the Beer Game",
    "notification_type": "your_turn"
  }'
```

- [ ] "Your Turn" notification received

#### 7.2 Test Quiet Hours
```bash
# Set quiet hours (22:00 to 08:00)
curl -X PUT http://localhost:8000/api/v1/notifications/preferences \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "quiet_hours_enabled": true,
    "quiet_hours_start": "22:00",
    "quiet_hours_end": "08:00"
  }'

# Try sending notification during quiet hours
# (Adjust time based on your current time)
curl -X POST http://localhost:8000/api/v1/notifications/test \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Quiet Hours Test",
    "body": "Should be blocked if during quiet hours"
  }'
```

- [ ] Quiet hours configured
- [ ] Notifications blocked during quiet hours
- [ ] Notifications work outside quiet hours

---

## ✅ Verification Checklist

### Firebase Console
- [ ] Project created: "Beer Game Mobile"
- [ ] iOS app registered with Bundle ID: `com.autonomy.app`
- [ ] Android app registered with Package: `com.autonomy.app`
- [ ] APNs key uploaded and verified
- [ ] Service account created and downloaded

### File Locations
- [ ] `mobile/ios/GoogleService-Info.plist` exists
- [ ] `mobile/android/app/google-services.json` exists
- [ ] `backend/firebase-credentials.json` exists and has correct permissions (600)
- [ ] All credential files are in `.gitignore`

### Backend
- [ ] Backend restarted successfully
- [ ] No Firebase errors in logs
- [ ] API endpoints responding

### Mobile Apps
- [ ] iOS app builds and runs
- [ ] Android app builds and runs
- [ ] Both apps request notification permissions
- [ ] FCM tokens obtained from both platforms

### Notification Delivery
- [ ] Tokens registered via API
- [ ] Test notifications sent
- [ ] iOS receives notifications (< 5 seconds)
- [ ] Android receives notifications (< 5 seconds)
- [ ] Notification logs show successful delivery
- [ ] Quiet hours feature works

---

## 🐛 Troubleshooting

### Issue: iOS not receiving notifications

**Check APNs key**:
- [ ] Key uploaded to Firebase
- [ ] Key ID and Team ID are correct
- [ ] App Bundle ID matches Firebase registration
- [ ] Device has notification permissions enabled

**Check logs**:
```bash
docker compose logs backend | grep -i "ios\|apns"
```

### Issue: Android not receiving notifications

**Check google-services.json**:
- [ ] File location: `mobile/android/app/google-services.json`
- [ ] Package name matches: `com.autonomy.app`
- [ ] File is included in Android build

**Check logs**:
```bash
docker compose logs backend | grep -i "android\|fcm"
```

### Issue: Backend errors

**Check Firebase credentials**:
```bash
# Verify file exists and has correct permissions
ls -la backend/firebase-credentials.json

# Check content
docker compose exec backend cat /app/firebase-credentials.json | jq '.project_id'
```

**Restart backend**:
```bash
docker compose restart backend
docker compose logs backend --tail 100
```

---

## 📝 Notes

### Free Tier Limits
- **Cloud Messaging**: Unlimited
- **Notifications per day**: No hard limit on free tier
- **Concurrent connections**: Should be sufficient for testing

### Security Notes
- ✅ `firebase-credentials.json` must NEVER be committed to git
- ✅ All credential files should have restricted permissions (600)
- ✅ Use environment-specific credentials for production
- ✅ Rotate keys if accidentally exposed

### Next Steps
Once Firebase setup is complete:
- ✅ Move to [MOBILE_TESTING_GUIDE.md](MOBILE_TESTING_GUIDE.md)
- ✅ Run comprehensive test suite (70+ tests)
- ✅ Document results and sign off

---

## ⏱️ Time Tracking

- [ ] Part 1: Firebase Console (30 min) - Started: _____ Completed: _____
- [ ] Part 2: iOS Configuration (2-3 hours) - Started: _____ Completed: _____
- [ ] Part 3: Android Configuration (30 min) - Started: _____ Completed: _____
- [ ] Part 4: Backend Service Account (30 min) - Started: _____ Completed: _____
- [ ] Part 5: Backend Configuration (15 min) - Started: _____ Completed: _____
- [ ] Part 6: Test Delivery (1 hour) - Started: _____ Completed: _____
- [ ] Part 7: Test Types (30 min) - Started: _____ Completed: _____

**Total Estimated**: 4-6 hours
**Actual Time**: _____ hours

---

**Status**: Ready to start
**Next Step**: Part 1 - Create Firebase project at https://console.firebase.google.com/

Good luck! 🚀
