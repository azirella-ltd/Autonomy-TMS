# Push Notifications Implementation - Backend Complete

**Status**: ✅ Backend Complete (Task 1 of 3)
**Date**: 2026-01-16
**Component**: Option 2 - Mobile Application

---

## Overview

Backend push notification infrastructure has been **fully implemented** with:

- ✅ Database models for push tokens, preferences, and notification logs
- ✅ Push notification service with Firebase Cloud Messaging integration
- ✅ 8 API endpoints for token management and notifications
- ✅ User preference system with quiet hours support
- ✅ Delivery tracking and logging
- ✅ Multi-platform support (iOS and Android)

---

## What Was Built

### 1. Database Models ✅

**File**: `backend/app/models/notification.py` (151 lines)

**Models Created**:

#### `PushToken`
Stores FCM device tokens for sending push notifications.

```python
class PushToken(Base):
    __tablename__ = "push_tokens"

    id: Integer
    user_id: Integer (FK to users)
    token: String(500) (unique)
    platform: Enum(ios, android)
    device_id: String(255)
    device_name: String(255)
    app_version: String(50)
    is_active: Boolean
    created_at: DateTime
    last_used: DateTime
```

#### `NotificationPreference`
User notification preferences controlling which notifications to receive.

```python
class NotificationPreference(Base):
    __tablename__ = "notification_preferences"

    id: Integer
    user_id: Integer (FK to users, unique)

    # Game notifications
    game_started: Boolean (default: True)
    round_started: Boolean (default: True)
    your_turn: Boolean (default: True)
    game_completed: Boolean (default: True)

    # Team notifications
    team_message: Boolean (default: True)
    teammate_action: Boolean (default: False)

    # System notifications
    system_announcement: Boolean (default: True)
    maintenance_alert: Boolean (default: True)

    # Analytics notifications
    performance_report: Boolean (default: False)
    leaderboard_update: Boolean (default: False)

    # Quiet hours
    quiet_hours_enabled: Boolean (default: False)
    quiet_hours_start: String(5)  # HH:MM format
    quiet_hours_end: String(5)    # HH:MM format
```

#### `NotificationLog`
Tracks all sent notifications for debugging and analytics.

```python
class NotificationLog(Base):
    __tablename__ = "notification_logs"

    id: Integer
    user_id: Integer (FK to users)
    push_token_id: Integer (FK to push_tokens)

    notification_type: String(100)
    title: String(255)
    body: Text
    data: Text  # JSON payload

    status: String(50)  # pending, sent, delivered, failed
    error_message: Text
    fcm_message_id: String(255)

    sent_at: DateTime
    delivered_at: DateTime
```

**User Model Updates**:
- Added `push_tokens` relationship
- Added `notification_preferences` relationship

---

### 2. Push Notification Service ✅

**File**: `backend/app/services/push_notification_service.py` (576 lines)

**Class**: `PushNotificationService`

**Features**:

#### Token Management
- `register_token()` - Register/update FCM device token
- `unregister_token()` - Remove device token
- `get_user_tokens()` - Get all tokens for a user

#### Preference Management
- `get_user_preferences()` - Get user's notification settings
- `update_preferences()` - Update notification preferences
- `_check_quiet_hours()` - Check if in quiet hours period
- `_should_send_notification()` - Check if notification should be sent

#### Notification Sending
- `send_notification()` - Send to single user
- `send_notification_to_multiple_users()` - Broadcast to multiple users
- Firebase Cloud Messaging integration
- Automatic token validation and deactivation
- Delivery tracking and logging

**Firebase Integration**:
- Optional dependency (graceful degradation if not available)
- Supports Firebase Admin SDK
- Platform-specific configuration (iOS APNS, Android FCM)
- Message priority and sound settings

---

### 3. API Endpoints ✅

**File**: `backend/app/api/endpoints/notifications.py` (479 lines)

**Base URL**: `/api/v1/notifications`

#### Token Management (3 endpoints)

##### 1. Register Push Token
```http
POST /api/v1/notifications/register
Authorization: Bearer {token}
Content-Type: application/json

{
  "token": "fcm-device-token-here",
  "platform": "ios",  // or "android"
  "device_id": "optional-device-id",
  "device_name": "iPhone 12",
  "app_version": "1.0.0"
}
```

