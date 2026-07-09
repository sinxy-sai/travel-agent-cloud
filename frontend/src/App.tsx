import { useMemo, useState, type ReactNode } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Button, Empty, Input, InputNumber, Select, Spin } from 'antd';
import { HistoryOutlined, SendOutlined } from '@ant-design/icons';
import {
  createTripPlan,
  getConversation,
  getTripPlan,
  listConversations,
  listTripPlans,
  sendChatMessage,
  type ChatMessage,
  type Conversation,
  type SavedTripPlan,
  type TripPlanResponse,
} from './lib/api';

const interestOptions = [
  'city walk',
  'local food',
  'museums',
  'nature',
  'family friendly',
  'photography',
  'slow travel',
];

export default function App() {
  const queryClient = useQueryClient();
  const [destination, setDestination] = useState('Chengdu');
  const [days, setDays] = useState(3);
  const [budget, setBudget] = useState('moderate');
  const [interests, setInterests] = useState<string[]>(['local food', 'city walk']);
  const [plan, setPlan] = useState<TripPlanResponse | null>(null);
  const [selectedTripPlanId, setSelectedTripPlanId] = useState<string | undefined>();
  const [conversationId, setConversationId] = useState<string | undefined>();
  const [chatInput, setChatInput] = useState('I want a relaxed 3-day Chengdu food trip.');
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);

  const conversationsQuery = useQuery({
    queryKey: ['conversations'],
    queryFn: () => listConversations(1, 8),
  });

  const tripPlansQuery = useQuery({
    queryKey: ['trip-plans'],
    queryFn: () => listTripPlans(1, 8),
  });

  const tripPlanMutation = useMutation({
    mutationFn: createTripPlan,
    onSuccess: (response) => {
      setPlan(response);
      setSelectedTripPlanId(undefined);
      queryClient.invalidateQueries({ queryKey: ['conversations'] });
      queryClient.invalidateQueries({ queryKey: ['trip-plans'] });
    },
  });

  const chatMutation = useMutation({
    mutationFn: sendChatMessage,
    onSuccess: (response) => {
      setConversationId(response.conversationId);
      setChatMessages((messages) => [...messages, response.message]);
      queryClient.invalidateQueries({ queryKey: ['conversations'] });
    },
  });

  const loadConversationMutation = useMutation({
    mutationFn: getConversation,
    onSuccess: (conversation) => {
      setConversationId(conversation.id);
      setChatMessages(conversation.messages);
      setChatInput('');
    },
  });

  const loadTripPlanMutation = useMutation({
    mutationFn: getTripPlan,
    onSuccess: (savedTripPlan) => {
      setPlan(savedTripPlan.plan);
      setSelectedTripPlanId(savedTripPlan.id);
      setDestination(savedTripPlan.destination);
      setDays(savedTripPlan.days);
      setBudget(savedTripPlan.budget);
      setInterests(splitInterests(savedTripPlan.interests));
      if (savedTripPlan.conversationId) {
        setConversationId(savedTripPlan.conversationId);
      }
    },
  });

  const requestPreview = useMemo(
    () => `${days} days in ${destination}, ${budget} budget, focused on ${interests.join(', ')}`,
    [budget, days, destination, interests],
  );

  const sendMessage = () => {
    const message = chatInput.trim();
    if (!message || chatMutation.isPending) {
      return;
    }

    setChatMessages((messages) => [
      ...messages,
      {
        id: `local-${Date.now()}`,
        role: 'USER',
        content: message,
        createdAt: new Date().toISOString(),
      },
    ]);
    setChatInput('');
    chatMutation.mutate({
      message,
      conversationId,
      mode: 'TRIP_PLANNING',
    });
  };

  return (
    <main className="min-h-screen bg-mist">
      <section className="mx-auto grid min-h-screen max-w-[1480px] grid-cols-1 gap-6 px-5 py-6 xl:grid-cols-[340px_minmax(0,1fr)_360px]">
        <aside className="rounded-lg bg-white p-5 shadow-panel">
          <div className="mb-6">
            <p className="text-sm font-medium uppercase tracking-wide text-trail">Travel Agent Cloud</p>
            <h1 className="mt-2 text-3xl font-semibold text-ink">Trip planner workspace</h1>
          </div>

          <div className="space-y-4">
            <label className="block">
              <span className="mb-2 block text-sm font-medium text-ink">Destination</span>
              <Input value={destination} onChange={(event) => setDestination(event.target.value)} />
            </label>

            <label className="block">
              <span className="mb-2 block text-sm font-medium text-ink">Days</span>
              <InputNumber min={1} max={14} value={days} onChange={(value) => setDays(value ?? 1)} className="w-full" />
            </label>

            <label className="block">
              <span className="mb-2 block text-sm font-medium text-ink">Budget</span>
              <Select
                value={budget}
                onChange={setBudget}
                className="w-full"
                options={[
                  { value: 'low', label: 'Low' },
                  { value: 'moderate', label: 'Moderate' },
                  { value: 'premium', label: 'Premium' },
                ]}
              />
            </label>

            <label className="block">
              <span className="mb-2 block text-sm font-medium text-ink">Interests</span>
              <Select
                mode="multiple"
                value={interests}
                onChange={setInterests}
                className="w-full"
                options={interestOptions.map((value) => ({ value, label: value }))}
              />
            </label>

            <Button
              type="primary"
              icon={<SendOutlined />}
              loading={tripPlanMutation.isPending}
              onClick={() =>
                tripPlanMutation.mutate({
                  destination,
                  days,
                  budget,
                  interests: interests.join(', '),
                })
              }
              className="w-full"
            >
              Generate itinerary
            </Button>
          </div>

          <div className="mt-6 border-t border-slate-200 pt-5">
            <HistorySection
              title="Recent conversations"
              emptyText="No saved threads yet"
              loading={conversationsQuery.isLoading || loadConversationMutation.isPending}
            >
              {conversationsQuery.data?.data.map((conversation) => (
                <ConversationHistoryItem
                  key={conversation.id}
                  conversation={conversation}
                  active={conversation.id === conversationId}
                  onClick={() => loadConversationMutation.mutate(conversation.id)}
                />
              ))}
            </HistorySection>

            <HistorySection
              title="Saved itineraries"
              emptyText="No saved plans yet"
              loading={tripPlansQuery.isLoading || loadTripPlanMutation.isPending}
            >
              {tripPlansQuery.data?.data.map((savedTripPlan) => (
                <TripPlanHistoryItem
                  key={savedTripPlan.id}
                  tripPlan={savedTripPlan}
                  active={savedTripPlan.id === selectedTripPlanId}
                  onClick={() => loadTripPlanMutation.mutate(savedTripPlan.id)}
                />
              ))}
            </HistorySection>
          </div>
        </aside>

        <section className="rounded-lg bg-white p-5 shadow-panel">
          <div className="mb-5 border-b border-slate-200 pb-4">
            <p className="text-sm text-slate-500">Current request</p>
            <h2 className="mt-1 text-xl font-semibold text-ink">{requestPreview}</h2>
          </div>

          {tripPlanMutation.isPending && (
            <div className="flex h-80 items-center justify-center">
              <Spin tip="Planning route..." />
            </div>
          )}

          {tripPlanMutation.isError && (
            <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-red-700">
              Agent runtime is unavailable. Start the FastAPI service and try again.
            </div>
          )}

          {!tripPlanMutation.isPending && !plan && !tripPlanMutation.isError && (
            <div className="rounded-lg border border-dashed border-slate-300 p-8 text-slate-600">
              Generate a plan to preview the first Agent Runtime response.
            </div>
          )}

          {plan && !tripPlanMutation.isPending && (
            <div>
              <div className="mb-5">
                <h2 className="text-2xl font-semibold text-ink">{plan.title}</h2>
                <p className="mt-2 max-w-3xl text-slate-600">{plan.summary}</p>
              </div>

              <div className="grid gap-4">
                {plan.days.map((day) => (
                  <article key={day.day} className="rounded-lg border border-slate-200 p-4">
                    <div className="mb-3 flex items-center justify-between">
                      <h3 className="text-lg font-semibold text-ink">Day {day.day}</h3>
                      <span className="rounded-full bg-trail px-3 py-1 text-sm text-white">{day.theme}</span>
                    </div>
                    <div className="grid gap-3 md:grid-cols-3">
                      <PlanBlock title="Morning" value={day.morning} />
                      <PlanBlock title="Afternoon" value={day.afternoon} />
                      <PlanBlock title="Evening" value={day.evening} />
                    </div>
                  </article>
                ))}
              </div>

              <div className="mt-5 rounded-lg bg-slate-50 p-4">
                <h3 className="font-semibold text-ink">Travel notes</h3>
                <ul className="mt-2 list-inside list-disc text-slate-600">
                  {plan.tips.map((tip) => (
                    <li key={tip}>{tip}</li>
                  ))}
                </ul>
              </div>
            </div>
          )}
        </section>

        <aside className="flex min-h-[560px] flex-col rounded-lg bg-ink p-5 text-white shadow-panel">
          <div className="mb-4">
            <p className="text-sm font-medium uppercase tracking-wide text-mist/70">Agent chat</p>
            <h2 className="mt-2 text-2xl font-semibold">Planning thread</h2>
          </div>

          <div className="min-h-0 flex-1 space-y-3 overflow-y-auto pr-1">
            {chatMessages.length === 0 && (
              <div className="rounded-lg border border-white/15 bg-white/5 p-4 text-sm leading-6 text-mist/80">
                Ask for a route, constraints, or a planning change.
              </div>
            )}

            {chatMessages.map((message) => (
              <ChatBubble key={message.id} message={message} />
            ))}

            {chatMutation.isPending && (
              <div className="rounded-lg border border-white/15 bg-white/5 p-3 text-sm text-mist/80">Thinking...</div>
            )}

            {chatMutation.isError && (
              <div className="rounded-lg border border-red-300/40 bg-red-500/10 p-3 text-sm text-red-100">
                Agent runtime is unavailable.
              </div>
            )}
          </div>

          <div className="mt-4 space-y-3">
            <Input.TextArea
              value={chatInput}
              onChange={(event) => setChatInput(event.target.value)}
              onPressEnter={(event) => {
                if (!event.shiftKey) {
                  event.preventDefault();
                  sendMessage();
                }
              }}
              rows={4}
              maxLength={2000}
              placeholder="Ask the agent to adjust the trip..."
            />
            <Button
              type="primary"
              icon={<SendOutlined />}
              loading={chatMutation.isPending}
              onClick={sendMessage}
              className="w-full"
            >
              Send message
            </Button>
          </div>
        </aside>
      </section>
    </main>
  );
}

