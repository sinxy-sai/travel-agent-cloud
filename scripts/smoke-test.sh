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
rm -f "${HEALTH_HEADERS}"
HAS_MESSAGE_QUEUE_FIELD="$(printf '%s' "${HEALTH_JSON}" | python3 -c 'import json, sys; print("yes" if "messageQueueEnabled" in json.load(sys.stdin) else "no")')"
if [ "${HAS_MESSAGE_QUEUE_FIELD}" != "yes" ]; then
  echo "Health API did not return messageQueueEnabled" >&2
  exit 1
fi
echo

echo "Checking auth API"
AUTH_COOKIE_JAR="$(mktemp)"
AUTH_EMAIL="smoke-$(date +%s)-$$@example.com"
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
CURRENT_AUTH_USER_JSON="$(curl -fsS "${BASE_URL}/api/v1/auth/me" \
  -b "${AUTH_COOKIE_JAR}")"
CURRENT_AUTH_EMAIL="$(printf '%s' "${CURRENT_AUTH_USER_JSON}" | python3 -c 'import json, sys; print(json.load(sys.stdin).get("email", ""))')"
if [ "${CURRENT_AUTH_EMAIL}" != "${AUTH_EMAIL}" ]; then
  echo "Auth me API did not return the cookie-authenticated user" >&2
  rm -f "${AUTH_COOKIE_JAR}"
  exit 1
fi
curl -fsS -X POST "${BASE_URL}/api/v1/auth/logout" \
  -b "${AUTH_COOKIE_JAR}" \
  -c "${AUTH_COOKIE_JAR}"
LOGGED_OUT_STATUS="$(curl -s -o /dev/null -w '%{http_code}' "${BASE_URL}/api/v1/auth/me" \
  -b "${AUTH_COOKIE_JAR}")"
rm -f "${AUTH_COOKIE_JAR}"
if [ "${LOGGED_OUT_STATUS}" != "401" ]; then
  echo "Auth me API accepted a logged-out session" >&2
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