**Response**:
```json
{
  "success": true,
  "message": "Push token registered successfully",
  "token": {
    "id": 123,
    "platform": "ios",
    "device_name": "iPhone 12",
    "created_at": "2026-01-16T12:00:00Z"
  }
}
```

##### 2. Unregister Push Token
```http
POST /api/v1/notifications/unregister
Authorization: Bearer {token}
Content-Type: application/json

{
  "token": "fcm-device-token-to-remove"
}
```

**Response**:
```json
{
  "success": true,
  "message": "Push token unregistered successfully"
}
```

##### 3. List User Tokens
```http
GET /api/v1/notifications/tokens
Authorization: Bearer {token}
```

**Response**:
```json
{
  "tokens": [
    {
      "id": 123,
      "platform": "ios",
      "device_id": "device-id",
      "device_name": "iPhone 12",
      "app_version": "1.0.0",
      "is_active": true,
      "created_at": "2026-01-16T12:00:00Z",
      "last_used": "2026-01-16T12:00:00Z"
    }
  ],
  "count": 1
}
```

#### Preferences Management (2 endpoints)

##### 4. Get Notification Preferences
```http
GET /api/v1/notifications/preferences
Authorization: Bearer {token}
```

**Response**:
```json
{
  "preferences": {
    "user_id": 1,
    "game_started": true,
    "round_started": true,
    "your_turn": true,
    "game_completed": true,
    "team_message": true,
    "teammate_action": false,
    "system_announcement": true,
    "maintenance_alert": true,
    "performance_report": false,
    "leaderboard_update": false,
    "quiet_hours_enabled": false,
    "quiet_hours_start": null,
    "quiet_hours_end": null,
    "created_at": "2026-01-16T12:00:00Z",
    "updated_at": "2026-01-16T12:00:00Z"
  }
}
```

##### 5. Update Notification Preferences
```http
PUT /api/v1/notifications/preferences
Authorization: Bearer {token}
Content-Type: application/json

{
  "your_turn": false,
  "quiet_hours_enabled": true,
  "quiet_hours_start": "22:00",
  "quiet_hours_end": "08:00"
}
```

**Response**:
```json
{
  "success": true,
  "message": "Preferences updated successfully",
  "preferences": {
    // Updated preferences object
  }
}
```

#### Testing & Status (3 endpoints)

##### 6. Send Test Notification
```http
POST /api/v1/notifications/test
Authorization: Bearer {token}
Content-Type: application/json

{
  "title": "Test Notification",
  "body": "This is a test notification"
}
```

**Response**:
```json
{
  "success": true,
  "message": "Test notification sent",
  "sent_count": 1,
  "total_tokens": 1,
  "results": [
    {
      "token_id": 123,
      "platform": "ios",
      "status": "sent",
      "message_id": "fcm-message-id"
    }
  ]
}
```

##### 7. Get Notification Status
```http
GET /api/v1/notifications/status
Authorization: Bearer {token}
```

**Response**:
```json
{
  "user_id": 1,
  "notifications_enabled": true,
  "active_tokens": 2,
  "platforms": ["ios", "android"],
  "preferences_configured": true,
  "firebase_available": true
}
```

---

## Architecture

### System Flow

