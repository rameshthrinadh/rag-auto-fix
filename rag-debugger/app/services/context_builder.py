import tiktoken
from typing import Dict, Any, List, Optional
import os

from app.core.constants import MAX_TOTAL_CONTEXT_TOKENS

tokenizer = tiktoken.get_encoding("cl100k_base")

def build_context(error: str, stacktrace: str, file: Optional[str], line: Optional[int], 
                  retrieved_chunks: List[Dict[str, Any]], 
                  trace_snippets: List[Dict[str, Any]], repo_path: str,
                  extras: Optional[Dict[str, Any]] = None) -> str:
    """
    Synthesizes the error layout and retrieved context. 
    Aims to stay strictly under MAX_TOTAL_CONTEXT_TOKENS.
    """
    
    context = []
    
    # Priority 1: Error info is mandatory
    header = [
        "### Runtime Error Info ###",
        f"Error Message: {error}",
        f"Stacktrace:\n{stacktrace}",
    ]
    
    if file and line:
        rel_file = os.path.relpath(file, repo_path) if file.startswith("/") else file
        header.append(f"Primary File Location: {rel_file}:{line}")
        
    if extras:
        header.append(f"\n### Extra Context / Project Info ###")
        for k, v in extras.items():
            header.append(f"{k}: {v}")
        
    header.append("\n---")
    
    if trace_snippets:
        header.append("\n### Exception Trace Breadcrumbs (Application Flow) ###")
        for i, ts in enumerate(trace_snippets):
            rel_file = os.path.relpath(ts['file'], repo_path) if ts['file'].startswith("/") else ts['file']
            primary_mark = " [PRIMARY ERROR LOCATION]" if ts['is_primary'] else ""
            header.append(f"\n[{i+1}] File: {rel_file}:{ts['line']}{primary_mark}")
            header.append(ts['snippet'])
            header.append("-" * 10)
        header.append("\n---")
        
    header.append("\n### Relevant Source Code Chunks ###")
    
    for r in header:
        context.append(r)
        
    current_tokens = len(tokenizer.encode("\n".join(context)))
    
    # Priority 2: Append chunks as long as we fit inside the tokens
    for i, chunk in enumerate(retrieved_chunks):
        c_file = chunk.get('file', '')
        rel_c_file = os.path.relpath(c_file, repo_path) if c_file.startswith("/") else c_file
        
        chunk_str = f"[{i+1}] File: {rel_c_file} | Type: {chunk.get('type')} | Name: {chunk.get('name')}\nCode:\n{chunk.get('code', '')}\n---"
        
        chunk_tokens = len(tokenizer.encode(chunk_str))
        if current_tokens + chunk_tokens > MAX_TOTAL_CONTEXT_TOKENS:
            # Reached context limit, skip injecting any further chunks
            context.append("\n[Warning: Further chunks omitted due to token limits]")
            break
            
        context.append(chunk_str)
        current_tokens += chunk_tokens
        
    return "\n".join(context)
