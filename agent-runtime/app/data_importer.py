from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from app.conversations import ConversationStore
from app.db import session_scope
from app.models import (
    ConversationRecord,
    ConversationSummaryRecord,
    MessageRecord,
    TripPlanRecord,
    UserProfileRecord,
)
from app.profiles import UserProfileStore
from app.schemas import (
    Conversation,
    ConversationSummary,
    SavedTripPlan,
    UserDataImportRequest,
    UserDataImportResponse,
)
from app.summaries import ConversationSummaryStore


class UserDataImporter:
    def __init__(
        self,
        session_factory: sessionmaker[Session] | None,
        conversation_store: object,
        profile_store: object,
        summary_store: object,
    ) -> None:
        self._session_factory = session_factory
        self._conversation_store = conversation_store
        self._profile_store = profile_store
        self._summary_store = summary_store

    def import_user_data(self, user_id: str, payload: UserDataImportRequest) -> UserDataImportResponse:
        if self._session_factory is not None:
            return self._import_database_data(user_id, payload)
        return self._import_memory_data(user_id, payload)

    def _import_database_data(self, user_id: str, payload: UserDataImportRequest) -> UserDataImportResponse:
        imported_conversation_ids: set[str] = set()
        skipped_items = 0
        summaries_imported = 0
        trip_plans_imported = 0

        with session_scope(self._session_factory) as session:
            _upsert_profile_record(session, user_id, payload)

            for conversation in payload.conversations:
                existing = session.get(ConversationRecord, conversation.id)
                if existing is not None and existing.user_id != user_id:
                    skipped_items += 1 + len(conversation.messages)
                    continue

                record = existing or ConversationRecord(id=conversation.id, user_id=user_id)
                record.user_id = user_id
                record.mode = conversation.mode.value
                record.title = conversation.title
                record.created_at = conversation.created_at
                record.updated_at = conversation.updated_at
                if existing is None:
                    session.add(record)
                    session.flush()

                session.execute(delete(MessageRecord).where(MessageRecord.conversation_id == conversation.id))
                for message in conversation.messages:
                    session.add(
                        MessageRecord(
                            id=message.id if session.get(MessageRecord, message.id) is None else str(uuid4()),
                            conversation_id=conversation.id,
                            role=message.role.value,
                            content=message.content,
                            created_at=message.created_at,
                        )
                    )
                imported_conversation_ids.add(conversation.id)

            valid_conversation_ids = _existing_conversation_ids(session, user_id, imported_conversation_ids)

            for summary in payload.conversation_summaries:
                if summary.conversation_id not in valid_conversation_ids:
                    skipped_items += 1
                    continue
                _replace_summary_record(session, user_id, summary)
                summaries_imported += 1

            for trip_plan in payload.trip_plans:
                existing = session.get(TripPlanRecord, trip_plan.id)
                if existing is not None and existing.user_id != user_id:
                    skipped_items += 1
                    continue
                _upsert_trip_plan_record(session, user_id, trip_plan, valid_conversation_ids)
                trip_plans_imported += 1

        return UserDataImportResponse(
            imported_at=_now(),
            profile_imported=True,
            conversations_imported=len(imported_conversation_ids),
            conversation_summaries_imported=summaries_imported,
            trip_plans_imported=trip_plans_imported,
            skipped_items=skipped_items,
        )

    def _import_memory_data(self, user_id: str, payload: UserDataImportRequest) -> UserDataImportResponse:
        imported_conversation_ids: set[str] = set()
        skipped_items = 0
        summaries_imported = 0
        trip_plans_imported = 0

        if isinstance(self._profile_store, UserProfileStore):
            profile = payload.profile.model_copy(update={"user_id": user_id, "updated_at": payload.profile.updated_at})
            self._profile_store._profiles[user_id] = profile

        if isinstance(self._conversation_store, ConversationStore):
            for conversation in payload.conversations:
                existing = self._conversation_store._conversations.get(conversation.id)
                if existing is not None and existing[0] != user_id:
                    skipped_items += 1 + len(conversation.messages)
                    continue
                self._conversation_store._conversations[conversation.id] = (user_id, conversation)
                imported_conversation_ids.add(conversation.id)

            valid_conversation_ids = {
                conversation_id
                for conversation_id, (owner_id, _conversation) in self._conversation_store._conversations.items()
                if owner_id == user_id and conversation_id in imported_conversation_ids
            }

            if isinstance(self._summary_store, ConversationSummaryStore):
                for summary in payload.conversation_summaries:
                    if summary.conversation_id not in valid_conversation_ids:
                        skipped_items += 1
                        continue
                    self._summary_store._summaries[summary.conversation_id] = (user_id, summary)
                    summaries_imported += 1

            for trip_plan in payload.trip_plans:
                existing = self._conversation_store._trip_plans.get(trip_plan.id)
                if existing is not None and existing[0] != user_id:
                    skipped_items += 1
                    continue
                conversation_id = trip_plan.conversation_id if trip_plan.conversation_id in valid_conversation_ids else None
                self._conversation_store._trip_plans[trip_plan.id] = (
                    user_id,
                    trip_plan.model_copy(update={"conversation_id": conversation_id}),
                )
                trip_plans_imported += 1

        return UserDataImportResponse(
            imported_at=_now(),
            profile_imported=True,
            conversations_imported=len(imported_conversation_ids),
            conversation_summaries_imported=summaries_imported,
            trip_plans_imported=trip_plans_imported,
            skipped_items=skipped_items,
        )


