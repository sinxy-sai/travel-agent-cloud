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

const api = axios.create({
  baseURL: import.meta.env.VITE_AGENT_API_BASE_URL ?? '',
  timeout: 30000,
});

export async function createTripPlan(request: TripPlanRequest): Promise<TripPlanResponse> {
  const response = await api.post<TripPlanResponse>('/api/v1/trip-plan', request);
  return response.data;
}
