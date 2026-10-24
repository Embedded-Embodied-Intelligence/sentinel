"""Background jobs (WP9a): long operations (plan, forecast, recommendation, simulator advance,
cockpit, text extraction) run in a thread pool with a job id and progress in the store, so a
request returns at once. A job's result is deterministic for the project's seed; its wall time
is not part of it."""

import logging
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from sentinel.app.errors import AppError
from sentinel.app.live import LiveError
from sentinel.app.store import JobRow, Store

LOG = logging.getLogger("sentinel.app")


class Progress:
    """What a running job reports: the share done and a short message."""

    def __init__(self, store: Store, job_id: str) -> None:
        self.store = store
        self.job_id = job_id

    def __call__(self, fraction: float, message: str = "") -> None:
        self.store.update_job(self.job_id, progress=fraction, message=message)


JobFunction = Callable[[Progress], Mapping[str, Any]]


class JobRunner:
    """Runs jobs on `workers` threads, or in the caller's thread with `inline` (tests)."""

    def __init__(self, store: Store, *, workers: int = 1, inline: bool = False) -> None:
        self.store = store
        self.inline = inline
        self.executor = None if inline else ThreadPoolExecutor(workers, "sentinel-job")

    def submit(self, session: str, project: str | None, kind: str, work: JobFunction) -> JobRow:
        job = self.store.create_job(session, project, kind)
        if self.executor is None:
            self.run(job.id, work)
        else:
            self.executor.submit(self.run, job.id, work)
        found = self.store.job(session, job.id)
        assert found is not None
        return found

    def run(self, job_id: str, work: JobFunction) -> None:
        store = self.store
        store.update_job(job_id, status="running")
        try:
            result = work(Progress(store, job_id))
        except AppError as exc:
            store.update_job(job_id, status="failed", error=error_payload(exc))
        except LiveError as exc:
            store.update_job(job_id, status="failed", error=error_payload(AppError.of(exc)))
        except Exception:
            LOG.exception("job %s failed", job_id)
            store.update_job(job_id, status="failed", error={"code": "internal_error"})
        else:
            store.update_job(job_id, status="done", progress=1.0, result=result)

    def shutdown(self) -> None:
        if self.executor is not None:
            self.executor.shutdown(wait=False, cancel_futures=True)


def error_payload(error: AppError) -> dict[str, Any]:
    """An error as stored with a job: code, parameters and issues, rendered when shown."""
    return {
        "code": error.code,
        "params": dict(error.params),
        "issues": [
            {"code": i.code, "params": i.values, "where": i.where, "severity": i.severity}
            for i in error.issues
        ],
    }
