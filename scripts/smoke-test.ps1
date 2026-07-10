param(
  [string]$BaseUrl = "http://localhost:8000"
)

$ErrorActionPreference = "Stop"
$headers = @{
  "X-User-Id" = "smoke-test-user"
}

Write-Host "Checking health: $BaseUrl/health"
$healthResponse = Invoke-WebRequest -Uri "$BaseUrl/health"
if (-not $healthResponse.Headers["X-Request-ID"]) {
  throw "Health API did not return X-Request-ID"
}
if (-not $healthResponse.Headers["X-Process-Time-Ms"]) {
  throw "Health API did not return X-Process-Time-Ms"
}
$health = $healthResponse.Content | ConvertFrom-Json
$health
if (-not ($health.PSObject.Properties.Name -contains "messageQueueEnabled")) {
  throw "Health API did not return messageQueueEnabled"
}

Write-Host "Checking user profile API"
$profileBody = @{
  displayName = "Smoke Test Traveler"
  homeCity = "Beijing"
  preferredBudget = "moderate"
  travelStyle = "relaxed city walks"
  interests = @("local food", "museums")
} | ConvertTo-Json
$updatedProfile = Invoke-RestMethod -Uri "$BaseUrl/api/v1/me/profile" -Method Patch -ContentType "application/json" -Headers $headers -Body $profileBody
if ($updatedProfile.displayName -ne "Smoke Test Traveler") {
  throw "User profile API did not persist displayName"
}
if (-not ($updatedProfile.interests -contains "local food")) {
  throw "User profile API did not persist interests"
}
$loadedProfile = Invoke-RestMethod -Uri "$BaseUrl/api/v1/me/profile" -Headers $headers
if ($loadedProfile.preferredBudget -ne "moderate") {
  throw "User profile API did not load persisted preferredBudget"
}

Write-Host "Checking chat API"
$chatBody = @{
  message = "I want a relaxed 3-day Chengdu food trip."
  mode = "TRIP_PLANNING"
} | ConvertTo-Json
$chatResponse = Invoke-RestMethod -Uri "$BaseUrl/api/v1/chat" -Method Post -ContentType "application/json" -Headers $headers -Body $chatBody
if (-not $chatResponse.suggestions -or $chatResponse.suggestions.Count -eq 0) {
  throw "Chat API did not return suggestions"
}
if (-not $chatResponse.conversationId) {
  throw "Chat API did not return conversationId"
}

Write-Host "Checking trip plan API"
$tripBody = @{
  destination = "Chengdu"
  days = 3
  budget = "moderate"
  interests = "local food, city walk"
  conversationId = $chatResponse.conversationId
} | ConvertTo-Json
$createdTripPlan = Invoke-RestMethod -Uri "$BaseUrl/api/v1/trip-plan" -Method Post -ContentType "application/json" -Headers $headers -Body $tripBody
if (-not $createdTripPlan.savedTripPlanId) {
  throw "Trip plan API did not return savedTripPlanId"
}
if ($createdTripPlan.conversationId -ne $chatResponse.conversationId) {
  throw "Trip plan API did not bind to the active conversation"
}

Write-Host "Checking conversation list API"
$conversations = Invoke-RestMethod -Uri "$BaseUrl/api/v1/conversations?page=1&pageSize=20" -Headers $headers

if (-not $conversations.data -or $conversations.data.Count -eq 0) {
  throw "Conversation history did not return a saved conversation"
}
$searchConversations = Invoke-RestMethod -Uri "$BaseUrl/api/v1/conversations?page=1&pageSize=20&query=Chengdu" -Headers $headers
if (-not ($searchConversations.data | Where-Object { $_.id -eq $chatResponse.conversationId })) {
  throw "Conversation query filter did not return the created Chengdu conversation"
}

Write-Host "Checking conversation rename API"
$renameBody = @{
  title = "Chengdu planning thread"
} | ConvertTo-Json
$renamedConversation = Invoke-RestMethod -Uri "$BaseUrl/api/v1/conversations/$($chatResponse.conversationId)" -Method Patch -ContentType "application/json" -Headers $headers -Body $renameBody
if ($renamedConversation.title -ne "Chengdu planning thread") {
  throw "Conversation rename API did not persist title"
}
$renamedSearchConversations = Invoke-RestMethod -Uri "$BaseUrl/api/v1/conversations?page=1&pageSize=20&query=planning" -Headers $headers
if (-not ($renamedSearchConversations.data | Where-Object { $_.id -eq $chatResponse.conversationId })) {
  throw "Conversation query filter did not return the renamed conversation"
}

