import axios from 'axios';

export interface TripPlanRequest {
  destination: string;
  days: number;
  budget: string;
  interests: string;
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
  createdAt: string;
}

export interface TripPlanListResponse {
  data: SavedTripPlan[];
  page: number;
  pageSize: number;
  totalItems: number;
  totalPages: number;
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

export interface ConversationListResponse {
  data: Conversation[];
  page: number;
  pageSize: number;
  totalItems: number;
  totalPages: number;
}

export interface HealthResponse {
  status: string;
  service: string;
  env: string;
  llmEnabled: boolean;
  databaseEnabled: boolean;
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

export async function listConversations(page = 1, pageSize = 20): Promise<ConversationListResponse> {
  const response = await api.get<ConversationListResponse>('/api/v1/conversations', {
    params: { page, pageSize },
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

export async function listTripPlans(page = 1, pageSize = 20): Promise<TripPlanListResponse> {
  const response = await api.get<TripPlanListResponse>('/api/v1/trip-plans', {
    params: { page, pageSize },
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
