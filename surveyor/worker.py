"""Independent collection and maintenance cycles, with redacted failure reporting."""

import logging

from surveyor.db import Audit, SessionLocal
from surveyor.maintenance import maintain
from surveyor.sources import collect_all

log = logging.getLogger(__name__)


def run_cycle(session_factory=SessionLocal):
    for phase, operation in (("collection", collect_all), ("maintenance", maintain)):
        try:
            with session_factory() as db:
                operation(db)
        except Exception as exc:
            log.error("Worker %s failed (%s); next scheduled cycle remains active", phase, type(exc).__name__)
            try:
                with session_factory() as db:
                    db.add(
                        Audit(
                            action="worker.failed",
                            entity_id=phase,
                            data={"message": f"Worker {phase} failed", "error_type": type(exc).__name__},
                        )
                    )
                    db.commit()
            except Exception:
                log.error("Worker could not persist its failure status")
