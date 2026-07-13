import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Button, Empty, Input, InputNumber, Modal, Pagination, Popconfirm, Segmented, Select, Spin } from 'antd';
import {
  ArrowDownOutlined,
  ArrowUpOutlined,
  DeleteOutlined,
  DownloadOutlined,
  EditOutlined,
  HistoryOutlined,
  PlusOutlined,
  SendOutlined,
  StarFilled,
  StarOutlined,
  SyncOutlined,
  UploadOutlined,
} from '@ant-design/icons';
import {
  changePassword,
  confirmEmailVerification,
  confirmPasswordReset,
  createCurrentUserExportFile,
  createTripPlan,
  createConversationSummary,
  createConversationSummaryJob,
  deleteCurrentAuthUser,
  deleteConversation,
  deleteTripPlan,
  downloadCurrentUserExportFile,
  exportCurrentUserData,
  exportTripPlanMarkdown,
  getConversation,
  getConversationSummary,
  getCurrentAuthUser,
  getGithubOAuthStartUrl,
  getHealth,
  getLatestConversationSummaryJob,
  getAnonymousUserDataSummary,
  getAnonymousUserId,
  getTripPlan,
  getUserProfile,
  importAnonymousUserData,
  importCurrentUserData,
  isApiErrorStatus,
  listAuthIdentities,
  listAuthSessions,
  listUserSecurityEvents,
  loginUser,
  listConversations,
  listTripPlans,
  logoutUser,
  registerUser,
  regenerateTripPlanDay,
  requestEmailVerification,
  requestPasswordReset,
  revokeAuthSession,
  revokeOtherAuthSessions,
  sendChatMessage,
  unlinkAuthIdentity,
  updateConversationTitle,
  updateCurrentAuthUser,
  updateTripPlan,
  updateTripPlanFavorite,
  updateUserProfile,
  type AuthUser,
  type AuthIdentity,
  type AuthSessionInfo,
  type ChatMessage,
  type Conversation,
  type ConversationSummary,
  type ConversationSummaryJob,
  type HealthResponse,
  type Attraction,
  type Hotel,
  type Meal,
  type SavedTripPlan,
  type TripPlanResponse,
  type UserProfile,
  type UserExportFile,
  type UserSecurityEvent,
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
type AttractionTextField = 'name' | 'address' | 'description' | 'category';
type HotelTextField = 'name' | 'address' | 'priceRange' | 'rating' | 'distance' | 'type';
type MealTextField = 'type' | 'name' | 'address' | 'description';

export default function App() {
  const queryClient = useQueryClient();
  const importDataInputRef = useRef<HTMLInputElement | null>(null);
  const [destination, setDestination] = useState('Chengdu');
  const [days, setDays] = useState(3);
  const [budget, setBudget] = useState('moderate');
  const [interests, setInterests] = useState<string[]>(['local food', 'city walk']);
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [transportation, setTransportation] = useState('public transit');
  const [accommodation, setAccommodation] = useState('comfortable hotel');
  const [freeTextInput, setFreeTextInput] = useState('');
  const [plan, setPlan] = useState<TripPlanResponse | null>(null);
  const [selectedTripPlanId, setSelectedTripPlanId] = useState<string | undefined>();
  const [selectedTripPlanFavorite, setSelectedTripPlanFavorite] = useState(false);
  const [selectedTripPlanVersion, setSelectedTripPlanVersion] = useState(1);
  const [editingTripPlan, setEditingTripPlan] = useState<TripPlanResponse | null>(null);
  const [editingTripPlanTips, setEditingTripPlanTips] = useState('');
  const [tripPlanEditError, setTripPlanEditError] = useState('');
  const [regeneratingTripDay, setRegeneratingTripDay] = useState<number | null>(null);
  const [tripDayRegenerateInstruction, setTripDayRegenerateInstruction] = useState('');
  const [tripDayRegenerateError, setTripDayRegenerateError] = useState('');
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
  const [authActionMessage, setAuthActionMessage] = useState('');
  const [accountModalOpen, setAccountModalOpen] = useState(false);
  const [accountDisplayName, setAccountDisplayName] = useState('');
  const [passwordModalOpen, setPasswordModalOpen] = useState(false);
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmNewPassword, setConfirmNewPassword] = useState('');
  const [passwordChangeSucceeded, setPasswordChangeSucceeded] = useState(false);
  const [passwordResetRequestModalOpen, setPasswordResetRequestModalOpen] = useState(false);
  const [passwordResetIntent, setPasswordResetIntent] = useState<'RESET' | 'SET'>('RESET');
  const [passwordResetEmail, setPasswordResetEmail] = useState('');
  const [passwordResetRequested, setPasswordResetRequested] = useState(false);
  const [passwordResetConfirmModalOpen, setPasswordResetConfirmModalOpen] = useState(false);
  const [passwordResetToken, setPasswordResetToken] = useState('');
  const [passwordResetNewPassword, setPasswordResetNewPassword] = useState('');
  const [passwordResetConfirmPassword, setPasswordResetConfirmPassword] = useState('');
  const [deleteAccountModalOpen, setDeleteAccountModalOpen] = useState(false);
  const [deleteAccountPassword, setDeleteAccountPassword] = useState('');
  const [deleteAccountConfirmation, setDeleteAccountConfirmation] = useState('');
  const [exportDataError, setExportDataError] = useState('');
  const [archivedExportFile, setArchivedExportFile] = useState<UserExportFile | null>(null);
  const [archiveExportError, setArchiveExportError] = useState('');
  const [importDataError, setImportDataError] = useState('');
  const [anonymousImportMessage, setAnonymousImportMessage] = useState('');
  const [anonymousImportPromptOpen, setAnonymousImportPromptOpen] = useState(false);
  const [anonymousImportPromptDismissed, setAnonymousImportPromptDismissed] = useState(false);

  const authUserQuery = useQuery({
    queryKey: ['auth-user'],
    queryFn: getCurrentAuthUser,
    retry: false,
  });
  const anonymousImportPromptStorageKey = authUserQuery.data
    ? `travel-agent-cloud.anonymous-import.${authUserQuery.data.id}.${getAnonymousUserId()}`
    : '';

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

  const securityEventsQuery = useQuery({
    queryKey: ['security-events'],
    queryFn: () => listUserSecurityEvents(1, 5),
    enabled: Boolean(authUserQuery.data),
  });

  const authIdentitiesQuery = useQuery({
    queryKey: ['auth-identities'],
    queryFn: listAuthIdentities,
    enabled: Boolean(authUserQuery.data),
  });

  const authSessionsQuery = useQuery({
    queryKey: ['auth-sessions'],
    queryFn: listAuthSessions,
    enabled: Boolean(authUserQuery.data),
  });

  const anonymousDataSummaryQuery = useQuery({
    queryKey: ['anonymous-data-summary', authUserQuery.data?.id],
    queryFn: getAnonymousUserDataSummary,
    enabled: Boolean(authUserQuery.data),
    retry: false,
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
      setAnonymousImportMessage('');
      setAnonymousImportPromptOpen(false);
      setAnonymousImportPromptDismissed(false);
      queryClient.setQueryData(['auth-user'], null);
      queryClient.invalidateQueries({ queryKey: ['user-profile'] });
      queryClient.invalidateQueries({ queryKey: ['conversations'] });
      queryClient.invalidateQueries({ queryKey: ['trip-plans'] });
      queryClient.invalidateQueries({ queryKey: ['security-events'] });
      queryClient.invalidateQueries({ queryKey: ['auth-identities'] });
      queryClient.invalidateQueries({ queryKey: ['auth-sessions'] });
    },
  });

  const changePasswordMutation = useMutation({
    mutationFn: changePassword,
    onSuccess: () => {
      resetPasswordForm();
      setPasswordChangeSucceeded(true);
      queryClient.invalidateQueries({ queryKey: ['security-events'] });
    },
  });

  const requestEmailVerificationMutation = useMutation({
    mutationFn: requestEmailVerification,
    onSuccess: (response) => {
      setAuthActionMessage(
        response.actionUrl
          ? `Verification link generated: ${response.actionUrl}`
          : response.delivery === 'already_verified'
            ? 'Email is already verified.'
            : 'Verification email sent.',
      );
      queryClient.invalidateQueries({ queryKey: ['security-events'] });
    },
  });

  const confirmEmailVerificationMutation = useMutation({
    mutationFn: confirmEmailVerification,
    onSuccess: (user) => {
      queryClient.setQueryData(['auth-user'], user);
      setAuthActionMessage('Email verified.');
      setExportDataError('');
      setImportDataError('');
      queryClient.invalidateQueries({ queryKey: ['security-events'] });
    },
    onError: () => {
      setAuthActionMessage('Verification link is invalid or expired.');
    },
  });

  const requestPasswordResetMutation = useMutation({
    mutationFn: requestPasswordReset,
    onSuccess: (response) => {
      setPasswordResetRequested(true);
      if (response.devToken) {
        setPasswordResetToken(response.devToken);
        setPasswordResetRequestModalOpen(false);
        setPasswordResetConfirmModalOpen(true);
      }
    },
  });

  const confirmPasswordResetMutation = useMutation({
    mutationFn: confirmPasswordReset,
    onSuccess: () => {
      const wasSignedIn = Boolean(authUserQuery.data);
      const intent = passwordResetIntent;
      resetPasswordResetForm();
      setPasswordResetConfirmModalOpen(false);
      if (wasSignedIn || intent === 'SET') {
        setAuthActionMessage('Project password set. You can now use password-protected account actions.');
      } else {
        setAuthMode('LOGIN');
        setAuthModalOpen(true);
        setAuthActionMessage('Password reset. Sign in with the new password.');
      }
      queryClient.invalidateQueries({ queryKey: ['auth-user'] });
      queryClient.invalidateQueries({ queryKey: ['security-events'] });
    },
  });

  const updateAuthUserMutation = useMutation({
    mutationFn: updateCurrentAuthUser,
    onSuccess: (user) => {
      queryClient.setQueryData(['auth-user'], user);
      setAccountModalOpen(false);
    },
  });

  const unlinkAuthIdentityMutation = useMutation({
    mutationFn: unlinkAuthIdentity,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['auth-identities'] });
      queryClient.invalidateQueries({ queryKey: ['security-events'] });
    },
  });

  const revokeAuthSessionMutation = useMutation({
    mutationFn: revokeAuthSession,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['auth-sessions'] });
      queryClient.invalidateQueries({ queryKey: ['security-events'] });
    },
  });

  const revokeOtherAuthSessionsMutation = useMutation({
    mutationFn: revokeOtherAuthSessions,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['auth-sessions'] });
      queryClient.invalidateQueries({ queryKey: ['security-events'] });
    },
  });

  const exportUserDataMutation = useMutation({
    mutationFn: exportCurrentUserData,
    onMutate: () => {
      setExportDataError('');
    },
    onSuccess: (data) => {
      downloadJsonFile(data, `travel-agent-data-${new Date().toISOString().slice(0, 10)}.json`);
    },
    onError: () => {
      setExportDataError('Could not export account data. Verify your email and try again.');
    },
  });

  const archiveUserDataMutation = useMutation({
    mutationFn: createCurrentUserExportFile,
    onMutate: () => {
      setArchiveExportError('');
      setArchivedExportFile(null);
    },
    onSuccess: (file) => {
      setArchivedExportFile(file);
      queryClient.invalidateQueries({ queryKey: ['security-events'] });
    },
    onError: () => {
      setArchiveExportError('Could not archive account data in object storage.');
    },
  });

  const downloadArchivedExportMutation = useMutation({
    mutationFn: async (file: UserExportFile) => ({
      file,
      blob: await downloadCurrentUserExportFile(file.id),
    }),
    onSuccess: ({ file, blob }) => {
      downloadBlobFile(blob, file.filename);
    },
    onError: () => {
      setArchiveExportError('Could not download the archived export.');
    },
  });

  const importUserDataMutation = useMutation({
    mutationFn: importCurrentUserData,
    onSuccess: () => {
      setImportDataError('');
      clearWorkspace();
      queryClient.invalidateQueries({ queryKey: ['user-profile'] });
      queryClient.invalidateQueries({ queryKey: ['conversations'] });
      queryClient.invalidateQueries({ queryKey: ['trip-plans'] });
      queryClient.invalidateQueries({ queryKey: ['security-events'] });
    },
    onError: () => {
      setImportDataError('Could not import this data file.');
    },
  });

  const importAnonymousUserDataMutation = useMutation({
    mutationFn: importAnonymousUserData,
    onSuccess: (result) => {
      setAnonymousImportMessage(
        `Imported ${result.conversationsImported} conversations and ${result.tripPlansImported} trip plans from this browser.`,
      );
      if (anonymousImportPromptStorageKey) {
        window.localStorage.setItem(anonymousImportPromptStorageKey, 'handled');
      }
      setAnonymousImportPromptOpen(false);
      setAnonymousImportPromptDismissed(true);
      clearWorkspace();
      queryClient.invalidateQueries({ queryKey: ['anonymous-data-summary'] });
      queryClient.invalidateQueries({ queryKey: ['user-profile'] });
      queryClient.invalidateQueries({ queryKey: ['conversations'] });
      queryClient.invalidateQueries({ queryKey: ['trip-plans'] });
      queryClient.invalidateQueries({ queryKey: ['security-events'] });
    },
    onError: () => {
      setAnonymousImportPromptOpen(false);
      setAnonymousImportMessage('Could not import local anonymous data.');
    },
  });

  const deleteAccountMutation = useMutation({
    mutationFn: deleteCurrentAuthUser,
    onSuccess: () => {
      setDeleteAccountModalOpen(false);
      resetDeleteAccountForm();
      clearWorkspace();
      setAnonymousImportMessage('');
      setAnonymousImportPromptOpen(false);
      setAnonymousImportPromptDismissed(false);
      queryClient.setQueryData(['auth-user'], null);
      queryClient.invalidateQueries({ queryKey: ['user-profile'] });
      queryClient.invalidateQueries({ queryKey: ['conversations'] });
      queryClient.invalidateQueries({ queryKey: ['trip-plans'] });
      queryClient.invalidateQueries({ queryKey: ['security-events'] });
    },
  });

  const tripPlanMutation = useMutation({
    mutationFn: createTripPlan,
    onSuccess: (response) => {
      setPlan(response);
      setSelectedTripPlanId(response.savedTripPlanId);
      setSelectedTripPlanFavorite(false);
      setSelectedTripPlanVersion(1);
      setConversationId(response.conversationId);
      setConversationSummary(null);
      resetConversationSummaryJobPolling();
      setRegeneratingTripDay(null);
      setTripDayRegenerateInstruction('');
      setTripDayRegenerateError('');
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
      setSelectedTripPlanVersion(savedTripPlan.version);
      setDestination(savedTripPlan.destination);
      setDays(savedTripPlan.days);
      setBudget(savedTripPlan.budget);
      setInterests(splitInterests(savedTripPlan.interests));
      setStartDate(savedTripPlan.plan.startDate ?? '');
      setEndDate(savedTripPlan.plan.endDate ?? '');
      setTransportation(savedTripPlan.plan.transportation || 'public transit');
      setAccommodation(savedTripPlan.plan.accommodation || 'comfortable hotel');
      setFreeTextInput(savedTripPlan.plan.freeTextInput ?? '');
      setRegeneratingTripDay(null);
      setTripDayRegenerateInstruction('');
      setTripDayRegenerateError('');
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
        setSelectedTripPlanVersion(1);
        setPlan(null);
        setRegeneratingTripDay(null);
        setTripDayRegenerateInstruction('');
        setTripDayRegenerateError('');
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

  const updateTripPlanMutation = useMutation({
    mutationFn: ({
      tripPlanId,
      editedPlan,
      expectedVersion,
    }: {
      tripPlanId: string;
      editedPlan: TripPlanResponse;
      expectedVersion: number;
    }) => updateTripPlan(tripPlanId, { plan: editedPlan, expectedVersion }),
    onMutate: () => {
      setTripPlanEditError('');
    },
    onSuccess: (savedTripPlan) => {
      setPlan(savedTripPlan.plan);
      setSelectedTripPlanVersion(savedTripPlan.version);
      setEditingTripPlan(null);
      setEditingTripPlanTips('');
      setTripPlanEditError('');
      queryClient.invalidateQueries({ queryKey: ['trip-plans'] });
    },
    onError: (error) => {
      setTripPlanEditError(
        isApiErrorStatus(error, 409)
          ? 'This itinerary changed elsewhere. Close the editor, reload the saved itinerary, and apply your changes again.'
          : 'Could not save the itinerary. Check the fields and try again.',
      );
    },
  });

  const regenerateTripDayMutation = useMutation({
    mutationFn: ({
      tripPlanId,
      day,
      instruction,
      expectedVersion,
    }: {
      tripPlanId: string;
      day: number;
      instruction: string;
      expectedVersion: number;
    }) => regenerateTripPlanDay(tripPlanId, day, { instruction, expectedVersion }),
    onMutate: () => {
      setTripDayRegenerateError('');
    },
    onSuccess: (savedTripPlan) => {
      setPlan(savedTripPlan.plan);
      setSelectedTripPlanVersion(savedTripPlan.version);
      setRegeneratingTripDay(null);
      setTripDayRegenerateInstruction('');
      setTripDayRegenerateError('');
      queryClient.invalidateQueries({ queryKey: ['trip-plans'] });
      if (savedTripPlan.conversationId) {
        queryClient.invalidateQueries({ queryKey: ['conversations'] });
      }
    },
    onError: (error) => {
      setTripDayRegenerateError(
        isApiErrorStatus(error, 409)
          ? 'This itinerary changed elsewhere. Reload the saved itinerary before regenerating this day.'
          : 'Could not regenerate this day. Adjust the instruction and try again.',
      );
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
            startDate,
            endDate,
            transportation,
            accommodation,
            freeTextInput,
          });
      downloadTextFile(markdown, `${slugify(plan.title)}.md`);
    },
  });

  const requestPreview = useMemo(
    () => {
      const dateRange = startDate && endDate ? ` from ${startDate} to ${endDate}` : '';
      const focus = interests.length > 0 ? `, focused on ${interests.join(', ')}` : '';
      return `${days} days in ${destination}${dateRange}, ${budget} budget, ${transportation}, ${accommodation}${focus}`;
    },
    [accommodation, budget, days, destination, endDate, interests, startDate, transportation],
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

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const authAction = params.get('authAction');
    const token = params.get('token');
    if (!authAction) {
      return;
    }

    if (authAction === 'verify-email' && token) {
      confirmEmailVerificationMutation.mutate({ token });
    }
    if (authAction === 'reset-password' && token) {
      setPasswordResetToken(token);
      setPasswordResetConfirmModalOpen(true);
    }
    if (authAction === 'oauth-github') {
      const authStatus = params.get('authStatus');
      if (authStatus === 'success') {
        setAuthActionMessage('GitHub sign-in completed.');
        queryClient.invalidateQueries({ queryKey: ['auth-user'] });
        queryClient.invalidateQueries({ queryKey: ['auth-identities'] });
        queryClient.invalidateQueries({ queryKey: ['security-events'] });
      } else {
        setAuthActionMessage('GitHub sign-in failed. Check the OAuth app configuration and try again.');
      }
    }
    window.history.replaceState({}, document.title, window.location.pathname);
  }, []);

  useEffect(() => {
    if (
      authUserQuery.data &&
      anonymousDataSummaryQuery.data?.hasData &&
      !anonymousImportPromptDismissed &&
      !anonymousImportPromptOpen &&
      (!anonymousImportPromptStorageKey || !window.localStorage.getItem(anonymousImportPromptStorageKey))
    ) {
      setAnonymousImportPromptOpen(true);
    }
  }, [
    anonymousDataSummaryQuery.data?.hasData,
    anonymousImportPromptDismissed,
    anonymousImportPromptOpen,
    anonymousImportPromptStorageKey,
    authUserQuery.data,
  ]);

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
    setAnonymousImportMessage('');
    setAnonymousImportPromptDismissed(false);
    setAnonymousImportPromptOpen(false);
    clearWorkspace();
    queryClient.setQueryData(['auth-user'], user);
    queryClient.invalidateQueries({ queryKey: ['user-profile'] });
    queryClient.invalidateQueries({ queryKey: ['conversations'] });
    queryClient.invalidateQueries({ queryKey: ['trip-plans'] });
    queryClient.invalidateQueries({ queryKey: ['security-events'] });
    queryClient.invalidateQueries({ queryKey: ['auth-identities'] });
    queryClient.invalidateQueries({ queryKey: ['auth-sessions'] });
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

  function resetPasswordResetForm() {
    setPasswordResetIntent('RESET');
    setPasswordResetEmail('');
    setPasswordResetRequested(false);
    setPasswordResetToken('');
    setPasswordResetNewPassword('');
    setPasswordResetConfirmPassword('');
    requestPasswordResetMutation.reset();
    confirmPasswordResetMutation.reset();
  }

  function resetDeleteAccountForm() {
    setDeleteAccountPassword('');
    setDeleteAccountConfirmation('');
    deleteAccountMutation.reset();
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

  function openSetPasswordFlow() {
    resetPasswordResetForm();
    setPasswordResetIntent('SET');
    setPasswordResetEmail(authUserQuery.data?.email ?? '');
    setPasswordResetRequestModalOpen(true);
    setAuthActionMessage('Request a password setup link for this account email.');
  }

  function submitPasswordResetRequest() {
    const email = passwordResetEmail.trim();
    if (!email || requestPasswordResetMutation.isPending) {
      return;
    }
    requestPasswordResetMutation.mutate({ email });
  }

  function submitPasswordResetConfirm() {
    if (
      !passwordResetToken ||
      passwordResetNewPassword.length < 8 ||
      passwordResetNewPassword !== passwordResetConfirmPassword
    ) {
      return;
    }
    confirmPasswordResetMutation.mutate({
      token: passwordResetToken,
      newPassword: passwordResetNewPassword,
    });
  }

  function submitDeleteAccount() {
    if (!deleteAccountPassword || deleteAccountConfirmation.trim().toUpperCase() !== 'DELETE') {
      return;
    }
    deleteAccountMutation.mutate({
      currentPassword: deleteAccountPassword,
      confirmation: deleteAccountConfirmation,
    });
  }

  async function importUserDataFile(file: File | undefined) {
    setImportDataError('');
    if (!file) {
      return;
    }
    if (file.size > 2 * 1024 * 1024) {
      setImportDataError('Data file is too large.');
      return;
    }

    try {
      const parsed = JSON.parse(await file.text());
      importUserDataMutation.mutate(parsed);
    } catch {
      setImportDataError('Could not read this JSON file.');
    }
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
    setSelectedTripPlanVersion(1);
    setEditingTripPlan(null);
    setEditingTripPlanTips('');
    setTripPlanEditError('');
    setRegeneratingTripDay(null);
    setTripDayRegenerateInstruction('');
    setTripDayRegenerateError('');
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

  const updateDateRange = (nextStartDate: string, nextEndDate: string) => {
    setStartDate(nextStartDate);
    setEndDate(nextEndDate);
    const derivedDays = calculateInclusiveDays(nextStartDate, nextEndDate);
    if (derivedDays !== null) {
      setDays(derivedDays);
    }
  };

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

  const openTripPlanEditor = () => {
    if (!plan || !selectedTripPlanId) {
      return;
    }
    setEditingTripPlan({
      ...plan,
      days: plan.days.map((day) => ({
        ...day,
        hotel: day.hotel
          ? {
              ...day.hotel,
              location: day.hotel.location ? { ...day.hotel.location } : day.hotel.location,
            }
          : day.hotel,
        attractions: (day.attractions ?? []).map((attraction) => ({
          ...attraction,
          location: attraction.location ? { ...attraction.location } : attraction.location,
        })),
        meals: (day.meals ?? []).map((meal) => ({
          ...meal,
          location: meal.location ? { ...meal.location } : meal.location,
        })),
      })),
      tips: [...plan.tips],
    });
    setEditingTripPlanTips(plan.tips.join('\n'));
    setTripPlanEditError('');
    updateTripPlanMutation.reset();
  };

  const updateEditingTripDay = (index: number, field: keyof TripPlanResponse['days'][number], value: string) => {
    setEditingTripPlan((current) => {
      if (!current) {
        return current;
      }
      return {
        ...current,
        days: current.days.map((day, dayIndex) => (dayIndex === index ? { ...day, [field]: value } : day)),
      };
    });
  };

  const updateEditingDayHotel = (dayIndex: number, updater: (hotel: Hotel | null, dayNumber: number) => Hotel | null) => {
    setEditingTripPlan((current) => {
      if (!current) {
        return current;
      }
      return {
        ...current,
        days: current.days.map((day, index) =>
          index === dayIndex
            ? {
                ...day,
                hotel: updater(day.hotel ?? null, day.day),
              }
            : day,
        ),
      };
    });
  };

  const updateEditingHotelText = (dayIndex: number, field: HotelTextField, value: string) => {
    updateEditingDayHotel(dayIndex, (hotel, dayNumber) => ({
      ...(hotel ?? createDraftHotel(dayNumber)),
      [field]: value,
    }));
  };

  const updateEditingHotelCost = (dayIndex: number, value: number | string | null) => {
    const numericValue = typeof value === 'string' ? Number(value) : value;
    updateEditingDayHotel(dayIndex, (hotel, dayNumber) => ({
      ...(hotel ?? createDraftHotel(dayNumber)),
      estimatedCost: numericValue ?? 0,
    }));
  };

  const addEditingHotel = (dayIndex: number) => {
    updateEditingDayHotel(dayIndex, (hotel, dayNumber) => hotel ?? createDraftHotel(dayNumber));
  };

  const clearEditingHotel = (dayIndex: number) => {
    updateEditingDayHotel(dayIndex, () => null);
  };

  const updateEditingDayMeals = (
    dayIndex: number,
    updater: (meals: Meal[], dayNumber: number) => Meal[],
  ) => {
    setEditingTripPlan((current) => {
      if (!current) {
        return current;
      }
      return {
        ...current,
        days: current.days.map((day, index) =>
          index === dayIndex
            ? {
                ...day,
                meals: updater([...(day.meals ?? [])], day.day),
              }
            : day,
        ),
      };
    });
  };

  const updateEditingMealText = (dayIndex: number, mealIndex: number, field: MealTextField, value: string) => {
    updateEditingDayMeals(dayIndex, (meals) =>
      meals.map((meal, index) => (index === mealIndex ? { ...meal, [field]: value } : meal)),
    );
  };

  const updateEditingMealCost = (dayIndex: number, mealIndex: number, value: number | string | null) => {
    const numericValue = typeof value === 'string' ? Number(value) : value;
    updateEditingDayMeals(dayIndex, (meals) =>
      meals.map((meal, index) => (index === mealIndex ? { ...meal, estimatedCost: numericValue ?? 0 } : meal)),
    );
  };

  const addEditingMeal = (dayIndex: number) => {
    updateEditingDayMeals(dayIndex, (meals, dayNumber) => [...meals, createDraftMeal(dayNumber, meals.length + 1)]);
  };

  const deleteEditingMeal = (dayIndex: number, mealIndex: number) => {
    updateEditingDayMeals(dayIndex, (meals) => meals.filter((_meal, index) => index !== mealIndex));
  };

  const updateEditingDayAttractions = (
    dayIndex: number,
    updater: (attractions: Attraction[], dayNumber: number) => Attraction[],
  ) => {
    setEditingTripPlan((current) => {
      if (!current) {
        return current;
      }
      return {
        ...current,
        days: current.days.map((day, index) =>
          index === dayIndex
            ? {
                ...day,
                attractions: updater([...(day.attractions ?? [])], day.day),
              }
            : day,
        ),
      };
    });
  };

  const updateEditingAttractionText = (
    dayIndex: number,
    attractionIndex: number,
    field: AttractionTextField,
    value: string,
  ) => {
    updateEditingDayAttractions(dayIndex, (attractions) =>
      attractions.map((attraction, index) =>
        index === attractionIndex ? { ...attraction, [field]: value } : attraction,
      ),
    );
  };

  const updateEditingAttractionNumber = (
    dayIndex: number,
    attractionIndex: number,
    field: 'visitDuration' | 'ticketPrice',
    value: number | string | null,
  ) => {
    const numericValue = typeof value === 'string' ? Number(value) : value;
    updateEditingDayAttractions(dayIndex, (attractions) =>
      attractions.map((attraction, index) =>
        index === attractionIndex ? { ...attraction, [field]: numericValue ?? 0 } : attraction,
      ),
    );
  };

  const addEditingAttraction = (dayIndex: number) => {
    updateEditingDayAttractions(dayIndex, (attractions, dayNumber) => [
      ...attractions,
      createDraftAttraction(dayNumber, attractions.length + 1),
    ]);
  };

  const deleteEditingAttraction = (dayIndex: number, attractionIndex: number) => {
    updateEditingDayAttractions(dayIndex, (attractions) =>
      attractions.filter((_attraction, index) => index !== attractionIndex),
    );
  };

  const moveEditingAttraction = (dayIndex: number, attractionIndex: number, direction: -1 | 1) => {
    updateEditingDayAttractions(dayIndex, (attractions) => {
      const nextIndex = attractionIndex + direction;
      if (nextIndex < 0 || nextIndex >= attractions.length) {
        return attractions;
      }
      const reordered = [...attractions];
      const [item] = reordered.splice(attractionIndex, 1);
      reordered.splice(nextIndex, 0, item);
      return reordered;
    });
  };

  const submitTripPlanEdit = () => {
    if (!selectedTripPlanId || !editingTripPlan || !isTripPlanDraftValid(editingTripPlan, editingTripPlanTips)) {
      return;
    }
    updateTripPlanMutation.mutate({
      tripPlanId: selectedTripPlanId,
      editedPlan: {
        ...editingTripPlan,
        title: editingTripPlan.title.trim(),
        summary: editingTripPlan.summary.trim(),
        days: editingTripPlan.days.map((day) => ({
          ...day,
          theme: day.theme.trim(),
          morning: day.morning.trim(),
          afternoon: day.afternoon.trim(),
          evening: day.evening.trim(),
          description: day.description?.trim() ?? '',
          transportation: day.transportation?.trim() ?? '',
          accommodation: day.accommodation?.trim() ?? '',
          hotel: normalizeHotel(day.hotel ?? null),
          attractions: normalizeAttractions(day.attractions ?? []),
          meals: normalizeMeals(day.meals ?? []),
        })),
        tips: editingTripPlanTips
          .split('\n')
          .map((tip) => tip.trim())
          .filter(Boolean),
      },
      expectedVersion: selectedTripPlanVersion,
    });
  };

  const openTripDayRegenerator = (day: number) => {
    setRegeneratingTripDay(day);
    setTripDayRegenerateInstruction('');
    setTripDayRegenerateError('');
    regenerateTripDayMutation.reset();
  };

  const submitTripDayRegeneration = () => {
    const instruction = tripDayRegenerateInstruction.trim();
    if (!selectedTripPlanId || regeneratingTripDay === null || !instruction) {
      return;
    }
    regenerateTripDayMutation.mutate({
      tripPlanId: selectedTripPlanId,
      day: regeneratingTripDay,
      instruction,
      expectedVersion: selectedTripPlanVersion,
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

          <RuntimeStatus health={healthQuery.data} loading={healthQuery.isLoading} error={healthQuery.isError} />
          <AccountStatus
            user={authUserQuery.data}
            authIdentities={authIdentitiesQuery.data?.data ?? []}
            authSessions={authSessionsQuery.data?.data ?? []}
            securityEvents={securityEventsQuery.data?.data ?? []}
            loading={
              authUserQuery.isLoading ||
              authIdentitiesQuery.isLoading ||
              authSessionsQuery.isLoading ||
              securityEventsQuery.isLoading ||
              logoutMutation.isPending ||
              changePasswordMutation.isPending ||
              updateAuthUserMutation.isPending ||
              unlinkAuthIdentityMutation.isPending ||
              revokeAuthSessionMutation.isPending ||
              revokeOtherAuthSessionsMutation.isPending ||
              exportUserDataMutation.isPending ||
              archiveUserDataMutation.isPending ||
              downloadArchivedExportMutation.isPending ||
              importUserDataMutation.isPending ||
              importAnonymousUserDataMutation.isPending ||
              requestEmailVerificationMutation.isPending ||
              deleteAccountMutation.isPending
            }
            onLogin={() => openAuthModal('LOGIN')}
            onRegister={() => openAuthModal('REGISTER')}
            githubOAuthEnabled={Boolean(healthQuery.data?.githubOAuthEnabled)}
            onStartGithubOAuth={() => {
              window.location.assign(getGithubOAuthStartUrl());
            }}
            onUnlinkGithub={() => unlinkAuthIdentityMutation.mutate('github')}
            onRevokeSession={(sessionId) => revokeAuthSessionMutation.mutate(sessionId)}
            onRevokeOtherSessions={() => revokeOtherAuthSessionsMutation.mutate()}
            authActionMessage={authActionMessage}
            onRequestEmailVerification={() => requestEmailVerificationMutation.mutate()}
            onEditAccount={() => {
              setAccountDisplayName(authUserQuery.data?.displayName ?? '');
              updateAuthUserMutation.reset();
              setAccountModalOpen(true);
            }}
            onChangePassword={() => {
              resetPasswordForm();
              setPasswordModalOpen(true);
            }}
            onSetPassword={openSetPasswordFlow}
            onExportData={() => exportUserDataMutation.mutate()}
            objectStorageEnabled={Boolean(healthQuery.data?.objectStorageEnabled)}
            archivedExportFile={archivedExportFile}
            archiveExportError={archiveExportError}
            onArchiveData={() => archiveUserDataMutation.mutate()}
            onDownloadArchivedExport={() =>
              archivedExportFile && downloadArchivedExportMutation.mutate(archivedExportFile)
            }
            onImportData={() => {
              setImportDataError('');
              importDataInputRef.current?.click();
            }}
            onImportAnonymousData={() => {
              setAnonymousImportMessage('');
              importAnonymousUserDataMutation.mutate();
            }}
            exportDataError={exportDataError}
            importDataError={importDataError}
            anonymousImportMessage={anonymousImportMessage}
            onDeleteAccount={() => {
              resetDeleteAccountForm();
              setDeleteAccountModalOpen(true);
            }}
            onLogout={() => logoutMutation.mutate()}
          />
          <input
            ref={importDataInputRef}
            type="file"
            accept="application/json,.json"
            className="hidden"
            onChange={(event) => {
              void importUserDataFile(event.target.files?.[0]);
              event.target.value = '';
            }}
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
              <InputNumber min={1} max={30} value={days} onChange={(value) => setDays(value ?? 1)} className="w-full" />
            </label>

            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-1">
              <label className="block">
                <span className="mb-2 block text-sm font-medium text-ink">Start date</span>
                <Input
                  type="date"
                  value={startDate}
                  onChange={(event) => updateDateRange(event.target.value, endDate)}
                />
              </label>
              <label className="block">
                <span className="mb-2 block text-sm font-medium text-ink">End date</span>
                <Input
                  type="date"
                  value={endDate}
                  onChange={(event) => updateDateRange(startDate, event.target.value)}
                />
              </label>
            </div>

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
              <span className="mb-2 block text-sm font-medium text-ink">Transportation</span>
              <Select
                value={transportation}
                onChange={setTransportation}
                className="w-full"
                options={[
                  { value: 'public transit', label: 'Public transit' },
                  { value: 'walking and metro', label: 'Walking and metro' },
                  { value: 'taxi / ride hailing', label: 'Taxi / ride hailing' },
                  { value: 'self drive', label: 'Self drive' },
                ]}
              />
            </label>

            <label className="block">
              <span className="mb-2 block text-sm font-medium text-ink">Accommodation</span>
              <Select
                value={accommodation}
                onChange={setAccommodation}
                className="w-full"
                options={[
                  { value: 'budget hostel', label: 'Budget hostel' },
                  { value: 'comfortable hotel', label: 'Comfortable hotel' },
                  { value: 'boutique hotel', label: 'Boutique hotel' },
                  { value: 'premium hotel', label: 'Premium hotel' },
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

            <label className="block">
              <span className="mb-2 block text-sm font-medium text-ink">Additional constraints</span>
              <Input.TextArea
                rows={3}
                maxLength={1000}
                value={freeTextInput}
                onChange={(event) => setFreeTextInput(event.target.value)}
                placeholder="No early mornings, avoid stairs, include spicy food..."
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
                  startDate: startDate || undefined,
                  endDate: endDate || undefined,
                  transportation,
                  accommodation,
                  preferences: interests,
                  freeTextInput,
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
                    <Button icon={<EditOutlined />} onClick={openTripPlanEditor}>
                      Edit
                    </Button>
                  )}
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

              <div className="mb-5 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                <PlanMeta label="Dates" value={formatDateRange(plan.startDate, plan.endDate)} />
                <PlanMeta label="Transportation" value={plan.transportation || transportation} />
                <PlanMeta label="Accommodation" value={plan.accommodation || accommodation} />
                <PlanMeta label="Preferences" value={(plan.preferences?.length ? plan.preferences : interests).join(', ')} />
              </div>

              {(plan.budget || (plan.weatherInfo?.length ?? 0) > 0 || plan.overallSuggestions) && (
                <div className="mb-5 grid gap-4 lg:grid-cols-[280px_minmax(0,1fr)]">
                  {plan.budget && (
                    <section className="rounded-lg border border-slate-200 p-4">
                      <h3 className="font-semibold text-ink">Budget estimate</h3>
                      <div className="mt-3 grid gap-2 text-sm text-slate-600">
                        <PlanCost label="Attractions" value={plan.budget.totalAttractions} />
                        <PlanCost label="Hotels" value={plan.budget.totalHotels} />
                        <PlanCost label="Meals" value={plan.budget.totalMeals} />
                        <PlanCost label="Transportation" value={plan.budget.totalTransportation} />
                        <div className="mt-2 flex items-center justify-between border-t border-slate-200 pt-2 font-semibold text-ink">
                          <span>Total</span>
                          <span>{formatCost(plan.budget.total)}</span>
                        </div>
                      </div>
                    </section>
                  )}

                  <section className="rounded-lg border border-slate-200 p-4">
                    <h3 className="font-semibold text-ink">Weather and planning notes</h3>
                    {plan.weatherInfo?.length ? (
                      <div className="mt-3 grid gap-2 md:grid-cols-2">
                        {plan.weatherInfo.map((weather) => (
                          <div key={weather.date} className="rounded-md bg-slate-50 p-3 text-sm text-slate-600">
                            <p className="font-medium text-ink">{weather.date}</p>
                            <p className="mt-1">
                              {weather.dayWeather || 'Unknown'} / {weather.nightWeather || 'Unknown'}
                            </p>
                            <p>
                              {weather.dayTemp}C / {weather.nightTemp}C, {weather.windDirection} {weather.windPower}
                            </p>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="mt-2 text-sm text-slate-500">Weather data will appear after tool enrichment.</p>
                    )}
                    {plan.overallSuggestions && (
                      <p className="mt-3 rounded-md bg-mist p-3 text-sm leading-6 text-slate-700">
                        {plan.overallSuggestions}
                      </p>
                    )}
                  </section>
                </div>
              )}

              <div className="grid gap-4">
                {(plan.days ?? []).map((day) => (
                  <article key={day.day} className="rounded-lg border border-slate-200 p-4">
                    <div className="mb-3 flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                      <div>
                        <h3 className="text-lg font-semibold text-ink">Day {day.day}</h3>
                        {day.date && <p className="text-sm text-slate-500">{day.date}</p>}
                      </div>
                      <div className="flex flex-wrap items-center gap-2 md:justify-end">
                        <span className="rounded-full bg-trail px-3 py-1 text-sm text-white">{day.theme}</span>
                        {selectedTripPlanId && (
                          <Button
                            size="small"
                            icon={<SyncOutlined />}
                            loading={regenerateTripDayMutation.isPending && regeneratingTripDay === day.day}
                            onClick={() => openTripDayRegenerator(day.day)}
                          >
                            Regenerate
                          </Button>
                        )}
                      </div>
                    </div>
                    {day.description && <p className="mb-3 text-sm leading-6 text-slate-600">{day.description}</p>}
                    <div className="mb-3 grid gap-3 md:grid-cols-3">
                      {day.transportation && <PlanMeta label="Transit" value={day.transportation} />}
                      {day.accommodation && <PlanMeta label="Stay type" value={day.accommodation} />}
                      {day.hotel && (
                        <PlanMeta
                          label="Hotel"
                          value={`${day.hotel.name}${day.hotel.estimatedCost ? ` / ${formatCost(day.hotel.estimatedCost)}` : ''}`}
                        />
                      )}
                    </div>
                    {(day.attractions?.length ?? 0) > 0 && (
                      <div className="mb-3">
                        <h4 className="mb-2 text-sm font-semibold text-ink">Attractions</h4>
                        <div className="grid gap-3 md:grid-cols-2">
                          {day.attractions?.map((attraction) => (
                            <div key={`${day.day}-${attraction.name}`} className="rounded-md bg-slate-50 p-3">
                              <div className="flex items-start justify-between gap-3">
                                <div>
                                  <p className="font-medium text-ink">{attraction.name}</p>
                                  {attraction.address && (
                                    <p className="mt-1 text-xs text-slate-500">{attraction.address}</p>
                                  )}
                                </div>
                                {attraction.rating !== null && attraction.rating !== undefined && (
                                  <span className="rounded-full bg-white px-2 py-1 text-xs text-trail">
                                    {attraction.rating.toFixed(1)}
                                  </span>
                                )}
                              </div>
                              {attraction.description && (
                                <p className="mt-2 text-sm leading-6 text-slate-600">{attraction.description}</p>
                              )}
                              <p className="mt-2 text-xs text-slate-500">
                                {attraction.category || 'attraction'} / {attraction.visitDuration} min
                                {attraction.ticketPrice ? ` / ${formatCost(attraction.ticketPrice)}` : ''}
                              </p>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                    {(day.meals?.length ?? 0) > 0 && (
                      <div className="mb-3">
                        <h4 className="mb-2 text-sm font-semibold text-ink">Meals</h4>
                        <div className="grid gap-2 md:grid-cols-3">
                          {day.meals?.map((meal) => (
                            <div key={`${day.day}-${meal.type}-${meal.name}`} className="rounded-md bg-mist p-3">
                              <p className="text-xs font-medium uppercase text-trail">{meal.type}</p>
                              <p className="mt-1 text-sm font-medium text-ink">{meal.name}</p>
                              {meal.description && (
                                <p className="mt-1 text-xs leading-5 text-slate-600">{meal.description}</p>
                              )}
                              {meal.estimatedCost > 0 && (
                                <p className="mt-2 text-xs text-slate-500">{formatCost(meal.estimatedCost)}</p>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
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
        title="Edit itinerary"
        open={Boolean(editingTripPlan)}
        width={900}
        okText="Save changes"
        onOk={submitTripPlanEdit}
        confirmLoading={updateTripPlanMutation.isPending}
        okButtonProps={{
          disabled: !editingTripPlan || !isTripPlanDraftValid(editingTripPlan, editingTripPlanTips),
        }}
        onCancel={() => {
          setEditingTripPlan(null);
          setEditingTripPlanTips('');
          setTripPlanEditError('');
          updateTripPlanMutation.reset();
        }}
      >
        {editingTripPlan && (
          <div className="max-h-[65vh] space-y-5 overflow-y-auto pr-2">
            <label className="block">
              <span className="mb-1 block text-sm font-medium text-ink">Title</span>
              <Input
                maxLength={160}
                value={editingTripPlan.title}
                onChange={(event) => setEditingTripPlan({ ...editingTripPlan, title: event.target.value })}
              />
            </label>
            <label className="block">
              <span className="mb-1 block text-sm font-medium text-ink">Summary</span>
              <Input.TextArea
                rows={3}
                maxLength={4000}
                value={editingTripPlan.summary}
                onChange={(event) => setEditingTripPlan({ ...editingTripPlan, summary: event.target.value })}
              />
            </label>
            {editingTripPlan.days.map((day, index) => (
              <section key={day.day} className="border-t border-slate-200 pt-4">
                <h3 className="mb-3 font-semibold text-ink">Day {day.day}</h3>
                <div className="grid gap-3 md:grid-cols-2">
                  <label className="block md:col-span-2">
                    <span className="mb-1 block text-sm font-medium text-ink">Theme</span>
                    <Input
                      maxLength={1000}
                      value={day.theme}
                      onChange={(event) => updateEditingTripDay(index, 'theme', event.target.value)}
                    />
                  </label>
                  {(['morning', 'afternoon', 'evening'] as const).map((period) => (
                    <label key={period} className={period === 'evening' ? 'block md:col-span-2' : 'block'}>
                      <span className="mb-1 block text-sm font-medium capitalize text-ink">{period}</span>
                      <Input.TextArea
                        rows={3}
                        maxLength={1000}
                        value={day[period]}
                        onChange={(event) => updateEditingTripDay(index, period, event.target.value)}
                      />
                    </label>
                  ))}
                </div>
                <div className="mt-4 rounded-lg border border-slate-200 bg-slate-50 p-3">
                  <div className="mb-3 flex items-center justify-between gap-3">
                    <div>
                      <h4 className="text-sm font-semibold text-ink">Hotel</h4>
                      <p className="mt-1 text-xs text-slate-500">Edit the overnight stay for this day.</p>
                    </div>
                    {day.hotel ? (
                      <Popconfirm title="Clear hotel for this day?" onConfirm={() => clearEditingHotel(index)}>
                        <Button size="small" danger icon={<DeleteOutlined />}>
                          Clear
                        </Button>
                      </Popconfirm>
                    ) : (
                      <Button size="small" icon={<PlusOutlined />} onClick={() => addEditingHotel(index)}>
                        Add
                      </Button>
                    )}
                  </div>
                  {day.hotel ? (
                    <div className="grid gap-3 rounded-md bg-white p-3 md:grid-cols-2">
                      <label className="block">
                        <span className="mb-1 block text-xs font-medium text-slate-600">Name</span>
                        <Input
                          maxLength={160}
                          value={day.hotel.name}
                          onChange={(event) => updateEditingHotelText(index, 'name', event.target.value)}
                        />
                      </label>
                      <label className="block">
                        <span className="mb-1 block text-xs font-medium text-slate-600">Type</span>
                        <Input
                          maxLength={80}
                          value={day.hotel.type}
                          onChange={(event) => updateEditingHotelText(index, 'type', event.target.value)}
                        />
                      </label>
                      <label className="block md:col-span-2">
                        <span className="mb-1 block text-xs font-medium text-slate-600">Address</span>
                        <Input
                          maxLength={240}
                          value={day.hotel.address}
                          onChange={(event) => updateEditingHotelText(index, 'address', event.target.value)}
                        />
                      </label>
                      <label className="block">
                        <span className="mb-1 block text-xs font-medium text-slate-600">Price range</span>
                        <Input
                          maxLength={80}
                          value={day.hotel.priceRange}
                          onChange={(event) => updateEditingHotelText(index, 'priceRange', event.target.value)}
                        />
                      </label>
                      <label className="block">
                        <span className="mb-1 block text-xs font-medium text-slate-600">Rating</span>
                        <Input
                          maxLength={40}
                          value={day.hotel.rating}
                          onChange={(event) => updateEditingHotelText(index, 'rating', event.target.value)}
                        />
                      </label>
                      <label className="block">
                        <span className="mb-1 block text-xs font-medium text-slate-600">Distance</span>
                        <Input
                          maxLength={120}
                          value={day.hotel.distance}
                          onChange={(event) => updateEditingHotelText(index, 'distance', event.target.value)}
                        />
                      </label>
                      <label className="block">
                        <span className="mb-1 block text-xs font-medium text-slate-600">Estimated cost</span>
                        <InputNumber
                          min={0}
                          max={100000}
                          value={day.hotel.estimatedCost}
                          onChange={(value) => updateEditingHotelCost(index, value)}
                          addonAfter="CNY"
                          className="w-full"
                        />
                      </label>
                    </div>
                  ) : (
                    <div className="rounded-md border border-dashed border-slate-300 bg-white p-3 text-sm text-slate-500">
                      No hotel selected for this day.
                    </div>
                  )}
                </div>
                <div className="mt-4 rounded-lg border border-slate-200 bg-slate-50 p-3">
                  <div className="mb-3 flex items-center justify-between gap-3">
                    <div>
                      <h4 className="text-sm font-semibold text-ink">Attractions</h4>
                      <p className="mt-1 text-xs text-slate-500">Edit route stops, order, visit time, and notes.</p>
                    </div>
                    <Button
                      size="small"
                      icon={<PlusOutlined />}
                      disabled={(day.attractions?.length ?? 0) >= 8}
                      onClick={() => addEditingAttraction(index)}
                    >
                      Add
                    </Button>
                  </div>
                  {(day.attractions ?? []).length === 0 ? (
                    <div className="rounded-md border border-dashed border-slate-300 bg-white p-3 text-sm text-slate-500">
                      No attractions yet.
                    </div>
                  ) : (
                    <div className="space-y-3">
                      {(day.attractions ?? []).map((attraction, attractionIndex) => (
                        <section key={`${day.day}-${attractionIndex}`} className="rounded-md bg-white p-3">
                          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                            <p className="text-sm font-semibold text-ink">Stop {attractionIndex + 1}</p>
                            <div className="flex gap-2">
                              <Button
                                size="small"
                                icon={<ArrowUpOutlined />}
                                disabled={attractionIndex === 0}
                                onClick={() => moveEditingAttraction(index, attractionIndex, -1)}
                                aria-label="Move attraction up"
                              />
                              <Button
                                size="small"
                                icon={<ArrowDownOutlined />}
                                disabled={attractionIndex === (day.attractions?.length ?? 0) - 1}
                                onClick={() => moveEditingAttraction(index, attractionIndex, 1)}
                                aria-label="Move attraction down"
                              />
                              <Popconfirm
                                title="Delete this attraction?"
                                onConfirm={() => deleteEditingAttraction(index, attractionIndex)}
                              >
                                <Button size="small" danger icon={<DeleteOutlined />} aria-label="Delete attraction" />
                              </Popconfirm>
                            </div>
                          </div>
                          <div className="grid gap-3 md:grid-cols-2">
                            <label className="block">
                              <span className="mb-1 block text-xs font-medium text-slate-600">Name</span>
                              <Input
                                maxLength={160}
                                value={attraction.name}
                                onChange={(event) =>
                                  updateEditingAttractionText(index, attractionIndex, 'name', event.target.value)
                                }
                              />
                            </label>
                            <label className="block">
                              <span className="mb-1 block text-xs font-medium text-slate-600">Category</span>
                              <Input
                                maxLength={80}
                                value={attraction.category}
                                onChange={(event) =>
                                  updateEditingAttractionText(index, attractionIndex, 'category', event.target.value)
                                }
                              />
                            </label>
                            <label className="block md:col-span-2">
                              <span className="mb-1 block text-xs font-medium text-slate-600">Address</span>
                              <Input
                                maxLength={240}
                                value={attraction.address}
                                onChange={(event) =>
                                  updateEditingAttractionText(index, attractionIndex, 'address', event.target.value)
                                }
                              />
                            </label>
                            <label className="block">
                              <span className="mb-1 block text-xs font-medium text-slate-600">
                                Visit duration
                              </span>
                              <InputNumber
                                min={10}
                                max={480}
                                value={attraction.visitDuration}
                                onChange={(value) =>
                                  updateEditingAttractionNumber(index, attractionIndex, 'visitDuration', value)
                                }
                                addonAfter="min"
                                className="w-full"
                              />
                            </label>
                            <label className="block">
                              <span className="mb-1 block text-xs font-medium text-slate-600">Ticket price</span>
                              <InputNumber
                                min={0}
                                max={100000}
                                value={attraction.ticketPrice}
                                onChange={(value) =>
                                  updateEditingAttractionNumber(index, attractionIndex, 'ticketPrice', value)
                                }
                                addonAfter="CNY"
                                className="w-full"
                              />
                            </label>
                            <label className="block md:col-span-2">
                              <span className="mb-1 block text-xs font-medium text-slate-600">Description</span>
                              <Input.TextArea
                                rows={2}
                                maxLength={1000}
                                value={attraction.description}
                                onChange={(event) =>
                                  updateEditingAttractionText(index, attractionIndex, 'description', event.target.value)
                                }
                              />
                            </label>
                          </div>
                        </section>
                      ))}
                    </div>
                  )}
                </div>
                <div className="mt-4 rounded-lg border border-slate-200 bg-slate-50 p-3">
                  <div className="mb-3 flex items-center justify-between gap-3">
                    <div>
                      <h4 className="text-sm font-semibold text-ink">Meals</h4>
                      <p className="mt-1 text-xs text-slate-500">Edit meal stops and estimated costs.</p>
                    </div>
                    <Button
                      size="small"
                      icon={<PlusOutlined />}
                      disabled={(day.meals?.length ?? 0) >= 8}
                      onClick={() => addEditingMeal(index)}
                    >
                      Add
                    </Button>
                  </div>
                  {(day.meals ?? []).length === 0 ? (
                    <div className="rounded-md border border-dashed border-slate-300 bg-white p-3 text-sm text-slate-500">
                      No meals yet.
                    </div>
                  ) : (
                    <div className="space-y-3">
                      {(day.meals ?? []).map((meal, mealIndex) => (
                        <section key={`${day.day}-meal-${mealIndex}`} className="rounded-md bg-white p-3">
                          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                            <p className="text-sm font-semibold text-ink">Meal {mealIndex + 1}</p>
                            <Popconfirm
                              title="Delete this meal?"
                              onConfirm={() => deleteEditingMeal(index, mealIndex)}
                            >
                              <Button size="small" danger icon={<DeleteOutlined />} aria-label="Delete meal" />
                            </Popconfirm>
                          </div>
                          <div className="grid gap-3 md:grid-cols-2">
                            <label className="block">
                              <span className="mb-1 block text-xs font-medium text-slate-600">Type</span>
                              <Input
                                maxLength={40}
                                value={meal.type}
                                onChange={(event) => updateEditingMealText(index, mealIndex, 'type', event.target.value)}
                              />
                            </label>
                            <label className="block">
                              <span className="mb-1 block text-xs font-medium text-slate-600">Name</span>
                              <Input
                                maxLength={160}
                                value={meal.name}
                                onChange={(event) => updateEditingMealText(index, mealIndex, 'name', event.target.value)}
                              />
                            </label>
                            <label className="block md:col-span-2">
                              <span className="mb-1 block text-xs font-medium text-slate-600">Address</span>
                              <Input
                                maxLength={240}
                                value={meal.address}
                                onChange={(event) =>
                                  updateEditingMealText(index, mealIndex, 'address', event.target.value)
                                }
                              />
                            </label>
                            <label className="block">
                              <span className="mb-1 block text-xs font-medium text-slate-600">Estimated cost</span>
                              <InputNumber
                                min={0}
                                max={100000}
                                value={meal.estimatedCost}
                                onChange={(value) => updateEditingMealCost(index, mealIndex, value)}
                                addonAfter="CNY"
                                className="w-full"
                              />
                            </label>
                            <label className="block md:col-span-2">
                              <span className="mb-1 block text-xs font-medium text-slate-600">Description</span>
                              <Input.TextArea
                                rows={2}
                                maxLength={1000}
                                value={meal.description}
                                onChange={(event) =>
                                  updateEditingMealText(index, mealIndex, 'description', event.target.value)
                                }
                              />
                            </label>
                          </div>
                        </section>
                      ))}
                    </div>
                  )}
                </div>
              </section>
            ))}
            <label className="block border-t border-slate-200 pt-4">
              <span className="mb-1 block text-sm font-medium text-ink">Travel notes</span>
              <Input.TextArea
                rows={5}
                maxLength={10019}
                value={editingTripPlanTips}
                onChange={(event) => setEditingTripPlanTips(event.target.value)}
                placeholder="One note per line"
              />
            </label>
            {tripPlanEditError && (
              <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
                {tripPlanEditError}
              </div>
            )}
          </div>
        )}
      </Modal>
      <Modal
        title={regeneratingTripDay === null ? 'Regenerate day' : `Regenerate day ${regeneratingTripDay}`}
        open={regeneratingTripDay !== null}
        okText="Regenerate"
        onOk={submitTripDayRegeneration}
        confirmLoading={regenerateTripDayMutation.isPending}
        okButtonProps={{ disabled: !tripDayRegenerateInstruction.trim() }}
        onCancel={() => {
          setRegeneratingTripDay(null);
          setTripDayRegenerateInstruction('');
          setTripDayRegenerateError('');
          regenerateTripDayMutation.reset();
        }}
      >
        <div className="space-y-3">
          <Input.TextArea
            rows={4}
            maxLength={1000}
            value={tripDayRegenerateInstruction}
            onChange={(event) => setTripDayRegenerateInstruction(event.target.value)}
            placeholder="Make this day slower, avoid spicy food, add photography spots..."
          />
          {tripDayRegenerateError && (
            <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
              {tripDayRegenerateError}
            </div>
          )}
        </div>
      </Modal>
      <Modal
        title="Import local data?"
        open={anonymousImportPromptOpen}
        okText="Import local data"
        cancelText="Skip"
        onOk={() => importAnonymousUserDataMutation.mutate()}
        confirmLoading={importAnonymousUserDataMutation.isPending}
        onCancel={() => {
          if (anonymousImportPromptStorageKey) {
            window.localStorage.setItem(anonymousImportPromptStorageKey, 'handled');
          }
          setAnonymousImportPromptOpen(false);
          setAnonymousImportPromptDismissed(true);
        }}
      >
        <div className="space-y-3">
          <p className="text-sm leading-6 text-slate-600">
            This browser has anonymous travel planning data. You can copy it into your signed-in account.
          </p>
          <div className="grid grid-cols-2 gap-2 text-sm">
            <div className="rounded-md bg-slate-50 px-3 py-2">
              <p className="text-xs font-medium text-slate-500">Conversations</p>
              <p className="mt-1 text-lg font-semibold text-ink">
                {anonymousDataSummaryQuery.data?.conversations ?? 0}
              </p>
            </div>
            <div className="rounded-md bg-slate-50 px-3 py-2">
              <p className="text-xs font-medium text-slate-500">Trip plans</p>
              <p className="mt-1 text-lg font-semibold text-ink">
                {anonymousDataSummaryQuery.data?.tripPlans ?? 0}
              </p>
            </div>
          </div>
          <p className="text-xs leading-5 text-slate-500">
            Importing copies the local data into your account. The anonymous local copy is left untouched.
          </p>
        </div>
      </Modal>
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
          {authActionMessage && (
            <div className="break-words rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-600">
              {authActionMessage}
            </div>
          )}
          {authMode === 'LOGIN' && (
            <Button
              type="link"
              className="px-0"
              onClick={() => {
                setPasswordResetIntent('RESET');
                setPasswordResetEmail(authEmail.trim());
                setPasswordResetRequested(false);
                requestPasswordResetMutation.reset();
                setPasswordResetRequestModalOpen(true);
              }}
            >
              Forgot password?
            </Button>
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
        title={passwordResetIntent === 'SET' ? 'Set project password' : 'Reset password'}
        open={passwordResetRequestModalOpen}
        okText={passwordResetIntent === 'SET' ? 'Send setup link' : 'Send reset link'}
        onOk={submitPasswordResetRequest}
        confirmLoading={requestPasswordResetMutation.isPending}
        okButtonProps={{ disabled: !passwordResetEmail.trim() }}
        onCancel={() => {
          setPasswordResetRequestModalOpen(false);
          resetPasswordResetForm();
        }}
      >
        <div className="space-y-3">
          <p className="text-sm leading-6 text-slate-600">
            {passwordResetIntent === 'SET'
              ? 'A setup link will be sent to this account email. Use it to add a project password to this GitHub account.'
              : 'Enter your account email. If it exists, a password reset link will be sent.'}
          </p>
          <label className="block">
            <span className="mb-1 block text-sm font-medium text-ink">Email</span>
            <Input
              value={passwordResetEmail}
              onChange={(event) => {
                setPasswordResetEmail(event.target.value);
                setPasswordResetRequested(false);
                requestPasswordResetMutation.reset();
              }}
              onPressEnter={submitPasswordResetRequest}
              placeholder="you@example.com"
            />
          </label>
          {passwordResetRequested && (
            <div className="rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-700">
              {passwordResetIntent === 'SET'
                ? 'If the email exists, a setup link has been sent.'
                : 'If the email exists, a reset link has been sent.'}
            </div>
          )}
          {requestPasswordResetMutation.isError && (
            <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
              Could not request password reset. Please try again later.
            </div>
          )}
        </div>
      </Modal>
      <Modal
        title={passwordResetIntent === 'SET' ? 'Set project password' : 'Set new password'}
        open={passwordResetConfirmModalOpen}
        okText={passwordResetIntent === 'SET' ? 'Set password' : 'Update password'}
        onOk={submitPasswordResetConfirm}
        confirmLoading={confirmPasswordResetMutation.isPending}
        okButtonProps={{
          disabled:
            !passwordResetToken ||
            passwordResetNewPassword.length < 8 ||
            passwordResetNewPassword !== passwordResetConfirmPassword,
        }}
        onCancel={() => {
          setPasswordResetConfirmModalOpen(false);
          resetPasswordResetForm();
        }}
      >
        <div className="space-y-3">
          <p className="text-sm leading-6 text-slate-600">
            {passwordResetIntent === 'SET'
              ? 'This link has been verified. Set a project password for password-protected account actions.'
              : 'This reset link has been verified. Set a new password for your account.'}
          </p>
          <label className="block">
            <span className="mb-1 block text-sm font-medium text-ink">New password</span>
            <Input.Password
              value={passwordResetNewPassword}
              onChange={(event) => {
                setPasswordResetNewPassword(event.target.value);
                confirmPasswordResetMutation.reset();
              }}
              placeholder="At least 8 characters"
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-sm font-medium text-ink">Confirm new password</span>
            <Input.Password
              value={passwordResetConfirmPassword}
              onChange={(event) => {
                setPasswordResetConfirmPassword(event.target.value);
                confirmPasswordResetMutation.reset();
              }}
              onPressEnter={submitPasswordResetConfirm}
              placeholder="Repeat new password"
            />
          </label>
          {passwordResetNewPassword &&
            passwordResetConfirmPassword &&
            passwordResetNewPassword !== passwordResetConfirmPassword && (
              <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-700">
                New passwords do not match.
              </div>
            )}
          {confirmPasswordResetMutation.isError && (
            <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
              Password reset link is invalid or expired.
            </div>
          )}
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
        title="Delete account"
        open={deleteAccountModalOpen}
        okText="Delete account"
        okButtonProps={{
          danger: true,
          disabled: !deleteAccountPassword || deleteAccountConfirmation.trim().toUpperCase() !== 'DELETE',
        }}
        confirmLoading={deleteAccountMutation.isPending}
        onOk={submitDeleteAccount}
        onCancel={() => {
          setDeleteAccountModalOpen(false);
          resetDeleteAccountForm();
        }}
      >
        <div className="space-y-3">
          <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
            This permanently deletes your account, traveler profile, conversations, summaries, and saved trip plans.
          </div>
          <label className="block">
            <span className="mb-1 block text-sm font-medium text-ink">Current password</span>
            <Input.Password
              value={deleteAccountPassword}
              onChange={(event) => {
                setDeleteAccountPassword(event.target.value);
                deleteAccountMutation.reset();
              }}
              placeholder="Current password"
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-sm font-medium text-ink">Type DELETE to confirm</span>
            <Input
              value={deleteAccountConfirmation}
              onChange={(event) => {
                setDeleteAccountConfirmation(event.target.value);
                deleteAccountMutation.reset();
              }}
              onPressEnter={submitDeleteAccount}
              placeholder="DELETE"
            />
          </label>
          {deleteAccountMutation.isError && (
            <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
              Could not delete account. Check the current password and confirmation.
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

function PlanMeta({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md bg-slate-50 p-3">
      <p className="text-xs font-medium uppercase text-slate-400">{label}</p>
      <p className="mt-1 text-sm font-medium text-ink">{value || 'Not specified'}</p>
    </div>
  );
}

function PlanCost({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span>{label}</span>
      <span className="font-medium text-ink">{formatCost(value)}</span>
    </div>
  );
}

function createDraftHotel(day: number): Hotel {
  return {
    name: `Day ${day} hotel`,
    address: '',
    location: null,
    priceRange: '',
    rating: '',
    distance: '',
    type: 'comfortable hotel',
    estimatedCost: 0,
  };
}

function createDraftAttraction(day: number, index: number): Attraction {
  return {
    name: `New attraction ${day}-${index}`,
    address: '',
    location: null,
    visitDuration: 90,
    description: '',
    category: 'attraction',
    rating: null,
    imageUrl: null,
    ticketPrice: 0,
  };
}

function createDraftMeal(day: number, index: number): Meal {
  return {
    type: index === 1 ? 'breakfast' : index === 2 ? 'lunch' : index === 3 ? 'dinner' : 'meal',
    name: `Day ${day} meal ${index}`,
    address: '',
    location: null,
    description: '',
    estimatedCost: 0,
  };
}

function normalizeHotel(hotel: Hotel | null): Hotel | null {
  if (!hotel || !hotel.name.trim()) {
    return null;
  }
  return {
    ...hotel,
    name: hotel.name.trim(),
    address: hotel.address.trim(),
    priceRange: hotel.priceRange.trim(),
    rating: hotel.rating.trim(),
    distance: hotel.distance.trim(),
    type: hotel.type.trim(),
    estimatedCost: clampInteger(hotel.estimatedCost, 0, 100000),
  };
}

function normalizeAttractions(attractions: Attraction[]): Attraction[] {
  return attractions
    .map((attraction) => ({
      ...attraction,
      name: attraction.name.trim(),
      address: attraction.address.trim(),
      description: attraction.description.trim(),
      category: attraction.category.trim(),
      visitDuration: clampInteger(attraction.visitDuration, 10, 480),
      ticketPrice: clampInteger(attraction.ticketPrice, 0, 100000),
    }))
    .filter((attraction) => attraction.name.length > 0)
    .slice(0, 8);
}

function normalizeMeals(meals: Meal[]): Meal[] {
  return meals
    .map((meal) => ({
      ...meal,
      type: meal.type.trim() || 'meal',
      name: meal.name.trim(),
      address: meal.address.trim(),
      description: meal.description.trim(),
      estimatedCost: clampInteger(meal.estimatedCost, 0, 100000),
    }))
    .filter((meal) => meal.name.length > 0)
    .slice(0, 8);
}

function clampInteger(value: number, min: number, max: number): number {
  if (!Number.isFinite(value)) {
    return min;
  }
  return Math.min(max, Math.max(min, Math.round(value)));
}

function isTripPlanDraftValid(plan: TripPlanResponse, rawTips: string): boolean {
  const tips = rawTips
    .split('\n')
    .map((tip) => tip.trim())
    .filter(Boolean);
  return (
    Boolean(plan.title.trim()) &&
    Boolean(plan.summary.trim()) &&
    plan.days.length > 0 &&
    plan.days.every((day) =>
      [day.theme, day.morning, day.afternoon, day.evening].every((value) => Boolean(value.trim())),
    ) &&
    tips.length <= 20 &&
    tips.every((tip) => tip.length <= 500)
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
        <StatusRow label="Redis rate limit" active={Boolean(health?.redisRateLimitEnabled)} muted={!runtimeOnline || loading} />
        <StatusRow label="Object storage" active={Boolean(health?.objectStorageEnabled)} muted={!runtimeOnline || loading} />
        <StatusRow
          label={`Travel tools: ${health?.travelToolsProvider ?? 'mock'}`}
          active={runtimeOnline}
          muted={!runtimeOnline || loading}
        />
      </div>
    </section>
  );
}

function AccountStatus({
  user,
  authIdentities,
  authSessions,
  securityEvents,
  loading,
  onLogin,
  onRegister,
  githubOAuthEnabled,
  onStartGithubOAuth,
  onUnlinkGithub,
  onRevokeSession,
  onRevokeOtherSessions,
  authActionMessage,
  onRequestEmailVerification,
  onEditAccount,
  onChangePassword,
  onSetPassword,
  onExportData,
  objectStorageEnabled,
  archivedExportFile,
  archiveExportError,
  onArchiveData,
  onDownloadArchivedExport,
  onImportData,
  onImportAnonymousData,
  exportDataError,
  importDataError,
  anonymousImportMessage,
  onDeleteAccount,
  onLogout,
}: {
  user?: AuthUser | null;
  authIdentities: AuthIdentity[];
  authSessions: AuthSessionInfo[];
  securityEvents: UserSecurityEvent[];
  loading: boolean;
  onLogin: () => void;
  onRegister: () => void;
  githubOAuthEnabled: boolean;
  onStartGithubOAuth: () => void;
  onUnlinkGithub: () => void;
  onRevokeSession: (sessionId: string) => void;
  onRevokeOtherSessions: () => void;
  authActionMessage: string;
  onRequestEmailVerification: () => void;
  onEditAccount: () => void;
  onChangePassword: () => void;
  onSetPassword: () => void;
  onExportData: () => void;
  objectStorageEnabled: boolean;
  archivedExportFile: UserExportFile | null;
  archiveExportError: string;
  onArchiveData: () => void;
  onDownloadArchivedExport: () => void;
  onImportData: () => void;
  onImportAnonymousData: () => void;
  exportDataError: string;
  importDataError: string;
  anonymousImportMessage: string;
  onDeleteAccount: () => void;
  onLogout: () => void;
}) {
  const accountDataManagementDisabled = Boolean(user && !user.emailVerified);
  const githubIdentity = authIdentities.find((identity) => identity.provider === 'github');
  const passwordConfigured = user?.passwordConfigured ?? true;
  const activeSessions = authSessions.filter((session) => !session.revoked);
  const otherSessions = activeSessions.filter((session) => !session.current);

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
          <div
            className={`rounded-md px-2 py-2 text-xs ${
              user.emailVerified ? 'bg-emerald-50 text-emerald-700' : 'bg-amber-50 text-amber-700'
            }`}
          >
            {user.emailVerified ? 'Email verified' : 'Email not verified'}
          </div>
          {!user.emailVerified && (
            <Button size="small" onClick={onRequestEmailVerification}>
              Resend verification
            </Button>
          )}
          {authActionMessage && (
            <div className="break-words rounded-md border border-slate-200 bg-slate-50 px-2 py-2 text-xs text-slate-600">
              {authActionMessage}
            </div>
          )}
          <Button size="small" onClick={onEditAccount}>
            Edit account
          </Button>
          <Button size="small" onClick={passwordConfigured ? onChangePassword : onSetPassword}>
            {passwordConfigured ? 'Change password' : 'Set password'}
          </Button>
          {!passwordConfigured && (
            <div className="rounded-md border border-amber-200 bg-amber-50 px-2 py-2 text-xs text-amber-700">
              This GitHub account has no project password yet. Set one before deleting the account or unlinking GitHub.
            </div>
          )}
          <div className="rounded-md border border-slate-200 bg-slate-50 px-2 py-2">
            <div className="flex items-center justify-between gap-2">
              <div className="min-w-0">
                <p className="text-xs font-medium text-slate-600">GitHub</p>
                <p className="truncate text-xs text-slate-400">
                  {githubIdentity
                    ? githubIdentity.displayName || githubIdentity.email || 'Linked'
                    : githubOAuthEnabled
                      ? 'Not linked'
                      : 'Not configured'}
                </p>
              </div>
              {githubIdentity ? (
                <Button size="small" onClick={onUnlinkGithub} disabled={!passwordConfigured}>
                  Unlink
                </Button>
              ) : (
                <Button size="small" onClick={onStartGithubOAuth} disabled={!githubOAuthEnabled}>
                  Link
                </Button>
              )}
            </div>
          </div>
          {accountDataManagementDisabled && (
            <div className="rounded-md border border-amber-200 bg-amber-50 px-2 py-2 text-xs text-amber-700">
              Verify your email before exporting or importing account data.
            </div>
          )}
          {activeSessions.length > 0 && (
            <div className="rounded-md border border-slate-200 bg-slate-50 px-2 py-2">
              <div className="mb-2 flex items-center justify-between gap-2">
                <p className="text-xs font-medium text-slate-600">Active sessions</p>
                <Popconfirm
                  title="Sign out other devices?"
                  description="Other active sessions will need to sign in again."
                  okText="Sign out"
                  cancelText="Cancel"
                  onConfirm={onRevokeOtherSessions}
                  disabled={otherSessions.length === 0}
                >
                  <Button size="small" disabled={otherSessions.length === 0}>
                    Sign out others
                  </Button>
                </Popconfirm>
              </div>
              <div className="space-y-2">
                {activeSessions.slice(0, 3).map((session) => (
                  <div key={session.id} className="rounded-md bg-white px-2 py-2 text-xs">
                    <div className="flex items-center justify-between gap-2">
                      <div className="min-w-0">
                        <p className="truncate font-medium text-slate-700">
                          {session.current ? 'Current device' : session.userAgent || 'Unknown device'}
                        </p>
                        <p className="mt-1 text-slate-400">Last seen {formatDateTime(session.lastSeenAt)}</p>
                      </div>
                      {session.current ? (
                        <span className="shrink-0 rounded bg-emerald-50 px-2 py-1 text-emerald-700">Current</span>
                      ) : (
                        <Popconfirm
                          title="Revoke this session?"
                          description="This device will need to sign in again."
                          okText="Revoke"
                          cancelText="Cancel"
                          onConfirm={() => onRevokeSession(session.id)}
                        >
                          <Button size="small">Revoke</Button>
                        </Popconfirm>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
          <Button size="small" onClick={onExportData} disabled={accountDataManagementDisabled}>
            Export data
          </Button>
          <Button
            size="small"
            icon={<UploadOutlined />}
            onClick={onArchiveData}
            disabled={accountDataManagementDisabled || !objectStorageEnabled}
          >
            Archive export
          </Button>
          {archivedExportFile && (
            <div className="rounded-md border border-emerald-200 bg-emerald-50 px-2 py-2 text-xs text-emerald-700">
              <p className="truncate">Archived {archivedExportFile.filename}</p>
              <Button size="small" className="mt-2" icon={<DownloadOutlined />} onClick={onDownloadArchivedExport}>
                Download archived export
              </Button>
            </div>
          )}
          {archiveExportError && (
            <div className="rounded-md border border-red-200 bg-red-50 px-2 py-2 text-xs text-red-700">
              {archiveExportError}
            </div>
          )}
          <Button size="small" icon={<UploadOutlined />} onClick={onImportData} disabled={accountDataManagementDisabled}>
            Import data
          </Button>
          <Button size="small" onClick={onImportAnonymousData} disabled={accountDataManagementDisabled}>
            Import local data
          </Button>
          {exportDataError && (
            <div className="rounded-md border border-red-200 bg-red-50 px-2 py-2 text-xs text-red-700">
              {exportDataError}
            </div>
          )}
          {importDataError && (
            <div className="rounded-md border border-red-200 bg-red-50 px-2 py-2 text-xs text-red-700">
              {importDataError}
            </div>
          )}
          {anonymousImportMessage && (
            <div className="rounded-md border border-slate-200 bg-slate-50 px-2 py-2 text-xs text-slate-600">
              {anonymousImportMessage}
            </div>
          )}
          {securityEvents.length > 0 && (
            <div className="rounded-md bg-slate-50 px-2 py-2">
              <p className="mb-2 text-xs font-medium text-slate-500">Recent security activity</p>
              <div className="space-y-1">
                {securityEvents.map((event) => (
                  <div key={event.id} className="flex items-center justify-between gap-2 text-xs">
                    <span className="min-w-0 truncate text-slate-700">{formatSecurityEventType(event.eventType)}</span>
                    <span className="shrink-0 text-slate-400">{formatDateTime(event.createdAt)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
          <Button size="small" danger icon={<DeleteOutlined />} onClick={onDeleteAccount} disabled={!passwordConfigured}>
            Delete account
          </Button>
          <Button size="small" className="w-full" loading={loading} onClick={onLogout}>
            Sign out
          </Button>
        </div>
      ) : (
        <div className="grid gap-2">
          <div className="grid grid-cols-2 gap-2">
            <Button size="small" type="primary" onClick={onLogin}>
              Sign in
            </Button>
            <Button size="small" onClick={onRegister}>
              Register
            </Button>
          </div>
          <Button size="small" onClick={onStartGithubOAuth} disabled={!githubOAuthEnabled}>
            Continue with GitHub
          </Button>
          {authActionMessage && (
            <div className="break-words rounded-md border border-slate-200 bg-slate-50 px-2 py-2 text-xs text-slate-600">
              {authActionMessage}
            </div>
          )}
          {!githubOAuthEnabled && <p className="text-xs text-slate-400">GitHub OAuth is not configured.</p>}
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

function formatSecurityEventType(value: string): string {
  const labels: Record<string, string> = {
    'auth.registered': 'Account created',
    'auth.logged_in': 'Signed in',
    'auth.logged_out': 'Signed out',
    'auth.session_created': 'Session created',
    'auth.session_revoked': 'Session revoked',
    'auth.sessions_revoked_all': 'Other sessions revoked',
    'auth.password_changed': 'Password changed',
    'auth.email_verification_requested': 'Verification email sent',
    'auth.email_verified': 'Email verified',
    'auth.password_reset_requested': 'Password reset requested',
    'auth.password_reset_completed': 'Password reset completed',
    'auth.oauth_logged_in': 'GitHub sign-in',
    'auth.identity_linked': 'Identity linked',
    'auth.identity_unlinked': 'Identity unlinked',
    'user.data_exported': 'Data exported',
    'user.export_file_created': 'Export archived',
    'user.data_imported': 'Data imported',
    'user.anonymous_data_imported': 'Local data imported',
  };
  return labels[value] ?? value.replace(/[._-]/g, ' ');
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

function calculateInclusiveDays(startDate: string, endDate: string): number | null {
  if (!startDate || !endDate) {
    return null;
  }
  const start = new Date(`${startDate}T00:00:00`);
  const end = new Date(`${endDate}T00:00:00`);
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime()) || end < start) {
    return null;
  }
  const oneDayMs = 24 * 60 * 60 * 1000;
  return Math.min(30, Math.max(1, Math.round((end.getTime() - start.getTime()) / oneDayMs) + 1));
}

function formatDateRange(startDate?: string | null, endDate?: string | null): string {
  if (startDate && endDate) {
    return `${startDate} to ${endDate}`;
  }
  return startDate || endDate || '';
}

function formatCost(value: number): string {
  if (!Number.isFinite(value) || value <= 0) {
    return '-';
  }
  return `CNY ${value}`;
}

function tripPlanToMarkdown(
  plan: TripPlanResponse,
  request: {
    destination: string;
    days: number;
    budget: string;
    interests: string;
    startDate?: string;
    endDate?: string;
    transportation?: string;
    accommodation?: string;
    freeTextInput?: string;
  },
): string {
  const header = [
    `# ${plan.title}`,
    '',
    `- Destination: ${request.destination}`,
    `- Days: ${request.days}`,
    `- Budget: ${request.budget}`,
  ];

  const startDate = plan.startDate ?? request.startDate;
  const endDate = plan.endDate ?? request.endDate;
  const transportation = plan.transportation ?? request.transportation;
  const accommodation = plan.accommodation ?? request.accommodation;
  const freeTextInput = plan.freeTextInput ?? request.freeTextInput;

  if (startDate) {
    header.push(`- Start date: ${startDate}`);
  }
  if (endDate) {
    header.push(`- End date: ${endDate}`);
  }
  if (transportation) {
    header.push(`- Transportation: ${transportation}`);
  }
  if (accommodation) {
    header.push(`- Accommodation: ${accommodation}`);
  }
  if (request.interests) {
    header.push(`- Interests: ${request.interests}`);
  }
  if (freeTextInput) {
    header.push(`- Constraints: ${freeTextInput}`);
  }

  const body = [
    '',
    plan.summary,
    '',
  ];

  if (plan.budget) {
    body.push(
      '## Budget',
      '',
      `- Attractions: ${plan.budget.totalAttractions}`,
      `- Hotels: ${plan.budget.totalHotels}`,
      `- Meals: ${plan.budget.totalMeals}`,
      `- Transportation: ${plan.budget.totalTransportation}`,
      `- Total: ${plan.budget.total}`,
      '',
    );
  }

  if (plan.weatherInfo?.length) {
    body.push('## Weather', '');
    plan.weatherInfo.forEach((weather) => {
      body.push(
        `- ${weather.date}: ${weather.dayWeather} / ${weather.nightWeather}, ${weather.dayTemp}C / ${weather.nightTemp}C, ${weather.windDirection} wind ${weather.windPower}`,
      );
    });
    body.push('');
  }

  if (plan.overallSuggestions) {
    body.push('## Overall suggestions', '', plan.overallSuggestions, '');
  }

  body.push('## Itinerary', '');
  (plan.days ?? []).forEach((day) => {
    body.push(`### Day ${day.day}: ${day.theme}${day.date ? ` (${day.date})` : ''}`, '');
    if (day.description) {
      body.push(day.description, '');
    }
    if (day.transportation) {
      body.push(`- Transportation: ${day.transportation}`);
    }
    if (day.accommodation) {
      body.push(`- Accommodation: ${day.accommodation}`);
    }
    if (day.hotel) {
      body.push(`- Hotel: ${day.hotel.name}${day.hotel.estimatedCost ? ` (${day.hotel.estimatedCost})` : ''}`);
    }
    if (day.transportation || day.accommodation || day.hotel) {
      body.push('');
    }
    if (day.attractions?.length) {
      body.push('#### Attractions', '');
      day.attractions.forEach((attraction) => {
        body.push(`- ${attraction.name}`);
        if (attraction.address) {
          body.push(`  - Address: ${attraction.address}`);
        }
        if (attraction.description) {
          body.push(`  - Notes: ${attraction.description}`);
        }
      });
      body.push('');
    }
    if (day.meals?.length) {
      body.push('#### Meals', '');
      day.meals.forEach((meal) => {
        body.push(`- ${meal.type}: ${meal.name}${meal.estimatedCost ? ` (${meal.estimatedCost})` : ''}`);
      });
      body.push('');
    }
    body.push(
      '#### Daily rhythm',
      '',
      `- Morning: ${day.morning}`,
      `- Afternoon: ${day.afternoon}`,
      `- Evening: ${day.evening}`,
      '',
    );
  });

  const tips = plan.tips ?? [];
  if (tips.length > 0) {
    body.push('## Travel notes', '', ...tips.map((tip) => `- ${tip}`), '');
  }

  return [...header, ...body].join('\n').trim() + '\n';
}

function downloadTextFile(content: string, filename: string) {
  const blob = new Blob([content], { type: 'text/markdown;charset=utf-8' });
  downloadBlobFile(blob, filename);
}

function downloadBlobFile(blob: Blob, filename: string) {
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
}

function downloadJsonFile(data: unknown, filename: string) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json;charset=utf-8' });
  downloadBlobFile(blob, filename);
}

function slugify(value: string): string {
  const filename = value
    .normalize('NFKC')
    .replace(/[\u0000-\u001f\u007f<>:"/\\|?*]+/g, '-')
    .replace(/\s+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^[.\-\s]+|[.\-\s]+$/g, '')
    .slice(0, 120);
  return filename || 'trip-plan';
}
