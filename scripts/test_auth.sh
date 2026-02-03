#!/bin/bash

# Quick authentication flow test script
# Tests: Register → Verify Email → Login → Refresh → Logout

API_URL="http://localhost:8000/api"
COOKIES_FILE="test_cookies.txt"

echo "🧪 FastAPI Authentication Flow Test"
echo "===================================="
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test user data
TEST_EMAIL="test_$(date +%s)@example.com"
TEST_PASSWORD="SecurePass123"
TEST_NAME="Test User"

echo "📝 Test User Details:"
echo "   Email: $TEST_EMAIL"
echo "   Password: $TEST_PASSWORD"
echo ""

# Step 1: Register
echo "1️⃣  Registering new buyer..."
REGISTER_RESPONSE=$(curl -s -X POST "$API_URL/auth/register" \
  -H "Content-Type: application/json" \
  -d "{
    \"name\": \"$TEST_NAME\",
    \"email\": \"$TEST_EMAIL\",
    \"password\": \"$TEST_PASSWORD\",
    \"role\": \"buyer\"
  }")

echo "$REGISTER_RESPONSE" | jq '.'

if echo "$REGISTER_RESPONSE" | jq -e '.success' > /dev/null; then
    echo -e "${GREEN}✅ Registration successful${NC}"
    USER_ID=$(echo "$REGISTER_RESPONSE" | jq -r '.user_id')
    echo "   User ID: $USER_ID"
else
    echo -e "${RED}❌ Registration failed${NC}"
    exit 1
fi

echo ""

# Step 2: Get verification token (in real scenario, user would get this from email)
echo "2️⃣  Note: In production, user would get verification token from email"
echo "   For testing, you need to get the token from:"
echo "   - Email logs (if SendGrid configured)"
echo "   - Console logs (development mode)"
echo "   - Database: SELECT token FROM email_verification_tokens WHERE user_id = '$USER_ID';"
echo ""
echo "   Run this SQL command to get the token:"
echo "   ${YELLOW}psql \$DATABASE_URL -c \"SELECT token FROM email_verification_tokens WHERE user_id = '$USER_ID';\"${NC}"
echo ""

read -p "   Enter verification token: " VERIFY_TOKEN

echo ""
echo "3️⃣  Verifying email..."
VERIFY_RESPONSE=$(curl -s -X GET "$API_URL/auth/verify-email?token=$VERIFY_TOKEN")

echo "$VERIFY_RESPONSE" | jq '.'

if echo "$VERIFY_RESPONSE" | jq -e '.success' > /dev/null; then
    echo -e "${GREEN}✅ Email verified${NC}"
else
    echo -e "${RED}❌ Email verification failed${NC}"
    exit 1
fi

echo ""

# Step 3: Login
echo "4️⃣  Logging in..."
LOGIN_RESPONSE=$(curl -s -X POST "$API_URL/auth/login" \
  -H "Content-Type: application/json" \
  -c "$COOKIES_FILE" \
  -d "{
    \"email\": \"$TEST_EMAIL\",
    \"password\": \"$TEST_PASSWORD\",
    \"remember_me\": false
  }")

echo "$LOGIN_RESPONSE" | jq '.'

if echo "$LOGIN_RESPONSE" | jq -e '.success' > /dev/null; then
    echo -e "${GREEN}✅ Login successful${NC}"
    echo "   Cookies saved to: $COOKIES_FILE"
else
    echo -e "${RED}❌ Login failed${NC}"
    exit 1
fi

echo ""

# Step 4: Test protected endpoint (would be /api/users/me when implemented)
echo "5️⃣  Testing authenticated request..."
echo "   (This will work once /api/users/me endpoint is implemented in Phase 2)"
echo ""

# Step 5: Refresh token
echo "6️⃣  Refreshing access token..."
REFRESH_RESPONSE=$(curl -s -X POST "$API_URL/auth/refresh" \
  -b "$COOKIES_FILE" \
  -c "$COOKIES_FILE")

echo "$REFRESH_RESPONSE" | jq '.'

if echo "$REFRESH_RESPONSE" | jq -e '.success' > /dev/null; then
    echo -e "${GREEN}✅ Token refresh successful${NC}"
else
    echo -e "${RED}❌ Token refresh failed${NC}"
    exit 1
fi

echo ""

# Step 6: Logout
echo "7️⃣  Logging out..."

# Extract CSRF token from cookies
CSRF_TOKEN=$(grep csrf_token "$COOKIES_FILE" | awk '{print $7}')

LOGOUT_RESPONSE=$(curl -s -X POST "$API_URL/auth/logout" \
  -b "$COOKIES_FILE" \
  -H "X-CSRF-Token: $CSRF_TOKEN")

echo "$LOGOUT_RESPONSE" | jq '.'

if echo "$LOGOUT_RESPONSE" | jq -e '.success' > /dev/null; then
    echo -e "${GREEN}✅ Logout successful${NC}"
else
    echo -e "${RED}❌ Logout failed${NC}"
    exit 1
fi

echo ""
echo "🎉 All tests passed!"
echo ""
echo "Cleanup:"
echo "  - Cookies file: $COOKIES_FILE"
echo "  - Test user: $TEST_EMAIL"
echo ""
