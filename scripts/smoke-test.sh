#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-http://localhost:8000}"
USER_ID="smoke-test-user"

echo "Checking health: ${BASE_URL}/health"
curl -fsS "${BASE_URL}/health"
echo

echo "Checking chat API"
curl -fsS -X POST "${BASE_URL}/api/v1/chat" \
  -H "Content-Type: application/json" \
  -H "X-User-Id: ${USER_ID}" \
  -d '{"message":"I want a relaxed 3-day Chengdu food trip.","mode":"TRIP_PLANNING"}'
echo

echo "Checking trip plan API"
curl -fsS -X POST "${BASE_URL}/api/v1/trip-plan" \
  -H "Content-Type: application/json" \
  -H "X-User-Id: ${USER_ID}" \
  -d '{"destination":"Chengdu","days":3,"budget":"moderate","interests":"local food, city walk"}'
echo

echo "Checking conversation list API"
curl -fsS "${BASE_URL}/api/v1/conversations?page=1&pageSize=20" \
  -H "X-User-Id: ${USER_ID}"
echo

echo "Checking trip plan history API"
TRIP_PLANS_JSON="$(curl -fsS "${BASE_URL}/api/v1/trip-plans?page=1&pageSize=20" \
  -H "X-User-Id: ${USER_ID}")"
echo "${TRIP_PLANS_JSON}"
echo

TRIP_PLAN_ID="$(printf '%s' "${TRIP_PLANS_JSON}" | python3 -c 'import json, sys; data = json.load(sys.stdin).get("data", []); print(data[0]["id"] if data else "")')"
if [ -z "${TRIP_PLAN_ID}" ]; then
  echo "Trip plan history did not return a saved plan" >&2
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

echo "Smoke test passed"
