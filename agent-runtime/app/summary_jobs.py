from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import delete, desc, select
from sqlalchemy.orm import Session, sessionmaker

from app.conversations import ConversationNotFoundError
from app.db import session_scope
from app.models import ConversationRecord, ConversationSummaryJobRecord
from app.schemas import ConversationSummaryJob, ConversationSummaryJobStatus


class ConversationSummaryJobNotFoundError(Exception):
    pass


class ConversationSummaryJobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, tuple[str, ConversationSummaryJob]] = {}

    def create(self, user_id: str, conversation_id: str, event_type: str) -> ConversationSummaryJob:
        now = _now()
        job = ConversationSummaryJob(
            id=str(uuid4()),
            conversation_id=conversation_id,
            status=ConversationSummaryJobStatus.QUEUED,
            event_type=event_type,
            created_at=now,
            updated_at=now,
            completed_at=None,
            error_message=None,
        )
        self._jobs[job.id] = (user_id, job)
        return job

    def get_latest(self, user_id: str, conversation_id: str) -> ConversationSummaryJob:
        matches = [
            job
            for owner_id, job in self._jobs.values()
            if owner_id == user_id and job.conversation_id == conversation_id
        ]
        if not matches:
            raise ConversationSummaryJobNotFoundError(conversation_id)
        return max(matches, key=lambda job: job.updated_at)

    def mark_running(self, user_id: str, job_id: str) -> ConversationSummaryJob:
        return self._update_status(user_id, job_id, ConversationSummaryJobStatus.RUNNING)

    def mark_succeeded(self, user_id: str, job_id: str) -> ConversationSummaryJob:
        return self._update_status(user_id, job_id, ConversationSummaryJobStatus.SUCCEEDED, completed=True)

    def mark_failed(self, user_id: str, job_id: str, error_message: str) -> ConversationSummaryJob:
        return self._update_status(
            user_id,
            job_id,
            ConversationSummaryJobStatus.FAILED,
            completed=True,
            error_message=_compact_error(error_message),
        )

    def delete_for_conversation(self, user_id: str, conversation_id: str) -> None:
        job_ids = [
            job_id
            for job_id, (owner_id, job) in self._jobs.items()
            if owner_id == user_id and job.conversation_id == conversation_id
        ]
        for job_id in job_ids:
            del self._jobs[job_id]

    def _update_status(
        self,
        user_id: str,
        job_id: str,
        status: ConversationSummaryJobStatus,
        *,
        completed: bool = False,
        error_message: str | None = None,
    ) -> ConversationSummaryJob:
        item = self._jobs.get(job_id)
        if item is None or item[0] != user_id:
            raise ConversationSummaryJobNotFoundError(job_id)

        now = _now()
        job = item[1]
        job.status = status
        job.updated_at = now
        job.error_message = error_message
        if completed:
            job.completed_at = now
        self._jobs[job_id] = (user_id, job)
        return job


class DatabaseConversationSummaryJobStore:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def create(self, user_id: str, conversation_id: str, event_type: str) -> ConversationSummaryJob:
        with session_scope(self._session_factory) as session:
            conversation = session.scalar(
                select(ConversationRecord).where(
                    ConversationRecord.id == conversation_id,
                    ConversationRecord.user_id == user_id,
                )
            )
            if conversation is None:
                raise ConversationNotFoundError(conversation_id)

            record = ConversationSummaryJobRecord(
                user_id=user_id,
                conversation_id=conversation_id,
                status=ConversationSummaryJobStatus.QUEUED.value,
                event_type=event_type,
            )
            session.add(record)
            session.flush()
            return _to_summary_job(record)

    def get_latest(self, user_id: str, conversation_id: str) -> ConversationSummaryJob:
        with session_scope(self._session_factory) as session:
            record = session.scalar(
                select(ConversationSummaryJobRecord)
                .where(
                    ConversationSummaryJobRecord.user_id == user_id,
                    ConversationSummaryJobRecord.conversation_id == conversation_id,
                )
                .order_by(desc(ConversationSummaryJobRecord.updated_at), desc(ConversationSummaryJobRecord.created_at))
                .limit(1)
            )
            if record is None:
                raise ConversationSummaryJobNotFoundError(conversation_id)
            return _to_summary_job(record)

    def mark_running(self, user_id: str, job_id: str) -> ConversationSummaryJob:
        return self._update_status(user_id, job_id, ConversationSummaryJobStatus.RUNNING)

    def mark_succeeded(self, user_id: str, job_id: str) -> ConversationSummaryJob:
        return self._update_status(user_id, job_id, ConversationSummaryJobStatus.SUCCEEDED, completed=True)

    def mark_failed(self, user_id: str, job_id: str, error_message: str) -> ConversationSummaryJob:
        return self._update_status(
            user_id,
            job_id,
            ConversationSummaryJobStatus.FAILED,
            completed=True,
            error_message=_compact_error(error_message),
        )

    def delete_for_conversation(self, user_id: str, conversation_id: str) -> None:
        with session_scope(self._session_factory) as session:
            session.execute(
                delete(ConversationSummaryJobRecord).where(
                    ConversationSummaryJobRecord.conversation_id == conversation_id,
                    ConversationSummaryJobRecord.user_id == user_id,
                )
            )

    def _update_status(
        self,
        user_id: str,
        job_id: str,
        status: ConversationSummaryJobStatus,
        *,
        completed: bool = False,
        error_message: str | None = None,
    ) -> ConversationSummaryJob:
        with session_scope(self._session_factory) as session:
            record = session.scalar(
                select(ConversationSummaryJobRecord).where(
                    ConversationSummaryJobRecord.id == job_id,
                    ConversationSummaryJobRecord.user_id == user_id,
                )
            )
            if record is None:
                raise ConversationSummaryJobNotFoundError(job_id)

            now = _now()
            record.status = status.value
            record.updated_at = now
            record.error_message = error_message
            if completed:
                record.completed_at = now
            session.flush()
            return _to_summary_job(record)


def _to_summary_job(record: ConversationSummaryJobRecord) -> ConversationSummaryJob:
    return ConversationSummaryJob(
        id=record.id,
        conversation_id=record.conversation_id,
        status=ConversationSummaryJobStatus(record.status),
        event_type=record.event_type,
        error_message=record.error_message,
        created_at=record.created_at,
        updated_at=record.updated_at,
        completed_at=record.completed_at,
    )


def _compact_error(value: str, max_length: int = 1000) -> str:
    normalized = " ".join(value.split())
    return normalized if len(normalized) <= max_length else normalized[: max_length - 3].rstrip() + "..."


def _now() -> datetime:
    return datetime.now(UTC)
