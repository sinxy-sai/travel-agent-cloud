#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-http://localhost:8000}"
USER_ID="smoke-test-user"

echo "Checking health: ${BASE_URL}/health"
HEALTH_HEADERS="$(mktemp)"
HEALTH_JSON="$(curl -fsS -D "${HEALTH_HEADERS}" "${BASE_URL}/health")"
echo "${HEALTH_JSON}"
if ! grep -qi '^x-request-id:' "${HEALTH_HEADERS}"; then
  echo "Health API did not return X-Request-ID" >&2
  rm -f "${HEALTH_HEADERS}"
  exit 1
fi
if ! grep -qi '^x-process-time-ms:' "${HEALTH_HEADERS}"; then
  echo "Health API did not return X-Process-Time-Ms" >&2
  rm -f "${HEALTH_HEADERS}"
  exit 1
fi
if ! grep -qi '^x-content-type-options: nosniff' "${HEALTH_HEADERS}"; then
  echo "Health API did not return X-Content-Type-Options" >&2
  rm -f "${HEALTH_HEADERS}"
  exit 1
fi
rm -f "${HEALTH_HEADERS}"
HAS_MESSAGE_QUEUE_FIELD="$(printf '%s' "${HEALTH_JSON}" | python3 -c 'import json, sys; print("yes" if "messageQueueEnabled" in json.load(sys.stdin) else "no")')"
if [ "${HAS_MESSAGE_QUEUE_FIELD}" != "yes" ]; then
  echo "Health API did not return messageQueueEnabled" >&2
  exit 1
fi
echo

echo "Preparing anonymous local data"
ANONYMOUS_USER_ID="smoke-anon-$(date +%s)-$$"
ANONYMOUS_CHAT_JSON="$(curl -fsS -X POST "${BASE_URL}/api/v1/chat" \
  -H "Content-Type: application/json" \
  -H "X-User-Id: ${ANONYMOUS_USER_ID}" \
  -d '{"message":"Plan a relaxed 2-day Hangzhou tea and lake trip.","mode":"TRIP_PLANNING"}')"
ANONYMOUS_CONVERSATION_ID="$(printf '%s' "${ANONYMOUS_CHAT_JSON}" | python3 -c 'import json, sys; print(json.load(sys.stdin).get("conversationId", ""))')"
if [ -z "${ANONYMOUS_CONVERSATION_ID}" ]; then
  echo "Anonymous chat API did not return conversationId" >&2
  exit 1
fi
ANONYMOUS_TRIP_PLAN_JSON="$(curl -fsS -X POST "${BASE_URL}/api/v1/trip-plan" \
  -H "Content-Type: application/json" \
  -H "X-User-Id: ${ANONYMOUS_USER_ID}" \
  -d "{\"destination\":\"Hangzhou\",\"days\":2,\"budget\":\"moderate\",\"interests\":\"tea, lake\",\"conversationId\":\"${ANONYMOUS_CONVERSATION_ID}\"}")"
ANONYMOUS_TRIP_PLAN_ID="$(printf '%s' "${ANONYMOUS_TRIP_PLAN_JSON}" | python3 -c 'import json, sys; print(json.load(sys.stdin).get("savedTripPlanId", ""))')"
if [ -z "${ANONYMOUS_TRIP_PLAN_ID}" ]; then
  echo "Anonymous trip plan API did not return savedTripPlanId" >&2
  exit 1
fi
echo

echo "Checking auth API"
AUTH_COOKIE_JAR="$(mktemp)"
AUTH_EMAIL="smoke-$(date +%s)-$$@example.com"
AUTH_CHANGED_PASSWORD="SmokeTest456!"
REGISTER_JSON="$(curl -fsS -X POST "${BASE_URL}/api/v1/auth/register" \
  -H "Content-Type: application/json" \
  -c "${AUTH_COOKIE_JAR}" \
  -b "${AUTH_COOKIE_JAR}" \
  -d "{\"email\":\"${AUTH_EMAIL}\",\"password\":\"SmokeTest123!\",\"displayName\":\"Smoke Test Account\"}")"
echo "${REGISTER_JSON}"
REGISTERED_EMAIL="$(printf '%s' "${REGISTER_JSON}" | python3 -c 'import json, sys; print(json.load(sys.stdin).get("user", {}).get("email", ""))')"
if [ "${REGISTERED_EMAIL}" != "${AUTH_EMAIL}" ]; then
  echo "Auth register API did not return the created user" >&2
  rm -f "${AUTH_COOKIE_JAR}"
  exit 1
