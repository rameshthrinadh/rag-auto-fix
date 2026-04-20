from pydantic import BaseModel
from typing import Optional, Dict, Any

class DebugRequest(BaseModel):
    error: str
    stacktrace: str
    file: Optional[str] = None
    line: Optional[int] = None
    repo_path: Optional[str] = None
    extras: Optional[Dict[str, Any]] = None

class DebugResponse(BaseModel):
    status: str  # "success", "failed", "not_applied"
    fix_diff: str
    test_results: Optional[str] = None
    logs: Optional[str] = None
    reason: Optional[str] = None
    suggested_fix: Optional[str] = None
    explanation: Optional[str] = None
    confidence: Optional[int] = None
    risk: Optional[str] = None
