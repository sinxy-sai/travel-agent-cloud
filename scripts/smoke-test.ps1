param(
  [string]$BaseUrl = "http://localhost:8000"
)

$ErrorActionPreference = "Stop"
$headers = @{
  "X-User-Id" = "smoke-test-user"
}

Write-Host "Checking health: $BaseUrl/health"
$healthResponse = Invoke-WebRequest -Uri "$BaseUrl/health" -UseBasicParsing
if (-not $healthResponse.Headers["X-Request-ID"]) {
  throw "Health API did not return X-Request-ID"
}
if (-not $healthResponse.Headers["X-Process-Time-Ms"]) {
  throw "Health API did not return X-Process-Time-Ms"
}
if ($healthResponse.Headers["X-Content-Type-Options"] -ne "nosniff") {
  throw "Health API did not return X-Content-Type-Options"
}
$health = $healthResponse.Content | ConvertFrom-Json
$health
if (-not ($health.PSObject.Properties.Name -contains "messageQueueEnabled")) {
  throw "Health API did not return messageQueueEnabled"
}
if (-not ($health.PSObject.Properties.Name -contains "githubOAuthEnabled")) {
  throw "Health API did not return githubOAuthEnabled"
}
if (-not ($health.PSObject.Properties.Name -contains "redisRateLimitEnabled")) {
  throw "Health API did not return redisRateLimitEnabled"
}
if (-not ($health.PSObject.Properties.Name -contains "objectStorageEnabled")) {
  throw "Health API did not return objectStorageEnabled"
}
if (-not ($health.PSObject.Properties.Name -contains "agentEngine")) {
  throw "Health API did not return agentEngine"
}
if (-not ($health.PSObject.Properties.Name -contains "agentEngineCapabilities")) {
  throw "Health API did not return agentEngineCapabilities"
}
if (-not ($health.PSObject.Properties.Name -contains "travelToolsProvider")) {
  throw "Health API did not return travelToolsProvider"
}
$agentStatus = Invoke-RestMethod -Uri "$BaseUrl/api/v1/agent/status"
if (-not $agentStatus.engine -or -not $agentStatus.capabilities) {
  throw "Agent status API did not return engine capabilities"
}

Write-Host "Preparing anonymous local data"
$anonymousUserId = "smoke-anon-$([guid]::NewGuid().ToString('N'))"
$anonymousHeaders = @{
  "X-User-Id" = $anonymousUserId
}
$anonymousChatBody = @{
  message = "Plan a relaxed 2-day Hangzhou tea and lake trip."
  mode = "TRIP_PLANNING"
} | ConvertTo-Json
$anonymousChatResponse = Invoke-RestMethod -Uri "$BaseUrl/api/v1/chat" -Method Post -ContentType "application/json" -Headers $anonymousHeaders -Body $anonymousChatBody
if (-not $anonymousChatResponse.conversationId) {
  throw "Anonymous chat API did not return conversationId"
}
$anonymousTripBody = @{
  destination = "Hangzhou"
  days = 2
  budget = "moderate"
  interests = "tea, lake"
  conversationId = $anonymousChatResponse.conversationId
} | ConvertTo-Json
$anonymousTripPlan = Invoke-RestMethod -Uri "$BaseUrl/api/v1/trip-plan" -Method Post -ContentType "application/json" -Headers $anonymousHeaders -Body $anonymousTripBody
if (-not $anonymousTripPlan.savedTripPlanId) {
  throw "Anonymous trip plan API did not return savedTripPlanId"
}