fi
REGISTERED_EMAIL_VERIFIED="$(printf '%s' "${REGISTER_JSON}" | python3 -c 'import json, sys; print("yes" if json.load(sys.stdin).get("user", {}).get("emailVerified") else "no")')"
if [ "${REGISTERED_EMAIL_VERIFIED}" != "no" ]; then
  echo "Newly registered accounts should start with emailVerified=false" >&2
  rm -f "${AUTH_COOKIE_JAR}"
  exit 1
fi
CURRENT_AUTH_USER_JSON="$(curl -fsS "${BASE_URL}/api/v1/auth/me" \
  -b "${AUTH_COOKIE_JAR}")"
CURRENT_AUTH_EMAIL="$(printf '%s' "${CURRENT_AUTH_USER_JSON}" | python3 -c 'import json, sys; print(json.load(sys.stdin).get("email", ""))')"
if [ "${CURRENT_AUTH_EMAIL}" != "${AUTH_EMAIL}" ]; then
  echo "Auth me API did not return the cookie-authenticated user" >&2
  rm -f "${AUTH_COOKIE_JAR}"
  exit 1
fi
UNVERIFIED_EXPORT_STATUS="$(curl -s -o /dev/null -w '%{http_code}' "${BASE_URL}/api/v1/me/export" \
  -b "${AUTH_COOKIE_JAR}")"
if [ "${UNVERIFIED_EXPORT_STATUS}" != "403" ]; then
  echo "User data export API accepted an unverified account" >&2
  rm -f "${AUTH_COOKIE_JAR}"
  exit 1
fi
ACCOUNT_DATA_VERIFIED="no"
VERIFICATION_JSON="$(curl -fsS -X POST "${BASE_URL}/api/v1/auth/email-verification/request" \
  -b "${AUTH_COOKIE_JAR}")"
VERIFICATION_DEV_TOKEN="$(printf '%s' "${VERIFICATION_JSON}" | python3 -c 'import json, sys; print(json.load(sys.stdin).get("devToken") or "")')"
if [ -n "${VERIFICATION_DEV_TOKEN}" ]; then
  VERIFIED_USER_JSON="$(curl -fsS -X POST "${BASE_URL}/api/v1/auth/email-verification/confirm" \
    -H "Content-Type: application/json" \
    -d "{\"token\":\"${VERIFICATION_DEV_TOKEN}\"}")"
  VERIFIED_EMAIL_STATUS="$(printf '%s' "${VERIFIED_USER_JSON}" | python3 -c 'import json, sys; print("yes" if json.load(sys.stdin).get("emailVerified") else "no")')"
  if [ "${VERIFIED_EMAIL_STATUS}" != "yes" ]; then
    echo "Email verification API did not mark the user as verified" >&2
    rm -f "${AUTH_COOKIE_JAR}"
    exit 1
  fi
  ACCOUNT_DATA_VERIFIED="yes"
fi
MISSING_RESET_JSON="$(curl -fsS -X POST "${BASE_URL}/api/v1/auth/password-reset/request" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"missing-$(date +%s)-$$@example.com\"}")"
MISSING_RESET_SENT="$(printf '%s' "${MISSING_RESET_JSON}" | python3 -c 'import json, sys; print("yes" if json.load(sys.stdin).get("sent") else "no")')"
if [ "${MISSING_RESET_SENT}" != "yes" ]; then
  echo "Password reset request should return a generic accepted response for missing email" >&2
  rm -f "${AUTH_COOKIE_JAR}"
  exit 1
fi
SECURITY_EVENTS_JSON="$(curl -fsS "${BASE_URL}/api/v1/auth/security-events?page=1&pageSize=5" \
  -b "${AUTH_COOKIE_JAR}")"
SECURITY_EVENTS_COUNT="$(printf '%s' "${SECURITY_EVENTS_JSON}" | python3 -c 'import json, sys; print(len(json.load(sys.stdin).get("data", [])))')"
if [ "${SECURITY_EVENTS_COUNT}" = "0" ]; then
  echo "Security events API did not return recent account activity" >&2
  rm -f "${AUTH_COOKIE_JAR}"
  exit 1
fi
UPDATED_AUTH_USER_JSON="$(curl -fsS -X PATCH "${BASE_URL}/api/v1/auth/me" \
  -H "Content-Type: application/json" \
  -b "${AUTH_COOKIE_JAR}" \
  -d '{"displayName":"Updated Smoke Account"}')"
UPDATED_AUTH_DISPLAY_NAME="$(printf '%s' "${UPDATED_AUTH_USER_JSON}" | python3 -c 'import json, sys; print(json.load(sys.stdin).get("displayName", ""))')"
if [ "${UPDATED_AUTH_DISPLAY_NAME}" != "Updated Smoke Account" ]; then
  echo "Auth user update API did not persist displayName" >&2
  rm -f "${AUTH_COOKIE_JAR}"
  exit 1
