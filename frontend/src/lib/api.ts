import axios from 'axios';

export interface TripPlanRequest {
  destination: string;
  days: number;
  budget: string;
  interests: string;
  startDate?: string;
  endDate?: string;
  transportation?: string;
  accommodation?: string;
  preferences?: string[];
  freeTextInput?: string;
  conversationId?: string;
}

export interface Location {
  longitude: number;
  latitude: number;
}

export interface Attraction {
  name: string;
  address: string;
  location?: Location | null;
  visitDuration: number;
  description: string;
  category: string;
  rating?: number | null;
  imageUrl?: string | null;
  ticketPrice: number;
}

export interface Meal {
  type: string;
  name: string;
  address: string;
  location?: Location | null;
  description: string;
  estimatedCost: number;
}

export interface Hotel {
  name: string;
  address: string;
  location?: Location | null;
  priceRange: string;
  rating: string;
  distance: string;
  type: string;
  estimatedCost: number;
}

export interface Budget {
  totalAttractions: number;
  totalHotels: number;
  totalMeals: number;
  totalTransportation: number;
  total: number;
}

export interface WeatherInfo {
  date: string;
  dayWeather: string;
  nightWeather: string;
  dayTemp: number;
  nightTemp: number;
  windDirection: string;
  windPower: string;
}

export interface TripDay {
  day: number;
  theme: string;
  morning: string;
  afternoon: string;
  evening: string;
  date?: string | null;
  description?: string;
  transportation?: string;
  accommodation?: string;
  hotel?: Hotel | null;
  attractions?: Attraction[];
  meals?: Meal[];
}

export interface TripPlanResponse {
  title: string;
  summary: string;
  days: TripDay[];
  tips: string[];
  startDate?: string | null;
  endDate?: string | null;
  transportation?: string;
  accommodation?: string;
  preferences?: string[];
  freeTextInput?: string;
  weatherInfo?: WeatherInfo[];
  overallSuggestions?: string;
  budget?: Budget | null;
  savedTripPlanId?: string;
  conversationId?: string;
}

export interface SavedTripPlan {
  id: string;
  conversationId?: string;
  title: string;
  destination: string;
  days: number;
  budget: string;
  interests: string;
  plan: TripPlanResponse;
  favorite: boolean;
  version: number;
  createdAt: string;
  updatedAt?: string | null;
}

export interface TripPlanUpdateRequest {
  favorite?: boolean;
  plan?: TripPlanResponse;
  expectedVersion?: number;
}

export interface TripDayRegenerateRequest {
  instruction: string;
  expectedVersion: number;
}

export interface TripPlanListResponse {
  data: SavedTripPlan[];
  page: number;
  pageSize: number;
  totalItems: number;
  totalPages: number;
}

export interface TripPlanListParams {
  favoriteOnly?: boolean;
  query?: string;
}

export type MessageRole = 'USER' | 'ASSISTANT' | 'SYSTEM';
export type AgentMode = 'CHAT' | 'TRIP_PLANNING';

export interface ChatRequest {
  message: string;
  conversationId?: string;
  mode?: AgentMode;
}

export interface ChatMessage {
  id: string;
  role: MessageRole;
  content: string;
  createdAt: string;
}

export interface ChatResponse {
  conversationId: string;
  message: ChatMessage;
  suggestions: string[];
}

export interface Conversation {
  id: string;
  mode: AgentMode;
  title: string;
  createdAt: string;
  updatedAt: string;
  messages: ChatMessage[];
}

export interface ConversationSummary {
  id: string;
  conversationId: string;
  summary: string;
  messageCount: number;
  createdAt: string;
  updatedAt: string;
}

export interface ConversationSummaryJob {
  id: string;
  conversationId: string;
  status: 'QUEUED' | 'RUNNING' | 'SUCCEEDED' | 'FAILED';
  eventType: string;
  errorMessage?: string | null;
  createdAt: string;
  updatedAt: string;
  completedAt?: string | null;
}

export interface ConversationListResponse {
  data: Conversation[];
  page: number;
  pageSize: number;
  totalItems: number;
  totalPages: number;
}

export interface ConversationListParams {
  query?: string;
}

