from fastapi import APIRouter, HTTPException, Request
import os
import logging

from app.models.schemas import DebugRequest, DebugResponse
from app.services.orchestrator import run_debugging_pipeline
from app.core.config import settings

router = APIRouter()
logger = logging.getLogger("uvicorn.error")

@router.post("/debug", response_model=DebugResponse)
async def debug_endpoint(payload: DebugRequest, request: Request):
    """
    Endpoint that accepts an error report and orchestrates the RAG debugging pipeline.
    """
    client_host = request.client.host if request.client else "Unknown"
    logger.info(f"Received /debug request from Source IP: {client_host}")
    logger.info(f"Request Payload: {payload.dict()}")
    
    # Check payload first, then environment settings, then fallback
    repo_path = payload.repo_path or settings.REPO_PATH
    
    if not os.path.exists(repo_path):
        logger.error(f"400 Bad Request: Repository path '{repo_path}' not configured or unavailable.")
        raise HTTPException(status_code=400, detail=f"Repository path '{repo_path}' not configured or unavailable.")
    
    try:
        response = run_debugging_pipeline(payload, repo_path)
        return response
    except Exception as e:
        logger.exception("500 Internal Server Error during orchestration.")
        raise HTTPException(status_code=500, detail=str(e))
