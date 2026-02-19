#!/bin/bash

# Firebase Setup Helper Script
# This script helps verify prerequisites and guides through Firebase setup

set -e

echo "============================================"
echo "Firebase Setup Helper"
echo "============================================"
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Check backend status
echo -e "${BLUE}Step 1: Checking Backend Status${NC}"
echo "-------------------------------------------"
cd /home/trevor/Projects/The_Beer_Game

if docker compose ps backend | grep -q "Up.*healthy"; then
    echo -e "${GREEN}✓${NC} Backend is healthy"
else
    echo -e "${RED}✗${NC} Backend is not healthy"
    echo "Run: docker compose restart backend"
    exit 1
fi

# Check database
echo -e "\n${BLUE}Step 2: Checking Database${NC}"
echo "-------------------------------------------"
TABLE_COUNT=$(docker compose exec -T backend python -c "
from sqlalchemy import text
from app.db.session import engine
import asyncio
async def count():
    async with engine.connect() as conn:
        result = await conn.execute(text('SHOW TABLES'))
        print(len(result.fetchall()))
asyncio.run(count())
" 2>/dev/null | tail -1)

if [ "$TABLE_COUNT" -ge 97 ]; then
    echo -e "${GREEN}✓${NC} Database has $TABLE_COUNT tables (expected: 97)"
else
    echo -e "${YELLOW}⚠${NC} Database has $TABLE_COUNT tables (expected: 97)"
fi

# Check notification API
echo -e "\n${BLUE}Step 3: Checking Notification API${NC}"
echo "-------------------------------------------"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/v1/notifications/status)

if [ "$HTTP_CODE" = "401" ]; then
    echo -e "${GREEN}✓${NC} Notification API is responding (HTTP $HTTP_CODE - auth required)"
else
    echo -e "${RED}✗${NC} Notification API error (HTTP $HTTP_CODE)"
fi

# Check for mobile directory
echo -e "\n${BLUE}Step 4: Checking Mobile Directory${NC}"
echo "-------------------------------------------"
if [ -d "mobile" ]; then
    echo -e "${GREEN}✓${NC} Mobile directory exists"
    
    # Check for iOS directory
    if [ -d "mobile/ios" ]; then
        echo -e "${GREEN}✓${NC} iOS directory exists"
    else
        echo -e "${YELLOW}⚠${NC} iOS directory not found (will create during setup)"
        mkdir -p mobile/ios
    fi
    
    # Check for Android directory
    if [ -d "mobile/android/app" ]; then
        echo -e "${GREEN}✓${NC} Android directory exists"
    else
        echo -e "${YELLOW}⚠${NC} Android directory not found (will create during setup)"
        mkdir -p mobile/android/app
    fi
else
    echo -e "${YELLOW}⚠${NC} Mobile directory not found - creating structure"
    mkdir -p mobile/ios
    mkdir -p mobile/android/app
fi

# Check for .gitignore entries
echo -e "\n${BLUE}Step 5: Checking .gitignore${NC}"
echo "-------------------------------------------"
if grep -q "firebase-credentials.json" backend/.gitignore 2>/dev/null; then
    echo -e "${GREEN}✓${NC} firebase-credentials.json is in .gitignore"
else
    echo -e "${YELLOW}⚠${NC} Adding firebase-credentials.json to .gitignore"
    echo "firebase-credentials.json" >> backend/.gitignore
fi

if grep -q "GoogleService-Info.plist" .gitignore 2>/dev/null; then
    echo -e "${GREEN}✓${NC} GoogleService-Info.plist is in .gitignore"
else
    echo -e "${YELLOW}⚠${NC} Adding GoogleService-Info.plist to .gitignore"
    echo "GoogleService-Info.plist" >> .gitignore
fi

if grep -q "google-services.json" .gitignore 2>/dev/null; then
    echo -e "${GREEN}✓${NC} google-services.json is in .gitignore"
else
    echo -e "${YELLOW}⚠${NC} Adding google-services.json to .gitignore"
    echo "google-services.json" >> .gitignore
fi

# Prerequisites check
echo -e "\n${BLUE}Step 6: Prerequisites Checklist${NC}"
echo "-------------------------------------------"
echo "You will need the following:"
echo ""
echo -e "${YELLOW}Accounts:${NC}"
echo "  □ Google Account (for Firebase)"
echo "  □ Apple Developer Account (\$99/year)"
echo ""
echo -e "${YELLOW}Devices:${NC}"
echo "  □ Physical iPhone (iOS 16+)"
echo "  □ Physical Android device (Android 11+)"
echo ""
echo -e "${YELLOW}Software:${NC}"
echo "  □ Mac computer (for iOS development)"
echo "  □ Xcode (for iOS)"
echo "  □ Android Studio (for Android)"
echo ""

# Next steps
echo "============================================"
echo -e "${GREEN}System is Ready for Firebase Setup!${NC}"
echo "============================================"
echo ""
echo "Next Steps:"
echo ""
echo "1. Open Firebase Setup Checklist:"
echo -e "   ${BLUE}code FIREBASE_SETUP_CHECKLIST.md${NC}"
echo ""
echo "2. Go to Firebase Console:"
echo -e "   ${BLUE}https://console.firebase.google.com/${NC}"
echo ""
echo "3. Follow the checklist step-by-step"
echo "   - Create project 'Autonomy Mobile'"
echo "   - Register iOS app (Bundle ID: com.autonomy.app)"
echo "   - Register Android app (Package: com.autonomy.app)"
echo "   - Download config files"
echo "   - Create service account"
echo ""
echo "4. Files you'll download and where to place them:"
echo -e "   ${YELLOW}iOS:${NC}"
echo "   - GoogleService-Info.plist → mobile/ios/"
echo -e "   ${YELLOW}Android:${NC}"
echo "   - google-services.json → mobile/android/app/"
echo -e "   ${YELLOW}Backend:${NC}"
echo "   - firebase-credentials.json → backend/"
echo ""
echo "Estimated time: 4-6 hours"
echo ""
echo "============================================"

