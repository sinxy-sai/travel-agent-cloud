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

const api = axios.create({
  baseURL: import.meta.env.VITE_AGENT_API_BASE_URL ?? '',
  timeout: 30000,
});

export async function createTripPlan(request: TripPlanRequest): Promise<TripPlanResponse> {
  const response = await api.post<TripPlanResponse>('/api/v1/trip-plan', request);
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