fi
if [ "${ACCOUNT_DATA_VERIFIED}" = "yes" ]; then
  EXPORTED_USER_DATA_JSON="$(curl -fsS "${BASE_URL}/api/v1/me/export" \
    -b "${AUTH_COOKIE_JAR}")"
  EXPORTED_USER_EMAIL="$(printf '%s' "${EXPORTED_USER_DATA_JSON}" | python3 -c 'import json, sys; print(json.load(sys.stdin).get("user", {}).get("email", ""))')"
  HAS_EXPORTED_CONVERSATIONS="$(printf '%s' "${EXPORTED_USER_DATA_JSON}" | python3 -c 'import json, sys; print("yes" if "conversations" in json.load(sys.stdin) else "no")')"
  if [ "${EXPORTED_USER_EMAIL}" != "${AUTH_EMAIL}" ] || [ "${HAS_EXPORTED_CONVERSATIONS}" != "yes" ]; then
    echo "User data export API did not return the authenticated user data" >&2
    rm -f "${AUTH_COOKIE_JAR}"
    exit 1
  fi
  IMPORTED_USER_DATA_JSON="$(curl -fsS -X POST "${BASE_URL}/api/v1/me/import" \
    -H "Content-Type: application/json" \
    -b "${AUTH_COOKIE_JAR}" \
    -d "${EXPORTED_USER_DATA_JSON}")"
  PROFILE_IMPORTED="$(printf '%s' "${IMPORTED_USER_DATA_JSON}" | python3 -c 'import json, sys; print("yes" if json.load(sys.stdin).get("profileImported") else "no")')"
  if [ "${PROFILE_IMPORTED}" != "yes" ]; then
    echo "User data import API did not import the profile" >&2
    rm -f "${AUTH_COOKIE_JAR}"
    exit 1
  fi
  ANONYMOUS_SUMMARY_JSON="$(curl -fsS "${BASE_URL}/api/v1/me/anonymous-data/summary" \
    -H "X-User-Id: ${ANONYMOUS_USER_ID}" \
    -b "${AUTH_COOKIE_JAR}")"
  ANONYMOUS_SUMMARY_HAS_DATA="$(printf '%s' "${ANONYMOUS_SUMMARY_JSON}" | python3 -c 'import json, sys; print("yes" if json.load(sys.stdin).get("hasData") else "no")')"
  ANONYMOUS_SUMMARY_CONVERSATIONS="$(printf '%s' "${ANONYMOUS_SUMMARY_JSON}" | python3 -c 'import json, sys; print(json.load(sys.stdin).get("conversations", 0))')"
  ANONYMOUS_SUMMARY_TRIP_PLANS="$(printf '%s' "${ANONYMOUS_SUMMARY_JSON}" | python3 -c 'import json, sys; print(json.load(sys.stdin).get("tripPlans", 0))')"
  if [ "${ANONYMOUS_SUMMARY_HAS_DATA}" != "yes" ] || [ "${ANONYMOUS_SUMMARY_CONVERSATIONS}" -lt 1 ] || [ "${ANONYMOUS_SUMMARY_TRIP_PLANS}" -lt 1 ]; then
    echo "Anonymous data summary API did not report local anonymous data" >&2
    rm -f "${AUTH_COOKIE_JAR}"
    exit 1
  fi
  ANONYMOUS_IMPORT_JSON="$(curl -fsS -X POST "${BASE_URL}/api/v1/me/anonymous-data/import" \
    -H "X-User-Id: ${ANONYMOUS_USER_ID}" \
    -b "${AUTH_COOKIE_JAR}")"
  ANONYMOUS_IMPORT_CONVERSATIONS="$(printf '%s' "${ANONYMOUS_IMPORT_JSON}" | python3 -c 'import json, sys; print(json.load(sys.stdin).get("conversationsImported", 0))')"
  ANONYMOUS_IMPORT_TRIP_PLANS="$(printf '%s' "${ANONYMOUS_IMPORT_JSON}" | python3 -c 'import json, sys; print(json.load(sys.stdin).get("tripPlansImported", 0))')"
  if [ "${ANONYMOUS_IMPORT_CONVERSATIONS}" -lt 1 ] || [ "${ANONYMOUS_IMPORT_TRIP_PLANS}" -lt 1 ]; then
    echo "Anonymous data import API did not import local conversations and trip plans" >&2
    rm -f "${AUTH_COOKIE_JAR}"
    exit 1
  fi
  EXPORTED_AFTER_ANONYMOUS_IMPORT_JSON="$(curl -fsS "${BASE_URL}/api/v1/me/export" \
    -b "${AUTH_COOKIE_JAR}")"
  HAS_IMPORTED_ANONYMOUS_CONVERSATION="$(printf '%s' "${EXPORTED_AFTER_ANONYMOUS_IMPORT_JSON}" | python3 -c 'import json, sys; data=json.load(sys.stdin).get("conversations", []); print("yes" if any("Hangzhou" in item.get("title", "") or any("Hangzhou" in msg.get("content", "") for msg in item.get("messages", [])) for item in data) else "no")')"
  HAS_IMPORTED_ANONYMOUS_TRIP_PLAN="$(printf '%s' "${EXPORTED_AFTER_ANONYMOUS_IMPORT_JSON}" | python3 -c 'import json, sys; data=json.load(sys.stdin).get("tripPlans", []); print("yes" if any(item.get("destination") == "Hangzhou" for item in data) else "no")')"
  if [ "${HAS_IMPORTED_ANONYMOUS_CONVERSATION}" != "yes" ] || [ "${HAS_IMPORTED_ANONYMOUS_TRIP_PLAN}" != "yes" ]; then
    echo "User data export did not include imported anonymous data" >&2
    rm -f "${AUTH_COOKIE_JAR}"
    exit 1
  fi
