from app.conversations import ConversationStore
from app.schemas import ChatRequest, ChatResponse, MessageRole
from app.travel_agent_service import TravelAgentService


def handle_chat(
    user_id: str,
    request: ChatRequest,
    store: ConversationStore,
    agent_service: TravelAgentService,
) -> ChatResponse:
    conversation = store.get_or_create(
        user_id=user_id,
        conversation_id=request.conversation_id,
        mode=request.mode,
        title=_title_from_message(request.message),
    )
    store.append_message(conversation, MessageRole.USER, request.message)

    content = agent_service.generate_chat_reply(request, conversation.messages)
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


def _title_from_message(message: str) -> str:
    normalized = " ".join(message.strip().split())
    if not normalized:
        return "New conversation"
    return normalized[:60]