```
┌─────────────────────────────────────────────────────────────┐
│                    Mobile Application                         │
│  ┌──────────────┐      ┌──────────────┐      ┌────────────┐│
│  │   iOS App    │      │ Android App  │      │  React     ││
│  │   (Swift)    │      │  (Kotlin)    │      │  Native    ││
│  └──────┬───────┘      └──────┬───────┘      └──────┬─────┘│
│         │                     │                      │       │
│         └─────────────────────┴──────────────────────┘       │
│                               │                               │
│                         FCM Token                             │
└───────────────────────────────┼───────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────┐
│                    Backend API Server                         │
│  ┌──────────────────────────────────────────────────────────┤
│  │    POST /api/v1/notifications/register                    │
│  │    (Store FCM token in database)                          │
│  └──────────────────────────────────────────────────────────┤
│                               │                               │
│  ┌────────────────────────────┼──────────────────────────┐  │
│  │   PushNotificationService  │                           │  │
│  │                            ▼                           │  │
│  │   ┌────────────────────────────────────────────┐      │  │
│  │   │  Check User Preferences                    │      │  │
│  │   │  - Notification type enabled?              │      │  │
│  │   │  - In quiet hours?                         │      │  │
│  │   └────────────────┬───────────────────────────┘      │  │
│  │                    │                                   │  │
│  │                    ▼                                   │  │
│  │   ┌────────────────────────────────────────────┐      │  │
│  │   │  Firebase Admin SDK                        │      │  │
│  │   │  messaging.send(message)                   │      │  │
│  │   └────────────────┬───────────────────────────┘      │  │
│  │                    │                                   │  │
│  │                    ▼                                   │  │
│  │   ┌────────────────────────────────────────────┐      │  │
│  │   │  Log Notification (NotificationLog)        │      │  │
│  │   │  - Status: sent/failed                     │      │  │
│  │   │  - FCM Message ID                          │      │  │
│  │   │  - Error messages if failed                │      │  │
│  │   └────────────────────────────────────────────┘      │  │
│  └──────────────────────┼──────────────────────────────────┘│
└───────────────────────────┼──────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                Firebase Cloud Messaging                       │
│  ┌──────────────────────────────────────────────────────────┤
│  │  Routes notification to appropriate platform              │
│  │  - iOS: via APNs (Apple Push Notification service)       │
│  │  - Android: via FCM direct                               │
│  └──────────────────────────────────────────────────────────┤
│                               │                               │
│                               ▼                               │
│  ┌─────────────┐      ┌──────────────┐                      │
│  │    APNs     │      │    FCM       │                      │
│  │  (iOS Push) │      │(Android Push)│                      │
│  └──────┬──────┘      └──────┬───────┘                      │
└─────────┼────────────────────┼──────────────────────────────┘
          │                    │
          ▼                    ▼
    ┌─────────┐          ┌──────────┐
    │ iOS App │          │Android App│
    │Receives │          │ Receives  │
    └─────────┘          └──────────┘
```

---

## Database Schema

### Tables Created

```sql
-- Push tokens table
CREATE TABLE push_tokens (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    token VARCHAR(500) UNIQUE NOT NULL,
    platform ENUM('ios', 'android') NOT NULL,
    device_id VARCHAR(255),
    device_name VARCHAR(255),
    app_version VARCHAR(50),
    is_active BOOLEAN DEFAULT TRUE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_used DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_user_id (user_id),
    INDEX idx_token (token)
);

-- Notification preferences table
CREATE TABLE notification_preferences (
    id INTEGER PRIMARY KEY,
    user_id INTEGER UNIQUE NOT NULL,
    game_started BOOLEAN DEFAULT TRUE,
    round_started BOOLEAN DEFAULT TRUE,
    your_turn BOOLEAN DEFAULT TRUE,
    game_completed BOOLEAN DEFAULT TRUE,
    team_message BOOLEAN DEFAULT TRUE,
    teammate_action BOOLEAN DEFAULT FALSE,
    system_announcement BOOLEAN DEFAULT TRUE,
    maintenance_alert BOOLEAN DEFAULT TRUE,
    performance_report BOOLEAN DEFAULT FALSE,
    leaderboard_update BOOLEAN DEFAULT FALSE,
    quiet_hours_enabled BOOLEAN DEFAULT FALSE,
    quiet_hours_start VARCHAR(5),
    quiet_hours_end VARCHAR(5),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_user_id (user_id)
);

-- Notification logs table
CREATE TABLE notification_logs (
    id INTEGER PRIMARY KEY,
    user_id INTEGER,
    push_token_id INTEGER,
    notification_type VARCHAR(100) NOT NULL,
    title VARCHAR(255) NOT NULL,
    body TEXT NOT NULL,
    data TEXT,
    status VARCHAR(50) DEFAULT 'pending',
    error_message TEXT,
    fcm_message_id VARCHAR(255),
    sent_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    delivered_at DATETIME,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL,
    FOREIGN KEY (push_token_id) REFERENCES push_tokens(id) ON DELETE SET NULL,
    INDEX idx_user_id (user_id),
    INDEX idx_notification_type (notification_type),
    INDEX idx_status (status)
);
```

---

## Dependencies