else
  echo "Skipping verified account data import/export checks because no dev verification token was returned"
fi
AUTH_RESET_PASSWORD="SmokeTest789!"
RESET_JSON="$(curl -fsS -X POST "${BASE_URL}/api/v1/auth/password-reset/request" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"${AUTH_EMAIL}\"}")"
RESET_DEV_TOKEN="$(printf '%s' "${RESET_JSON}" | python3 -c 'import json, sys; print(json.load(sys.stdin).get("devToken") or "")')"
if [ -n "${RESET_DEV_TOKEN}" ]; then
  curl -fsS -X POST "${BASE_URL}/api/v1/auth/password-reset/confirm" \
    -H "Content-Type: application/json" \
    -d "{\"token\":\"${RESET_DEV_TOKEN}\",\"newPassword\":\"${AUTH_RESET_PASSWORD}\"}"
  AUTH_CHANGED_PASSWORD="${AUTH_RESET_PASSWORD}"
else
  curl -fsS -X PATCH "${BASE_URL}/api/v1/auth/password" \
    -H "Content-Type: application/json" \
    -b "${AUTH_COOKIE_JAR}" \
    -d "{\"currentPassword\":\"SmokeTest123!\",\"newPassword\":\"${AUTH_CHANGED_PASSWORD}\"}"
fi
curl -fsS -X POST "${BASE_URL}/api/v1/auth/logout" \
  -b "${AUTH_COOKIE_JAR}" \
  -c "${AUTH_COOKIE_JAR}"
LOGGED_OUT_STATUS="$(curl -s -o /dev/null -w '%{http_code}' "${BASE_URL}/api/v1/auth/me" \
  -b "${AUTH_COOKIE_JAR}")"
if [ "${LOGGED_OUT_STATUS}" != "401" ]; then
  echo "Auth me API accepted a logged-out session" >&2
  rm -f "${AUTH_COOKIE_JAR}"
  exit 1
fi
OLD_PASSWORD_LOGIN_STATUS="$(curl -s -o /dev/null -w '%{http_code}' -X POST "${BASE_URL}/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -c "${AUTH_COOKIE_JAR}" \
  -b "${AUTH_COOKIE_JAR}" \
  -d "{\"email\":\"${AUTH_EMAIL}\",\"password\":\"SmokeTest123!\"}")"
if [ "${OLD_PASSWORD_LOGIN_STATUS}" != "401" ]; then
  echo "Auth login accepted the old password after a password change" >&2
  rm -f "${AUTH_COOKIE_JAR}"
  exit 1
fi
CHANGED_LOGIN_JSON="$(curl -fsS -X POST "${BASE_URL}/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -c "${AUTH_COOKIE_JAR}" \
  -b "${AUTH_COOKIE_JAR}" \
  -d "{\"email\":\"${AUTH_EMAIL}\",\"password\":\"${AUTH_CHANGED_PASSWORD}\"}")"
CHANGED_LOGIN_EMAIL="$(printf '%s' "${CHANGED_LOGIN_JSON}" | python3 -c 'import json, sys; print(json.load(sys.stdin).get("user", {}).get("email", ""))')"
if [ "${CHANGED_LOGIN_EMAIL}" != "${AUTH_EMAIL}" ]; then
  echo "Auth login did not accept the changed password" >&2
  rm -f "${AUTH_COOKIE_JAR}"
  exit 1
