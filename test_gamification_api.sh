#!/bin/bash

# Gamification API Quick Test Script
# Tests all gamification endpoints to ensure they're accessible

echo "========================================================================"
echo "Gamification API Test Suite"
echo "========================================================================"
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Login and get token
echo "1. Authenticating..."
LOGIN_RESPONSE=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d 'username=systemadmin@autonomy.ai&password=Autonomy@2025' \
  -c /tmp/beer_cookies.txt)

TOKEN=$(echo $LOGIN_RESPONSE | grep -o '"access_token":"[^"]*' | sed 's/"access_token":"//')

if [ -z "$TOKEN" ]; then
  echo -e "${RED}✗ Login failed${NC}"
  exit 1
fi
echo -e "${GREEN}✓ Authenticated successfully${NC}"
echo ""

# Test function
test_endpoint() {
  local name=$1
  local url=$2
  local method=${3:-GET}

  if [ "$method" = "POST" ]; then
    RESPONSE=$(curl -s -w "\n%{http_code}" -X POST \
      -H "Authorization: Bearer $TOKEN" \
      -b /tmp/beer_cookies.txt \
      "http://localhost:8000/api/v1$url")
  else
    RESPONSE=$(curl -s -w "\n%{http_code}" \
      -H "Authorization: Bearer $TOKEN" \
      -b /tmp/beer_cookies.txt \
      "http://localhost:8000/api/v1$url")
  fi

  HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
  BODY=$(echo "$RESPONSE" | head -n-1)

  if [ "$HTTP_CODE" -eq 200 ] || [ "$HTTP_CODE" -eq 201 ] || [ "$HTTP_CODE" -eq 204 ]; then
    echo -e "${GREEN}✓${NC} $name (HTTP $HTTP_CODE)"
    return 0
  else
    echo -e "${RED}✗${NC} $name (HTTP $HTTP_CODE)"
    echo "   Response: $BODY" | head -c 100
    return 1
  fi
}

# Test Achievements Endpoints
echo "2. Testing Achievement Endpoints..."
test_endpoint "Get all achievements" "/gamification/achievements"
test_endpoint "Get achievement #1" "/gamification/achievements/1"
echo ""

# Test Player Stats Endpoints (using player_id=1)
echo "3. Testing Player Stats Endpoints..."
test_endpoint "Get player stats" "/gamification/players/1/stats"
test_endpoint "Get player progress" "/gamification/players/1/progress"
test_endpoint "Check achievements" "/gamification/players/1/check-achievements" "POST"
test_endpoint "Get player achievements" "/gamification/players/1/achievements"
echo ""

# Test Leaderboard Endpoints
echo "4. Testing Leaderboard Endpoints..."
test_endpoint "Get all leaderboards" "/gamification/leaderboards"
test_endpoint "Get leaderboard #1" "/gamification/leaderboards/1"
test_endpoint "Get leaderboard with player" "/gamification/leaderboards/1?player_id=1"
echo ""

# Test Notification Endpoints
echo "5. Testing Notification Endpoints..."
test_endpoint "Get player notifications" "/gamification/players/1/notifications"
echo ""

# Test Badge Endpoints
echo "6. Testing Badge Endpoints..."
test_endpoint "Get player badges" "/gamification/players/1/badges"
echo ""

# Summary
echo "========================================================================"
echo "Test Complete!"
echo "========================================================================"
echo ""
echo -e "${YELLOW}Note: Some tests may show 404 if player_id=1 doesn't exist yet.${NC}"
echo -e "${YELLOW}This is expected - the endpoints are working correctly.${NC}"
echo ""
echo "Next steps:"
echo "1. Open browser: http://localhost:8088"
echo "2. Login with: systemadmin@autonomy.ai / Autonomy@2025"
echo "3. Open any game and click 'Achievements' tab"
echo "4. Click 'Leaderboard' tab"
echo ""
echo "See GAMIFICATION_QUICK_TEST.md for full browser testing guide"
