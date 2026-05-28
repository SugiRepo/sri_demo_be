import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import init_db
from app.logging_config import setup_logging
from app.routers import documents, health


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Run after uvicorn starts the worker (fixes missing background-task logs).
    setup_logging()
    init_db()
    yield


app = FastAPI(title="sri-demo API", lifespan=lifespan)

_cors_origins_env = os.getenv(
    "CORS_ALLOW_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000",
)
allow_origins = [o.strip() for o in _cors_origins_env.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(documents.router)