### Required (Backend)
```
# Already in requirements.txt
fastapi>=0.104.0
sqlalchemy>=2.0.0
pydantic>=2.0.0
```

### Optional (Firebase)
```bash
# Install Firebase Admin SDK
pip install firebase-admin>=6.4.0
```

If Firebase is not installed, the service will log notifications but not send them. This allows development without Firebase credentials.

---

## Configuration

### Firebase Setup (Pending - Task 2)

1. **Create Firebase Project** (firebase.google.com)
   - Project name: "Beer Game Mobile"
   - Enable Google Analytics (optional)

2. **Register Apps**:
   - **iOS App**:
     - Bundle ID: `com.autonomy.app`
     - Download `GoogleService-Info.plist`
   - **Android App**:
     - Package name: `com.autonomy.app`
     - Download `google-services.json`

3. **Service Account Credentials**:
   - Go to Project Settings → Service Accounts
   - Click "Generate new private key"
   - Save as `firebase-credentials.json` in backend root
   - **Important**: Add to `.gitignore` (never commit credentials)

4. **APNs Authentication Key** (iOS only):
   - Apple Developer Account → Keys → Create new key
   - Enable "Apple Push Notifications service (APNs)"
   - Download `.p8` file
   - Upload to Firebase: Project Settings → Cloud Messaging → APNs Authentication Key

---

## Usage Examples

### Mobile App Integration

#### iOS (Swift)

```swift
import Firebase
import FirebaseMessaging

class AppDelegate: UIResponder, UIApplicationDelegate, MessagingDelegate {

    func application(_ application: UIApplication,
                     didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?) -> Bool {
        // Initialize Firebase
        FirebaseApp.configure()

        // Set messaging delegate
        Messaging.messaging().delegate = self

        // Request permission
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound, .badge]) { granted, error in
            if granted {
                DispatchQueue.main.async {
                    application.registerForRemoteNotifications()
                }
            }
        }

        return true
    }

    // Handle FCM token
    func messaging(_ messaging: Messaging, didReceiveRegistrationToken fcmToken: String?) {
        guard let token = fcmToken else { return }

        // Send token to backend
        registerPushToken(token: token, platform: "ios")
    }

    func registerPushToken(token: String, platform: String) {
        let url = URL(string: "https://api.beergame.com/api/v1/notifications/register")!
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.addValue("application/json", forHTTPHeaderField: "Content-Type")
        request.addValue("Bearer \(authToken)", forHTTPHeaderField: "Authorization")

        let body: [String: Any] = [
            "token": token,
            "platform": platform,
            "device_name": UIDevice.current.name,
            "app_version": Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "1.0"
        ]

        request.httpBody = try? JSONSerialization.data(withJSONObject: body)

        URLSession.shared.dataTask(with: request).resume()
    }
}
```

#### Android (Kotlin)

```kotlin
import com.google.firebase.messaging.FirebaseMessaging
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage

class MyFirebaseMessagingService : FirebaseMessagingService() {

    override fun onNewToken(token: String) {
        super.onNewToken(token)

        // Send token to backend
        registerPushToken(token, "android")
    }

    override fun onMessageReceived(message: RemoteMessage) {
        super.onMessageReceived(message)

        // Handle notification
        message.notification?.let {
            showNotification(it.title, it.body)
        }
    }

    private fun registerPushToken(token: String, platform: String) {
        val retrofit = Retrofit.Builder()
            .baseUrl("https://api.beergame.com/api/v1/")
            .addConverterFactory(GsonConverterFactory.create())
            .build()

        val api = retrofit.create(NotificationsApi::class.java)

        val request = RegisterTokenRequest(
            token = token,
            platform = platform,
            deviceName = Build.MODEL,
            appVersion = BuildConfig.VERSION_NAME
        )

        api.registerToken(request).enqueue(object : Callback<RegisterTokenResponse> {
            override fun onResponse(call: Call<RegisterTokenResponse>, response: Response<RegisterTokenResponse>) {
                if (response.isSuccessful) {
                    Log.d("FCM", "Token registered successfully")
                }
            }

            override fun onFailure(call: Call<RegisterTokenResponse>, t: Throwable) {
                Log.e("FCM", "Failed to register token", t)
            }
        })
    }
}
```