function PlanBlock({ title, value }: { title: string; value: string }) {
  return (
    <div className="rounded-md bg-mist p-3">
      <p className="text-sm font-medium text-trail">{title}</p>
      <p className="mt-1 text-sm leading-6 text-slate-700">{value}</p>
    </div>
  );
}

function HistorySection({
  title,
  emptyText,
  loading,
  children,
}: {
  title: string;
  emptyText: string;
  loading: boolean;
  children: ReactNode;
}) {
  const hasItems = Array.isArray(children) ? children.length > 0 : Boolean(children);

  return (
    <section className="mb-5">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-ink">{title}</h2>
        {loading && <Spin size="small" />}
      </div>
      <div className="space-y-2">
        {hasItems ? (
          children
        ) : (
          <div className="rounded-md border border-dashed border-slate-200 px-2 py-3">
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={emptyText} />
          </div>
        )}
      </div>
    </section>
  );
}

function ConversationHistoryItem({
  conversation,
  active,
  onClick,
}: {
  conversation: Conversation;
  active: boolean;
  onClick: () => void;
}) {
  const lastMessage = conversation.messages[conversation.messages.length - 1]?.content ?? 'No messages yet';

  return (
    <button
      type="button"
      onClick={onClick}
      className={`w-full rounded-md border px-3 py-2 text-left transition ${
        active ? 'border-trail bg-mist' : 'border-slate-200 bg-white hover:border-trail/60 hover:bg-slate-50'
      }`}
    >
      <div className="flex items-center gap-2 text-sm font-medium text-ink">
        <HistoryOutlined className="text-trail" />
        <span className="min-w-0 flex-1 truncate">{conversation.title}</span>
      </div>
      <p className="mt-1 line-clamp-2 text-xs leading-5 text-slate-500">{lastMessage}</p>
      <p className="mt-1 text-xs text-slate-400">{formatDateTime(conversation.updatedAt)}</p>
    </button>
  );
}