fi
curl -fsS -X DELETE "${BASE_URL}/api/v1/auth/me" \
  -H "Content-Type: application/json" \
  -b "${AUTH_COOKIE_JAR}" \
  -c "${AUTH_COOKIE_JAR}" \
  -d "{\"currentPassword\":\"${AUTH_CHANGED_PASSWORD}\",\"confirmation\":\"DELETE\"}"
DELETED_AUTH_STATUS="$(curl -s -o /dev/null -w '%{http_code}' "${BASE_URL}/api/v1/auth/me" \
  -b "${AUTH_COOKIE_JAR}")"
if [ "${DELETED_AUTH_STATUS}" != "401" ]; then
  echo "Auth me API accepted a deleted account session" >&2
  rm -f "${AUTH_COOKIE_JAR}"
  exit 1
fi
DELETED_ACCOUNT_LOGIN_STATUS="$(curl -s -o /dev/null -w '%{http_code}' -X POST "${BASE_URL}/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -c "${AUTH_COOKIE_JAR}" \
  -b "${AUTH_COOKIE_JAR}" \
  -d "{\"email\":\"${AUTH_EMAIL}\",\"password\":\"${AUTH_CHANGED_PASSWORD}\"}")"
rm -f "${AUTH_COOKIE_JAR}"
if [ "${DELETED_ACCOUNT_LOGIN_STATUS}" != "401" ]; then
  echo "Auth login accepted a deleted account" >&2
  exit 1
fi
echo

echo "Checking user profile API"
UPDATED_PROFILE_JSON="$(curl -fsS -X PATCH "${BASE_URL}/api/v1/me/profile" \
  -H "Content-Type: application/json" \
  -H "X-User-Id: ${USER_ID}" \
  -d '{"displayName":"Smoke Test Traveler","homeCity":"Beijing","preferredBudget":"moderate","travelStyle":"relaxed city walks","interests":["local food","museums"]}')"
echo "${UPDATED_PROFILE_JSON}"
PROFILE_DISPLAY_NAME="$(printf '%s' "${UPDATED_PROFILE_JSON}" | python3 -c 'import json, sys; print(json.load(sys.stdin).get("displayName", ""))')"
if [ "${PROFILE_DISPLAY_NAME}" != "Smoke Test Traveler" ]; then
  echo "User profile API did not persist displayName" >&2
  exit 1
fi
PROFILE_HAS_INTEREST="$(printf '%s' "${UPDATED_PROFILE_JSON}" | python3 -c 'import json, sys; print("yes" if "local food" in json.load(sys.stdin).get("interests", []) else "no")')"
if [ "${PROFILE_HAS_INTEREST}" != "yes" ]; then
  echo "User profile API did not persist interests" >&2
  exit 1
fi
LOADED_PROFILE_JSON="$(curl -fsS "${BASE_URL}/api/v1/me/profile" \
  -H "X-User-Id: ${USER_ID}")"
LOADED_PROFILE_BUDGET="$(printf '%s' "${LOADED_PROFILE_JSON}" | python3 -c 'import json, sys; print(json.load(sys.stdin).get("preferredBudget", ""))')"
if [ "${LOADED_PROFILE_BUDGET}" != "moderate" ]; then
  echo "User profile API did not load persisted preferredBudget" >&2
  exit 1
fi
echo

echo "Checking chat API"
CHAT_JSON="$(curl -fsS -X POST "${BASE_URL}/api/v1/chat" \
  -H "Content-Type: application/json" \
  -H "X-User-Id: ${USER_ID}" \
  -d '{"message":"I want a relaxed 3-day Chengdu food trip.","mode":"TRIP_PLANNING"}')"
echo "${CHAT_JSON}"
HAS_SUGGESTIONS="$(printf '%s' "${CHAT_JSON}" | python3 -c 'import json, sys; print("yes" if json.load(sys.stdin).get("suggestions") else "no")')"
if [ "${HAS_SUGGESTIONS}" != "yes" ]; then
  echo "Chat API did not return suggestions" >&2
  exit 1
fi
CHAT_CONVERSATION_ID="$(printf '%s' "${CHAT_JSON}" | python3 -c 'import json, sys; print(json.load(sys.stdin).get("conversationId", ""))')"
if [ -z "${CHAT_CONVERSATION_ID}" ]; then
  echo "Chat API did not return conversationId" >&2
  exit 1
fi
echo

echo "Checking trip plan API"
CREATED_TRIP_PLAN_JSON="$(curl -fsS -X POST "${BASE_URL}/api/v1/trip-plan" \
  -H "Content-Type: application/json" \
  -H "X-User-Id: ${USER_ID}" \
  -d "{\"destination\":\"Chengdu\",\"days\":3,\"budget\":\"moderate\",\"interests\":\"local food, city walk\",\"conversationId\":\"${CHAT_CONVERSATION_ID}\"}")"
