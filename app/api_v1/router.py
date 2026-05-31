"""Aggregator untuk seluruh router Public API v1."""

from fastapi import APIRouter

from app.api_v1.arsip import router as arsip_router
from app.api_v1.system import router as system_router

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(system_router)
api_v1_router.include_router(arsip_router)
