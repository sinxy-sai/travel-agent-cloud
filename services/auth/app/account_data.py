from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import JSON, bindparam, text
from sqlalchemy.orm import Session, sessionmaker

from app.db import session_scope
from app.schemas import (
    AgentMode,
    AnonymousDataSummary,
    AuthUser,
    ChatMessage,
    Conversation,
    ConversationSummary,
    MessageRole,
    SavedTripPlan,
    UserDataExport,
    UserDataImportRequest,
    UserDataImportResponse,
    UserProfile,
)


class AccountDataStore:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def export_user_data(self, user_id: str, user: AuthUser) -> UserDataExport:
        with session_scope(self._session_factory) as session:
            conversations = _list_conversations(session, user_id)
            return UserDataExport(
                exported_at=_now(),
                user=user,
                profile=_get_profile(session, user_id),
                conversations=conversations,
                conversation_summaries=_list_conversation_summaries(session, user_id, {item.id for item in conversations}),
                trip_plans=_list_trip_plans(session, user_id),
            )

    def summarize_anonymous_data(self, user_id: str) -> AnonymousDataSummary:
        with session_scope(self._session_factory) as session:
            conversations = int(
                session.execute(
                    text("SELECT COUNT(*) FROM conversations WHERE user_id = :user_id"),
                    {"user_id": user_id},
                ).scalar()
                or 0
            )
            summaries = int(
                session.execute(
                    text("SELECT COUNT(*) FROM conversation_summaries WHERE user_id = :user_id"),
                    {"user_id": user_id},
                ).scalar()
                or 0
            )
            trip_plans = int(
                session.execute(
                    text("SELECT COUNT(*) FROM trip_plans WHERE user_id = :user_id"),
                    {"user_id": user_id},
                ).scalar()
                or 0
            )
            return AnonymousDataSummary(
                has_data=bool(conversations or summaries or trip_plans),
                conversations=conversations,
                conversation_summaries=summaries,
                trip_plans=trip_plans,
            )

    def clone_user_data_for_import(self, source_user_id: str, target_user: AuthUser) -> UserDataImportRequest:
        exported = self.export_user_data(
            source_user_id,
            AuthUser(
                id=source_user_id,
                email=f"{source_user_id}@anonymous.local",
                display_name="Anonymous user",
                email_verified=False,
                password_configured=False,
                created_at=_now(),
            ),
        )
        target_profile = _profile_for_import(target_user.id, exported.profile)
        return UserDataImportRequest(
            exported_at=_now(),
            user=target_user,
            profile=target_profile,
            conversations=[
                conversation.model_copy(
                    update={
                        "id": str(uuid4()),
                        "created_at": _now(),
                        "updated_at": _now(),
                        "messages": [
                            message.model_copy(update={"id": str(uuid4()), "created_at": _now()})
                            for message in conversation.messages
                        ],
                    }
                )
                for conversation in exported.conversations
            ],
            conversation_summaries=[],
            trip_plans=[
                trip_plan.model_copy(
                    update={
                        "id": str(uuid4()),
                        "conversation_id": None,
                        "created_at": _now(),
                        "updated_at": _now(),
                    }
                )
                for trip_plan in exported.trip_plans
            ],
        )

    def import_user_data(self, user_id: str, payload: UserDataImportRequest) -> UserDataImportResponse:
        imported_conversation_ids: set[str] = set()
        skipped_items = 0
        summaries_imported = 0
        trip_plans_imported = 0
        with session_scope(self._session_factory) as session:
            _upsert_profile(session, user_id, payload.profile)

            for conversation in payload.conversations:
                owner_id = _scalar_text(
                    session,
                    "SELECT user_id FROM conversations WHERE id = :id",
                    {"id": conversation.id},
                )
                if owner_id and owner_id != user_id:
                    skipped_items += 1 + len(conversation.messages)
                    continue
                _delete_conversation_messages(session, conversation.id)
                _upsert_conversation(session, user_id, conversation)
                for message in conversation.messages:
                    _insert_message(session, conversation.id, message)
                imported_conversation_ids.add(conversation.id)

            valid_conversation_ids = _existing_conversation_ids(session, user_id, imported_conversation_ids)

            for summary in payload.conversation_summaries:
                if summary.conversation_id not in valid_conversation_ids:
                    skipped_items += 1
                    continue
                _replace_summary(session, user_id, summary)
                summaries_imported += 1

            for trip_plan in payload.trip_plans:
                owner_id = _scalar_text(
                    session,
                    "SELECT user_id FROM trip_plans WHERE id = :id",
                    {"id": trip_plan.id},
                )
                if owner_id and owner_id != user_id:
                    skipped_items += 1
                    continue
                _upsert_trip_plan(session, user_id, trip_plan, valid_conversation_ids)
                trip_plans_imported += 1

        return UserDataImportResponse(
            imported_at=_now(),
            profile_imported=True,
            conversations_imported=len(imported_conversation_ids),
            conversation_summaries_imported=summaries_imported,
            trip_plans_imported=trip_plans_imported,
            skipped_items=skipped_items,
        )


