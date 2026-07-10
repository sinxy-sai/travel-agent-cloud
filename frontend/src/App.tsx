import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Button, Empty, Input, InputNumber, Modal, Pagination, Popconfirm, Segmented, Select, Spin } from 'antd';
import {
  DeleteOutlined,
  DownloadOutlined,
  EditOutlined,
  HistoryOutlined,
  PlusOutlined,
  SendOutlined,
  StarFilled,
  StarOutlined,
} from '@ant-design/icons';
import {
  changePassword,
  createTripPlan,
  createConversationSummary,
  createConversationSummaryJob,
  deleteConversation,
  deleteTripPlan,
  exportTripPlanMarkdown,
  getConversation,
  getConversationSummary,
  getCurrentAuthUser,
  getHealth,
  getLatestConversationSummaryJob,
  getTripPlan,
  getUserProfile,
  loginUser,
  listConversations,
  listTripPlans,
  logoutUser,
  registerUser,
  sendChatMessage,
  updateConversationTitle,
  updateCurrentAuthUser,
  updateTripPlanFavorite,
  updateUserProfile,
  type AuthUser,
  type ChatMessage,
  type Conversation,
  type ConversationSummary,
  type ConversationSummaryJob,
  type HealthResponse,
  type SavedTripPlan,
  type TripPlanResponse,
  type UserProfile,
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

const defaultChatSuggestions = [
  'Generate a structured itinerary',
  'Add weather and transit constraints',
  'Make this plan more budget friendly',
];

const historyPageSize = 8;
const summaryJobPollingIntervalMs = 2000;
const summaryJobPollingTimeoutMs = 30000;
type ConversationSummaryJobUiStatus = 'IDLE' | 'POLLING' | 'FAILED' | 'TIMEOUT';

export default function App() {
  const queryClient = useQueryClient();
  const [destination, setDestination] = useState('Chengdu');
  const [days, setDays] = useState(3);
  const [budget, setBudget] = useState('moderate');
  const [interests, setInterests] = useState<string[]>(['local food', 'city walk']);
  const [plan, setPlan] = useState<TripPlanResponse | null>(null);
  const [selectedTripPlanId, setSelectedTripPlanId] = useState<string | undefined>();
  const [selectedTripPlanFavorite, setSelectedTripPlanFavorite] = useState(false);
  const [conversationId, setConversationId] = useState<string | undefined>();
  const [chatInput, setChatInput] = useState('I want a relaxed 3-day Chengdu food trip.');
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [chatSuggestions, setChatSuggestions] = useState<string[]>(defaultChatSuggestions);
  const [conversationSummary, setConversationSummary] = useState<ConversationSummary | null>(null);
  const [conversationSummaryJob, setConversationSummaryJob] = useState<ConversationSummaryJob | null>(null);
  const [conversationSummaryJobStatus, setConversationSummaryJobStatus] =
    useState<ConversationSummaryJobUiStatus>('IDLE');
  const [conversationSummaryJobError, setConversationSummaryJobError] = useState('');
  const summaryJobPollingIntervalRef = useRef<number | undefined>(undefined);
  const summaryJobPollingConversationIdRef = useRef<string | undefined>(undefined);
  const [tripPlanFilter, setTripPlanFilter] = useState<'ALL' | 'FAVORITES'>('ALL');
  const [tripPlanSearchInput, setTripPlanSearchInput] = useState('');
  const [tripPlanSearch, setTripPlanSearch] = useState('');
  const [conversationSearchInput, setConversationSearchInput] = useState('');
  const [conversationSearch, setConversationSearch] = useState('');
  const [conversationPage, setConversationPage] = useState(1);
  const [tripPlanPage, setTripPlanPage] = useState(1);
  const [renameConversation, setRenameConversation] = useState<Conversation | null>(null);
  const [renameConversationTitle, setRenameConversationTitle] = useState('');
  const [profileModalOpen, setProfileModalOpen] = useState(false);
  const [profileDisplayName, setProfileDisplayName] = useState('');
  const [profileHomeCity, setProfileHomeCity] = useState('');
  const [profilePreferredBudget, setProfilePreferredBudget] = useState('');
  const [profileTravelStyle, setProfileTravelStyle] = useState('');
  const [profileInterests, setProfileInterests] = useState<string[]>([]);
  const [authModalOpen, setAuthModalOpen] = useState(false);
  const [authMode, setAuthMode] = useState<'LOGIN' | 'REGISTER'>('LOGIN');
  const [authEmail, setAuthEmail] = useState('');
  const [authPassword, setAuthPassword] = useState('');
  const [authDisplayName, setAuthDisplayName] = useState('');
  const [accountModalOpen, setAccountModalOpen] = useState(false);
  const [accountDisplayName, setAccountDisplayName] = useState('');
  const [passwordModalOpen, setPasswordModalOpen] = useState(false);
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmNewPassword, setConfirmNewPassword] = useState('');
  const [passwordChangeSucceeded, setPasswordChangeSucceeded] = useState(false);

  const authUserQuery = useQuery({
    queryKey: ['auth-user'],
    queryFn: getCurrentAuthUser,
    retry: false,
  });

  const conversationsQuery = useQuery({
    queryKey: ['conversations', conversationPage, conversationSearch],
    queryFn: () =>
      listConversations(conversationPage, historyPageSize, {
        query: conversationSearch || undefined,
      }),
  });

  const tripPlansQuery = useQuery({
    queryKey: ['trip-plans', tripPlanPage, tripPlanFilter, tripPlanSearch],
    queryFn: () =>
      listTripPlans(tripPlanPage, historyPageSize, {
        favoriteOnly: tripPlanFilter === 'FAVORITES',
        query: tripPlanSearch || undefined,
      }),
  });

  const healthQuery = useQuery({
    queryKey: ['health'],
    queryFn: getHealth,
    refetchInterval: 30000,
    retry: 1,
  });

  const userProfileQuery = useQuery({
    queryKey: ['user-profile'],
    queryFn: getUserProfile,
  });

  const registerMutation = useMutation({
    mutationFn: registerUser,
    onSuccess: (session) => {
      applyAuthenticatedSession(session.user);
    },
  });

  const loginMutation = useMutation({
    mutationFn: loginUser,
    onSuccess: (session) => {
      applyAuthenticatedSession(session.user);
    },
  });

  const logoutMutation = useMutation({
    mutationFn: logoutUser,
    onSuccess: () => {
      clearWorkspace();
      resetPasswordForm();
      queryClient.setQueryData(['auth-user'], null);
      queryClient.invalidateQueries({ queryKey: ['user-profile'] });
      queryClient.invalidateQueries({ queryKey: ['conversations'] });
      queryClient.invalidateQueries({ queryKey: ['trip-plans'] });
    },
  });

  const changePasswordMutation = useMutation({
    mutationFn: changePassword,
    onSuccess: () => {
      resetPasswordForm();
      setPasswordChangeSucceeded(true);
    },
  });

  const updateAuthUserMutation = useMutation({
    mutationFn: updateCurrentAuthUser,
    onSuccess: (user) => {
      queryClient.setQueryData(['auth-user'], user);
      setAccountModalOpen(false);
    },
  });

  const tripPlanMutation = useMutation({
    mutationFn: createTripPlan,
    onSuccess: (response) => {
      setPlan(response);
      setSelectedTripPlanId(response.savedTripPlanId);
      setSelectedTripPlanFavorite(false);
      setConversationId(response.conversationId);
      setConversationSummary(null);
      resetConversationSummaryJobPolling();
      setConversationPage(1);
      setTripPlanPage(1);
      queryClient.invalidateQueries({ queryKey: ['conversations'] });
      queryClient.invalidateQueries({ queryKey: ['trip-plans'] });
    },
  });

  const chatMutation = useMutation({
    mutationFn: sendChatMessage,
    onSuccess: (response) => {
      setConversationId(response.conversationId);
      setChatMessages((messages) => [...messages, response.message]);
      setChatSuggestions(response.suggestions);
      setConversationPage(1);
      queryClient.invalidateQueries({ queryKey: ['conversations'] });
    },
  });

  const loadConversationSummaryMutation = useMutation({
    mutationFn: getConversationSummary,
    onSuccess: (summary) => {
      setConversationSummary(summary);
      if (summary) {
        resetConversationSummaryJobPolling();
      }
    },
  });

  const loadConversationMutation = useMutation({
    mutationFn: getConversation,
    onSuccess: (conversation) => {
      setConversationId(conversation.id);
      setChatMessages(conversation.messages);
      setConversationSummary(null);
      resetConversationSummaryJobPolling();
      setChatInput('');
      setChatSuggestions(defaultChatSuggestions);
      loadConversationSummaryMutation.mutate(conversation.id);
    },
  });

  const loadTripPlanMutation = useMutation({
    mutationFn: getTripPlan,
    onSuccess: (savedTripPlan) => {
      setPlan(savedTripPlan.plan);
      setSelectedTripPlanId(savedTripPlan.id);
      setSelectedTripPlanFavorite(savedTripPlan.favorite);
      setDestination(savedTripPlan.destination);
      setDays(savedTripPlan.days);
      setBudget(savedTripPlan.budget);
      setInterests(splitInterests(savedTripPlan.interests));
      if (savedTripPlan.conversationId) {
        setConversationId(savedTripPlan.conversationId);
        setConversationSummary(null);
        resetConversationSummaryJobPolling();
      }
    },
  });

  const deleteConversationMutation = useMutation({
    mutationFn: deleteConversation,
    onSuccess: (_response, deletedConversationId) => {
      if (deletedConversationId === conversationId) {
        setConversationId(undefined);
        setChatMessages([]);
        setConversationSummary(null);
        resetConversationSummaryJobPolling();
      }
      queryClient.invalidateQueries({ queryKey: ['conversations'] });
    },
  });

  const updateConversationTitleMutation = useMutation({
    mutationFn: ({ targetConversationId, title }: { targetConversationId: string; title: string }) =>
      updateConversationTitle(targetConversationId, title),
    onSuccess: () => {
      setRenameConversation(null);
      setRenameConversationTitle('');
      setConversationPage(1);
      queryClient.invalidateQueries({ queryKey: ['conversations'] });
    },
  });

  const createConversationSummaryMutation = useMutation({
    mutationFn: createConversationSummary,
    onSuccess: (summary) => {
      setConversationSummary(summary);
      resetConversationSummaryJobPolling();
    },
  });

  const createConversationSummaryJobMutation = useMutation({
    mutationFn: createConversationSummaryJob,
    onSuccess: (job) => {
      setConversationSummaryJob(job);
      startConversationSummaryJobPolling(job.conversationId);
    },
  });

  const updateUserProfileMutation = useMutation({
    mutationFn: updateUserProfile,
    onSuccess: (profile) => {
      setProfileModalOpen(false);
      applyProfilePreferences(profile);
      queryClient.invalidateQueries({ queryKey: ['user-profile'] });
    },
  });

  const deleteTripPlanMutation = useMutation({
    mutationFn: deleteTripPlan,
    onSuccess: (_response, deletedTripPlanId) => {
      if (deletedTripPlanId === selectedTripPlanId) {
        setSelectedTripPlanId(undefined);
        setSelectedTripPlanFavorite(false);
        setPlan(null);
      }
      queryClient.invalidateQueries({ queryKey: ['trip-plans'] });
    },
  });

  const updateTripPlanFavoriteMutation = useMutation({
    mutationFn: ({ tripPlanId, favorite }: { tripPlanId: string; favorite: boolean }) =>
      updateTripPlanFavorite(tripPlanId, favorite),
    onSuccess: (savedTripPlan) => {
      if (savedTripPlan.id === selectedTripPlanId) {
        setSelectedTripPlanFavorite(savedTripPlan.favorite);
      }
      queryClient.invalidateQueries({ queryKey: ['trip-plans'] });
    },
  });

  const exportTripPlanMutation = useMutation({
    mutationFn: async () => {
      if (!plan) {
        return;
      }

      const markdown = selectedTripPlanId
        ? await exportTripPlanMarkdown(selectedTripPlanId)
        : tripPlanToMarkdown(plan, {
            destination,
            days,
            budget,
            interests: interests.join(', '),
          });
      downloadTextFile(markdown, `${slugify(plan.title)}.md`);
    },
  });

  const requestPreview = useMemo(
    () => `${days} days in ${destination}, ${budget} budget, focused on ${interests.join(', ')}`,
    [budget, days, destination, interests],
  );
  const conversations = conversationsQuery.data?.data ?? [];
  const tripPlans = tripPlansQuery.data?.data ?? [];

  useEffect(() => {
    const totalPages = conversationsQuery.data?.totalPages ?? 0;
    if (totalPages > 0 && conversationPage > totalPages) {
      setConversationPage(totalPages);
    }
  }, [conversationPage, conversationsQuery.data?.totalPages]);

  useEffect(() => {
    const totalPages = tripPlansQuery.data?.totalPages ?? 0;
    if (totalPages > 0 && tripPlanPage > totalPages) {
      setTripPlanPage(totalPages);
    }
  }, [tripPlanPage, tripPlansQuery.data?.totalPages]);

  useEffect(() => {
    return () => {
      stopConversationSummaryJobPolling();
    };
  }, []);

  function stopConversationSummaryJobPolling() {
    if (summaryJobPollingIntervalRef.current !== undefined) {
      window.clearInterval(summaryJobPollingIntervalRef.current);
      summaryJobPollingIntervalRef.current = undefined;
    }
    summaryJobPollingConversationIdRef.current = undefined;
  }

  function resetConversationSummaryJobPolling() {
    stopConversationSummaryJobPolling();
    setConversationSummaryJobStatus('IDLE');
    setConversationSummaryJob(null);
    setConversationSummaryJobError('');
  }

  function startConversationSummaryJobPolling(targetConversationId: string) {
    stopConversationSummaryJobPolling();
    setConversationSummaryJobStatus('POLLING');
    setConversationSummaryJobError('');
    summaryJobPollingConversationIdRef.current = targetConversationId;
    const startedAt = Date.now();

    void pollConversationSummaryJob(targetConversationId, startedAt);
    summaryJobPollingIntervalRef.current = window.setInterval(() => {
      void pollConversationSummaryJob(targetConversationId, startedAt);
    }, summaryJobPollingIntervalMs);
  }

  async function pollConversationSummaryJob(targetConversationId: string, startedAt: number) {
    if (summaryJobPollingConversationIdRef.current !== targetConversationId) {
      return;
    }

    try {
      const latestJob = await getLatestConversationSummaryJob(targetConversationId);
      if (summaryJobPollingConversationIdRef.current !== targetConversationId) {
        return;
      }

      if (latestJob) {
        setConversationSummaryJob(latestJob);

        if (latestJob.status === 'FAILED') {
          stopConversationSummaryJobPolling();
          setConversationSummaryJobStatus('FAILED');
          setConversationSummaryJobError(latestJob.errorMessage || 'Summary job failed. Please try again.');
          return;
        }

        if (latestJob.status === 'SUCCEEDED') {
          const summary = await getConversationSummary(targetConversationId);
          if (summaryJobPollingConversationIdRef.current !== targetConversationId) {
            return;
          }
          if (summary) {
            setConversationSummary(summary);
            resetConversationSummaryJobPolling();
          }
          return;
        }
      } else {
        const summary = await getConversationSummary(targetConversationId);
        if (summaryJobPollingConversationIdRef.current !== targetConversationId) {
          return;
        }
        if (summary) {
          setConversationSummary(summary);
          resetConversationSummaryJobPolling();
          return;
        }
      }
    } catch {
      try {
        const summary = await getConversationSummary(targetConversationId);
        if (summaryJobPollingConversationIdRef.current !== targetConversationId) {
          return;
        }
        if (summary) {
          setConversationSummary(summary);
          resetConversationSummaryJobPolling();
          return;
        }
      } catch {
        // Keep polling until the timeout; transient API failures should not immediately fail the queued job UI.
      }
    }

    if (Date.now() - startedAt >= summaryJobPollingTimeoutMs) {
      stopConversationSummaryJobPolling();
      setConversationSummaryJobStatus('TIMEOUT');
      setConversationSummaryJobError('Summary job is still running. Try loading the saved summary again later.');
    }
  }

  const sendMessage = () => {
    submitChatMessage(chatInput);
  };

  function applyAuthenticatedSession(user: AuthUser) {
    setAuthModalOpen(false);
    resetAuthForm();
    clearWorkspace();
    queryClient.setQueryData(['auth-user'], user);
    queryClient.invalidateQueries({ queryKey: ['user-profile'] });
    queryClient.invalidateQueries({ queryKey: ['conversations'] });
    queryClient.invalidateQueries({ queryKey: ['trip-plans'] });
  }

  function openAuthModal(mode: 'LOGIN' | 'REGISTER') {
    setAuthMode(mode);
    setAuthModalOpen(true);
    loginMutation.reset();
    registerMutation.reset();
  }

  function resetAuthForm() {
    setAuthEmail('');
    setAuthPassword('');
    setAuthDisplayName('');
    loginMutation.reset();
    registerMutation.reset();
  }

  function resetPasswordForm() {
    setCurrentPassword('');
    setNewPassword('');
    setConfirmNewPassword('');
    setPasswordChangeSucceeded(false);
    changePasswordMutation.reset();
  }

  function submitAuth() {
    const email = authEmail.trim();
    if (!email || !authPassword || loginMutation.isPending || registerMutation.isPending) {
      return;
    }

    if (authMode === 'LOGIN') {
      loginMutation.mutate({ email, password: authPassword });
    } else {
      registerMutation.mutate({
        email,
        password: authPassword,
        displayName: authDisplayName,
      });
    }
  }

  function submitAccountUpdate() {
    if (!authUserQuery.data || updateAuthUserMutation.isPending) {
      return;
    }
    updateAuthUserMutation.mutate({
      displayName: accountDisplayName,
    });
  }

  function submitPasswordChange() {
    if (!currentPassword || newPassword.length < 8 || newPassword !== confirmNewPassword) {
      return;
    }
    changePasswordMutation.mutate({
      currentPassword,
      newPassword,
    });
  }

  function clearWorkspace() {
    setConversationId(undefined);
    setChatMessages([]);
    setChatSuggestions(defaultChatSuggestions);
    setChatInput('');
    setConversationSummary(null);
    resetConversationSummaryJobPolling();
    setPlan(null);
    setSelectedTripPlanId(undefined);
    setSelectedTripPlanFavorite(false);
    setConversationPage(1);
    setTripPlanPage(1);
  }

  const submitChatMessage = (rawMessage: string) => {
    const message = rawMessage.trim();
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
    setConversationSummary(null);
    resetConversationSummaryJobPolling();
    setChatInput('');
    chatMutation.mutate({
      message,
      conversationId,
      mode: 'TRIP_PLANNING',
    });
  };

  const startNewChat = () => {
    setConversationId(undefined);
    setChatMessages([]);
    setConversationSummary(null);
    resetConversationSummaryJobPolling();
    setChatInput('');
    setChatSuggestions(defaultChatSuggestions);
  };

  const openProfileModal = () => {
    const profile = userProfileQuery.data;
    setProfileDisplayName(profile?.displayName ?? '');
    setProfileHomeCity(profile?.homeCity ?? '');
    setProfilePreferredBudget(profile?.preferredBudget || budget);
    setProfileTravelStyle(profile?.travelStyle ?? '');
    setProfileInterests(profile?.interests?.length ? profile.interests : interests);
    setProfileModalOpen(true);
  };

  const saveProfile = () => {
    updateUserProfileMutation.mutate({
      displayName: profileDisplayName,
      homeCity: profileHomeCity,
      preferredBudget: profilePreferredBudget,
      travelStyle: profileTravelStyle,
      interests: profileInterests,
    });
  };

  function applyProfilePreferences(profile: UserProfile) {
    if (profile.preferredBudget) {
      setBudget(profile.preferredBudget);
    }
    if (profile.interests?.length > 0) {
      setInterests(profile.interests);
    }
  }

  const openRenameConversation = (conversation: Conversation) => {
    setRenameConversation(conversation);
    setRenameConversationTitle(conversation.title);
  };

  const submitRenameConversation = () => {
    const title = renameConversationTitle.trim();
    if (!renameConversation || !title) {
      return;
    }

    updateConversationTitleMutation.mutate({
      targetConversationId: renameConversation.id,
      title,
    });
  };

  const toggleTripPlanFavorite = (tripPlanId: string, favorite: boolean) => {
    updateTripPlanFavoriteMutation.mutate({ tripPlanId, favorite });
  };

  return (
    <main className="min-h-screen bg-mist">
      <section className="mx-auto grid min-h-screen max-w-[1480px] grid-cols-1 gap-6 px-5 py-6 xl:grid-cols-[340px_minmax(0,1fr)_360px]">
        <aside className="rounded-lg bg-white p-5 shadow-panel">
          <div className="mb-6">
            <p className="text-sm font-medium uppercase tracking-wide text-trail">Travel Agent Cloud</p>
            <h1 className="mt-2 text-3xl font-semibold text-ink">Trip planner workspace</h1>
          </div>

          <RuntimeStatus health={healthQuery.data} loading={healthQuery.isLoading} error={healthQuery.isError} />
          <AccountStatus
            user={authUserQuery.data}
            loading={
              authUserQuery.isLoading ||
              logoutMutation.isPending ||
              changePasswordMutation.isPending ||
              updateAuthUserMutation.isPending
            }
            onLogin={() => openAuthModal('LOGIN')}
            onRegister={() => openAuthModal('REGISTER')}
            onEditAccount={() => {
              setAccountDisplayName(authUserQuery.data?.displayName ?? '');
              updateAuthUserMutation.reset();
              setAccountModalOpen(true);
            }}
            onChangePassword={() => {
              resetPasswordForm();
              setPasswordModalOpen(true);
            }}
            onLogout={() => logoutMutation.mutate()}
          />
          <TravelerProfile
            profile={userProfileQuery.data}
            loading={userProfileQuery.isLoading}
            onEdit={openProfileModal}
            onUsePreferences={() => userProfileQuery.data && applyProfilePreferences(userProfileQuery.data)}
          />

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
                  conversationId,
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
              hasItems={conversations.length > 0}
              loading={
                conversationsQuery.isLoading ||
                loadConversationMutation.isPending ||
                deleteConversationMutation.isPending ||
                updateConversationTitleMutation.isPending
              }
              controls={
                <Input.Search
                  allowClear
                  size="small"
                  placeholder="Search conversations"
                  value={conversationSearchInput}
                  onChange={(event) => {
                    setConversationSearchInput(event.target.value);
                    if (!event.target.value) {
                      setConversationSearch('');
                      setConversationPage(1);
                    }
                  }}
                  onSearch={(value) => {
                    setConversationSearch(value.trim());
                    setConversationPage(1);
                  }}
                />
              }
              footer={
                <HistoryPagination
                  page={conversationPage}
                  totalItems={conversationsQuery.data?.totalItems ?? 0}
                  pageSize={historyPageSize}
                  onChange={setConversationPage}
                />
              }
            >
              {conversations.map((conversation) => (
                <ConversationHistoryItem
                  key={conversation.id}
                  conversation={conversation}
                  active={conversation.id === conversationId}
                  onClick={() => loadConversationMutation.mutate(conversation.id)}
                  onRename={() => openRenameConversation(conversation)}
                  onDelete={() => deleteConversationMutation.mutate(conversation.id)}
                />
              ))}
            </HistorySection>

            <HistorySection
              title="Saved itineraries"
              emptyText="No saved plans yet"
              hasItems={tripPlans.length > 0}
              loading={
                tripPlansQuery.isLoading ||
                loadTripPlanMutation.isPending ||
                deleteTripPlanMutation.isPending ||
                updateTripPlanFavoriteMutation.isPending
              }
              controls={
                <div className="space-y-2">
                  <Segmented
                    block
                    size="small"
                    value={tripPlanFilter}
                    options={[
                      { label: 'All', value: 'ALL' },
                      { label: 'Favorites', value: 'FAVORITES' },
                    ]}
                    onChange={(value) => {
                      setTripPlanFilter(value as 'ALL' | 'FAVORITES');
                      setTripPlanPage(1);
                    }}
                  />
                  <Input.Search
                    allowClear
                    size="small"
                    placeholder="Search saved trips"
                    value={tripPlanSearchInput}
                    onChange={(event) => {
                      setTripPlanSearchInput(event.target.value);
                      if (!event.target.value) {
                        setTripPlanSearch('');
                        setTripPlanPage(1);
                      }
                    }}
                    onSearch={(value) => {
                      setTripPlanSearch(value.trim());
                      setTripPlanPage(1);
                    }}
                  />
                </div>
              }
              footer={
                <HistoryPagination
                  page={tripPlanPage}
                  totalItems={tripPlansQuery.data?.totalItems ?? 0}
                  pageSize={historyPageSize}
                  onChange={setTripPlanPage}
                />
              }
            >
              {tripPlans.map((savedTripPlan) => (
                <TripPlanHistoryItem
                  key={savedTripPlan.id}
                  tripPlan={savedTripPlan}
                  active={savedTripPlan.id === selectedTripPlanId}
                  onClick={() => loadTripPlanMutation.mutate(savedTripPlan.id)}
                  onDelete={() => deleteTripPlanMutation.mutate(savedTripPlan.id)}
                  onToggleFavorite={() => toggleTripPlanFavorite(savedTripPlan.id, !savedTripPlan.favorite)}
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
              <div className="mb-5 flex flex-col gap-3 border-b border-slate-200 pb-5 md:flex-row md:items-start md:justify-between">
                <div>
                  <h2 className="text-2xl font-semibold text-ink">{plan.title}</h2>
                  <p className="mt-2 max-w-3xl text-slate-600">{plan.summary}</p>
                </div>
                <div className="flex flex-wrap gap-2 md:justify-end">
                  {selectedTripPlanId && (
                    <Button
                      icon={selectedTripPlanFavorite ? <StarFilled /> : <StarOutlined />}
                      loading={updateTripPlanFavoriteMutation.isPending}
                      onClick={() => toggleTripPlanFavorite(selectedTripPlanId, !selectedTripPlanFavorite)}
                      className={selectedTripPlanFavorite ? 'text-amber-500' : undefined}
                    >
                      {selectedTripPlanFavorite ? 'Favorited' : 'Favorite'}
                    </Button>
                  )}
                  <Button
                    icon={<DownloadOutlined />}
                    loading={exportTripPlanMutation.isPending}
                    onClick={() => exportTripPlanMutation.mutate()}
                  >
                    Export .md
                  </Button>
                </div>
              </div>

              <div className="grid gap-4">
                {(plan.days ?? []).map((day) => (
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
                  {(plan.tips ?? []).map((tip) => (
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
            <div className="mt-2 flex items-center justify-between gap-3">
              <h2 className="text-2xl font-semibold">Planning thread</h2>
              <div className="flex flex-wrap justify-end gap-2">
                <Button
                  onClick={() => conversationId && createConversationSummaryMutation.mutate(conversationId)}
                  loading={createConversationSummaryMutation.isPending}
                  disabled={!conversationId || chatMessages.length === 0}
                >
                  Summarize
                </Button>
                {healthQuery.data?.messageQueueEnabled && (
                  <Button
                    onClick={() => conversationId && createConversationSummaryJobMutation.mutate(conversationId)}
                    loading={createConversationSummaryJobMutation.isPending}
                    disabled={
                      !conversationId ||
                      chatMessages.length === 0 ||
                      conversationSummaryJobStatus === 'POLLING'
                    }
                  >
                    Queue summary
                  </Button>
                )}
                <Button icon={<PlusOutlined />} onClick={startNewChat}>
                  New chat
                </Button>
              </div>
            </div>
          </div>

          {loadConversationSummaryMutation.isPending && (
            <div className="mb-4 rounded-lg border border-white/15 bg-white/5 p-3 text-sm text-mist/75">
              Loading saved summary...
            </div>
          )}

          {conversationSummaryJobStatus === 'POLLING' && (
            <div className="mb-4 rounded-lg border border-white/15 bg-white/5 p-3 text-sm text-mist/75">
              Summary job {formatSummaryJobStatus(conversationSummaryJob?.status)}. Waiting for worker result...
            </div>
          )}

          {conversationSummaryJobStatus === 'TIMEOUT' && (
            <div className="mb-4 rounded-lg border border-amber-300/30 bg-amber-400/10 p-3 text-sm text-amber-100">
              {conversationSummaryJobError || 'Summary job is still running. Try loading the saved summary again later.'}
            </div>
          )}

          {conversationSummaryJobStatus === 'FAILED' && (
            <div className="mb-4 rounded-lg border border-red-300/40 bg-red-500/10 p-3 text-sm text-red-100">
              {conversationSummaryJobError || 'Summary job failed. Please try again.'}
            </div>
          )}

          {conversationSummary && (
            <div className="mb-4 rounded-lg border border-white/15 bg-white/5 p-3 text-sm leading-6 text-mist/85">
              <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-mist/60">Conversation summary</p>
              <p className="whitespace-pre-line">{conversationSummary.summary}</p>
            </div>
          )}

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

          <div className="mt-4 flex flex-wrap gap-2">
            {chatSuggestions.map((suggestion) => (
              <Button
                key={suggestion}
                size="small"
                onClick={() => submitChatMessage(suggestion)}
                disabled={chatMutation.isPending}
              >
                {suggestion}
              </Button>
            ))}
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
      <Modal
        title={authMode === 'LOGIN' ? 'Sign in' : 'Create account'}
        open={authModalOpen}
        okText={authMode === 'LOGIN' ? 'Sign in' : 'Create account'}
        onOk={submitAuth}
        confirmLoading={loginMutation.isPending || registerMutation.isPending}
        okButtonProps={{ disabled: !authEmail.trim() || !authPassword }}
        onCancel={() => {
          setAuthModalOpen(false);
          resetAuthForm();
        }}
      >
        <div className="space-y-3">
          {authMode === 'REGISTER' && (
            <label className="block">
              <span className="mb-1 block text-sm font-medium text-ink">Display name</span>
              <Input
                maxLength={80}
                value={authDisplayName}
                onChange={(event) => setAuthDisplayName(event.target.value)}
                placeholder="Traveler name"
              />
            </label>
          )}
          <label className="block">
            <span className="mb-1 block text-sm font-medium text-ink">Email</span>
            <Input
              value={authEmail}
              onChange={(event) => setAuthEmail(event.target.value)}
              placeholder="you@example.com"
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-sm font-medium text-ink">Password</span>
            <Input.Password
              value={authPassword}
              onChange={(event) => setAuthPassword(event.target.value)}
              onPressEnter={submitAuth}
              placeholder={authMode === 'LOGIN' ? 'Password' : 'At least 8 characters'}
            />
          </label>
          {(loginMutation.isError || registerMutation.isError) && (
            <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
              {authMode === 'LOGIN'
                ? 'Email or password is incorrect.'
                : 'Could not create account. The email may already be registered.'}
            </div>
          )}
          <Button
            type="link"
            className="px-0"
            onClick={() => {
              setAuthMode(authMode === 'LOGIN' ? 'REGISTER' : 'LOGIN');
              loginMutation.reset();
              registerMutation.reset();
            }}
          >
            {authMode === 'LOGIN' ? 'Create a new account' : 'Sign in to an existing account'}
          </Button>
        </div>
      </Modal>
      <Modal
        title="Account settings"
        open={accountModalOpen}
        okText="Save"
        onOk={submitAccountUpdate}
        confirmLoading={updateAuthUserMutation.isPending}
        onCancel={() => {
          setAccountModalOpen(false);
          updateAuthUserMutation.reset();
        }}
      >
        <div className="space-y-3">
          <label className="block">
            <span className="mb-1 block text-sm font-medium text-ink">Email</span>
            <Input value={authUserQuery.data?.email ?? ''} disabled />
          </label>
          <label className="block">
            <span className="mb-1 block text-sm font-medium text-ink">Display name</span>
            <Input
              maxLength={80}
              value={accountDisplayName}
              onChange={(event) => {
                setAccountDisplayName(event.target.value);
                updateAuthUserMutation.reset();
              }}
              onPressEnter={submitAccountUpdate}
              placeholder="Traveler name"
            />
          </label>
          {updateAuthUserMutation.isError && (
            <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
              Could not update account.
            </div>
          )}
        </div>
      </Modal>
      <Modal
        title="Change password"
        open={passwordModalOpen}
        okText="Update password"
        onOk={submitPasswordChange}
        confirmLoading={changePasswordMutation.isPending}
        okButtonProps={{
          disabled: !currentPassword || newPassword.length < 8 || newPassword !== confirmNewPassword,
        }}
        onCancel={() => {
          setPasswordModalOpen(false);
          resetPasswordForm();
        }}
      >
        <div className="space-y-3">
          {passwordChangeSucceeded && (
            <div className="rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-700">
              Password updated. Use the new password next time you sign in.
            </div>
          )}
          <label className="block">
            <span className="mb-1 block text-sm font-medium text-ink">Current password</span>
            <Input.Password
              value={currentPassword}
              onChange={(event) => {
                setCurrentPassword(event.target.value);
                setPasswordChangeSucceeded(false);
                changePasswordMutation.reset();
              }}
              placeholder="Current password"
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-sm font-medium text-ink">New password</span>
            <Input.Password
              value={newPassword}
              onChange={(event) => {
                setNewPassword(event.target.value);
                setPasswordChangeSucceeded(false);
                changePasswordMutation.reset();
              }}
              placeholder="At least 8 characters"
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-sm font-medium text-ink">Confirm new password</span>
            <Input.Password
              value={confirmNewPassword}
              onChange={(event) => {
                setConfirmNewPassword(event.target.value);
                setPasswordChangeSucceeded(false);
                changePasswordMutation.reset();
              }}
              onPressEnter={submitPasswordChange}
              placeholder="Repeat new password"
            />
          </label>
          {newPassword && confirmNewPassword && newPassword !== confirmNewPassword && (
            <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-700">
              New passwords do not match.
            </div>
          )}
          {changePasswordMutation.isError && (
            <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
              Could not update password. Check the current password and try again.
            </div>
          )}
        </div>
      </Modal>
      <Modal
        title="Rename conversation"
        open={Boolean(renameConversation)}
        okText="Save"
        onOk={submitRenameConversation}
        confirmLoading={updateConversationTitleMutation.isPending}
        okButtonProps={{ disabled: !renameConversationTitle.trim() }}
        onCancel={() => {
          setRenameConversation(null);
          setRenameConversationTitle('');
        }}
      >
        <Input
          autoFocus
          maxLength={120}
          value={renameConversationTitle}
          onChange={(event) => setRenameConversationTitle(event.target.value)}
          onPressEnter={submitRenameConversation}
          placeholder="Conversation title"
        />
      </Modal>
      <Modal
        title="Traveler profile"
        open={profileModalOpen}
        okText="Save"
        onOk={saveProfile}
        confirmLoading={updateUserProfileMutation.isPending}
        onCancel={() => setProfileModalOpen(false)}
      >
        <div className="space-y-3">
          <label className="block">
            <span className="mb-1 block text-sm font-medium text-ink">Display name</span>
            <Input
              maxLength={80}
              value={profileDisplayName}
              onChange={(event) => setProfileDisplayName(event.target.value)}
              placeholder="Anonymous traveler"
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-sm font-medium text-ink">Home city</span>
            <Input
              maxLength={80}
              value={profileHomeCity}
              onChange={(event) => setProfileHomeCity(event.target.value)}
              placeholder="Beijing"
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-sm font-medium text-ink">Preferred budget</span>
            <Select
              allowClear
              value={profilePreferredBudget || undefined}
              onChange={(value) => setProfilePreferredBudget(value ?? '')}
              className="w-full"
              options={[
                { value: 'low', label: 'Low' },
                { value: 'moderate', label: 'Moderate' },
                { value: 'premium', label: 'Premium' },
              ]}
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-sm font-medium text-ink">Travel style</span>
            <Input
              maxLength={80}
              value={profileTravelStyle}
              onChange={(event) => setProfileTravelStyle(event.target.value)}
              placeholder="Relaxed city walks"
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-sm font-medium text-ink">Interests</span>
            <Select
              mode="tags"
              maxCount={12}
              value={profileInterests}
              onChange={setProfileInterests}
              className="w-full"
              options={interestOptions.map((value) => ({ value, label: value }))}
            />
          </label>
        </div>
      </Modal>
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

function RuntimeStatus({
  health,
  loading,
  error,
}: {
  health?: HealthResponse;
  loading: boolean;
  error: boolean;
}) {
  const runtimeOnline = Boolean(health && health.status === 'ok' && !error);

  return (
    <section className="mb-5 rounded-lg border border-slate-200 bg-slate-50 p-3">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-ink">Runtime status</h2>
          <p className="mt-1 text-xs text-slate-500">{health?.env ?? (loading ? 'checking' : 'unavailable')}</p>
        </div>
        {loading && <Spin size="small" />}
      </div>
      <div className="grid gap-2">
        <StatusRow label="Agent Runtime" active={runtimeOnline} muted={loading} />
        <StatusRow label="LLM" active={Boolean(health?.llmEnabled)} muted={!runtimeOnline || loading} />
        <StatusRow label="PostgreSQL" active={Boolean(health?.databaseEnabled)} muted={!runtimeOnline || loading} />
        <StatusRow label="RabbitMQ" active={Boolean(health?.messageQueueEnabled)} muted={!runtimeOnline || loading} />
      </div>
    </section>
  );
}

function AccountStatus({
  user,
  loading,
  onLogin,
  onRegister,
  onEditAccount,
  onChangePassword,
  onLogout,
}: {
  user?: AuthUser | null;
  loading: boolean;
  onLogin: () => void;
  onRegister: () => void;
  onEditAccount: () => void;
  onChangePassword: () => void;
  onLogout: () => void;
}) {
  return (
    <section className="mb-5 rounded-lg border border-slate-200 bg-white p-3">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="text-sm font-semibold text-ink">Account</h2>
          <p className="mt-1 truncate text-xs text-slate-500">
            {user ? user.displayName || user.email : 'Anonymous mode'}
          </p>
        </div>
        {loading && <Spin size="small" />}
      </div>
      {user ? (
        <div className="grid gap-2">
          <Button size="small" onClick={onEditAccount}>
            Edit account
          </Button>
          <Button size="small" onClick={onChangePassword}>
            Change password
          </Button>
          <Button size="small" className="w-full" loading={loading} onClick={onLogout}>
            Sign out
          </Button>
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-2">
          <Button size="small" type="primary" onClick={onLogin}>
            Sign in
          </Button>
          <Button size="small" onClick={onRegister}>
            Register
          </Button>
        </div>
      )}
    </section>
  );
}

function TravelerProfile({
  profile,
  loading,
  onEdit,
  onUsePreferences,
}: {
  profile?: UserProfile;
  loading: boolean;
  onEdit: () => void;
  onUsePreferences: () => void;
}) {
  const hasPreferences = Boolean(profile?.preferredBudget || profile?.interests?.length);

  return (
    <section className="mb-5 rounded-lg border border-slate-200 bg-white p-3">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="text-sm font-semibold text-ink">Traveler profile</h2>
          <p className="mt-1 truncate text-xs text-slate-500">{profile?.displayName || 'Anonymous traveler'}</p>
        </div>
        {loading ? (
          <Spin size="small" />
        ) : (
          <Button type="text" size="small" icon={<EditOutlined />} aria-label="Edit traveler profile" onClick={onEdit} />
        )}
      </div>
      <div className="grid gap-2 text-xs text-slate-600">
        <ProfileDetail label="Home" value={profile?.homeCity} />
        <ProfileDetail label="Budget" value={profile?.preferredBudget} />
        <ProfileDetail label="Style" value={profile?.travelStyle} />
        <ProfileDetail label="Interests" value={profile?.interests?.join(', ')} />
      </div>
      {hasPreferences && (
        <Button size="small" className="mt-3 w-full" onClick={onUsePreferences}>
          Use preferences
        </Button>
      )}
    </section>
  );
}

function ProfileDetail({ label, value }: { label: string; value?: string }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-md bg-slate-50 px-2 py-2">
      <span className="font-medium text-slate-500">{label}</span>
      <span className="min-w-0 truncate text-right text-slate-700">{value || '-'}</span>
    </div>
  );
}

function StatusRow({ label, active, muted }: { label: string; active: boolean; muted: boolean }) {
  const colorClass = active ? 'bg-emerald-500' : muted ? 'bg-slate-300' : 'bg-red-500';
  const text = active ? 'online' : muted ? 'unknown' : 'offline';

  return (
    <div className="flex items-center justify-between rounded-md bg-white px-2 py-2 text-xs">
      <span className="font-medium text-slate-700">{label}</span>
      <span className="flex items-center gap-2 text-slate-500">
        <span className={`h-2 w-2 rounded-full ${colorClass}`} />
        {text}
      </span>
    </div>
  );
}

function HistorySection({
  title,
  emptyText,
  loading,
  hasItems,
  controls,
  footer,
  children,
}: {
  title: string;
  emptyText: string;
  loading: boolean;
  hasItems?: boolean;
  controls?: ReactNode;
  footer?: ReactNode;
  children: ReactNode;
}) {
  const hasVisibleItems = hasItems ?? (Array.isArray(children) ? children.length > 0 : Boolean(children));

  return (
    <section className="mb-5">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-ink">{title}</h2>
        {loading && <Spin size="small" />}
      </div>
      {controls && <div className="mb-3">{controls}</div>}
      <div className="space-y-2">
        {hasVisibleItems ? (
          children
        ) : (
          <div className="rounded-md border border-dashed border-slate-200 px-2 py-3">
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={emptyText} />
          </div>
        )}
      </div>
      {footer && <div className="mt-3">{footer}</div>}
    </section>
  );
}

function HistoryPagination({
  page,
  totalItems,
  pageSize,
  onChange,
}: {
  page: number;
  totalItems: number;
  pageSize: number;
  onChange: (page: number) => void;
}) {
  if (totalItems <= pageSize) {
    return null;
  }

  return (
    <Pagination
      simple
      size="small"
      current={page}
      pageSize={pageSize}
      total={totalItems}
      onChange={onChange}
      className="text-right"
    />
  );
}

function ConversationHistoryItem({
  conversation,
  active,
  onClick,
  onRename,
  onDelete,
}: {
  conversation: Conversation;
  active: boolean;
  onClick: () => void;
  onRename: () => void;
  onDelete: () => void;
}) {
  const messages = conversation.messages ?? [];
  const lastMessage = messages[messages.length - 1]?.content ?? 'No messages yet';

  return (
    <div
      className={`flex w-full items-start gap-2 rounded-md border px-3 py-2 transition ${
        active ? 'border-trail bg-mist' : 'border-slate-200 bg-white hover:border-trail/60 hover:bg-slate-50'
      }`}
    >
      <button type="button" onClick={onClick} className="min-w-0 flex-1 text-left">
        <div className="flex items-center gap-2 text-sm font-medium text-ink">
          <HistoryOutlined className="text-trail" />
          <span className="min-w-0 flex-1 truncate">{conversation.title}</span>
        </div>
        <p className="mt-1 line-clamp-2 text-xs leading-5 text-slate-500">{lastMessage}</p>
        <p className="mt-1 text-xs text-slate-400">{formatDateTime(conversation.updatedAt)}</p>
      </button>
      <Button type="text" size="small" icon={<EditOutlined />} aria-label="Rename conversation" onClick={onRename} />
      <Popconfirm title="Delete conversation?" okText="Delete" okButtonProps={{ danger: true }} onConfirm={onDelete}>
        <Button danger type="text" size="small" icon={<DeleteOutlined />} aria-label="Delete conversation" />
      </Popconfirm>
    </div>
  );
}

function TripPlanHistoryItem({
  tripPlan,
  active,
  onClick,
  onDelete,
  onToggleFavorite,
}: {
  tripPlan: SavedTripPlan;
  active: boolean;
  onClick: () => void;
  onDelete: () => void;
  onToggleFavorite: () => void;
}) {
  return (
    <div
      className={`flex w-full items-start gap-2 rounded-md border px-3 py-2 transition ${
        active ? 'border-coral bg-coral/5' : 'border-slate-200 bg-white hover:border-coral/60 hover:bg-slate-50'
      }`}
    >
      <button type="button" onClick={onClick} className="min-w-0 flex-1 text-left">
        <p className="truncate text-sm font-medium text-ink">{tripPlan.title}</p>
        <p className="mt-1 text-xs text-slate-500">
          {tripPlan.destination} / {tripPlan.days} days / {tripPlan.budget}
        </p>
        <p className="mt-1 text-xs text-slate-400">{formatDateTime(tripPlan.createdAt)}</p>
      </button>
      <Button
        type="text"
        size="small"
        icon={tripPlan.favorite ? <StarFilled /> : <StarOutlined />}
        aria-label={tripPlan.favorite ? 'Unfavorite itinerary' : 'Favorite itinerary'}
        className={tripPlan.favorite ? 'text-amber-500' : 'text-slate-400'}
        onClick={onToggleFavorite}
      />
      <Popconfirm title="Delete itinerary?" okText="Delete" okButtonProps={{ danger: true }} onConfirm={onDelete}>
        <Button danger type="text" size="small" icon={<DeleteOutlined />} aria-label="Delete itinerary" />
      </Popconfirm>
    </div>
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

function formatSummaryJobStatus(status?: ConversationSummaryJob['status']): string {
  return status ? status.toLowerCase().replace('_', ' ') : 'queued';
}

function splitInterests(value: string): string[] {
  return value
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);
}

function tripPlanToMarkdown(
  plan: TripPlanResponse,
  request: { destination: string; days: number; budget: string; interests: string },
): string {
  const header = [
    `# ${plan.title}`,
    '',
    `- Destination: ${request.destination}`,
    `- Days: ${request.days}`,
    `- Budget: ${request.budget}`,
  ];

  if (request.interests) {
    header.push(`- Interests: ${request.interests}`);
  }

  const body = [
    '',
    plan.summary,
    '',
    '## Itinerary',
    '',
    ...(plan.days ?? []).flatMap((day) => [
      `### Day ${day.day}: ${day.theme}`,
      '',
      `- Morning: ${day.morning}`,
      `- Afternoon: ${day.afternoon}`,
      `- Evening: ${day.evening}`,
      '',
    ]),
  ];

  const tips = plan.tips ?? [];
  if (tips.length > 0) {
    body.push('## Travel notes', '', ...tips.map((tip) => `- ${tip}`), '');
  }

  return [...header, ...body].join('\n').trim() + '\n';
}

function downloadTextFile(content: string, filename: string) {
  const blob = new Blob([content], { type: 'text/markdown;charset=utf-8' });
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
}

function slugify(value: string): string {
  const slug = value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
  return slug || 'trip-plan';
}
