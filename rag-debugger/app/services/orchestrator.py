import os
import logging
import shutil
from typing import Tuple

from app.core.config import settings
from app.models.schemas import DebugRequest, DebugResponse
from app.services.retriever import Retriever
from app.services.context_builder import build_context
from app.services.llm_agent import generate_fix
from app.services.patcher import apply_patch
from app.services.test_runner import run_tests

def run_debugging_pipeline(request: DebugRequest, repo_path: str) -> DebugResponse:
    logger = logging.getLogger("uvicorn.error")
    logger.info(f"==== Starting RAG Pipeline Execution ====")
    logger.info(f"Target Repository: {repo_path}")
    """
    The main orchestrator loop with model fallback:
    1. Retrieve context
    2. Build context
    3. Generate fix (Try Primary, fallback to stronger model on retry)
    4. Apply to repo
    5. Run tests
    6. Retry if tests fail
    """
    retriever = Retriever()
    trace_snippets = []
    
    # Extract all repository-local locations from the stacktrace
    all_repo_locs = retriever.extract_all_repo_locations(request.stacktrace, repo_path)
    
    # Identify the 'Primary' (logical) location if not explicitly provided
    if not request.file or not request.line:
        ext_file, ext_line = retriever.extract_primary_location(request.stacktrace, repo_path)
        if ext_file:
            request.file = ext_file
            request.line = ext_line
            logger.info(f"Auto-extracted logical primary location: {request.file}:{request.line}")

    # Load snippets for the trace 'breadcrumbs' (up to top 3 in-repo locations)
    # We prioritize the primary file and the rest of the path
    unique_files_in_trace = []
    for loc in reversed(all_repo_locs): # Go bottom-up (inner to outer)
        if len(trace_snippets) >= 3: break
        
        rel_path = loc['file']
        line_num = loc['line']
        
        if rel_path not in unique_files_in_trace:
            full_path = os.path.join(repo_path, rel_path)
            snippet = retriever.get_file_snippet(full_path, line_num)
            trace_snippets.append({
                "file": rel_path,
                "line": line_num,
                "snippet": snippet,
                "is_primary": (rel_path == request.file and line_num == request.line)
            })
            unique_files_in_trace.append(rel_path)
            
    if request.file and not any(s['is_primary'] for s in trace_snippets):
        # Ensure the primary is definitely included if it wasn't caught in the trace scan
        full_path = os.path.join(repo_path, request.file)
        snippet = retriever.get_file_snippet(full_path, request.line)
        trace_snippets.insert(0, {
            "file": request.file,
            "line": request.line,
            "snippet": snippet,
            "is_primary": True
        })

    logger.info(f"Loaded {len(trace_snippets)} trace breadcrumbs for context.")
    
    logger.info("Executing FAISS context retrieval...")
    retrieved_chunks = retriever.search(request.error, request.stacktrace, request.file)
    logger.info(f"Retrieved {len(retrieved_chunks)} relevant chunk geometries.")
    
    context = build_context(
        error=request.error,
        stacktrace=request.stacktrace,
        file=request.file,
        line=request.line,
        retrieved_chunks=retrieved_chunks,
        trace_snippets=trace_snippets,
        repo_path=repo_path,
        extras=request.extras
    )
    
    logger.info("Context built successfully. Generating Fix via LLM Agent...")
    logs = []
    
    for attempt in range(settings.MAX_RETRIES):
        model_to_use = settings.PRIMARY_LLM_MODEL if attempt == 0 else settings.FALLBACK_LLM_MODEL
        attempt_msg = f"--- Attempt {attempt+1} [{model_to_use}] ---"
        logs.append(attempt_msg)
        logger.info(attempt_msg)
        
        diff = generate_fix(context, model_to_use)
        
        if not diff:
            fail_msg = "No diff generated. Halting."
            logs.append(fail_msg)
            logger.error(fail_msg)
            break
            
        logs.append("Generated diff fix.")
        logger.info(f"Successfully Generated Patch Length: {len(diff)} chars")
        logger.info(f"Diff Payload:\n{diff}")
        
        logger.info("Applying diff directly to source code...")
        patched = apply_patch(repo_path, diff)
        
        if not patched:
            logs.append("Failed to apply patch explicitly to repository.")
            logger.warning("Patch rejection detected. Natively reverting...")
            continue
            
        logs.append("Patch applied directly to source code. Running tests...")
        logger.info("Host patched successfully. Bootstrapping pytest framework...")
        tests_passed, test_output = run_tests(repo_path)
        
        if tests_passed:
            logs.append("Tests passed!")
            logger.info("✅ Tests executed successfully! Pipeline Complete!")
            return DebugResponse(
                status="success",
                fix_diff=diff,
                test_results=test_output,
                logs="\n".join(logs)
            )
        else:
            logs.append("Tests failed on this attempt.")
            logger.warning(f"❌ Tests Failed! Re-formatting context block for LLM escalation...")
            logger.debug(f"Test Execution Logs: {test_output}")
            context += f"\n\n### Attempt {attempt+1} failed with tests: ###\n{test_output}\nGenerate a better fix."
            
    logger.error("Pipeline reached maximum fallback retries. Halting.")
            
    return DebugResponse(
        status="failed",
        fix_diff="",
        test_results="Max retries reached without passing tests.",
        logs="\n".join(logs)
    )
