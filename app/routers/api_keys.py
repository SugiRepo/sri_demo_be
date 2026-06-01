import logging
import time

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.api_v1.envelope import SuccessResponse, make_meta
from app.services.api_key_generate import generate_api_key

router = APIRouter(tags=["API Keys"])
logger = logging.getLogger("app.routers.api_keys")


class ApiKeyGenerateData(BaseModel):
    api_key: str = Field(
        ...,
        description="API Key string yang baru; harap setting manual pada file .env",
    )


@router.post(
    "/api-keys/generate",
    response_model=SuccessResponse[ApiKeyGenerateData],
    summary="Generate API key string yang baru untuk keperluan API Key",
)
def generate_api_key_endpoint(
    request: Request,
) -> SuccessResponse[ApiKeyGenerateData]:
    """Return a new API key string. Register it manually in API_KEYS in .env."""
    api_key = generate_api_key()
    logger.info("api_key generated (value not logged)")
    return SuccessResponse[ApiKeyGenerateData](
        data=ApiKeyGenerateData(api_key=api_key),
        meta=make_meta(
            request_id=request.state.request_id,
            execution_time_ms=(time.perf_counter() - request.state.start_time) * 1000,
        ),
    )