def _upsert_profile_record(session: Session, user_id: str, payload: UserDataImportRequest) -> None:
    record = session.get(UserProfileRecord, user_id)
    if record is None:
        record = UserProfileRecord(user_id=user_id)
        session.add(record)
    record.display_name = payload.profile.display_name
    record.home_city = payload.profile.home_city
    record.preferred_budget = payload.profile.preferred_budget
    record.travel_style = payload.profile.travel_style
    record.interests = payload.profile.interests
    record.updated_at = payload.profile.updated_at


def _existing_conversation_ids(session: Session, user_id: str, candidate_ids: set[str]) -> set[str]:
    if not candidate_ids:
        return set()
    return set(
        session.scalars(
            select(ConversationRecord.id).where(
                ConversationRecord.user_id == user_id,
                ConversationRecord.id.in_(candidate_ids),
            )
        )
    )


def _replace_summary_record(session: Session, user_id: str, summary: ConversationSummary) -> None:
    session.execute(
        delete(ConversationSummaryRecord).where(
            ConversationSummaryRecord.user_id == user_id,
            ConversationSummaryRecord.conversation_id == summary.conversation_id,
        )
    )
    summary_id = summary.id if session.get(ConversationSummaryRecord, summary.id) is None else str(uuid4())
    session.add(
        ConversationSummaryRecord(
            id=summary_id,
            user_id=user_id,
            conversation_id=summary.conversation_id,
            summary=summary.summary,
            message_count=summary.message_count,
            created_at=summary.created_at,
            updated_at=summary.updated_at,
        )
    )


def _upsert_trip_plan_record(
    session: Session,
    user_id: str,
    trip_plan: SavedTripPlan,
    valid_conversation_ids: set[str],
) -> None:
    record = session.get(TripPlanRecord, trip_plan.id)
    if record is None:
        record = TripPlanRecord(id=trip_plan.id, user_id=user_id)
        session.add(record)

    record.user_id = user_id
    record.conversation_id = trip_plan.conversation_id if trip_plan.conversation_id in valid_conversation_ids else None
    record.title = trip_plan.title
    record.destination = trip_plan.destination
    record.days = trip_plan.days
    record.budget = trip_plan.budget
    record.interests = trip_plan.interests
    record.plan = trip_plan.plan.model_dump(mode="json", by_alias=True)
    record.is_favorite = trip_plan.favorite
    record.created_at = trip_plan.created_at


def _now() -> datetime:
    return datetime.now(UTC)
