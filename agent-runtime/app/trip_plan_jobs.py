from datetime import UTC, datetime
from threading import Lock
from uuid import uuid4

from app.schemas import TripPlanJob, TripPlanJobStage, TripPlanJobStageStatus, TripPlanJobStatus, TripPlanResponse


TRIP_PLAN_JOB_STAGES: list[tuple[str, str, str]] = [
    ("understanding", "Understanding your trip", "Normalizing dates, preferences, and constraints"),
    ("finding_attractions", "Finding attractions", "Searching travel tools for relevant places"),
    ("checking_weather", "Checking weather", "Matching forecasts to each itinerary day"),
    ("selecting_stays_meals", "Selecting stays and meals", "Balancing location, budget, and travel style"),
    ("building_routes_budget", "Building routes and budget", "Connecting stops and estimating costs"),
    ("quality_checking", "Quality checking", "Validating the final itinerary before saving"),
    ("saving", "Saving itinerary", "Persisting the plan and conversation history"),
]


class TripPlanJobNotFoundError(Exception):
    pass


class TripPlanJobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, tuple[str, TripPlanJob]] = {}
        self._lock = Lock()

    def create(self, user_id: str) -> TripPlanJob:
        now = _now()
        job = TripPlanJob(
            id=str(uuid4()),
            status=TripPlanJobStatus.QUEUED,
            current_stage_key=TRIP_PLAN_JOB_STAGES[0][0],
            stages=[
                TripPlanJobStage(
                    key=key,
                    label=label,
                    detail=detail,
                    status=TripPlanJobStageStatus.PENDING,
                )
                for key, label, detail in TRIP_PLAN_JOB_STAGES
            ],
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            self._jobs[job.id] = (user_id, job)
        return job.model_copy(deep=True)

    def get(self, user_id: str, job_id: str) -> TripPlanJob:
        with self._lock:
            owner_id, job = self._get_owned(user_id, job_id)
            self._jobs[job_id] = (owner_id, job)
            return job.model_copy(deep=True)

    def mark_running(self, user_id: str, job_id: str) -> TripPlanJob:
        with self._lock:
            owner_id, job = self._get_owned(user_id, job_id)
            job.status = TripPlanJobStatus.RUNNING
            job.started_at = job.started_at or _now()
            job.updated_at = _now()
            self._jobs[job_id] = (owner_id, job)
            return job.model_copy(deep=True)

    def mark_stage_running(self, user_id: str, job_id: str, stage_key: str) -> TripPlanJob:
        with self._lock:
            owner_id, job = self._get_owned(user_id, job_id)
            job.status = TripPlanJobStatus.RUNNING
            job.started_at = job.started_at or _now()
            job.current_stage_key = stage_key
            seen_current = False
            for stage in job.stages:
                if stage.key == stage_key:
                    stage.status = TripPlanJobStageStatus.RUNNING
                    seen_current = True
                elif not seen_current:
                    stage.status = TripPlanJobStageStatus.SUCCEEDED
                elif stage.status == TripPlanJobStageStatus.RUNNING:
                    stage.status = TripPlanJobStageStatus.PENDING
            job.updated_at = _now()
            self._jobs[job_id] = (owner_id, job)
            return job.model_copy(deep=True)

    def mark_succeeded(self, user_id: str, job_id: str, plan: TripPlanResponse) -> TripPlanJob:
        with self._lock:
            owner_id, job = self._get_owned(user_id, job_id)
            now = _now()
            job.status = TripPlanJobStatus.SUCCEEDED
            job.current_stage_key = TRIP_PLAN_JOB_STAGES[-1][0]
            job.plan = plan
            job.error_message = None
            job.completed_at = now
            job.updated_at = now
            for stage in job.stages:
                stage.status = TripPlanJobStageStatus.SUCCEEDED
            self._jobs[job_id] = (owner_id, job)
            return job.model_copy(deep=True)

    def mark_failed(self, user_id: str, job_id: str, error_message: str) -> TripPlanJob:
        with self._lock:
            owner_id, job = self._get_owned(user_id, job_id)
            now = _now()
            job.status = TripPlanJobStatus.FAILED
            job.error_message = error_message
            job.completed_at = now
            job.updated_at = now
            for stage in job.stages:
                if stage.key == job.current_stage_key or stage.status == TripPlanJobStageStatus.RUNNING:
                    stage.status = TripPlanJobStageStatus.FAILED
                    break
            self._jobs[job_id] = (owner_id, job)
            return job.model_copy(deep=True)

    def _get_owned(self, user_id: str, job_id: str) -> tuple[str, TripPlanJob]:
        item = self._jobs.get(job_id)
        if item is None or item[0] != user_id:
            raise TripPlanJobNotFoundError(job_id)
        return item


def _now() -> datetime:
    return datetime.now(UTC)
