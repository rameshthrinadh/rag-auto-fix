import ast
import tiktoken
from typing import List, Dict, Any
from app.core.constants import MAX_CHUNK_TOKENS, TARGET_CHUNK_TOKENS

# Initialize tiktoken globally for efficiency
tokenizer = tiktoken.get_encoding("cl100k_base")

def count_tokens(text: str) -> int:
    return len(tokenizer.encode(text))

def sliding_window_chunk(text: str, file_path: str, name: str, node_type: str, imports: List[str], start_line: int) -> List[Dict[str, Any]]:
    """
    Splits text blocks that exceed MAX_CHUNK_TOKENS using a targeted sliding window approach.
    """
    lines = text.splitlines()
    chunks = []
    current_chunk_lines = []
    current_tokens = 0
    current_start_line = start_line
    
    for i, line in enumerate(lines):
        line_tokens = count_tokens(line + "\n")
        
        if current_tokens + line_tokens > TARGET_CHUNK_TOKENS and current_chunk_lines:
            # finalize chunk
            block_code = "\n".join(current_chunk_lines)
            chunks.append({
                "name": f"{name}_part_{len(chunks)+1}",
                "type": node_type,
                "code": block_code,
                "file": file_path,
                "imports": imports,
                "start_line": current_start_line,
                "end_line": current_start_line + len(current_chunk_lines) - 1,
                "tokens": current_tokens
            })
            
            # Slide window (keep some overlap, e.g. last 5 lines if possible)
            overlap_lines = current_chunk_lines[-5:] if len(current_chunk_lines) > 5 else []
            current_chunk_lines = overlap_lines + [line]
            current_tokens = count_tokens("\n".join(current_chunk_lines) + "\n")
            current_start_line = current_start_line + len(current_chunk_lines) - len(overlap_lines)
        else:
            current_chunk_lines.append(line)
            current_tokens += line_tokens
            
    if current_chunk_lines:
        block_code = "\n".join(current_chunk_lines)
        chunks.append({
            "name": f"{name}_part_{len(chunks)+1}",
            "type": node_type,
            "code": block_code,
            "file": file_path,
            "imports": imports,
            "start_line": current_start_line,
            "end_line": current_start_line + len(current_chunk_lines) - 1,
            "tokens": current_tokens
        })
        
    return chunks

def process_node(node_code: str, file_path: str, name: str, node_type: str, imports: List[str], start_line: int, end_line: int) -> List[Dict[str, Any]]:
    tokens = count_tokens(node_code)
    
    if tokens > MAX_CHUNK_TOKENS:
        return sliding_window_chunk(node_code, file_path, name, node_type, imports, start_line)
    
    return [{
        "name": name,
        "type": node_type,
        "code": node_code,
        "file": file_path,
        "imports": imports,
        "start_line": start_line,
        "end_line": end_line,
        "tokens": tokens
    }]

def get_ast_chunks(file_content: str, file_path: str) -> List[Dict[str, Any]]:
    """
    Parses a python file content into token-safe chunks representing classes and functions.
    """
    chunks = []
    
    try:
        tree = ast.parse(file_content)
    except SyntaxError:
        # Fallback if there's a syntax error in the python file
        return process_node(file_content, file_path, "module_scope", "module", [], 1, len(file_content.splitlines()))

    # Very naive import scraper
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for n in node.names:
                imports.append(n.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)
                
    lines = file_content.splitlines()

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            start_line = node.lineno
            end_line = getattr(node, 'end_lineno', start_line + 10)
            
            block_code = "\n".join(lines[start_line - 1:end_line])
            node_type = "class" if isinstance(node, ast.ClassDef) else "function"
            
            node_chunks = process_node(block_code, file_path, node.name, node_type, imports, start_line, end_line)
            chunks.extend(node_chunks)
            
    # If no functions/classes were caught, chunk the entire module
    if not chunks and file_content.strip():
        module_chunks = process_node(file_content, file_path, "module", "module", imports, 1, len(lines))
        chunks.extend(module_chunks)
        
    return chunks