echo "${CREATED_TRIP_PLAN_JSON}"
CREATED_TRIP_PLAN_ID="$(printf '%s' "${CREATED_TRIP_PLAN_JSON}" | python3 -c 'import json, sys; print(json.load(sys.stdin).get("savedTripPlanId", ""))')"
if [ -z "${CREATED_TRIP_PLAN_ID}" ]; then
  echo "Trip plan API did not return savedTripPlanId" >&2
  exit 1
fi
CREATED_CONVERSATION_ID="$(printf '%s' "${CREATED_TRIP_PLAN_JSON}" | python3 -c 'import json, sys; print(json.load(sys.stdin).get("conversationId", ""))')"
if [ "${CREATED_CONVERSATION_ID}" != "${CHAT_CONVERSATION_ID}" ]; then
  echo "Trip plan API did not bind to the active conversation" >&2
  exit 1
fi
echo

echo "Checking conversation list API"
CONVERSATIONS_JSON="$(curl -fsS "${BASE_URL}/api/v1/conversations?page=1&pageSize=20" \
  -H "X-User-Id: ${USER_ID}")"
echo "${CONVERSATIONS_JSON}"
echo

CONVERSATION_ID="$(printf '%s' "${CONVERSATIONS_JSON}" | python3 -c 'import json, sys; data = json.load(sys.stdin).get("data", []); print(data[0]["id"] if data else "")')"
if [ -z "${CONVERSATION_ID}" ]; then
  echo "Conversation history did not return a saved conversation" >&2
  exit 1
fi
SEARCH_CONVERSATIONS_JSON="$(curl -fsS "${BASE_URL}/api/v1/conversations?page=1&pageSize=20&query=Chengdu" \
  -H "X-User-Id: ${USER_ID}")"
SEARCH_HAS_CREATED_CONVERSATION="$(printf '%s' "${SEARCH_CONVERSATIONS_JSON}" | CHAT_CONVERSATION_ID="${CHAT_CONVERSATION_ID}" python3 -c 'import json, os, sys; data = json.load(sys.stdin).get("data", []); conversation_id = os.environ["CHAT_CONVERSATION_ID"]; print("yes" if any(item.get("id") == conversation_id for item in data) else "no")')"
if [ "${SEARCH_HAS_CREATED_CONVERSATION}" != "yes" ]; then
  echo "Conversation query filter did not return the created Chengdu conversation" >&2
  exit 1
fi

echo "Checking conversation rename API"
RENAMED_CONVERSATION_JSON="$(curl -fsS -X PATCH "${BASE_URL}/api/v1/conversations/${CHAT_CONVERSATION_ID}" \
  -H "Content-Type: application/json" \
  -H "X-User-Id: ${USER_ID}" \
  -d '{"title":"Chengdu planning thread"}')"
echo "${RENAMED_CONVERSATION_JSON}"
RENAMED_CONVERSATION_TITLE="$(printf '%s' "${RENAMED_CONVERSATION_JSON}" | python3 -c 'import json, sys; print(json.load(sys.stdin).get("title", ""))')"
if [ "${RENAMED_CONVERSATION_TITLE}" != "Chengdu planning thread" ]; then
  echo "Conversation rename API did not persist title" >&2
  exit 1
fi
RENAMED_SEARCH_CONVERSATIONS_JSON="$(curl -fsS "${BASE_URL}/api/v1/conversations?page=1&pageSize=20&query=planning" \
  -H "X-User-Id: ${USER_ID}")"
RENAMED_SEARCH_HAS_CREATED_CONVERSATION="$(printf '%s' "${RENAMED_SEARCH_CONVERSATIONS_JSON}" | CHAT_CONVERSATION_ID="${CHAT_CONVERSATION_ID}" python3 -c 'import json, os, sys; data = json.load(sys.stdin).get("data", []); conversation_id = os.environ["CHAT_CONVERSATION_ID"]; print("yes" if any(item.get("id") == conversation_id for item in data) else "no")')"
if [ "${RENAMED_SEARCH_HAS_CREATED_CONVERSATION}" != "yes" ]; then
  echo "Conversation query filter did not return the renamed conversation" >&2
  exit 1
fi
echo

echo "Checking conversation summary API"
SUMMARY_JSON="$(curl -fsS -X POST "${BASE_URL}/api/v1/conversations/${CHAT_CONVERSATION_ID}/summary" \
  -H "X-User-Id: ${USER_ID}")"
