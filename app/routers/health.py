import logging
import time

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.api_v1.envelope import SuccessResponse, make_meta
from app.api_v1.errors import ApiError, ErrorCode
from app.config import es
from app.dependencies.api_auth import verify_api_key

router = APIRouter(tags=["Health"])
logger = logging.getLogger("app.routers.health")


class RootMessage(BaseModel):
    message: str


class HealthStatus(BaseModel):
    status: str = Field(..., description="ok when service is up.")


class ElasticsearchHealthStatus(BaseModel):
    status: str = Field(..., description="ok when cluster responds to ping.")
    cluster_name: str | None = None
    es_version: str | None = None


def _meta(request: Request):
    return make_meta(
        request_id=request.state.request_id,
        execution_time_ms=(time.perf_counter() - request.state.start_time) * 1000,
    )


@router.get(
    "/",
    dependencies=[Depends(verify_api_key)],
    response_model=SuccessResponse[RootMessage],
    summary="API welcome message",
)
def read_root(request: Request) -> SuccessResponse[RootMessage]:
    return SuccessResponse[RootMessage](
        data=RootMessage(message="Hello from FastAPI"),
        meta=_meta(request),
    )


@router.get(
    "/health",
    response_model=SuccessResponse[HealthStatus],
    summary="Health check (public)",
)
def health(request: Request) -> SuccessResponse[HealthStatus]:
    logger.info("Check Health Ya")
    return SuccessResponse[HealthStatus](
        data=HealthStatus(status="ok mantap"),
        meta=_meta(request),
    )


@router.get(
    "/healthElasticsearch",
    response_model=SuccessResponse[ElasticsearchHealthStatus],
    summary="Elasticsearch connectivity check",
)
def health_es(request: Request) -> SuccessResponse[ElasticsearchHealthStatus]:
    try:
        if not es.ping():
            logger.error("Elasticsearch connection failed: es.ping() returned False")
            raise ApiError(
                ErrorCode.SEARCH_ENGINE_UNAVAILABLE,
                "Elasticsearch cluster tidak merespons.",
            )
        info = es.info()
    except ApiError:
        raise
    except Exception as exc:
        logger.exception("Elasticsearch health check failed")
        raise ApiError(
            ErrorCode.SEARCH_ENGINE_UNAVAILABLE,
            "Elasticsearch cluster tidak dapat dihubungi.",
            details={"error": str(exc)},
        ) from exc
    logger.info(
        "Elasticsearch OK cluster=%s version=%s",
        info.get("cluster_name"),
        info.get("version", {}).get("number"),
    )
    return SuccessResponse[ElasticsearchHealthStatus](
        data=ElasticsearchHealthStatus(
            status="ok",
            cluster_name=info.get("cluster_name"),
            es_version=info.get("version", {}).get("number"),
        ),
        meta=_meta(request),
    )
