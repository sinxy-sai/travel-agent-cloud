import axios from 'axios';

export interface TripPlanRequest {
  destination: string;
  days: number;
  budget: string;
  interests: string;
  conversationId?: string;
}

export interface TripDay {
  day: number;
  theme: string;
  morning: string;
  afternoon: string;
  evening: string;
}

export interface TripPlanResponse {
  title: string;
  summary: string;
  days: TripDay[];
  tips: string[];
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
  createdAt: string;
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

const api = axios.create({
  baseURL: import.meta.env.VITE_AGENT_API_BASE_URL ?? '',
  timeout: 30000,
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
  const response = await api.patch<SavedTripPlan>(`/api/v1/trip-plans/${tripPlanId}`, { favorite });
  return response.data;
}

export async function exportTripPlanMarkdown(tripPlanId: string): Promise<string> {
  const response = await api.get<string>(`/api/v1/trip-plans/${tripPlanId}/export`, {
    responseType: 'text',
  });
  return response.data;
}

function getAnonymousUserId(): string {
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
