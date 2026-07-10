from pydantic import BaseModel


class HealthRead(BaseModel):
    """Health check response returned by the API."""

    status: str
    service: str
