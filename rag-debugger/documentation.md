# RAG-Debugger: Autonomous & Safe Code Repair

The RAG-Debugger is an agentic debugging pipeine designed to automatically resolve runtime errors in large repositories. It prioritizes system safety and trust by using a multi-stage validation engine before committing any changes.

---

## 🚀 Key Features

### 1. Logic-Anchored Discovery
- **Stacktrace Anchoring**: Real-time parsing of error logs to automatically identify the exact file and line number.
- **Application-First Heuristics**: Automatically skips infrastructure wrappers (DB drivers, metrics) to focus the AI on the business logic where the bug resides.
- **Function-Level Boosting**: Matches function names from the trace to prioritize relevant code chunks in the FAISS index (6x priority boost).

### 2. Trust & Safety Gates
- **Decision Engine**: Self-assessment of **Confidence (0-100)** and **Risk (LOW/MEDIUM/HIGH)**. If Confidence < 85% or Risk is HIGH, the fix is returned as a "Suggestion" but not applied.
- **Hard Safety Rules**: Automatically blocks any fix that:
    - Modifies function/class signatures.
    - Performs large-scale code deletions.
    - Touches more than 2 files.
    - Edits sensitive files (`.env`, `config.py`, database drivers).
- **Syntax Verification**: Pre-validates every patch using Python AST parsing before execution.

### 3. Smart Test Runner
- **Environment Aware**: Automatically detects and uses project virtual environments (`.venv`, `rvenv`).
- **Scoped Execution**: Runs `pytest` specifically on the patched files to minimize noise and speed up validation.
- **Heuristic Success**: If total tests fail due to environment noise, the system confirms if the **specific error message** from the original trace has vanished. If so, it considers the fix a "Probable Success."

---

## 🛠️ System Components

### 1. Vector Indexing (`indexing/indexer.py`)
Parses your Python workspace into AST-aware chunks and builds an offline FAISS vector index.
- **Command**: `python indexing/indexer.py --repo=/path/to/repo`

### 2. The API Server (`app/main.py`)
FastAPI instance exposing the debugging pipeline.
- **Command**: `uvicorn app.main:app --reload --port 8000`

---

## 📡 API Reference

### `POST /debug`
Triggers the full RAG-driven debugging pipeline.

**Request Schema (`DebugRequest`):**
```json
{
  "error": "The error message",
  "stacktrace": "Full Traceback string",
  "extras": { "context": "Additional project metadata" }
}
```

**Response Schema (`DebugResponse`):**
```json
{
  "status": "success | failed | not_applied",
  "fix_diff": "The Search/Replace block applied",
  "reason": "Reason for rejection if status is not_applied",
  "explanation": "AI reasoning for the fix",
  "confidence": 95,
  "risk": "LOW",
  "test_results": "Raw pytest output",
  "logs": "Pipeline execution breadcrumbs"
}
```

---

## 🏗️ Robust Patcher Format
The debugger uses **Search/Replace Blocks** that are whitespace-invariant and support fuzzy matching:

```python
<<<< relative/path/to/file.py
exact (or fuzzy) lines to find
====
new code to replace them with
>>>>
```
