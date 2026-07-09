param(
  [string]$BaseUrl = "http://localhost:8000"
)

$ErrorActionPreference = "Stop"
$headers = @{
  "X-User-Id" = "smoke-test-user"
}

Write-Host "Checking health: $BaseUrl/health"
Invoke-RestMethod -Uri "$BaseUrl/health"

Write-Host "Checking chat API"
$chatBody = @{
  message = "I want a relaxed 3-day Chengdu food trip."
  mode = "TRIP_PLANNING"
} | ConvertTo-Json
Invoke-RestMethod -Uri "$BaseUrl/api/v1/chat" -Method Post -ContentType "application/json" -Headers $headers -Body $chatBody

Write-Host "Checking trip plan API"
$tripBody = @{
  destination = "Chengdu"
  days = 3
  budget = "moderate"
  interests = "local food, city walk"
} | ConvertTo-Json
Invoke-RestMethod -Uri "$BaseUrl/api/v1/trip-plan" -Method Post -ContentType "application/json" -Headers $headers -Body $tripBody

Write-Host "Checking conversation list API"
Invoke-RestMethod -Uri "$BaseUrl/api/v1/conversations?page=1&pageSize=20" -Headers $headers

Write-Host "Checking trip plan history API"
Invoke-RestMethod -Uri "$BaseUrl/api/v1/trip-plans?page=1&pageSize=20" -Headers $headers

Write-Host "Smoke test passed"
