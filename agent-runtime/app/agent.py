from app.conversations import ConversationStore
from app.llm import LLMClient
from app.schemas import AgentMode, ChatRequest, ChatResponse, MessageRole
from app.settings import Settings


def handle_chat(user_id: str, request: ChatRequest, store: ConversationStore, settings: Settings) -> ChatResponse:
    conversation = store.get_or_create(
        user_id=user_id,
        conversation_id=request.conversation_id,
        mode=request.mode,
        title=_title_from_message(request.message),
    )
    store.append_message(conversation, MessageRole.USER, request.message)

    llm_client = LLMClient(settings)
    content = llm_client.generate_chat_reply(conversation.messages, request.mode) or _build_rule_based_reply(request)
    assistant_message = store.append_message(conversation, MessageRole.ASSISTANT, content)

    return ChatResponse(
        conversation_id=conversation.id,
        message=assistant_message,
        suggestions=[
            "Generate a structured itinerary",
            "Add weather and transit constraints",
            "Save this plan to my trip list",
        ],
    )


def _build_rule_based_reply(request: ChatRequest) -> str:
    message = request.message.strip()
    if request.mode == AgentMode.TRIP_PLANNING:
        return (
            "I can turn this travel requirement into a structured itinerary. "
            f"Current request: {message}. "
            "Next I will collect destination, days, budget, interests, and constraints before calling trip planning tools."
        )

    return (
        "I received your travel question and created a conversation context. "
        f"You said: {message}. "
        "The current runtime is rule-based; LLM planning and tool calls will be added behind this contract."
    )


def _title_from_message(message: str) -> str:
    normalized = " ".join(message.strip().split())
    if not normalized:
        return "New conversation"
    return normalized[:60]
