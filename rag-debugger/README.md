# RAG Debugger Service

An AI-powered contextual debugging standalone service using FastAPI and Retrieval-Augmented Generation (RAG).

## Components
- **API (FastAPI)**: Receives runtime assertions and stacktraces.
- **RAG Services**: FAISS vector database to retrieve most relevant files based on codebase embeddings.
- **LLM Agent**: Sends error data and surrounding context to OpenAI to request a git diff root-fix patch.
- **Patcher & Test Runner**: Applies the diff to a sandbox environment and verifies it locally using `pytest`.

## Getting Started

1. Set up dependencies:
```bash
pip install -r requirements.txt
```

2. Add environment variables in `.env`:
`OPENAI_API_KEY` etc.

3. Index a Repository:
```bash
python indexing/indexer.py --repo=/path/to/target/project
```

4. Run the API Server:
```bash
uvicorn app.main:app --reload --port 8000
```
