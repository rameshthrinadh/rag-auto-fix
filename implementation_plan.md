# Goal: Build a Production-ready RAG-based Debugger Service

The objective of this project is to build a standalone Python service (`rag-debugger`) utilizing FastAPI that handles runtime errors from a Flask application (or other apps). It will use Retrieval-Augmented Generation (RAG) to fetch relevant code contexts, leverage an LLM to identify the root cause and propose a fix, apply the fix in a temporary sandbox environment, and validate it using `pytest`, returning the unified outcome.

## User Review Required

> [!IMPORTANT]
> The sandbox approach for patching proposes copying the directory to a `tempfile.TemporaryDirectory()`. Ensure that the `git_loader.py` and `patcher.py` appropriately handle these sandboxes to avoid side effects on the primary branch.
> We're defaulting to `faiss-cpu` and `openai` (or an equivalent provider setup) for embeddings and completion. Let me know if you prefer to use local models right away (e.g., via `ollama`).

## Proposed Architecture & File Structure

The project will follow the structure you requested, with cleanly separated concerns for indexing vs. serving.

### Configuration & Base 
- `requirements.txt`: FastAPI, Uvicorn, FAISS-cpu, GitPython, pytest, pydantic, openai, python-dotenv, tiktoken.
- `.env`: API keys and config (e.g., OPENAI_API_KEY, REPO_PATH, FAISS_INDEX_PATH).
- `app/core/config.py`: Loads environments using Pydantic BaseSettings.
- `app/core/logger.py`: Standard logging.
- `app/core/constants.py`: Constants used across the app (chunk sizes, etc.).

### API Layer
- `app/main.py`: FastAPI instantiation, CORS, and router registration.
- `app/models/schemas.py`: Pydantic models for `DebugRequest` and `DebugResponse`.
- `app/routes/debug.py`: POST `/debug` endpoint implementation calling `orchestrator.py`.

### RAG Indexing Pipeline (`indexing/`)
- `indexing/git_loader.py`: Clone/pull and read files from a repo path.
- `indexing/chunker.py`: Split Python files into functions/classes using ast parsing (or naive line chunking).
- `indexing/indexer.py`: Generate embeddings via `openai.Embedding` and store in local `faiss` with string metadata storage (FAISS doesn't store strings natively, so a complementary JSON/Pickle file `index_metadata.json` will be used).

### Core Services (`app/services/`)
- `app/services/retriever.py`: Loads the FAISS vector store and performs similarity search, returning code snippets matching the error context.
- `app/services/context_builder.py`: Synthesizes retrieved chunks, the error stack trace, and dependency context into a single string/JSON.
- `app/services/llm_agent.py`: Uses the OpenAI (or similar) API to prompt for root cause analysis and a diff.
- `app/services/patcher.py`: Temporarily checks out or copies the repo, parses the LLm diff, and applies it.
- `app/services/test_runner.py`: Executes `pytest` on the temporary folder and captures output.
- `app/services/orchestrator.py`: The main loop coordinating `retriever` -> `context_builder` -> `llm_agent` -> `patcher` -> `test_runner`. Includes the retry logic.

## Open Questions

> [!WARNING]
> - Do you want the `indexing` to be available as an API endpoint, or strictly as a CLI as defined? (I'll implement it as a CLI script `indexing/indexer.py --repo=/path`).
> - Are there any specific test runner commands to be flexible, or is standard `pytest` sufficient for the boilerplate?

## Verification Plan

### Automated tests:
- I will create unit tests for `retriever.py`, `context_builder.py`, and `patcher.py` using `pytest` with mocked LLM and filesystem dependencies.

### Manual Verification
- We will trigger the `/debug` endpoint using `curl` or FastAPI's swagger UI on a dummy error block to ensure the orchestrator workflow executes seamlessly without exploding.