echo "${SUMMARY_JSON}"
SUMMARY_ID="$(printf '%s' "${SUMMARY_JSON}" | python3 -c 'import json, sys; print(json.load(sys.stdin).get("id", ""))')"
SUMMARY_MESSAGE_COUNT="$(printf '%s' "${SUMMARY_JSON}" | python3 -c 'import json, sys; print(json.load(sys.stdin).get("messageCount", 0))')"
if [ -z "${SUMMARY_ID}" ] || [ "${SUMMARY_MESSAGE_COUNT}" -lt 1 ]; then
  echo "Conversation summary API did not return a persisted summary" >&2
  exit 1
fi
LOADED_SUMMARY_JSON="$(curl -fsS "${BASE_URL}/api/v1/conversations/${CHAT_CONVERSATION_ID}/summary" \
  -H "X-User-Id: ${USER_ID}")"
LOADED_SUMMARY_ID="$(printf '%s' "${LOADED_SUMMARY_JSON}" | python3 -c 'import json, sys; print(json.load(sys.stdin).get("id", ""))')"
if [ "${LOADED_SUMMARY_ID}" != "${SUMMARY_ID}" ]; then
  echo "Conversation summary API did not load the latest persisted summary" >&2
  exit 1
fi
echo

echo "Checking conversation async summary job API"
MESSAGE_QUEUE_ENABLED="$(printf '%s' "${HEALTH_JSON}" | python3 -c 'import json, sys; print("yes" if json.load(sys.stdin).get("messageQueueEnabled") else "no")')"
if [ "${MESSAGE_QUEUE_ENABLED}" = "yes" ]; then
  SUMMARY_JOB_JSON="$(curl -fsS -X POST "${BASE_URL}/api/v1/conversations/${CHAT_CONVERSATION_ID}/summary-jobs" \
    -H "X-User-Id: ${USER_ID}")"
  echo "${SUMMARY_JOB_JSON}"
  SUMMARY_JOB_ID="$(printf '%s' "${SUMMARY_JOB_JSON}" | python3 -c 'import json, sys; print(json.load(sys.stdin).get("id", ""))')"
  if [ -z "${SUMMARY_JOB_ID}" ]; then
    echo "Conversation summary job API did not return job id" >&2
    exit 1
  fi
  SUMMARY_JOB_STATUS="$(printf '%s' "${SUMMARY_JOB_JSON}" | python3 -c 'import json, sys; print(json.load(sys.stdin).get("status", ""))')"
  if [ "${SUMMARY_JOB_STATUS}" != "QUEUED" ]; then
    echo "Conversation summary job API did not return QUEUED status" >&2
    exit 1
  fi
  LATEST_SUMMARY_JOB_JSON="$(curl -fsS "${BASE_URL}/api/v1/conversations/${CHAT_CONVERSATION_ID}/summary-jobs/latest" \
    -H "X-User-Id: ${USER_ID}")"
  LATEST_SUMMARY_JOB_ID="$(printf '%s' "${LATEST_SUMMARY_JOB_JSON}" | python3 -c 'import json, sys; print(json.load(sys.stdin).get("id", ""))')"
  if [ "${LATEST_SUMMARY_JOB_ID}" != "${SUMMARY_JOB_ID}" ]; then
    echo "Conversation summary latest job API did not return the queued job" >&2
    exit 1
  fi
else
  SUMMARY_JOB_STATUS_CODE="$(curl -s -o /dev/null -w '%{http_code}' -X POST "${BASE_URL}/api/v1/conversations/${CHAT_CONVERSATION_ID}/summary-jobs" \
    -H "X-User-Id: ${USER_ID}")"
  if [ "${SUMMARY_JOB_STATUS_CODE}" != "503" ]; then
    echo "Conversation summary job API accepted a job without RabbitMQ" >&2
    exit 1
  fi
fi
echo

echo "Checking trip plan history API"
TRIP_PLANS_JSON="$(curl -fsS "${BASE_URL}/api/v1/trip-plans?page=1&pageSize=20" \
  -H "X-User-Id: ${USER_ID}")"
echo "${TRIP_PLANS_JSON}"
echo

HAS_TRIP_PLANS="$(printf '%s' "${TRIP_PLANS_JSON}" | python3 -c 'import json, sys; print("yes" if json.load(sys.stdin).get("data") else "no")')"
if [ "${HAS_TRIP_PLANS}" != "yes" ]; then
  echo "Trip plan history did not return a saved plan" >&2
  exit 1
fi

TRIP_PLAN_ID="${CREATED_TRIP_PLAN_ID}"
if [ -z "${TRIP_PLAN_ID}" ]; then
  echo "Trip plan API did not return savedTripPlanId" >&2
  exit 1
