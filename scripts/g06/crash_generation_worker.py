"""Exit a real G06 worker process at the persisted slide-start boundary.

This helper is intentionally limited to the integration suite.  The abrupt
``os._exit`` proves that recovery does not depend on Python unwinding or an
in-process exception handler.
"""

from __future__ import annotations

import argparse
import os

from instant_ppt_domain.database import create_domain_engine, create_session_factory
from instant_ppt_worker.generation_pipeline import process_generation_job


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--organization-id", required=True)
    arguments = parser.parse_args()

    engine = create_domain_engine(arguments.database_url)
    session_factory = create_session_factory(engine)
    process_generation_job(
        session_factory,
        arguments.job_id,
        "g06-killed-worker",
        organization_id=arguments.organization_id,
        crash_callback=lambda _slide: os._exit(73),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
