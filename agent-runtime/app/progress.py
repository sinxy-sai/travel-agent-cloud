from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar


ProgressCallback = Callable[[str], None]

_progress_callback: ContextVar[ProgressCallback | None] = ContextVar("progress_callback", default=None)


@contextmanager
def trip_plan_progress(callback: ProgressCallback | None) -> Iterator[None]:
    token = _progress_callback.set(callback)
    try:
        yield
    finally:
        _progress_callback.reset(token)


def notify_trip_plan_progress(stage_key: str) -> None:
    callback = _progress_callback.get()
    if callback is None:
        return
    callback(stage_key)