export interface HealthResponse {
  status: string;
  service: string;
  env: string;
  llmEnabled: boolean;
  databaseEnabled: boolean;
  messageQueueEnabled: boolean;
  redisRateLimitEnabled: boolean;
  objectStorageEnabled: boolean;
  githubOAuthEnabled: boolean;
  agentEngine: string;
  agentEngineCapabilities: AgentEngineCapabilities;
  travelToolsProvider: string;
}

export interface AgentEngineCapabilities {
  supportsChat: boolean;
  supportsTripPlanning: boolean;
  supportsDayRegeneration: boolean;
  workflowNodes: string[];
  dependencyMode: string;
}

export interface AgentRunTrace {
  runId: string;
  operation: string;
  engineName: string;
  startedAt: string;
  durationMs: number;
  workflowNodes: string[];
  completedNodes: string[];
  fallbackUsed: boolean;
  llmEnabled: boolean;
  nodeEvents?: AgentNodeEvent[];
  toolCalls?: AgentToolCall[];
}

export interface AgentNodeEvent {
  nodeName: string;
  status: string;
  detail: string;
}

export interface AgentToolCall {
  toolName: string;
  status: string;
  detail: string;
}

export interface AgentRunSummary {
  windowSize: number;
  totalRuns: number;
  fallbackRuns: number;
  averageDurationMs: number;
  operationCounts: Record<string, number>;
}

export interface AgentToolCallSummary {
  windowSize: number;
  totalToolCalls: number;
  failedToolCalls: number;
  toolCounts: Record<string, number>;
  statusCounts: Record<string, number>;
}

export interface AgentToolDefinition {
  name: string;
  category: string;
  description: string;
}

export interface AgentToolCatalog {
  provider: string;
  toolCount: number;
  tools: AgentToolDefinition[];
}

export interface AgentStatusResponse {
  engine: string;
  llmEnabled: boolean;
  capabilities: AgentEngineCapabilities;
  lastRunTrace?: AgentRunTrace | null;
  recentRunTraces: AgentRunTrace[];
  runSummary?: AgentRunSummary;
  toolCallSummary?: AgentToolCallSummary;
  toolCatalog?: AgentToolCatalog;
}

export type AgentDiagnosticCheckStatus = 'OK' | 'DEGRADED' | 'DISABLED' | 'FAILED';

export interface AgentDiagnosticCheck {
  name: string;
  status: AgentDiagnosticCheckStatus;
  detail: string;
}

export interface AgentDiagnosticsResponse {
  status: AgentDiagnosticCheckStatus;
  engine: string;
  dependencyMode: string;
  llmEnabled: boolean;
  toolProvider: string;
  checks: AgentDiagnosticCheck[];
  statusCounts: Record<string, number>;
  capabilities: AgentEngineCapabilities;
  toolCatalog: AgentToolCatalog;
  runSummary: AgentRunSummary;
  lastRunTrace?: AgentRunTrace | null;
}

export interface UserProfile {
  userId: string;
  displayName: string;
  homeCity: string;
  preferredBudget: string;
  travelStyle: string;
  interests: string[];
  updatedAt: string;
}

export interface UserProfileUpdateRequest {
  displayName?: string;
  homeCity?: string;
  preferredBudget?: string;
  travelStyle?: string;
  interests?: string[];
}

export interface AuthUser {
  id: string;
  email: string;
  displayName: string;
  emailVerified: boolean;
  passwordConfigured: boolean;
  createdAt: string;
}

export interface AuthSession {
  user: AuthUser;
}

export interface AuthSessionInfo {
  id: string;
  userId: string;
  userAgent: string;
  current: boolean;
  revoked: boolean;
  createdAt: string;
  lastSeenAt: string;
  expiresAt: string;
  revokedAt?: string | null;
}

export interface AuthSessionListResponse {
  data: AuthSessionInfo[];
}

export interface AuthSessionRevokeAllResponse {
  revoked: number;
}

export interface AuthIdentity {
  id: string;
  userId: string;
  provider: string;
  providerUserId: string;
  email: string;
  displayName: string;
  avatarUrl: string;
  createdAt: string;
}

export interface AuthIdentityListResponse {
  data: AuthIdentity[];
}

export interface UserSecurityEvent {
  id: string;
  eventType: string;
  details: Record<string, string | number | boolean>;
  createdAt: string;
}

