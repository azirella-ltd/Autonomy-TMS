# Firebase Setup - Quick Reference Card

**Status**: ✅ System Ready
**Time**: 4-6 hours
**URL**: https://console.firebase.google.com/

---

## 📝 Key Information

### Bundle IDs & Package Names
```
iOS Bundle ID:       com.autonomy.app
Android Package:     com.autonomy.app
Firebase Project:    Beer Game Mobile
```

### File Locations
```
iOS Config:          mobile/ios/GoogleService-Info.plist
Android Config:      mobile/android/app/google-services.json
Backend Credentials: backend/firebase-credentials.json
```

---

## 🚀 Quick Start (5 Minutes)

### 1. Create Firebase Project
- Go to: https://console.firebase.google.com/
- Click: "Add project"
- Name: `Beer Game Mobile`
- Disable Analytics: Yes (optional)
- Wait: ~2 minutes for creation

### 2. Add iOS App
- Click: iOS icon
- Bundle ID: `com.autonomy.app`
- Download: `GoogleService-Info.plist`
- Save to: `mobile/ios/`

### 3. Add Android App
- Click: Android icon
- Package: `com.autonomy.app`
- Download: `google-services.json`
- Save to: `mobile/android/app/`

---

## 🔑 APNs Key Setup (2-3 Hours)

### Apple Developer Portal
**URL**: https://developer.apple.com/account/

**Steps**:
1. **Keys** → Create new key
2. Name: `Beer Game APNs Key`
3. Enable: "Apple Push Notifications service (APNs)"
4. Download: `.p8` file (SAVE IT - can only download once!)
5. Note: **Key ID** and **Team ID**

### Upload to Firebase
1. Firebase → Project Settings → Cloud Messaging
2. iOS configuration → Upload APNs key
3. Upload your `.p8` file
4. Enter Key ID and Team ID
5. Verify: "APNs Authentication Key uploaded" ✓

---

## 🔧 Service Account (30 Minutes)

### Create in Firebase
1. Firebase → Project Settings → Service Accounts
2. Click: "Generate new private key"
3. Download: JSON file
4. Rename: `firebase-credentials.json`
5. Move to: `backend/firebase-credentials.json`

### Secure the File
```bash
cd /home/trevor/Projects/The_Beer_Game
chmod 600 backend/firebase-credentials.json
```

### Verify Backend Can Load It
```bash
docker compose exec backend python -c "
import os, json
path = '/app/firebase-credentials.json'
if os.path.exists(path):
    with open(path) as f:
        data = json.load(f)
    print('✓ Loaded:', data.get('project_id'))
else:
    print('✗ File not found')
"
```

### Restart Backend
```bash
docker compose restart backend
sleep 10
docker compose ps backend
# Should show: Up (healthy)
```

---

## 🧪 Test Notifications (1 Hour)

### Get Test Token from Your App

**iOS (Swift)**:
```swift
import FirebaseMessaging

Messaging.messaging().token { token, error in
    if let token = token {
        print("FCM Token: \(token)")
    }
}
```

**Android (Kotlin)**:
```kotlin
import com.google.firebase.messaging.FirebaseMessaging

FirebaseMessaging.getInstance().token.addOnCompleteListener { task ->
    if (task.isSuccessful) {
        val token = task.result
        Log.d("FCM", "Token: $token")
    }
}
```

### Register Token via API

**Login**:
```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "systemadmin@autonomy.ai",
    "password": "Autonomy@2025"
  }' | jq -r '.access_token')

echo "Auth Token: $TOKEN"
```

**Register iOS Token**:
```bash
curl -X POST http://localhost:8000/api/v1/notifications/register \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "token": "YOUR_IOS_FCM_TOKEN_HERE",
    "platform": "ios",
    "device_name": "iPhone",
    "app_version": "1.0.0"
  }'
```

**Send Test Notification**:
```bash
curl -X POST http://localhost:8000/api/v1/notifications/test \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Test",
    "body": "Hello from Beer Game!"
  }'
```

**Check Status**:
```bash
curl -X GET http://localhost:8000/api/v1/notifications/status \
  -H "Authorization: Bearer $TOKEN" | jq
```

---

## ✅ Success Checklist

### Firebase Console
- [ ] Project "Beer Game Mobile" created
- [ ] iOS app registered (com.autonomy.app)
- [ ] Android app registered (com.autonomy.app)
- [ ] APNs key uploaded and verified
- [ ] Service account created

### Files Downloaded
- [ ] GoogleService-Info.plist → mobile/ios/
- [ ] google-services.json → mobile/android/app/
- [ ] firebase-credentials.json → backend/ (chmod 600)
- [ ] All files in .gitignore

### Backend
- [ ] Backend restarted successfully
- [ ] No Firebase errors in logs
- [ ] Credentials loaded correctly

### Testing
- [ ] iOS app gets FCM token
- [ ] Android app gets FCM token
- [ ] Tokens registered via API
- [ ] Test notification sent
- [ ] iOS receives notification (< 5 sec)
- [ ] Android receives notification (< 5 sec)

---

## 🆘 Troubleshooting

### "APNs key not working"
```bash
# Check:
# 1. Bundle ID matches exactly: com.autonomy.app
# 2. Key ID and Team ID are correct
# 3. Key is uploaded to Firebase
# 4. App has notification permissions
```

### "Android notifications not arriving"
```bash
# Check file location:
ls -la mobile/android/app/google-services.json

# Verify package name in file:
cat mobile/android/app/google-services.json | jq '.client[0].client_info.android_client_info.package_name'
# Should output: "com.autonomy.app"
```

### "Backend can't find credentials"
```bash
# Check file exists:
ls -la backend/firebase-credentials.json

# Set permissions:
chmod 600 backend/firebase-credentials.json

# Restart backend:
docker compose restart backend

# Check logs:
docker compose logs backend --tail 50 | grep -i firebase
```

### "Notification not received"
```bash
# Check token registration:
curl -X GET http://localhost:8000/api/v1/notifications/tokens \
  -H "Authorization: Bearer $TOKEN" | jq

# Check notification logs:
curl -X GET http://localhost:8000/api/v1/notifications/status \
  -H "Authorization: Bearer $TOKEN" | jq '.recent_notifications'

# Check backend logs:
docker compose logs backend --tail 100 | grep -i notification
```

---

## 📚 Full Documentation

**Detailed Guides**:
- [FIREBASE_SETUP_CHECKLIST.md](FIREBASE_SETUP_CHECKLIST.md) - Complete checklist
- [FIREBASE_SETUP_GUIDE.md](FIREBASE_SETUP_GUIDE.md) - Detailed explanations
- [START_HERE.md](START_HERE.md) - Getting started guide

**Testing**:
- [MOBILE_TESTING_GUIDE.md](MOBILE_TESTING_GUIDE.md) - After Firebase is done

---

## ⏱️ Time Breakdown

- [ ] Create Firebase project: **5 min**
- [ ] Register iOS app: **10 min**
- [ ] Generate APNs key: **2-3 hours** (waiting for Apple)
- [ ] Register Android app: **10 min**
- [ ] Create service account: **10 min**
- [ ] Configure backend: **15 min**
- [ ] Test notifications: **1 hour**

**Total**: 4-6 hours

---

## 🎯 You Are Here

```
✅ Backend code complete
✅ Database migrated
✅ API endpoints working
→ YOU ARE HERE: Firebase Setup
⏳ Next: Mobile Testing (1 day)
```

---

**Start**: https://console.firebase.google.com/
**Guide**: [FIREBASE_SETUP_CHECKLIST.md](FIREBASE_SETUP_CHECKLIST.md)

Good luck! 🚀
