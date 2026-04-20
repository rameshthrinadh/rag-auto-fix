# RAG-Debugger: Autonomous Code Repair Documentation

The RAG-Debugger is an intelligent, agentic debugging service designed to automatically resolve runtime errors in large repositories. By combining FAISS vector search, intelligent stacktrace analysis, and autonomous test-driven iteration, it identifies root causes and applies robust code fixes natively to the target codebase.

## 🚀 Key Features

- **Autonomous Orchestration**: Automatically retries fixes with escalated LLM models (`GPT-4o`) if initial attempts fail tests.
- **Stacktrace Anchoring**: Real-time parsing of error logs to automatically identify the exact file and line number within your repository.
- **Application-First Logic**: Heuristically prioritizes your business logic over infrastructure/utility boilerplates (e.g., database wrappers, telemetry).
- **Trace Breadcrumbs**: Injects snippets from multiple unique files along the execution path, providing the AI with a 360-degree view of the fault.
- **Robust Patching**: Uses a custom **Search/Replace Block** parser that is whitespace-invariant and supports fuzzy line-level matching to handle dynamic code construction.
- **Native Execution**: Operates directly on your repository (or a sandbox) without brittle `patch` command dependencies.

---

## 🛠️ System Components

### 1. Vector Indexing (`indexing/indexer.py`)
Parses your Python workspace into AST-aware chunks and builds an offline FAISS vector index.
- **Incremental Updates**: Uses `hashlib` to only embed modified or new code chunks, saving API costs.
- **Command**: `python indexing/indexer.py --repo=/path/to/repo`
- **Options**: Use `--force=true` to nuke the cache and rebuild from scratch.

### 2. The API Server (`app/main.py`)
A FastAPI instance that exposes the debugging pipeline to your IDE, CI/CD, or production environment.
- **Command**: `uvicorn app.main:app --reload --port 8000`

---

## 📡 API Reference

### `POST /debug`
Triggers the full RAG-driven debugging pipeline.

**Request Schema (`DebugRequest`):**
```json
{
  "error": "The error message (e.g. ValueError)",
  "stacktrace": "Full Traceback string",
  "file": "Optional: Path to target file",
  "line": "Optional: target line number (int)",
  "repo_path": "Optional: Override configured REPO_PATH",
  "extras": {
    "key": "Optional: Any extra project-specific context"
  }
}
```

**Response Schema (`DebugResponse`):**
```json
{
  "status": "success | failed",
  "fix_diff": "The Search/Replace block applied",
  "test_results": "Raw pytest output",
  "logs": "Pipeline execution breadcrumbs"
}
```

---

## 🧠 Logic & Retrieval Strategy

- **Function-Level Boosting**: The system Extracts function names from the stacktrace. If a code chunk's name matches a function in the trace, it receives a **6x higher prioritization** boost during retrieval.
- **Infrastructure Filtering**: The system automatically skips generic directories like `db_conn`, `utils`, `telemetry`, and `common` when identifying the "Primary" error location to anchor the fix on application logic.
- **Context Capacity**: 
  - **Token Budget**: 10,000 tokens (Tokenized via `cl100k_base`).
  - **Search Depth**: Top 5 relevant code chunks.
  - **Snippet Padding**: ±50 lines around the error points.

---

## 🏗️ Robust Patcher Format

The debugger avoids brittle `diff` formats. It emits **Search/Replace Blocks** that our native parser applies with high reliability:

```python
<<<< relative/path/to/file.py
exact (or fuzzy) lines to find
====
new code to replace them with
>>>>
```

**Matching Logic**:
1. **Exact Match**: Tries char-by-char matching first.
2. **Fuzzy Match**: Collapses all internal whitespace and ignores indentation to find a line-level match, ensuring stability across code formatters.

---

## ⚙️ Configuration (`.env`)

| Variable | Description | Default |
| :--- | :--- | :--- |
| `OPENAI_API_KEY` | Your OpenAI API Key | - |
| `REPO_PATH` | Path to the repository to debug | `/tmp/repo` |
| `PRIMARY_LLM_MODEL` | Faster model for first attempt | `gpt-4o-mini` |
| `FALLBACK_LLM_MODEL`| Stronger model for retries | `gpt-4o` |
| `FAISS_INDEX_PATH` | Path to FAISS vector binary | `./data/faiss_index/index.faiss` |
| `MAX_RETRIES` | Number of attempts before halting | `2` |
