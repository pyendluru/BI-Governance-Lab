import logging

from fastapi import FastAPI

from bi_governance_lab.api import governance_router
from bi_governance_lab.config import get_settings
from bi_governance_lab.schemas import HealthRead

settings = get_settings()
logging.basicConfig(level=settings.log_level)
app = FastAPI(title=settings.app_name, debug=settings.debug)
app.include_router(governance_router)


@app.get("/health", response_model=HealthRead)
def health() -> HealthRead:
    """Return service health metadata."""
    return HealthRead(status="ok", service=settings.app_name)