Write-Host "Checking conversation summary API"
$summary = Invoke-RestMethod -Uri "$BaseUrl/api/v1/conversations/$($chatResponse.conversationId)/summary" -Method Post -Headers $headers
if (-not $summary.summary -or $summary.messageCount -lt 1) {
  throw "Conversation summary API did not return a persisted summary"
}
$loadedSummary = Invoke-RestMethod -Uri "$BaseUrl/api/v1/conversations/$($chatResponse.conversationId)/summary" -Headers $headers
if ($loadedSummary.id -ne $summary.id) {
  throw "Conversation summary API did not load the latest persisted summary"
}

Write-Host "Checking conversation async summary job API"
if ($health.messageQueueEnabled) {
  $summaryJob = Invoke-RestMethod -Uri "$BaseUrl/api/v1/conversations/$($chatResponse.conversationId)/summary-jobs" -Method Post -Headers $headers
  if ($summaryJob.status -ne "QUEUED") {
    throw "Conversation summary job API did not return QUEUED status"
  }
} else {
  try {
    Invoke-RestMethod -Uri "$BaseUrl/api/v1/conversations/$($chatResponse.conversationId)/summary-jobs" -Method Post -Headers $headers
    throw "Conversation summary job API accepted a job without RabbitMQ"
  } catch {
    if ($_.Exception.Response.StatusCode.value__ -ne 503) {
      throw
    }
  }
}

Write-Host "Checking trip plan history API"
$tripPlans = Invoke-RestMethod -Uri "$BaseUrl/api/v1/trip-plans?page=1&pageSize=20" -Headers $headers

if (-not $tripPlans.data -or $tripPlans.data.Count -eq 0) {
  throw "Trip plan history did not return a saved plan"
}

Write-Host "Checking trip plan favorite API"
$favoriteBody = @{
  favorite = $true
} | ConvertTo-Json
$favoriteTripPlan = Invoke-RestMethod -Uri "$BaseUrl/api/v1/trip-plans/$($createdTripPlan.savedTripPlanId)" -Method Patch -ContentType "application/json" -Headers $headers -Body $favoriteBody
if (-not $favoriteTripPlan.favorite) {
  throw "Trip plan favorite API did not persist favorite=true"
}
$favoriteTripPlans = Invoke-RestMethod -Uri "$BaseUrl/api/v1/trip-plans?page=1&pageSize=20" -Headers $headers
if (-not $favoriteTripPlans.data[0].favorite) {
  throw "Trip plan history did not sort favorite plans first"
}
$favoriteOnlyTripPlans = Invoke-RestMethod -Uri "$BaseUrl/api/v1/trip-plans?page=1&pageSize=20&favoriteOnly=true" -Headers $headers
if (-not $favoriteOnlyTripPlans.data -or -not $favoriteOnlyTripPlans.data[0].favorite) {
  throw "Trip plan favoriteOnly filter did not return favorite plans"
}
$searchTripPlans = Invoke-RestMethod -Uri "$BaseUrl/api/v1/trip-plans?page=1&pageSize=20&query=Chengdu" -Headers $headers
if (-not ($searchTripPlans.data | Where-Object { $_.id -eq $createdTripPlan.savedTripPlanId })) {
  throw "Trip plan query filter did not return the created Chengdu plan"
}

Write-Host "Checking trip plan export API"
$markdown = Invoke-RestMethod -Uri "$BaseUrl/api/v1/trip-plans/$($createdTripPlan.savedTripPlanId)/export" -Headers $headers
if (-not ($markdown -like "# *")) {
  throw "Trip plan export did not return markdown"
}

Write-Host "Checking trip plan delete API"
$tripPlanId = $createdTripPlan.savedTripPlanId
Invoke-RestMethod -Uri "$BaseUrl/api/v1/trip-plans/$tripPlanId" -Method Delete -Headers $headers
try {
  Invoke-RestMethod -Uri "$BaseUrl/api/v1/trip-plans/$tripPlanId" -Headers $headers
  throw "Deleted trip plan was still readable"
} catch {
  if ($_.Exception.Response.StatusCode.value__ -ne 404) {
    throw
  }
}

Write-Host "Checking conversation delete API"
$conversationId = $conversations.data[0].id
Invoke-RestMethod -Uri "$BaseUrl/api/v1/conversations/$conversationId" -Method Delete -Headers $headers
try {
  Invoke-RestMethod -Uri "$BaseUrl/api/v1/conversations/$conversationId" -Headers $headers
  throw "Deleted conversation was still readable"
} catch {
  if ($_.Exception.Response.StatusCode.value__ -ne 404) {
    throw
  }
}

Write-Host "Smoke test passed"