export interface UserSecurityEventListResponse {
  data: UserSecurityEvent[];
  page: number;
  pageSize: number;
  totalItems: number;
  totalPages: number;
}

export interface AuthRegisterRequest {
  email: string;
  password: string;
  displayName?: string;
}

export interface AuthLoginRequest {
  email: string;
  password: string;
}

export interface AuthPasswordChangeRequest {
  currentPassword: string;
  newPassword: string;
}

export interface AuthEmailActionResponse {
  sent: boolean;
  delivery: string;
  expiresAt?: string | null;
  devToken?: string | null;
  actionUrl?: string | null;
}

export interface AuthEmailRequest {
  email: string;
}

export interface AuthTokenConfirmRequest {
  token: string;
}

export interface AuthPasswordResetConfirmRequest {
  token: string;
  newPassword: string;
}

export interface AuthAccountDeleteRequest {
  currentPassword: string;
  confirmation: string;
}

export interface AuthUserUpdateRequest {
  displayName: string;
}

export interface UserDataExport {
  exportedAt: string;
  user: AuthUser;
  profile: UserProfile;
  conversations: Conversation[];
  conversationSummaries: ConversationSummary[];
  tripPlans: SavedTripPlan[];
}

export interface UserExportFile {
  id: string;
  filename: string;
  contentType: string;
  sizeBytes: number;
  createdAt: string;
  downloadUrl: string;
}

export interface UserDataImportResponse {
  importedAt: string;
  profileImported: boolean;
  conversationsImported: number;
  conversationSummariesImported: number;
  tripPlansImported: number;
  skippedItems: number;
}

export interface AnonymousDataSummary {
  hasData: boolean;
  conversations: number;
  conversationSummaries: number;
  tripPlans: number;
}

const api = axios.create({
  baseURL: import.meta.env.VITE_AGENT_API_BASE_URL ?? '',
  timeout: 30000,
  withCredentials: true,
});

api.interceptors.request.use((config) => {
  config.headers.set('X-User-Id', getAnonymousUserId());
  return config;
});

export async function createTripPlan(request: TripPlanRequest): Promise<TripPlanResponse> {
  const response = await api.post<TripPlanResponse>('/api/v1/trip-plan', request);
  return response.data;
}

export async function getHealth(): Promise<HealthResponse> {
  const response = await api.get<HealthResponse>('/health');
  return response.data;
}

export async function getAgentStatus(): Promise<AgentStatusResponse> {
  const response = await api.get<AgentStatusResponse>('/api/v1/agent/status');
  return response.data;
}

export async function getAgentToolCatalog(): Promise<AgentToolCatalog> {
  const response = await api.get<AgentToolCatalog>('/api/v1/agent/tools');
  return response.data;
}

export async function getAgentDiagnostics(): Promise<AgentDiagnosticsResponse> {
  const response = await api.get<AgentDiagnosticsResponse>('/api/v1/agent/diagnostics');
  return response.data;
}

export async function registerUser(request: AuthRegisterRequest): Promise<AuthSession> {
  const response = await api.post<AuthSession>('/api/v1/auth/register', request);
  return response.data;
}

export async function loginUser(request: AuthLoginRequest): Promise<AuthSession> {
  const response = await api.post<AuthSession>('/api/v1/auth/login', request);
  return response.data;
}

export async function logoutUser(): Promise<void> {
  await api.post('/api/v1/auth/logout');
}

export async function listAuthSessions(): Promise<AuthSessionListResponse> {
  const response = await api.get<AuthSessionListResponse>('/api/v1/auth/sessions');
  return response.data;
}

export async function revokeAuthSession(sessionId: string): Promise<void> {
  await api.delete(`/api/v1/auth/sessions/${sessionId}`);
}

export async function revokeOtherAuthSessions(): Promise<AuthSessionRevokeAllResponse> {
  const response = await api.post<AuthSessionRevokeAllResponse>('/api/v1/auth/sessions/revoke-all');
  return response.data;
}

export async function changePassword(request: AuthPasswordChangeRequest): Promise<void> {
  await api.patch('/api/v1/auth/password', request);
}

export async function requestEmailVerification(): Promise<AuthEmailActionResponse> {
  const response = await api.post<AuthEmailActionResponse>('/api/v1/auth/email-verification/request');
  return response.data;
}