def _list_conversations(session: Session, user_id: str) -> list[Conversation]:
    rows = session.execute(
        text(
            """
            SELECT id, mode, title, created_at, updated_at
            FROM conversations
            WHERE user_id = :user_id
            ORDER BY updated_at DESC, created_at DESC
            """
        ),
        {"user_id": user_id},
    ).mappings()
    conversations: list[Conversation] = []
    for row in rows:
        conversations.append(
            Conversation(
                id=row["id"],
                mode=AgentMode(row["mode"]),
                title=row["title"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                messages=_list_messages(session, row["id"]),
            )
        )
    return conversations


def _list_messages(session: Session, conversation_id: str) -> list[ChatMessage]:
    rows = session.execute(
        text(
            """
            SELECT id, role, content, created_at
            FROM messages
            WHERE conversation_id = :conversation_id
            ORDER BY created_at ASC
            """
        ),
        {"conversation_id": conversation_id},
    ).mappings()
    return [
        ChatMessage(
            id=row["id"],
            role=MessageRole(row["role"]),
            content=row["content"],
            created_at=row["created_at"],
        )
        for row in rows
    ]


def _list_conversation_summaries(
    session: Session,
    user_id: str,
    conversation_ids: set[str],
) -> list[ConversationSummary]:
    if not conversation_ids:
        return []
    rows = session.execute(
        text(
            """
            SELECT id, conversation_id, summary, message_count, created_at, updated_at
            FROM conversation_summaries
            WHERE user_id = :user_id AND conversation_id IN :conversation_ids
            ORDER BY updated_at DESC
            """
        ).bindparams(bindparam("conversation_ids", expanding=True)),
        {"user_id": user_id, "conversation_ids": list(conversation_ids)},
    ).mappings()
    return [
        ConversationSummary(
            id=row["id"],
            conversation_id=row["conversation_id"],
            summary=row["summary"],
            message_count=row["message_count"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
        for row in rows
    ]


def _list_trip_plans(session: Session, user_id: str) -> list[SavedTripPlan]:
    rows = session.execute(
        text(
            """
            SELECT id, conversation_id, title, destination, days, budget, interests, plan,
                   is_favorite, version, created_at, updated_at
            FROM trip_plans
            WHERE user_id = :user_id
            ORDER BY created_at DESC
            """
        ),
        {"user_id": user_id},
    ).mappings()
    return [
        SavedTripPlan(
            id=row["id"],
            conversation_id=row["conversation_id"],
            title=row["title"],
            destination=row["destination"],
            days=row["days"],
            budget=row["budget"],
            interests=row["interests"],
            plan=row["plan"],
            favorite=row["is_favorite"],
            version=row["version"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
        for row in rows
    ]


def _get_profile(session: Session, user_id: str) -> UserProfile:
    row = session.execute(
        text(
            """
            SELECT user_id, display_name, home_city, preferred_budget, travel_style, interests, updated_at
            FROM user_profiles
            WHERE user_id = :user_id
            """
        ),
        {"user_id": user_id},
    ).mappings().first()
    if row is None:
        return UserProfile(user_id=user_id, updated_at=_now())
    return UserProfile(
        user_id=row["user_id"],
        display_name=row["display_name"],
        home_city=row["home_city"],
        preferred_budget=row["preferred_budget"],
        travel_style=row["travel_style"],
        interests=row["interests"] or [],
        updated_at=row["updated_at"],
    )


def _upsert_profile(session: Session, user_id: str, profile: UserProfile) -> None:
    session.execute(
        text(
            """
            INSERT INTO user_profiles
                (user_id, display_name, home_city, preferred_budget, travel_style, interests, updated_at)
            VALUES
                (:user_id, :display_name, :home_city, :preferred_budget, :travel_style, :interests, :updated_at)
            ON CONFLICT (user_id) DO UPDATE SET
                display_name = EXCLUDED.display_name,
                home_city = EXCLUDED.home_city,
                preferred_budget = EXCLUDED.preferred_budget,
                travel_style = EXCLUDED.travel_style,
                interests = EXCLUDED.interests,
                updated_at = EXCLUDED.updated_at
            """
        ).bindparams(bindparam("interests", type_=JSON)),
        {
            "user_id": user_id,
            "display_name": profile.display_name,
            "home_city": profile.home_city,
            "preferred_budget": profile.preferred_budget,
            "travel_style": profile.travel_style,
            "interests": profile.interests,
            "updated_at": profile.updated_at,
        },
    )


def _delete_conversation_messages(session: Session, conversation_id: str) -> None:
    session.execute(text("DELETE FROM messages WHERE conversation_id = :conversation_id"), {"conversation_id": conversation_id})


def _upsert_conversation(session: Session, user_id: str, conversation: Conversation) -> None:
    session.execute(
        text(
            """
            INSERT INTO conversations (id, user_id, mode, title, created_at, updated_at)
            VALUES (:id, :user_id, :mode, :title, :created_at, :updated_at)
            ON CONFLICT (id) DO UPDATE SET
                user_id = EXCLUDED.user_id,
                mode = EXCLUDED.mode,
                title = EXCLUDED.title,
                created_at = EXCLUDED.created_at,
                updated_at = EXCLUDED.updated_at
            """
        ),
        {
            "id": conversation.id,
            "user_id": user_id,
            "mode": conversation.mode.value,
            "title": conversation.title,
            "created_at": conversation.created_at,
            "updated_at": conversation.updated_at,
        },
    )


def _insert_message(session: Session, conversation_id: str, message: ChatMessage) -> None:
    message_id = message.id
    if _scalar_text(session, "SELECT id FROM messages WHERE id = :id", {"id": message_id}):
        message_id = str(uuid4())
    session.execute(
        text(
            """
            INSERT INTO messages (id, conversation_id, role, content, created_at)
            VALUES (:id, :conversation_id, :role, :content, :created_at)
            """
        ),
        {
            "id": message_id,
            "conversation_id": conversation_id,
            "role": message.role.value,
            "content": message.content,
            "created_at": message.created_at,
        },
    )


def _existing_conversation_ids(session: Session, user_id: str, candidate_ids: set[str]) -> set[str]:
    if not candidate_ids:
        return set()
    rows = session.execute(
        text(
            """
            SELECT id FROM conversations
            WHERE user_id = :user_id AND id IN :candidate_ids
            """
        ).bindparams(bindparam("candidate_ids", expanding=True)),
        {"user_id": user_id, "candidate_ids": list(candidate_ids)},
    )
    return {row[0] for row in rows}


def _replace_summary(session: Session, user_id: str, summary: ConversationSummary) -> None:
    session.execute(
        text(
            """
            DELETE FROM conversation_summaries
            WHERE user_id = :user_id AND conversation_id = :conversation_id
            """
        ),
        {"user_id": user_id, "conversation_id": summary.conversation_id},
    )
    summary_id = summary.id
    if _scalar_text(session, "SELECT id FROM conversation_summaries WHERE id = :id", {"id": summary_id}):
        summary_id = str(uuid4())
    session.execute(
        text(
            """
            INSERT INTO conversation_summaries
                (id, user_id, conversation_id, summary, message_count, created_at, updated_at)
            VALUES
                (:id, :user_id, :conversation_id, :summary, :message_count, :created_at, :updated_at)
            """
        ),
        {
            "id": summary_id,
            "user_id": user_id,
            "conversation_id": summary.conversation_id,
            "summary": summary.summary,
            "message_count": summary.message_count,
            "created_at": summary.created_at,
            "updated_at": summary.updated_at,
        },
    )


def _upsert_trip_plan(
    session: Session,
    user_id: str,
    trip_plan: SavedTripPlan,
    valid_conversation_ids: set[str],
) -> None:
    session.execute(
        text(
            """
            INSERT INTO trip_plans
                (id, user_id, conversation_id, title, destination, days, budget, interests, plan,
                 is_favorite, version, created_at, updated_at)
            VALUES
                (:id, :user_id, :conversation_id, :title, :destination, :days, :budget, :interests, :plan,
                 :is_favorite, :version, :created_at, :updated_at)
            ON CONFLICT (id) DO UPDATE SET
                user_id = EXCLUDED.user_id,
                conversation_id = EXCLUDED.conversation_id,
                title = EXCLUDED.title,
                destination = EXCLUDED.destination,
                days = EXCLUDED.days,
                budget = EXCLUDED.budget,
                interests = EXCLUDED.interests,
                plan = EXCLUDED.plan,
                is_favorite = EXCLUDED.is_favorite,
                version = EXCLUDED.version,
                created_at = EXCLUDED.created_at,
                updated_at = EXCLUDED.updated_at
            """
        ).bindparams(bindparam("plan", type_=JSON)),
        {
            "id": trip_plan.id,
            "user_id": user_id,
            "conversation_id": trip_plan.conversation_id if trip_plan.conversation_id in valid_conversation_ids else None,
            "title": trip_plan.title,
            "destination": trip_plan.destination,
            "days": trip_plan.days,
            "budget": trip_plan.budget,
            "interests": trip_plan.interests,
            "plan": trip_plan.plan,
            "is_favorite": trip_plan.favorite,
            "version": trip_plan.version,
            "created_at": trip_plan.created_at,
            "updated_at": trip_plan.updated_at or trip_plan.created_at,
        },
    )


def _profile_for_import(user_id: str, source_profile: UserProfile) -> UserProfile:
    return UserProfile(
        user_id=user_id,
        display_name=source_profile.display_name,
        home_city=source_profile.home_city,
        preferred_budget=source_profile.preferred_budget,
        travel_style=source_profile.travel_style,
        interests=source_profile.interests,
        updated_at=_now(),
    )


def _scalar_text(session: Session, query: str, params: dict) -> object:
    return session.execute(text(query), params).scalar()


def _now() -> datetime:
    return datetime.now(UTC)