fi

echo "Checking trip plan favorite API"
FAVORITE_TRIP_PLAN_JSON="$(curl -fsS -X PATCH "${BASE_URL}/api/v1/trip-plans/${TRIP_PLAN_ID}" \
  -H "Content-Type: application/json" \
  -H "X-User-Id: ${USER_ID}" \
  -d '{"favorite":true}')"
echo "${FAVORITE_TRIP_PLAN_JSON}"
IS_FAVORITE="$(printf '%s' "${FAVORITE_TRIP_PLAN_JSON}" | python3 -c 'import json, sys; print("yes" if json.load(sys.stdin).get("favorite") else "no")')"
if [ "${IS_FAVORITE}" != "yes" ]; then
  echo "Trip plan favorite API did not persist favorite=true" >&2
  exit 1
fi
FAVORITE_TRIP_PLANS_JSON="$(curl -fsS "${BASE_URL}/api/v1/trip-plans?page=1&pageSize=20" \
  -H "X-User-Id: ${USER_ID}")"
FIRST_IS_FAVORITE="$(printf '%s' "${FAVORITE_TRIP_PLANS_JSON}" | python3 -c 'import json, sys; data = json.load(sys.stdin).get("data", []); print("yes" if data and data[0].get("favorite") else "no")')"
if [ "${FIRST_IS_FAVORITE}" != "yes" ]; then
  echo "Trip plan history did not sort favorite plans first" >&2
  exit 1
fi
FAVORITE_ONLY_TRIP_PLANS_JSON="$(curl -fsS "${BASE_URL}/api/v1/trip-plans?page=1&pageSize=20&favoriteOnly=true" \
  -H "X-User-Id: ${USER_ID}")"
FAVORITE_ONLY_HAS_FAVORITE="$(printf '%s' "${FAVORITE_ONLY_TRIP_PLANS_JSON}" | python3 -c 'import json, sys; data = json.load(sys.stdin).get("data", []); print("yes" if data and data[0].get("favorite") else "no")')"
if [ "${FAVORITE_ONLY_HAS_FAVORITE}" != "yes" ]; then
  echo "Trip plan favoriteOnly filter did not return favorite plans" >&2
  exit 1
fi
SEARCH_TRIP_PLANS_JSON="$(curl -fsS "${BASE_URL}/api/v1/trip-plans?page=1&pageSize=20&query=Chengdu" \
  -H "X-User-Id: ${USER_ID}")"
SEARCH_HAS_CREATED_PLAN="$(printf '%s' "${SEARCH_TRIP_PLANS_JSON}" | TRIP_PLAN_ID="${TRIP_PLAN_ID}" python3 -c 'import json, os, sys; data = json.load(sys.stdin).get("data", []); trip_plan_id = os.environ["TRIP_PLAN_ID"]; print("yes" if any(item.get("id") == trip_plan_id for item in data) else "no")')"
if [ "${SEARCH_HAS_CREATED_PLAN}" != "yes" ]; then
  echo "Trip plan query filter did not return the created Chengdu plan" >&2
  exit 1
fi
echo

echo "Checking trip plan export API"
MARKDOWN="$(curl -fsS "${BASE_URL}/api/v1/trip-plans/${TRIP_PLAN_ID}/export" \
  -H "X-User-Id: ${USER_ID}")"
printf '%s\n' "${MARKDOWN}"
case "${MARKDOWN}" in
  \#*) ;;
  *)
    echo "Trip plan export did not return markdown" >&2
    exit 1
    ;;
esac
echo

echo "Checking trip plan delete API"
curl -fsS -X DELETE "${BASE_URL}/api/v1/trip-plans/${TRIP_PLAN_ID}" \
  -H "X-User-Id: ${USER_ID}"
if [ "$(curl -s -o /dev/null -w '%{http_code}' "${BASE_URL}/api/v1/trip-plans/${TRIP_PLAN_ID}" -H "X-User-Id: ${USER_ID}")" != "404" ]; then
  echo "Deleted trip plan was still readable" >&2
  exit 1
fi
echo

echo "Checking conversation delete API"
curl -fsS -X DELETE "${BASE_URL}/api/v1/conversations/${CONVERSATION_ID}" \
  -H "X-User-Id: ${USER_ID}"
if [ "$(curl -s -o /dev/null -w '%{http_code}' "${BASE_URL}/api/v1/conversations/${CONVERSATION_ID}" -H "X-User-Id: ${USER_ID}")" != "404" ]; then
  echo "Deleted conversation was still readable" >&2
  exit 1
fi
echo

echo "Smoke test passed"
