#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-http://localhost:8000}"
USER_ID="smoke-test-user"

echo "Checking health: ${BASE_URL}/health"
HEALTH_HEADERS="$(mktemp)"
curl -fsS -D "${HEALTH_HEADERS}" "${BASE_URL}/health"
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
