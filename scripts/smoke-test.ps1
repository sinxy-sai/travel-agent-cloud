param(
  [string]$BaseUrl = "http://localhost:8000"
)

$ErrorActionPreference = "Stop"

Write-Host "Checking health: $BaseUrl/health"
Invoke-RestMethod -Uri "$BaseUrl/health"

Write-Host "Checking chat API"
$chatBody = @{
  message = "I want a relaxed 3-day Chengdu food trip."
  mode = "TRIP_PLANNING"
} | ConvertTo-Json
Invoke-RestMethod -Uri "$BaseUrl/api/v1/chat" -Method Post -ContentType "application/json" -Body $chatBody

Write-Host "Checking trip plan API"
$tripBody = @{
  destination = "Chengdu"
  days = 3
  budget = "moderate"
  interests = "local food, city walk"
} | ConvertTo-Json
Invoke-RestMethod -Uri "$BaseUrl/api/v1/trip-plan" -Method Post -ContentType "application/json" -Body $tripBody

Write-Host "Smoke test passed"

