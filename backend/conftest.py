"""Root pytest configuration for the backend test suite.

Prevents APScheduler's background threads (started by the digest job when
the FastAPI app is imported during tests) from writing to pytest's captured
stdout after the session ends — which causes an I/O-on-closed-file crash on
Windows (pytest issue with BackgroundScheduler + captured output).
"""
import pytest
from apscheduler.schedulers.background import BackgroundScheduler


@pytest.fixture(autouse=True, scope="session")
def _stop_apscheduler_after_session():
    """Yield control to the test session, then stop any running APScheduler instances."""
    yield
    # Shut down all running BackgroundScheduler instances so their threads
    # don't try to write to pytest's already-closed capture files.
    for scheduler in list(BackgroundScheduler._instances if hasattr(BackgroundScheduler, "_instances") else []):
        try:
            if scheduler.running:
                scheduler.shutdown(wait=False)
        except Exception:
            pass
