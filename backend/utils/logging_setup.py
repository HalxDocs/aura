"""Process-wide logging setup.

``api.main`` and ``agent.worker`` both call :func:`setup_logging` once at
startup. Without it, records emitted through plain ``logging.getLogger(...)``
(e.g. the global error handler's traceback with ``exc_info=True``) are dropped
by uvicorn's default dictConfig, which configures no root handler — errors
never reached the container console, so production 500s were invisible in
``docker logs`` (see PR #25 audit).
"""

import logging
import sys


def setup_logging(level: int = logging.INFO) -> None:
    """Attach a stderr handler to the root logger, exactly once.

    Idempotent: the handler is named, and re-calls replace it rather than
    stacking duplicates (module reloads in tests, worker + api in one process).
    """
    root = logging.getLogger()
    handler_id = "_aura_stderr_handler"
    for h in list(root.handlers):
        if getattr(h, "name", None) == handler_id:
            root.removeHandler(h)
    handler = logging.StreamHandler(sys.stderr)
    handler.name = handler_id
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-8s %(name)s: %(message)s")
    )
    root.addHandler(handler)
    root.setLevel(level)
    # httpx logs one INFO record per outbound request (emails, LiveKit calls);
    # the root INFO handler would turn each into a docker-logs line.
    for noisy in ("httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
