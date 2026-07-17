from datetime import UTC, datetime
from uuid import uuid4

from app.schemas import TripPlanJob, TripPlanJobStage, TripPlanJobStageStatus, TripPlanJobStatus, TripPlanResponse


class TripPlanJobNotFoundError(Exception):
    pass


class TripPlanJobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, tuple[str, TripPlanJob]] = {}

    def create(self, user_id: str) -> TripPlanJob:
        now = _now()
        job = TripPlanJob(
            id=str(uuid4()),
            status=TripPlanJobStatus.QUEUED,
            current_stage_key="queued",
            stages=_initial_stages(),
            created_at=now,
            updated_at=now,
        )
        self._jobs[job.id] = (user_id, job)
        return job

    def get(self, user_id: str, job_id: str) -> TripPlanJob:
        item = self._jobs.get(job_id)
        if item is None or item[0] != user_id:
            raise TripPlanJobNotFoundError(job_id)
        return item[1]

    def mark_running(self, user_id: str, job_id: str) -> TripPlanJob:
        job = self.get(user_id, job_id)
        now = _now()
        job.status = TripPlanJobStatus.RUNNING
        job.current_stage_key = "planning"
        job.started_at = job.started_at or now
        job.updated_at = now
        _set_stage(job, "queued", TripPlanJobStageStatus.SUCCEEDED)
        _set_stage(job, "planning", TripPlanJobStageStatus.RUNNING)
        return job

    def mark_saving(self, user_id: str, job_id: str) -> TripPlanJob:
        job = self.get(user_id, job_id)
        job.current_stage_key = "saving"
        job.updated_at = _now()
        _set_stage(job, "planning", TripPlanJobStageStatus.SUCCEEDED)
        _set_stage(job, "saving", TripPlanJobStageStatus.RUNNING)
        return job

    def mark_succeeded(self, user_id: str, job_id: str, plan: TripPlanResponse) -> TripPlanJob:
        job = self.get(user_id, job_id)
        now = _now()
        job.status = TripPlanJobStatus.SUCCEEDED
        job.current_stage_key = "done"
        job.plan = plan
        job.updated_at = now
        job.completed_at = now
        _set_stage(job, "saving", TripPlanJobStageStatus.SUCCEEDED)
        _set_stage(job, "done", TripPlanJobStageStatus.SUCCEEDED)
        return job

    def mark_failed(self, user_id: str, job_id: str, error_message: str) -> TripPlanJob:
        job = self.get(user_id, job_id)
        now = _now()
        job.status = TripPlanJobStatus.FAILED
        job.error_message = error_message[:1000]
        job.updated_at = now
        job.completed_at = now
        for stage in job.stages:
            if stage.status == TripPlanJobStageStatus.RUNNING:
                stage.status = TripPlanJobStageStatus.FAILED
        return job


def _initial_stages() -> list[TripPlanJobStage]:
    return [
        TripPlanJobStage(key="queued", label="Queued", detail="Waiting for the planner.", status=TripPlanJobStageStatus.PENDING),
        TripPlanJobStage(key="planning", label="Planning", detail="Generating the itinerary.", status=TripPlanJobStageStatus.PENDING),
        TripPlanJobStage(key="saving", label="Saving", detail="Saving the itinerary.", status=TripPlanJobStageStatus.PENDING),
        TripPlanJobStage(key="done", label="Done", detail="Itinerary is ready.", status=TripPlanJobStageStatus.PENDING),
    ]


def _set_stage(job: TripPlanJob, key: str, status: TripPlanJobStageStatus) -> None:
    for stage in job.stages:
        if stage.key == key:
            stage.status = status
            return


def _now() -> datetime:
    return datetime.now(UTC)
