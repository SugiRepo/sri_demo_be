import logging
import os

from fastapi import APIRouter
from elasticsearch import Elasticsearch
from app.config import es

router = APIRouter(tags=["Health"])
logger = logging.getLogger("app.routers.health")

@router.get("/")
def read_root():
    return {"message": "Hello from FastAPI"}


@router.get("/health")
def health():
    print(f"check health nih")
    logger.info(
        "Check Health Ya"
    )
    return {"status": "ok mantap"}

@router.get("/healthElasticsearch")
def healthES():
    # Test the connection
    if es.ping():
            print("Connection is OK! Elasticsearch cluster is reachable.")
            logger.info("Connection is OK! Elasticsearch cluster is reachable.")
            print(es.info())
            logger.info(es.info())
            return {"status": "ok"}
    else:
            print("Connection failed. es.ping() returned False.")
            logger.error("Connection failed. es.ping() returned False.")
            return {"status": "error"}

    

