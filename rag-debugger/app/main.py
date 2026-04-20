from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes.debug import router as debug_router
from app.core.logger import get_logger

logger = get_logger(__name__)

app = FastAPI(
    title="RAG Auto-Fix Debugger API",
    description="An AI-powered system that uses Context-Aware RAG to fix runtime errors.",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(debug_router, tags=["Debugger"])

@app.get("/")
def health_check():
    return {"status": "healthy", "service": "rag-debugger"}

if __name__ == "__main__":
    import uvicorn
    # Typically you run via `uvicorn app.main:app --reload`
    uvicorn.run(app, host="0.0.0.0", port=8000)
