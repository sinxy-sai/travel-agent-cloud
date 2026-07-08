#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-http://localhost:8000}"

echo "Checking health: ${BASE_URL}/health"
curl -fsS "${BASE_URL}/health"
echo

echo "Checking chat API"
curl -fsS -X POST "${BASE_URL}/api/v1/chat" \
  -H "Content-Type: application/json" \
  -d '{"message":"I want a relaxed 3-day Chengdu food trip.","mode":"TRIP_PLANNING"}'
echo

echo "Checking trip plan API"
curl -fsS -X POST "${BASE_URL}/api/v1/trip-plan" \
  -H "Content-Type: application/json" \
  -d '{"destination":"Chengdu","days":3,"budget":"moderate","interests":"local food, city walk"}'
echo

echo "Smoke test passed"