export async function confirmEmailVerification(request: AuthTokenConfirmRequest): Promise<AuthUser> {
  const response = await api.post<AuthUser>('/api/v1/auth/email-verification/confirm', request);
  return response.data;
}

export async function requestPasswordReset(request: AuthEmailRequest): Promise<AuthEmailActionResponse> {
  const response = await api.post<AuthEmailActionResponse>('/api/v1/auth/password-reset/request', request);
  return response.data;
}

export async function confirmPasswordReset(request: AuthPasswordResetConfirmRequest): Promise<void> {
  await api.post('/api/v1/auth/password-reset/confirm', request);
}

export async function deleteCurrentAuthUser(request: AuthAccountDeleteRequest): Promise<void> {
  await api.delete('/api/v1/auth/me', { data: request });
}

export async function getCurrentAuthUser(): Promise<AuthUser | null> {
  try {
    const response = await api.get<AuthUser>('/api/v1/auth/me');
    return response.data;
  } catch (error) {
    if (axios.isAxiosError(error) && error.response?.status === 401) {
      return null;
    }
    throw error;
  }
}

export async function listUserSecurityEvents(page = 1, pageSize = 5): Promise<UserSecurityEventListResponse> {
  const response = await api.get<UserSecurityEventListResponse>('/api/v1/auth/security-events', {
    params: { page, pageSize },
  });
  return response.data;
}

export async function listAuthIdentities(): Promise<AuthIdentityListResponse> {
  const response = await api.get<AuthIdentityListResponse>('/api/v1/auth/identities');
  return response.data;
}

export async function unlinkAuthIdentity(provider: string): Promise<void> {
  await api.delete(`/api/v1/auth/identities/${provider}`);
}

export async function updateCurrentAuthUser(request: AuthUserUpdateRequest): Promise<AuthUser> {
  const response = await api.patch<AuthUser>('/api/v1/auth/me', request);
  return response.data;
}

export async function exportCurrentUserData(): Promise<UserDataExport> {
  const response = await api.get<UserDataExport>('/api/v1/me/export');
  return response.data;
}

export async function createCurrentUserExportFile(): Promise<UserExportFile> {
  const response = await api.post<UserExportFile>('/api/v1/me/export-files');
  return response.data;
}

export async function downloadCurrentUserExportFile(exportId: string): Promise<Blob> {
  const response = await api.get<Blob>(`/api/v1/me/export-files/${exportId}`, { responseType: 'blob' });
  return response.data;
}

export async function importCurrentUserData(request: UserDataExport): Promise<UserDataImportResponse> {
  const response = await api.post<UserDataImportResponse>('/api/v1/me/import', request);
  return response.data;
}

export async function getAnonymousUserDataSummary(): Promise<AnonymousDataSummary> {
  const response = await api.get<AnonymousDataSummary>('/api/v1/me/anonymous-data/summary');
  return response.data;
}

export async function importAnonymousUserData(): Promise<UserDataImportResponse> {
  const response = await api.post<UserDataImportResponse>('/api/v1/me/anonymous-data/import');
  return response.data;
}

export async function sendChatMessage(request: ChatRequest): Promise<ChatResponse> {
  const response = await api.post<ChatResponse>('/api/v1/chat', {
    message: request.message,
    conversationId: request.conversationId,
    mode: request.mode ?? 'CHAT',
  });
  return response.data;
}

export async function getUserProfile(): Promise<UserProfile> {
  const response = await api.get<UserProfile>('/api/v1/me/profile');
  return response.data;
}

export async function updateUserProfile(request: UserProfileUpdateRequest): Promise<UserProfile> {
  const response = await api.patch<UserProfile>('/api/v1/me/profile', request);
  return response.data;
}

export async function listConversations(
  page = 1,
  pageSize = 20,
  params: ConversationListParams = {},
): Promise<ConversationListResponse> {
  const response = await api.get<ConversationListResponse>('/api/v1/conversations', {
    params: { page, pageSize, ...params },
  });
  return response.data;
}

export async function getConversation(conversationId: string): Promise<Conversation> {
  const response = await api.get<Conversation>(`/api/v1/conversations/${conversationId}`);
  return response.data;
}

