import tiktoken
from typing import Dict, Any, List, Optional
import os

from app.core.constants import MAX_TOTAL_CONTEXT_TOKENS

tokenizer = tiktoken.get_encoding("cl100k_base")

# Duplicate build_context block removed
import re

# Cache for db_schema to avoid slow reads on every request
_SCHEMA_CACHE = None
_SCHEMA_MTIME = 0

def get_db_schema_dict(repo_path: str) -> Dict[str, str]:
    global _SCHEMA_CACHE, _SCHEMA_MTIME
    
    schema_path = os.path.join(repo_path, 'services', 'api', 'db_schema.md')
    if not os.path.exists(schema_path):
        return {}
        
    mtime = os.path.getmtime(schema_path)
    if _SCHEMA_CACHE is not None and _SCHEMA_MTIME == mtime:
        return _SCHEMA_CACHE
        
    schema_dict = {}
    current_table = None
    current_lines = []
    
    try:
        with open(schema_path, 'r', encoding='utf-8') as f:
            for line in f:
                # If line is not indented and has no special chars initially, it's likely a table name
                if not line.startswith(' ') and not line.startswith('\t') and not line.startswith('├') and not line.startswith('└') and line.strip() and re.match(r'^[a-zA-Z0-9_]+$', line.strip()):
                    if current_table:
                        schema_dict[current_table] = "".join(current_lines)
                    current_table = line.strip()
                    current_lines = [line]
                elif current_table:
                    current_lines.append(line)
                    
            if current_table:
                schema_dict[current_table] = "".join(current_lines)
                
        _SCHEMA_CACHE = schema_dict
        _SCHEMA_MTIME = mtime
    except Exception as e:
        print(f"Failed to parse DB schema: {e}")
        
    return schema_dict

def inject_schema_context(context_lines: List[str], error: str, trace_snippets: List[Dict], repo_path: str) -> int:
    """
    Finds tables referenced in the error or trace snippets and injects their schema.
    Returns the number of tokens added.
    """
    schemas = get_db_schema_dict(repo_path)
    if not schemas:
        return 0
        
    text_to_search = error + " " + " ".join([ts['snippet'] for ts in trace_snippets])
    
    found_tables = set()
    # Sort tables by length descending to match longest precise table names first (e.g. invoice_attachments over attachments)
    for table in sorted(schemas.keys(), key=len, reverse=True):
        if re.search(r'\b' + re.escape(table) + r'\b', text_to_search):
            found_tables.add(table)
            
    if not found_tables:
        return 0
        
    schema_context = ["\n### Related Database Schemas ###"]
    for table in found_tables:
        schema_context.append(schemas[table].strip())
        
    schema_str = "\n".join(schema_context) + "\n---"
    tokens_added = len(tokenizer.encode(schema_str))
    
    context_lines.append(schema_str)
    return tokens_added

def inject_repo_map(context_lines: List[str], repo_path: str) -> int:
    """
    Injects the high-level repository map.
    """
    map_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'data', 'faiss_index', 'repo_map.md')
    # Better to use settings:
    from app.core.config import settings
    map_path = settings.REPO_MAP_PATH
    
    if not os.path.exists(map_path):
        return 0
        
    try:
        with open(map_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        chunk_str = f"\n### Global Repository Overview ###\n{content}\n---"
        context_lines.append(chunk_str)
        return len(tokenizer.encode(chunk_str))
    except Exception as e:
        print(f"Failed to read repo map: {e}")
        return 0

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
        
    for r in header:
        context.append(r)
        
    current_tokens = len(tokenizer.encode("\n".join(context)))
    
    # Priority 1.2: Inject Repo Map (High Level)
    map_tokens = inject_repo_map(context, repo_path)
    current_tokens += map_tokens
    
    # Priority 1.5: Inject DB Schemas if applicable
    schema_tokens = inject_schema_context(context, error, trace_snippets, repo_path)
    current_tokens += schema_tokens
        
    context.append("\n### Relevant Source Code Chunks ###")
    
    # Priority 2: Append chunks using Structured XML format
    for i, chunk in enumerate(retrieved_chunks):
        c_file = chunk.get('file', '')
        rel_c_file = os.path.relpath(c_file, repo_path) if c_file.startswith("/") else c_file
        
        # Build XML-like structure
        entity_xml = [f'<entity name="{chunk.get("repo", "local")}/{rel_c_file}/{chunk.get("name", "unknown")}">']
        entity_xml.append(f'  <type>{chunk.get("entity_type", chunk.get("type", "unknown"))}</type>')
        
        calls = chunk.get('calls', [])
        if calls:
            entity_xml.append(f'  <internal_calls>{", ".join(calls)}</internal_calls>')
            
        ext_calls = chunk.get('external_calls', [])
        if ext_calls:
            ext_str = ", ".join([f"{ec['repo']}/{ec['function']}" for ec in ext_calls])
            entity_xml.append(f'  <external_calls>{ext_str}</external_calls>')
            
        entity_xml.append(f'  <code>\n{chunk.get("code", "")}\n  </code>')
        entity_xml.append('</entity>')
        
        chunk_str = "\n".join(entity_xml)
        
        chunk_tokens = len(tokenizer.encode(chunk_str))
        if current_tokens + chunk_tokens > MAX_TOTAL_CONTEXT_TOKENS:
            # Reached context limit, skip injecting any further chunks
            context.append("\n[Warning: Further context omitted due to token limits. Reasoning may be incomplete.]")
            break
            
        context.append(chunk_str)
        current_tokens += chunk_tokens
        
    return "\n".join(context)
