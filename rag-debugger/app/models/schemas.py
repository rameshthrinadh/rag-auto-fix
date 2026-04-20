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
    status: str
    fix_diff: str
    test_results: str
    logs: Optional[str] = None