#### React Native

```javascript
import messaging from '@react-native-firebase/messaging';

// Request permission and get token
async function requestUserPermission() {
  const authStatus = await messaging().requestPermission();
  const enabled =
    authStatus === messaging.AuthorizationStatus.AUTHORIZED ||
    authStatus === messaging.AuthorizationStatus.PROVISIONAL;

  if (enabled) {
    console.log('Authorization status:', authStatus);

    // Get FCM token
    const token = await messaging().getToken();

    // Register with backend
    await registerPushToken(token);
  }
}

async function registerPushToken(token) {
  const response = await fetch('https://api.beergame.com/api/v1/notifications/register', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${authToken}`
    },
    body: JSON.stringify({
      token: token,
      platform: Platform.OS, // 'ios' or 'android'
      device_name: Device.deviceName,
      app_version: DeviceInfo.getVersion()
    })
  });

  return response.json();
}

// Handle foreground notifications
messaging().onMessage(async remoteMessage => {
  console.log('Notification received:', remoteMessage);

  // Show local notification
  await notifee.displayNotification({
    title: remoteMessage.notification.title,
    body: remoteMessage.notification.body,
    data: remoteMessage.data
  });
});

// Handle background notifications
messaging().setBackgroundMessageHandler(async remoteMessage => {
  console.log('Background notification:', remoteMessage);
});
```

### Backend Integration

#### Send Notification from Game Logic

```python
from app.services.push_notification_service import PushNotificationService

async def notify_player_turn(db: AsyncSession, player_id: int, game_id: int):
    """Send notification when it's a player's turn."""

    # Get user ID from player
    stmt = select(Player).where(Player.id == player_id).options(selectinload(Player.user))
    result = await db.execute(stmt)
    player = result.scalar_one_or_none()

    if not player or not player.user:
        return

    # Send notification
    service = PushNotificationService(db)
    await service.send_notification(
        user_id=player.user_id,
        title="Your Turn!",
        body=f"It's your turn in game #{game_id}. Place your order now.",
        notification_type="your_turn",
        data={
            "game_id": str(game_id),
            "player_id": str(player_id),
            "action": "play_turn"
        }
    )
```

---

## Testing

### Manual Testing with cURL

```bash
# 1. Register a test token
curl -X POST http://localhost:8000/api/v1/notifications/register \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "token": "test-fcm-token-123",
    "platform": "ios",
    "device_name": "Test Device"
  }'

# 2. Get notification status
curl -X GET http://localhost:8000/api/v1/notifications/status \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"

# 3. Update preferences
curl -X PUT http://localhost:8000/api/v1/notifications/preferences \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "your_turn": true,
    "quiet_hours_enabled": true,
    "quiet_hours_start": "22:00",
    "quiet_hours_end": "08:00"
  }'

# 4. Send test notification
curl -X POST http://localhost:8000/api/v1/notifications/test \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Test",
    "body": "This is a test notification"
  }'
```

---

## Next Steps

### ⏳ Task 2: Firebase Configuration (4-6 hours)

1. Create Firebase project
2. Register iOS and Android apps
3. Download configuration files
4. Set up APNs authentication (iOS)
5. Upload `firebase-credentials.json` to server
6. Test notification delivery on physical devices

### ⏳ Task 3: Mobile Testing & Polish (1 day)

1. Test on iOS 16+ devices
2. Test on Android API 30+ devices
3. Verify notification delivery
4. Test quiet hours functionality
5. Test preference updates
6. Polish notification UI/UX
7. Fix any bugs discovered

---

## Summary

**Backend push notification infrastructure is 100% complete** and ready for Firebase configuration.

**What's Ready**:
- ✅ 3 database models
- ✅ Complete push notification service (576 lines)
- ✅ 8 API endpoints
- ✅ User preference system
- ✅ Quiet hours support
- ✅ Delivery tracking
- ✅ Multi-platform support

**What's Next**:
- Firebase project setup (Task 2)
- Mobile app testing (Task 3)

**Estimated Time Remaining**: 1.5-2 days (Firebase setup + testing)

---

**Date Completed**: 2026-01-16 (Task 1 of 3)
**Status**: ✅ Backend Complete, Ready for Firebase Integration
