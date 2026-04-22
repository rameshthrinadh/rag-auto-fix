import os
import logging
import shutil
from typing import Tuple

from app.core.config import settings
from app.models.schemas import DebugRequest, DebugResponse
from app.services.retriever import Retriever
from app.services.context_builder import build_context
from app.services.llm_agent import generate_fix
from app.services.patcher import apply_patch, create_sandbox, get_patch_blocks
from app.services.test_runner import run_tests
from app.services.safety import SafetyValidator

def log_unfixable(request: DebugRequest, reason: str, fix_payload: str, explanation: str):
    try:
        with open("unfixable_errors.log", "a", encoding="utf-8") as f:
            f.write(f"==== UNFIXABLE ERROR ====\n")
            f.write(f"Error: {request.error}\n")
            f.write(f"File: {request.file}:{request.line}\n")
            f.write(f"Reason: {reason}\n")
            f.write(f"Explanation: {explanation}\n")
            f.write(f"Suggested Payload:\n{fix_payload}\n")
            f.write(f"==========================\n\n")
    except Exception as e:
        logger = logging.getLogger("uvicorn.error")
        logger.error(f"Failed to log unfixable error: {e}")


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
    safety = SafetyValidator(repo_path)
    
    for attempt in range(settings.MAX_RETRIES):
        model_to_use = settings.PRIMARY_LLM_MODEL if attempt == 0 else settings.FALLBACK_LLM_MODEL
        attempt_msg = f"--- Attempt {attempt+1} [{model_to_use}] ---"
        logs.append(attempt_msg)
        logger.info(attempt_msg)
        
        # LLM returns a structured dict now
        llm_response = generate_fix(context, model_to_use)
        
        confidence = llm_response.get("confidence", 0)
        risk = llm_response.get("risk", "HIGH")
        fix_payload = llm_response.get("fix", "")
        explanation = llm_response.get("explanation", "")
        root_cause = llm_response.get("root_cause", "")

        logger.info(f"Fix generated: {fix_payload} \n Explanation: {explanation} \n Root Cause: {root_cause}")
        
        # 1. Decision Gate: Confidence & Risk
        if confidence < 70 or risk == "HIGH":
            msg = f"Fix rejected by Decision Engine: Confidence {confidence}%, Risk {risk}."
            logger.warning(msg)
            log_unfixable(request, msg, fix_payload, explanation)
            return DebugResponse(
                status="not_applied",
                fix_diff=fix_payload,
                reason=msg,
                suggested_fix=fix_payload,
                explanation=explanation,
                confidence=confidence,
                risk=risk,
                logs="\n".join(logs)
            )

        # 2. Safety Heuristics Check
        patch_blocks = get_patch_blocks(fix_payload)
        is_safe, safety_reason = safety.validate_patch(patch_blocks, {}) # Passing empty dict for now, expanded later
        if not is_safe:
            logger.warning(f"Fix rejected by Safety Heuristics: {safety_reason}")
            log_unfixable(request, f"Safety Heuristics: {safety_reason}", fix_payload, explanation)
            return DebugResponse(
                status="not_applied",
                fix_diff=fix_payload,
                reason=safety_reason,
                suggested_fix=fix_payload,
                explanation=explanation,
                confidence=confidence,
                risk=risk,
                logs="\n".join(logs)
            )

        # 3. Sandbox Logic: Never modify original code before full validation
        logger.info("Creating local sandbox for pre-commit validation...")
        sandbox_path = create_sandbox(repo_path)
        
        try:
            # 4. Apply to Sandbox
            patched = apply_patch(sandbox_path, fix_payload)
            if not patched:
                logger.warning("Failed to apply patch to sandbox. Retrying...")
                shutil.rmtree(os.path.dirname(sandbox_path))
                continue
                
            # 5. Syntax Validation
            for block in patch_blocks:
                full_file_path = os.path.join(sandbox_path, block["file"])
                if os.path.exists(full_file_path):
                    with open(full_file_path, 'r') as f:
                        valid, syntax_err = safety.validate_syntax(f.read())
                        if not valid:
                            logger.error(f"Syntax error detected after patching {block['file']}: {syntax_err}")
                            log_unfixable(request, f"Syntax Error after patch: {syntax_err}", fix_payload, explanation)
                            return DebugResponse(
                                status="not_applied",
                                fix_diff=fix_payload,
                                reason=f"Syntax Error after patch: {syntax_err}",
                                suggested_fix=fix_payload,
                                explanation=explanation,
                                confidence=confidence,
                                risk=risk,
                                logs="\n".join(logs)
                            )

            # 6. Post-Patch Test Validation
            logger.info("Sandbox patched and syntax verified. Running pytest...")
            
            # Identify the primary file being patched for scoped testing
            primary_patch_file = patch_blocks[0]["file"] if patch_blocks else None
            
            tests_passed, test_output = run_tests(
                sandbox_path, 
                target_file=primary_patch_file, 
                original_error=request.error
            )
            
            if tests_passed:
                # 7. COMMIT: Move changes back to repo_path only on total success
                logger.info("✅ All safety and test gates passed. Committing changes to original repository.")
                # We copy the modified files back to the original repo_path
                for block in patch_blocks:
                    src = os.path.join(sandbox_path, block["file"])
                    dst = os.path.join(repo_path, block["file"])
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    shutil.copy2(src, dst)
                
                logs.append("All gates passed. Fix applied natively.")
                return DebugResponse(
                    status="success",
                    fix_diff=fix_payload,
                    test_results=test_output,
                    explanation=explanation,
                    confidence=confidence,
                    risk=risk,
                    logs="\n".join(logs)
                )
            else:
                logger.warning(f"❌ Tests failed in sandbox. Root Cause: {root_cause}")
                logs.append(f"Test failure in sandbox on Attempt {attempt+1}")
                context += f"\n\n### Attempt {attempt+1} failed with tests: ###\n{test_output}\nFix the logic."
                
        finally:
            # Always cleanup sandbox
            if os.path.exists(os.path.dirname(sandbox_path)):
                shutil.rmtree(os.path.dirname(sandbox_path))
            
    log_unfixable(request, "Exhausted retries without passing tests.", "", "")
    return DebugResponse(
        status="failed",
        fix_diff="",
        test_results="Safety/Test boundaries could not be satisfied within retry limit.",
        logs="\n".join(logs)
    )