Write-Host "Checking auth API"
$authSession = New-Object Microsoft.PowerShell.Commands.WebRequestSession
$authEmail = "smoke-$([guid]::NewGuid().ToString('N'))@example.com"
$authBody = @{
  email = $authEmail
  password = "SmokeTest123!"
  displayName = "Smoke Test Account"
} | ConvertTo-Json
$changedPassword = "SmokeTest456!"
$registeredSession = Invoke-RestMethod -Uri "$BaseUrl/api/v1/auth/register" -Method Post -ContentType "application/json" -WebSession $authSession -Body $authBody
if ($registeredSession.user.email -ne $authEmail) {
  throw "Auth register API did not return the created user"
}
if ($registeredSession.user.emailVerified) {
  throw "Newly registered accounts should start with emailVerified=false"
}
if (-not $registeredSession.user.passwordConfigured) {
  throw "Password registration should return passwordConfigured=true"
}
$currentAuthUser = Invoke-RestMethod -Uri "$BaseUrl/api/v1/auth/me" -WebSession $authSession
if ($currentAuthUser.email -ne $authEmail) {
  throw "Auth me API did not return the cookie-authenticated user"
}
if (-not $currentAuthUser.passwordConfigured) {
  throw "Auth me API should return passwordConfigured=true for password accounts"
}
$authSessions = Invoke-RestMethod -Uri "$BaseUrl/api/v1/auth/sessions" -WebSession $authSession
if (-not $authSessions.data -or $authSessions.data.Count -lt 1) {
  throw "Auth sessions API did not return the current session"
}
if (-not ($authSessions.data | Where-Object { $_.current })) {
  throw "Auth sessions API did not mark the current session"
}
$revokeOtherSessionsResponse = Invoke-RestMethod -Uri "$BaseUrl/api/v1/auth/sessions/revoke-all" -Method Post -WebSession $authSession
if (-not ($revokeOtherSessionsResponse.PSObject.Properties.Name -contains "revoked")) {
  throw "Auth revoke other sessions API did not return revoked count"
}
try {
  Invoke-RestMethod -Uri "$BaseUrl/api/v1/me/export" -WebSession $authSession
  throw "User data export API accepted an unverified account"
} catch {
  if ($_.Exception.Response.StatusCode.value__ -ne 403) {
    throw
  }
}
$emailVerifiedForAccountData = [bool]$currentAuthUser.emailVerified
$verificationResponse = Invoke-RestMethod -Uri "$BaseUrl/api/v1/auth/email-verification/request" -Method Post -WebSession $authSession
if ($verificationResponse.PSObject.Properties.Name -contains "devToken" -and $verificationResponse.devToken) {
  $verifiedAuthUser = Invoke-RestMethod -Uri "$BaseUrl/api/v1/auth/email-verification/confirm" -Method Post -ContentType "application/json" -Body (@{
    token = $verificationResponse.devToken
  } | ConvertTo-Json)
  if (-not $verifiedAuthUser.emailVerified) {
    throw "Email verification API did not mark the user as verified"
  }
  $emailVerifiedForAccountData = $true
}
$missingResetResponse = Invoke-RestMethod -Uri "$BaseUrl/api/v1/auth/password-reset/request" -Method Post -ContentType "application/json" -Body (@{
  email = "missing-$([guid]::NewGuid().ToString('N'))@example.com"
} | ConvertTo-Json)
if (-not $missingResetResponse.sent) {
  throw "Password reset request should return a generic accepted response for missing email"
}
$securityEvents = Invoke-RestMethod -Uri "$BaseUrl/api/v1/auth/security-events?page=1&pageSize=5" -WebSession $authSession
if (-not $securityEvents.data -or $securityEvents.data.Count -eq 0) {
  throw "Security events API did not return recent account activity"
}
$authIdentities = Invoke-RestMethod -Uri "$BaseUrl/api/v1/auth/identities" -WebSession $authSession
if (-not ($authIdentities.PSObject.Properties.Name -contains "data")) {
  throw "Auth identities API did not return data"
}
$accountUpdateBody = @{
  displayName = "Updated Smoke Account"
} | ConvertTo-Json
$updatedAuthUser = Invoke-RestMethod -Uri "$BaseUrl/api/v1/auth/me" -Method Patch -ContentType "application/json" -WebSession $authSession -Body $accountUpdateBody
if ($updatedAuthUser.displayName -ne "Updated Smoke Account") {
  throw "Auth user update API did not persist displayName"
}
if ($emailVerifiedForAccountData) {
  $exportedUserData = Invoke-RestMethod -Uri "$BaseUrl/api/v1/me/export" -WebSession $authSession
  if ($exportedUserData.user.email -ne $authEmail) {
    throw "User data export API did not return the authenticated user"
  }
  if (-not ($exportedUserData.PSObject.Properties.Name -contains "conversations")) {
    throw "User data export API did not return conversations"
  }
  if ($health.objectStorageEnabled) {
    $archivedExport = Invoke-RestMethod -Uri "$BaseUrl/api/v1/me/export-files" -Method Post -WebSession $authSession
    if (-not $archivedExport.id -or $archivedExport.sizeBytes -lt 1) {
      throw "Object storage export API did not return an archived file"
    }
    $archivedExportResponse = Invoke-WebRequest -Uri "$BaseUrl/api/v1/me/export-files/$($archivedExport.id)" -UseBasicParsing -WebSession $authSession
    $archivedExportData = $archivedExportResponse.Content | ConvertFrom-Json
    if ($archivedExportData.user.email -ne $authEmail) {
      throw "Archived user export download did not return the authenticated user data"
    }
  }
  $importedUserData = Invoke-RestMethod -Uri "$BaseUrl/api/v1/me/import" -Method Post -ContentType "application/json" -WebSession $authSession -Body ($exportedUserData | ConvertTo-Json -Depth 40)
  if (-not $importedUserData.profileImported) {
    throw "User data import API did not import the profile"
  }
  $anonymousSummary = Invoke-RestMethod -Uri "$BaseUrl/api/v1/me/anonymous-data/summary" -WebSession $authSession -Headers $anonymousHeaders
  if (-not $anonymousSummary.hasData -or $anonymousSummary.conversations -lt 1 -or $anonymousSummary.tripPlans -lt 1) {
    throw "Anonymous data summary API did not report local anonymous data"
  }
  $anonymousImportResult = Invoke-RestMethod -Uri "$BaseUrl/api/v1/me/anonymous-data/import" -Method Post -WebSession $authSession -Headers $anonymousHeaders
  if ($anonymousImportResult.conversationsImported -lt 1 -or $anonymousImportResult.tripPlansImported -lt 1) {
    throw "Anonymous data import API did not import local conversations and trip plans"
  }
  $exportedAfterAnonymousImport = Invoke-RestMethod -Uri "$BaseUrl/api/v1/me/export" -WebSession $authSession
  if (-not ($exportedAfterAnonymousImport.conversations | Where-Object { $_.title -like "*Hangzhou*" -or ($_.messages | Where-Object { $_.content -like "*Hangzhou*" }) })) {
    throw "User data export did not include imported anonymous conversation"
  }
  if (-not ($exportedAfterAnonymousImport.tripPlans | Where-Object { $_.destination -eq "Hangzhou" })) {
    throw "User data export did not include imported anonymous trip plan"
  }
} else {
  Write-Host "Skipping verified account data import/export checks because no dev verification token was returned"
}
$resetPassword = "SmokeTest789!"
$resetResponse = Invoke-RestMethod -Uri "$BaseUrl/api/v1/auth/password-reset/request" -Method Post -ContentType "application/json" -Body (@{
  email = $authEmail
} | ConvertTo-Json)
if ($resetResponse.PSObject.Properties.Name -contains "devToken" -and $resetResponse.devToken) {
  Invoke-RestMethod -Uri "$BaseUrl/api/v1/auth/password-reset/confirm" -Method Post -ContentType "application/json" -Body (@{
    token = $resetResponse.devToken
    newPassword = $resetPassword
  } | ConvertTo-Json)
  $changedPassword = $resetPassword
} else {
  $passwordChangeBody = @{
    currentPassword = "SmokeTest123!"
    newPassword = $changedPassword
  } | ConvertTo-Json
  Invoke-RestMethod -Uri "$BaseUrl/api/v1/auth/password" -Method Patch -ContentType "application/json" -WebSession $authSession -Body $passwordChangeBody
}
Invoke-RestMethod -Uri "$BaseUrl/api/v1/auth/logout" -Method Post -WebSession $authSession
try {
  Invoke-RestMethod -Uri "$BaseUrl/api/v1/auth/me" -WebSession $authSession
  throw "Auth me API accepted a logged-out session"
} catch {
  if ($_.Exception.Response.StatusCode.value__ -ne 401) {
    throw
  }
}
$oldPasswordLoginBody = @{
  email = $authEmail
  password = "SmokeTest123!"
} | ConvertTo-Json
try {
  Invoke-RestMethod -Uri "$BaseUrl/api/v1/auth/login" -Method Post -ContentType "application/json" -WebSession $authSession -Body $oldPasswordLoginBody
  throw "Auth login accepted the old password after a password update"
} catch {
  if ($_.Exception.Response.StatusCode.value__ -ne 401) {
    throw
  }
}
$newPasswordLoginBody = @{
  email = $authEmail
  password = $changedPassword
} | ConvertTo-Json
$changedLoginSession = Invoke-RestMethod -Uri "$BaseUrl/api/v1/auth/login" -Method Post -ContentType "application/json" -WebSession $authSession -Body $newPasswordLoginBody
if ($changedLoginSession.user.email -ne $authEmail) {
  throw "Auth login did not accept the changed password"
}
if (-not $changedLoginSession.user.passwordConfigured) {
  throw "Auth login should return passwordConfigured=true after password reset/change"
}
$deleteAccountBody = @{
  currentPassword = $changedPassword
  confirmation = "DELETE"
} | ConvertTo-Json
Invoke-RestMethod -Uri "$BaseUrl/api/v1/auth/me" -Method Delete -ContentType "application/json" -WebSession $authSession -Body $deleteAccountBody
try {
  Invoke-RestMethod -Uri "$BaseUrl/api/v1/auth/me" -WebSession $authSession
  throw "Auth me API accepted a deleted account session"
} catch {
  if ($_.Exception.Response.StatusCode.value__ -ne 401) {
    throw
  }
}
try {
  Invoke-RestMethod -Uri "$BaseUrl/api/v1/auth/login" -Method Post -ContentType "application/json" -WebSession $authSession -Body $newPasswordLoginBody
  throw "Auth login accepted a deleted account"
} catch {
  if ($_.Exception.Response.StatusCode.value__ -ne 401) {
    throw
  }
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
  startDate = "2026-08-01"
  endDate = "2026-08-03"
  transportation = "walking and metro"
  accommodation = "comfortable hotel"
  preferences = @("local food", "city walk")
  freeTextInput = "Keep mornings relaxed and avoid packed schedules."
  conversationId = $chatResponse.conversationId
} | ConvertTo-Json
$createdTripPlan = Invoke-RestMethod -Uri "$BaseUrl/api/v1/trip-plan" -Method Post -ContentType "application/json" -Headers $headers -Body $tripBody
if (-not $createdTripPlan.savedTripPlanId) {
  throw "Trip plan API did not return savedTripPlanId"
}
if ($createdTripPlan.conversationId -ne $chatResponse.conversationId) {
  throw "Trip plan API did not bind to the active conversation"
}
if (-not $createdTripPlan.weatherInfo -or $createdTripPlan.weatherInfo.Count -lt 1) {
  throw "Trip plan API did not return weatherInfo"
}
if (-not $createdTripPlan.budget -or $createdTripPlan.budget.total -lt 1) {
  throw "Trip plan API did not return budget totals"
}
if (-not $createdTripPlan.days[0].attractions -or $createdTripPlan.days[0].attractions.Count -lt 1) {
  throw "Trip plan API did not return day attractions"
}
if (-not $createdTripPlan.days[0].meals -or $createdTripPlan.days[0].meals.Count -lt 1) {
  throw "Trip plan API did not return day meals"
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
  if (-not $summaryJob.id) {
    throw "Conversation summary job API did not return job id"
  }
  if ($summaryJob.status -ne "QUEUED") {
    throw "Conversation summary job API did not return QUEUED status"
  }
  $latestSummaryJob = Invoke-RestMethod -Uri "$BaseUrl/api/v1/conversations/$($chatResponse.conversationId)/summary-jobs/latest" -Headers $headers
  if ($latestSummaryJob.id -ne $summaryJob.id) {
    throw "Conversation summary latest job API did not return the queued job"
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

Write-Host "Checking trip plan content update and version conflict API"
$savedTripPlan = Invoke-RestMethod -Uri "$BaseUrl/api/v1/trip-plans/$($createdTripPlan.savedTripPlanId)" -Headers $headers
$initialTripPlanVersion = [int]$savedTripPlan.version
$editedTripTitle = -join ([char[]](0x0033, 0x5929, 0x6210, 0x90FD, 0x4E4B, 0x65C5))
$savedTripPlan.plan.title = $editedTripTitle
$savedTripPlan.plan.startDate = "2026-08-02"
$savedTripPlan.plan.endDate = "2026-08-05"
$savedTripPlan.plan.transportation = "metro, walking, and taxi"
$savedTripPlan.plan.accommodation = "boutique hotel near transit"
$savedTripPlan.plan.preferences = @("local food", "city walk", "tea house")
$savedTripPlan.plan.freeTextInput = "Keep the plan editable and leave room for a slow afternoon."
$savedTripPlan.plan.overallSuggestions = "Carry an umbrella and reserve dinner before peak hours."

$editedDays = @($savedTripPlan.plan.days)
if ($editedDays.Count -lt 3) {
  throw "Trip plan update setup expected at least 3 days"
}
$extraDay = [pscustomobject]@{
  day = 4
  theme = "Slow departure day"
  morning = "Pack and visit a neighborhood breakfast shop."
  afternoon = "Take a short walk near the station before departure."
  evening = "Depart Chengdu."
  date = "2026-08-05"
  description = "A lighter added day created by the itinerary editor."
  transportation = "taxi and metro"
  accommodation = "checkout day"
  hotel = $null
  attractions = @(
    [pscustomobject]@{
      name = "People's Park tea house"
      address = "Chengdu"
      location = $null
      visitDuration = 90
      description = "Classic relaxed tea house stop."
      category = "tea house"
      rating = $null
      imageUrl = $null
      ticketPrice = 0
    }
  )
  meals = @(
    [pscustomobject]@{
      type = "breakfast"
      name = "Neighborhood noodle breakfast"
      address = "Chengdu"
      location = $null
      description = "Simple local breakfast before checkout."
      estimatedCost = 30
    }
  )
}
$reorderedDays = @($editedDays[1], $editedDays[0], $editedDays[2], $extraDay)
for ($i = 0; $i -lt $reorderedDays.Count; $i++) {
  $reorderedDays[$i].day = $i + 1
}
$savedTripPlan.plan.days = $reorderedDays
$savedTripPlan.plan.weatherInfo = @(
  [pscustomobject]@{
    date = "2026-08-05"
    dayWeather = "Cloudy"
    nightWeather = "Light rain"
    dayTemp = 28
    nightTemp = 22
    windDirection = "NE"
    windPower = "2"
  }
)
$savedTripPlan.plan.budget.totalAttractions = 1
$savedTripPlan.plan.budget.totalHotels = 2
$savedTripPlan.plan.budget.totalMeals = 3
$savedTripPlan.plan.budget.totalTransportation = 180
$savedTripPlan.plan.budget.total = 4
$tripPlanUpdateBody = @{
  plan = $savedTripPlan.plan
  expectedVersion = $initialTripPlanVersion
} | ConvertTo-Json -Depth 40
$editedTripPlan = Invoke-RestMethod -Uri "$BaseUrl/api/v1/trip-plans/$($createdTripPlan.savedTripPlanId)" -Method Patch -ContentType "application/json" -Headers $headers -Body $tripPlanUpdateBody
if ($editedTripPlan.plan.title -ne $editedTripTitle) {
  throw "Trip plan content update API did not persist the edited title"
}
if ($editedTripPlan.days -ne 4 -or $editedTripPlan.plan.days.Count -ne 4) {
  throw "Trip plan content update API did not persist edited day count"
}
for ($i = 0; $i -lt $editedTripPlan.plan.days.Count; $i++) {
  if ($editedTripPlan.plan.days[$i].day -ne ($i + 1)) {
    throw "Trip plan content update API did not preserve sequential day numbers"
  }
}
if ($editedTripPlan.plan.startDate -ne "2026-08-02" -or $editedTripPlan.plan.endDate -ne "2026-08-05") {
  throw "Trip plan content update API did not persist edited dates"
}
if ($editedTripPlan.plan.preferences.Count -ne 3 -or -not ($editedTripPlan.plan.preferences -contains "tea house")) {
  throw "Trip plan content update API did not persist edited preferences"
}
if ($editedTripPlan.plan.weatherInfo.Count -ne 1 -or $editedTripPlan.plan.weatherInfo[0].dayWeather -ne "Cloudy") {
  throw "Trip plan content update API did not persist edited weatherInfo"
}
$expectedAttractions = 0
$expectedHotels = 0
$expectedMeals = 0
foreach ($day in $editedTripPlan.plan.days) {
  if ($day.attractions) {
    foreach ($attraction in @($day.attractions)) {
      $expectedAttractions += [int]$attraction.ticketPrice
    }
  }
  if ($day.hotel) {
    $expectedHotels += [int]$day.hotel.estimatedCost
  }
  if ($day.meals) {
    foreach ($meal in @($day.meals)) {
      $expectedMeals += [int]$meal.estimatedCost
    }
  }
}
$expectedTotal = $expectedAttractions + $expectedHotels + $expectedMeals + 180
if (
  $editedTripPlan.plan.budget.totalAttractions -ne $expectedAttractions -or
  $editedTripPlan.plan.budget.totalHotels -ne $expectedHotels -or
  $editedTripPlan.plan.budget.totalMeals -ne $expectedMeals -or
  $editedTripPlan.plan.budget.totalTransportation -ne 180 -or
  $editedTripPlan.plan.budget.total -ne $expectedTotal
) {
  throw "Trip plan content update API did not canonicalize edited budget from itinerary details"
}
if ([int]$editedTripPlan.version -ne ($initialTripPlanVersion + 1)) {
  throw "Trip plan content update API did not increment the version"
}
try {
  Invoke-RestMethod -Uri "$BaseUrl/api/v1/trip-plans/$($createdTripPlan.savedTripPlanId)" -Method Patch -ContentType "application/json" -Headers $headers -Body $tripPlanUpdateBody
  throw "Trip plan content update API accepted a stale version"
} catch {
  if ($_.Exception.Response.StatusCode.value__ -ne 409) {
    throw
  }
}

Write-Host "Checking trip plan day regeneration API"
$dayRegenerationBody = @{
  instruction = "Make this day slower and add a local food stop"
  expectedVersion = [int]$editedTripPlan.version
} | ConvertTo-Json
$regeneratedTripPlan = Invoke-RestMethod -Uri "$BaseUrl/api/v1/trip-plans/$($createdTripPlan.savedTripPlanId)/days/2/regenerate" -Method Post -ContentType "application/json" -Headers $headers -Body $dayRegenerationBody
$regeneratedDay = $regeneratedTripPlan.plan.days | Where-Object { $_.day -eq 2 } | Select-Object -First 1
if (-not $regeneratedDay -or -not $regeneratedDay.theme -or -not $regeneratedDay.morning -or -not $regeneratedDay.afternoon -or -not $regeneratedDay.evening) {
  throw "Trip plan day regeneration API did not update day 2"
}
if ([int]$regeneratedTripPlan.version -ne ([int]$editedTripPlan.version + 1)) {
  throw "Trip plan day regeneration API did not increment the version"
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
if (-not ($markdown -like "*## Budget*") -or -not ($markdown -like "*#### Attractions*")) {
  throw "Trip plan export did not include rich itinerary sections"
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
