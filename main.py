from contextlib import asynccontextmanager

from fastapi import FastAPI

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

app.include_router(health.router)
app.include_router(documents.router)