function TripPlanHistoryItem({
  tripPlan,
  active,
  onClick,
}: {
  tripPlan: SavedTripPlan;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`w-full rounded-md border px-3 py-2 text-left transition ${
        active ? 'border-coral bg-coral/5' : 'border-slate-200 bg-white hover:border-coral/60 hover:bg-slate-50'
      }`}
    >
      <p className="truncate text-sm font-medium text-ink">{tripPlan.title}</p>
      <p className="mt-1 text-xs text-slate-500">
        {tripPlan.destination} · {tripPlan.days} days · {tripPlan.budget}
      </p>
      <p className="mt-1 text-xs text-slate-400">{formatDateTime(tripPlan.createdAt)}</p>
    </button>
  );
}

function ChatBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === 'USER';

  return (
    <article className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[92%] rounded-lg px-3 py-2 text-sm leading-6 ${
          isUser ? 'bg-coral text-white' : 'bg-white text-ink'
        }`}
      >
        <p className="mb-1 text-xs font-semibold uppercase tracking-wide opacity-70">
          {isUser ? 'You' : 'Agent'}
        </p>
        <p>{message.content}</p>
      </div>
    </article>
  );
}

function formatDateTime(value: string): string {
  return new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value));
}

function splitInterests(value: string): string[] {
  return value
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);
}