export async function deleteConversation(conversationId: string): Promise<void> {
  await api.delete(`/api/v1/conversations/${conversationId}`);
}

export async function updateConversationTitle(conversationId: string, title: string): Promise<Conversation> {
  const response = await api.patch<Conversation>(`/api/v1/conversations/${conversationId}`, { title });
  return response.data;
}

export async function createConversationSummary(conversationId: string): Promise<ConversationSummary> {
  const response = await api.post<ConversationSummary>(`/api/v1/conversations/${conversationId}/summary`);
  return response.data;
}

export async function createConversationSummaryJob(conversationId: string): Promise<ConversationSummaryJob> {
  const response = await api.post<ConversationSummaryJob>(`/api/v1/conversations/${conversationId}/summary-jobs`);
  return response.data;
}

export async function getLatestConversationSummaryJob(conversationId: string): Promise<ConversationSummaryJob | null> {
  try {
    const response = await api.get<ConversationSummaryJob>(
      `/api/v1/conversations/${conversationId}/summary-jobs/latest`,
    );
    return response.data;
  } catch (error) {
    if (axios.isAxiosError(error) && error.response?.status === 404) {
      return null;
    }
    throw error;
  }
}

export async function getConversationSummary(conversationId: string): Promise<ConversationSummary | null> {
  try {
    const response = await api.get<ConversationSummary>(`/api/v1/conversations/${conversationId}/summary`);
    return response.data;
  } catch (error) {
    if (axios.isAxiosError(error) && error.response?.status === 404) {
      return null;
    }
    throw error;
  }
}

export async function listTripPlans(
  page = 1,
  pageSize = 20,
  params: TripPlanListParams = {},
): Promise<TripPlanListResponse> {
  const response = await api.get<TripPlanListResponse>('/api/v1/trip-plans', {
    params: { page, pageSize, ...params },
  });
  return response.data;
}

export async function getTripPlan(tripPlanId: string): Promise<SavedTripPlan> {
  const response = await api.get<SavedTripPlan>(`/api/v1/trip-plans/${tripPlanId}`);
  return response.data;
}

export async function deleteTripPlan(tripPlanId: string): Promise<void> {
  await api.delete(`/api/v1/trip-plans/${tripPlanId}`);
}

export async function updateTripPlanFavorite(tripPlanId: string, favorite: boolean): Promise<SavedTripPlan> {
  return updateTripPlan(tripPlanId, { favorite });
}

export async function updateTripPlan(
  tripPlanId: string,
  request: TripPlanUpdateRequest,
): Promise<SavedTripPlan> {
  const response = await api.patch<SavedTripPlan>(`/api/v1/trip-plans/${tripPlanId}`, request);
  return response.data;
}

export async function regenerateTripPlanDay(
  tripPlanId: string,
  day: number,
  request: TripDayRegenerateRequest,
): Promise<SavedTripPlan> {
  const response = await api.post<SavedTripPlan>(`/api/v1/trip-plans/${tripPlanId}/days/${day}/regenerate`, request);
  return response.data;
}

export function isApiErrorStatus(error: unknown, status: number): boolean {
  return axios.isAxiosError(error) && error.response?.status === status;
}

export async function exportTripPlanMarkdown(tripPlanId: string): Promise<string> {
  const response = await api.get<string>(`/api/v1/trip-plans/${tripPlanId}/export`, {
    responseType: 'text',
  });
  return response.data;
}

export function getAnonymousUserId(): string {
  const storageKey = 'travel-agent-cloud.user-id';
  const existing = window.localStorage.getItem(storageKey);
  if (existing) {
    return existing;
  }

  const userId =
    typeof window.crypto?.randomUUID === 'function'
      ? `anon:${window.crypto.randomUUID()}`
      : `anon:${Date.now()}:${Math.random().toString(16).slice(2)}`;
  window.localStorage.setItem(storageKey, userId);
  return userId;
}

export function getGithubOAuthStartUrl(): string {
  return buildApiUrl('/api/v1/auth/oauth/github/start');
}

function buildApiUrl(path: string): string {
  const baseUrl = import.meta.env.VITE_AGENT_API_BASE_URL ?? '';
  if (!baseUrl) {
    return path;
  }
  return `${baseUrl.replace(/\/$/, '')}${path}`;
}
